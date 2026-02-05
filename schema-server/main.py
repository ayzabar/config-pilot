import argparse
import json
import os

from flask import Flask, jsonify

app = Flask(__name__)

SCHEMA_DIR = "/app/data/schemas"

def load_schema_jk(app_name):
    safe_name = os.path.basename(app_name)
    file_path = os.path.join(SCHEMA_DIR, f"{safe_name}.schema.json")

    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading schema: {e}")
        return None

@app.route("/<app_name>", methods=["GET"])
def get_schema(app_name):
    schema = load_schema_jk(app_name)
    if schema:
        return jsonify(schema)
    else:
        return jsonify({"error": "schema not found"}), 404

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema-dir', default='/app/data/schemas', help='Directory containing schema files')
    parser.add_argument('--listen', default='0.0.0.0:5001', help='Host and port to listen on')
    args = parser.parse_args()

    SCHEMA_DIR = args.schema_dir
    host, port = args.listen.split(':')

    app.run(host=host, port=int(port))
