import json
import os

from flask import Flask, jsonify

app = Flask(__name__)

VALUES_DIR = os.getenv("VALUES_DIR", "/app/data/values")

def load_values(app_name):
    safe_name = os.path.basename(app_name)
    file_path = os.path.join(VALUES_DIR, f"{safe_name}.value.json")

    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading values: {e}")
        return None

@app.route("/<app_name>", methods=["GET"])
def get_values_jk(app_name):
    values = load_values(app_name)
    if values:
        return jsonify(values)
    else:
        return jsonify({"error": "no values found"}), 404

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
