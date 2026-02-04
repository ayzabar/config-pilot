import json
import os

from flask import Flask, jsonify

app = Flask(__name__) # initializing the values server

# this is where we store the actual app configs (matchmaking, chat, etc.)
# docker will mount this to a local folder later
VALUES_DIR = os.getenv("VALUES_DIR", "data/values")

@app.route("/<app_name>", methods=["GET"])
def get_values(app_name):
    # constructing the path to the json file
    # we expect files like matchmaking.json or tournament.json
    filename = f"{app_name}.json"
    file_path = os.path.join(VALUES_DIR, filename)

    # checking if the file actually exists so we don't go boom
    if not os.path.exists(file_path):
        return jsonify({"error": "config file not found kanka"}), 404

    try:
        # opening the file and parsing the json
        with open(file_path, 'r') as f:
            values_data = json.load(f)

        # sending the config back to the bot-server
        return jsonify(values_data)

    except Exception as e:
        # catching any weird file reading errors
        return jsonify({"error": f"failed to load values: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
