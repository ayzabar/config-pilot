import json
import logging
import os
import re

import jsonschema
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# env configs. defaulting to localhost.
SCHEMA_URL = os.getenv("SCHEMA_SERVICE_URL", "http://schema-server:5001")
VALUES_URL = os.getenv("VALUES_SERVICE_URL", "http://values-server:5002")
# poking the local ollama instance.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL_NAME = "llama3.1"

# logging setup.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def query_llm(system_prompt, user_input):
    # sending the payload to the silicon brain.
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0, # zero creativity allowed. be a robot.
            "num_predict": 2048 # enough tokens for a small surgery.
        }
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
    # cleaning up the garbage markdown the llm spits out.
    if not text:
        return "{}"
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    return text

def identify_app_name_ai(user_input):
    # asking the ai to guess the app name because regex is boring.
    # defaulting to matchmaking if the ai is clueless.
    sys_prompt = "identify app name (tournament, matchmaking, chat). output only name."
    try:
        res = query_llm(sys_prompt, user_input).strip().lower()
        if "tournament" in res: return "tournament"
        if "chat" in res: return "chat"
        return "matchmaking"
    except Exception:
        return "matchmaking"

@app.route("/message", methods=["POST"])
def handle_message_jk():
    # scope isolation strategy:
    # we yank out only the relevant part (workload), let the ai fix it, and stitch it back.
    # this creates reliable outputs and stops the schema from screaming at us.

    data = request.json
    user_input = data.get("input")
    if not user_input: return jsonify({"error": "feed me input"}), 400

    app_name = identify_app_name_ai(user_input)
    logger.info(f"target acquired: {app_name}")

    # 1. grab the full state
    try:
        curr_vals = requests.get(f"{VALUES_URL}/{app_name}").json()
    except Exception as e:
        return jsonify({"error": f"could not fetch current values: {str(e)}"}), 500

    # 2. surgery prep: isolate the workload
    # we assume 'statefulsets' for tournament, 'deployments' for others.
    workload_type = "statefulsets" if app_name == "tournament" else "deployments"

    # navigating the json tree carefully.
    try:
        root_workload = curr_vals.get("workloads", {}).get(workload_type, {}).get(app_name, {})
    except Exception:
        root_workload = {}

    # creating a mini context. less data = less hallucinations.
    context_data = {
        "replicas": root_workload.get("replicas", 1),
        "containers": root_workload.get("containers", {})
    }

    system_prompt = f"""
    you are a kubernetes updater.
    task: update the configuration for "{app_name}" based on: "{user_input}"

    input context: {json.dumps(context_data)}

    rules:
    1. output only the updated json object.
    2. maintain the same structure (keys: 'replicas', 'containers').
    3. update resources, images, or replicas as requested.
    4. do not add 'workloads', 'namespace' or other root keys. just return the updated context data.
    """

    # 3. execute the cut
    try:
        llm_out = query_llm(system_prompt, user_input)
        cleaned = clean_json_output(llm_out)
        updated_fragment = json.loads(cleaned)
    except Exception as e:
        logger.warning(f"llm botched the surgery: {e}")
        updated_fragment = context_data # fallback to original state

    # 4. stitching it back together
    # ensure the path exists in the big object
    if "workloads" not in curr_vals: curr_vals["workloads"] = {}
    if workload_type not in curr_vals["workloads"]: curr_vals["workloads"][workload_type] = {}
    if app_name not in curr_vals["workloads"][workload_type]: curr_vals["workloads"][workload_type][app_name] = {}

    target_node = curr_vals["workloads"][workload_type][app_name]

    # applying the updates.
    if "replicas" in updated_fragment:
        target_node["replicas"] = updated_fragment["replicas"]
    if "containers" in updated_fragment:
        target_node["containers"] = updated_fragment["containers"]

    # 5. validation check
    try:
        schema = requests.get(f"{SCHEMA_URL}/{app_name}").json()
        jsonschema.validate(instance=curr_vals, schema=schema)
        logger.info("schema validation passed. patient is alive.")
    except jsonschema.ValidationError as e:
        # specific schema error handling
        logger.error(f"schema fail: {e.message}")
        return jsonify({"error": f"schema violation: {e.message}"}), 422
    except Exception as e:
        # generic error handling
        logger.error(f"validation crashed: {e}")
        return jsonify({"error": f"validation crashed: {str(e)}"}), 500

    # finding containers recursively.
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
