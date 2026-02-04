import json  # to prase json data, read and write.
import logging  # to print logs (gotta see the errors in the termnial).
import os  # to talk to the os ( we need to read enviroment variables).
import re  # regex for text search ( finally programming languages class is paying off ).

import requests  # for HTTP requests ( for schema, values and ollama).
from flask import Flask, jsonify, request  # web server library for API's.

app = Flask(__name__) # starts the Flask app.

# grabbing config from env vars, falling back to defaults if needed
SCHEMA_URL = os.getenv("SCHEMA_SERVICE_URL", "http://schema-server:5001")
VALUES_URL = os.getenv("VALUES_SERVICE_URL", "http://values-server:5002")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://docker.internal:11434")
MODEL_NAME = "llama3.1"

# setting up logging to see what's going on in the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_json_response(response_text):
    # simple cleanup here. if llm adds markdown stuff we get rid of them
    if not response_text:
        return "{}"
    clean_text = re.sub(r'```json\s', '', response_text)
    clean_text = re.sub(r'```\s*','', clean_text)
    # just grabbing everything between the first and last brace
    start = clean_text.find('{')
    end = clean_text.rfind('}')
    if start != -1 and end != -1:
        return clean_text[start:end+1]
    return clean_text

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
            "temperature": 0.1, #keeping it low for consistent results
        }
    }
    try:
        url = f"{OLLAMA_HOST}/api/chat"
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception as e:
        logger.error(f"llm connection failed{e}")
        raise e

@app.route("/message", methods=["POST"])
def handle_message():
    data = request.json
    user_input = data.get("input")

    # figuring out which app we're deling with based on user input
    app_name = "matchmaking"
    if "tournament" in str(user_input).lower():
        app_name = "tournament"
    if "chat" in str(user_input).lower():
        app_name = "chat"

    # fetching current values from the values service
    try:
        values_res = requests.get(f"{VALUES_URL}/{app_name}")
        if values_res.status_code != 200:
            return jsonify({"error": "app data not found"}), 404
        current_values = values_res.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # basic prompt to guide the llm
    system_prompt = f"""
    You are a DevOps assistant. Update the Kurnetes values JSON.
    Input JSON: {json.dumps(current_values)}
    Rules: Return only valid JSON. No explanations.
    """

    try:
        llm_response = query_llm(system_prompt, user_input)
        cleaned_json = clean_json_response(llm_response)
        new_values = json.loads(cleaned_json)

        # trying to find containers in the standard path
        # this is low-key fragile, might break if structure changes
        if "workloads" in new_values:
           return jsonify({"containers": new_values.get("workloads")})
        return jsonify({"containers": {}})
    except Exception as e:
        return jsonify({"error": f"something went wrong: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
