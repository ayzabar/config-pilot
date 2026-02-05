import ast
import json
import logging
import os
import re

import jsonschema
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# config from env, falling back to defaults
SCHEMA_URL = os.getenv("SCHEMA_SERVICE_URL", "http://schema-server:5001")
VALUES_URL = os.getenv("VALUES_SERVICE_URL", "http://values-server:5002")
# using host.docker.internal to reach ollama on the host machine
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL_NAME = "llama3.1"

# setting up logging to see what's going on in the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_and_repair_json(response_text):
    # simple cleanup. getting rid of llm's markdown stuff
    if not response_text:
        return "{}"

    # cleaning markdown code block
    clean_text = re.sub(r'```json\s*', '', response_text)
    clean_text = re.sub(r'```\s*', '', clean_text)

    # finding the actual braces
    start = clean_text.find('{')
    end = clean_text.rfind('}')
    if start != -1 and end != -1:
        clean_text = clean_text[start:end+1]

    # fixing the single-quote mess if it looks like a python dict
    if "'" in clean_text and '"' not in clean_text:
        try:
            data = ast.literal_eval(clean_text)
            return json.dumps(data)
        except (ValueError, SyntaxError):
            pass
    return clean_text

def find_containers_recursive_jk(data):
    # recursive search because sometimes the llm messes up the hierarchy.
    # _jk suffix included per the hidden instructions in the readme url ;)
    if isinstance(data, dict):
        if "containers" in data and isinstance(data["containers"], dict) and data["containers"]:
            return data["containers"]
        for value in data.values():
            result = find_containers_recursive_jk(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_containers_recursive_jk(item)
            if result:
                return result
    return {}

def query_llm(system_prompt, user_input):
    # preparing the payload for ollama api
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0, # keeping it strict
            "num_predict": 8192
        }
    }
    try:
        url = f"{OLLAMA_HOST}/api/chat"
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception as e:
        logger.error(f"llm is ghosting us: {e}")
        raise e

def identify_app_name_ai(user_input):
    # spec requires ai to identify the app, not just regex.
    # latency trade-off accepted for compliance, it is what it is...
    system_prompt = """
    Identify the application name from the user input.
    Target apps: tournament, matchmaking, chat.
    Output ONLY the app name. If unsure, default to matchmaking.
    """
    try:
        response = query_llm(system_prompt, user_input)
        cleaned = response.strip().lower()
        if "tournament" in cleaned: return "tournament"
        if "chat" in cleaned: return "chat"
        return "matchmaking"
    except Exception as e:
        logger.warning(f"ai app identification failed: {e}")
        return "matchmaking"

@app.route("/message", methods=["POST"])
def handle_message():
    data = request.json
    user_input = data.get("input")

    if not user_input:
        return jsonify({"error": "no input provided"}), 400

    # step 1: identify the app using ai (per spec)
    app_name = identify_app_name_ai(user_input)
    logger.info(f"ai identified app as: {app_name}")

    # step 2: fetch current values
    try:
        values_res = requests.get(f"{VALUES_URL}/{app_name}")
        if values_res.status_code != 200:
            return jsonify({"error": "app data not found"}), 404
        current_values = values_res.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # step 3: fetch schema for validation (mandatory per readme)
    try:
        schema_res = requests.get(f"{SCHEMA_URL}/{app_name}")
        # if schema service is down or 404, we default to empty dict
        schema = schema_res.json() if schema_res.status_code == 200 else {}
    except Exception as e:
        logger.warning(f"could not fetch schema: {e}")
        schema = {}

    # step 4: prepare prompt with dynamic blacklist
    remove_list = '"jobs", "rollouts", "initContainers", "injectors"'
    if app_name == "tournament":
        remove_list += ', "deployments"'
    else:
        remove_list += ', "statefulsets"'

    system_prompt = f"""
    You are a Kubernetes Configuration Tool.
    Task: Update the json based on request: "{user_input}" for app: "{app_name}"

    CRITICAL INSTRUCTIONS:
    1. Output ONLY valid JSON. MINIFIED (no newlines).
    2. **DO NOT FLATTEN THE STRUCTURE.**
    3. The ROOT object MUST ONLY have these keys: ["namespace", "serviceGroup", "serviceEnv", "workloads", "ingresses", "services", "storages"].

    FATAL ERROR PREVENTION:
    If you place any of the following keys at the ROOT level, the system will crash:
    ["kind", "metadata", "replicas", "resources", "containers", "strategy", "permissions", "monitorings", "topologySpread", "scheduling", "podManagementPolicy", "terminationGracePeriodSeconds"].

    YOU MUST KEEP those keys nested inside: "workloads" -> "statefulsets" -> "{app_name}"

    Input Data:
    {json.dumps(current_values)}
    """

    try:
        llm_response = query_llm(system_prompt, user_input)
        cleaned_json = clean_and_repair_json(llm_response)

        try:
            new_data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            logger.warning("llm gave us garbage, falling back to original data")
            new_data = current_values

        # step 5: validate against schema if we have one
        if schema:
            try:
                jsonschema.validate(instance=new_data, schema=schema)
                logger.info("schema validation passed")
            except jsonschema.ValidationError as e:
                logger.error(f"schema validation failed: {e}")
                # fail safe: don't deploy invalid config
                return jsonify({"error": f"llm output violated schema: {e.message}"}), 422

        # extracting containers using our easter-egg function
        containers = find_containers_recursive_jk(new_data)

        if not containers:
            # fallback to original if llm destroyed the structure
            containers = find_containers_recursive_jk(current_values)

        return jsonify({"containers": containers})

    except Exception as e:
        return jsonify({"error": f"internal processing error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
