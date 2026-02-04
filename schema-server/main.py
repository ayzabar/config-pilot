import json
import os

from flask import Flask, jsonify

app = Flask(__name__)

# grabbing the directory where we keep the schemas.
# usually this is mounted via docker volume.
SCHEMA_DIR = os.getenv("SCHEMA_DIR", "data/schemas")

@app.route("/<app_name>", methods=["GET"])
def get_schema(app_name):
    # constructing the filename based on the app name.
    # e.g., matchmaking -> matchmaking.schema.json
    filename = f"{app_name}.schema.json"
    file_path = os.path.join(SCHEMA_DIR, filename)

    # checking if the file actually exists to avoid crashing.
    if not os.path.exists(file_path):
        return jsonify({"error": "schema file not found bro"}), 404

    try:
        # reading the json file from disk.
        with open(file_path, 'r') as f:
            schema_data = json.load(f)

        # sending it back as a json response.
        return jsonify(schema_data)

    except Exception as e:
        # something went wrong while reading the file.
        return jsonify({"error": f"failed to read schema: {str(e)}"}), 500

if __name__ == "__main__":
    # firing up the server on port 5001.
    app.run(host="0.0.0.0", port=5001)
