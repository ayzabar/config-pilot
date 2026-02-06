import json
import logging
import os
import re

import jsonschema
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# env configs. defaulting to localhost if not set.
SCHEMA_URL = os.getenv("SCHEMA_SERVICE_URL", "http://schema-server:5001")
VALUES_URL = os.getenv("VALUES_SERVICE_URL", "http://values-server:5002")

# poking the local ollama instance.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL_NAME = "llama3.1"

# logging setup. keeping it minimal.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def query_llm(system_prompt, user_input):
    # preparing payload for ollama.
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048}
    }
    try:
        url = f"{OLLAMA_HOST}/api/chat"
        r = requests.post(url, json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception as e:
        logger.error(f"llm died on us: {e}")
        raise e

def clean_json_output(text):
    if not text: return "{}"

    # cleaning up markdown artifacts.
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # finding the outer braces to isolate json.
    start = text.find('{')
    end = text.rfind('}')

    if start != -1 and end != -1:
        text = text[start:end+1]

    return text

def identify_app_name_ai(user_input):
    # defining the persona. telling the model to act as a router.
    sys_prompt = """
    You are a strict API Router. Your ONLY job is to classify the user request into one of these 3 service names.

    AVAILABLE SERVICES:
    1. tournament (Keywords: tourney, cup, bracket, prize, competition)
    2. matchmaking (Keywords: game, level, lobby, opponent, finding match, toyblast, toonblast)
    3. chat (Keywords: message, social, ban, communication, text)

    RULES:
    - Output ONLY the service name (e.g., tournament).
    - Do NOT write full sentences like "The service is...".
    - Do NOT output punctuation or markdown.
    - If the input is ambiguous but mentions 'game', choose 'matchmaking'.
    - If the input contains the exact name of a service, choose that service.
    """

    try:
        raw_response = query_llm(sys_prompt, user_input)

        # normalizing the output.
        res = raw_response.strip().lower().replace('"', '').replace("'", "").replace(".", "")

        allowed_apps = ["tournament", "matchmaking", "chat"]

        # fallback logic in case model gets chatty.
        if res not in allowed_apps:
            if "tournament" in res:
                return "tournament"
            if "matchmaking" in res:
                return "matchmaking"
            if "chat" in res:
                return "chat"
            return "matchmaking" # default safe bet.

        return res

    except Exception:
        return "matchmaking"

@app.route("/message", methods=["POST"])
def handle_message_jk():
    data = request.json
    user_input = data.get("input")
    if not user_input: return jsonify({"error": "feed me input"}), 400

    # step 1: figure out which app we are talking about.
    app_name = identify_app_name_ai(user_input)
    logger.info(f"target acquired: {app_name}")

    # step 2: fetch current values.
    try:
        curr_vals = requests.get(f"{VALUES_URL}/{app_name}").json()
    except Exception as e:
        return jsonify({"error": f"could not fetch current values: {str(e)}"}), 500

    # determining workload type based on app name logic.
    workload_type = "statefulsets" if app_name == "tournament" else "deployments"

    try:
        root_workload = curr_vals.get("workloads", {}).get(workload_type, {}).get(app_name, {})
    except Exception:
        root_workload = {}

    # preparing context for the surgery.
    context_data = {
        "replicas": root_workload.get("replicas", 1),
        "containers": root_workload.get("containers", {})
    }

    # strict prompt to ensure valid json output.
    system_prompt = f"""
    You are a configuration updater.
    Task: Update the JSON configuration for "{app_name}" based on: "{user_input}"

    Current Config: {json.dumps(context_data)}

    STRICT RULES:
    1. Output ONLY the valid, parsable JSON object.
    2. Maintain valid JSON syntax (double quotes for keys/strings, correct commas).
    3. Do not add keys like 'workloads' or 'namespace'.
    4. Return the full object structure provided in Current Config with updates applied.
    """

    # step 3: ask llm to perform the update.
    try:
        llm_out = query_llm(system_prompt, user_input)
        cleaned = clean_json_output(llm_out)
        updated_fragment = json.loads(cleaned)
    except Exception as e:
        logger.warning(f"llm botched the surgery: {e}")
        updated_fragment = context_data

    # step 4: apply updates to the main dict.
    if "workloads" not in curr_vals: curr_vals["workloads"] = {}
    if workload_type not in curr_vals["workloads"]: curr_vals["workloads"][workload_type] = {}
    if app_name not in curr_vals["workloads"][workload_type]: curr_vals["workloads"][workload_type][app_name] = {}

    target_node = curr_vals["workloads"][workload_type][app_name]

    if "replicas" in updated_fragment:
        target_node["replicas"] = updated_fragment["replicas"]
    if "containers" in updated_fragment:
        target_node["containers"] = updated_fragment["containers"]

    # step 5: validate against schema.
    try:
        schema = requests.get(f"{SCHEMA_URL}/{app_name}").json()
        jsonschema.validate(instance=curr_vals, schema=schema)
        logger.info("schema validation passed. patient is alive.")
    except jsonschema.ValidationError as e:
        logger.error(f"schema fail: {e.message}")
        return jsonify({"error": f"schema violation: {e.message}"}), 422
    except Exception as e:
        logger.error(f"validation crashed: {e}")
        return jsonify({"error": f"validation crashed: {str(e)}"}), 500

    # helper to clean up response (removing unnecessary nesting).
    def extract_containers(d):
        if "containers" in d and isinstance(d["containers"], dict):
            return d["containers"]
        for v in d.values():
            if isinstance(v, (dict, list)):
                res = extract_containers(v) if isinstance(v, dict) else None
                if res:
                    return res
        return {}

    final_containers = extract_containers(curr_vals)
    return jsonify({"containers": final_containers})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
