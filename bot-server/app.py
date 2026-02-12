#!/usr/bin/env python3
"""Bot Service - natural language config management using local llm"""

import argparse
import copy
import json
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import jsonschema

# apps we support
AVAILABLE_APPS = ["chat", "matchmaking", "tournament"]

# service urls - these work inside docker network
SCHEMA_SERVICE_URL = "http://schema-server:5001"
VALUES_SERVICE_URL = "http://values-server:5002"
OLLAMA_URL = "http://ollama:11434"

# timeout for llm calls, sometimes they take a while (specially if you don't realize and run it on your CPU at first Q_Q)
OLLAMA_TIMEOUT = 300


class BotHandler(BaseHTTPRequestHandler):
    """handles bot service http requests"""

    def do_POST(self):
        """handles POST /message requests"""
        if self.path != "/message":
            self._send_error(404, "Not Found")
            return

        try:
            # read the request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)

            user_input = data.get("input", "")
            if not user_input:
                self._send_error(400, "Missing 'input' field")
                return

            print(f"[BotService] got input: {user_input}")

            # step 1: figure out which app they're talking about
            app_name = self._identify_app_jk(user_input)
            if not app_name:
                self._send_error(400, "couldn't figure out which app you meant")
                return

            print(f"[BotService] identified app: {app_name}")

            # grab the schema and current values
            schema = self._fetch_schema(app_name)
            if schema is None:
                self._send_error(404, f"schema not found for {app_name}")
                return

            values = self._fetch_values(app_name)
            if values is None:
                self._send_error(404, f"values not found for {app_name}")
                return

            print(f"[BotService] fetched schema and values for {app_name}")

            # step 2: let the llm figure out what to change
            change_spec = self._get_change_spec(user_input, values, app_name)
            if change_spec is None:
                self._send_error(500, "couldn't determine what changes to make")
                return

            # apply the changes
            modified_values = self._apply_change(values, change_spec)
            if modified_values is None:
                self._send_error(500, "failed to apply changes")
                return

            # validate against schema just log if it fails, don't block
            try:
                jsonschema.validate(instance=modified_values, schema=schema)
                print(f"[BotService] schema validation passed")
            except jsonschema.ValidationError as e:
                # ngl this probably means the llm messed up but we'll return it anyway
                print(f"[BotService] validation warning: {e.message}")

            # send back the modified config
            print(f"[BotService] returning modified values")
            self._send_response(200, json.dumps(modified_values, indent=2))

        except json.JSONDecodeError:
            self._send_error(400, "invalid json in request")
        except Exception as e:
            print(f"[BotService] error: {str(e)}")
            self._send_error(500, f"internal server error: {str(e)}")

    def _identify_app_jk(self, user_input: str) -> str | None:
        """use llm to figure out which app the user wants to modify"""
        prompt = f"""you are a config assistant. identify which application the user wants to modify.

available applications: {', '.join(AVAILABLE_APPS)}

user request: "{user_input}"

respond with ONLY the application name (one of: {', '.join(AVAILABLE_APPS)}). nothing else."""

        response = self._call_ollama(prompt)
        if not response:
            return None

        response = response.strip().lower()
        # check if any of our app names are in the response
        for app in AVAILABLE_APPS:
            if app in response:
                return app
        return None

    def _get_change_spec(self, user_input: str, values: dict, app_name: str) -> dict | None:
        """use llm to extract what needs to change - returns a json patch spec"""
        # figure out if it's a deployment or statefulset
        workload_type = "statefulsets" if "statefulsets" in values.get("workloads", {}) else "deployments"

        # this prompt basically asks the llm to give us a json patch instead of regenerating
        # the entire config. way faster and less error-prone
        # you can't imagine how painful it was to create this prompt like i can make a timelapse of the changes and it'd be long T_T
        # deli deliyi gorunce sopasini saklarmis. llme yazdirdim, llmi yola getirdi
        prompt = f"""you are a config assistant. analyze the user request and output a json object specifying what to change.

the config is for the "{app_name}" application which uses "{workload_type}".

user request: "{user_input}"

you must output a json object with these fields:
- "path": array of strings representing the path to the field to change (e.g., ["workloads", "statefulsets", "tournament", "containers", "tournament", "resources", "memory", "limitMiB"])
- "value": the new value to set (number or string)

common paths you might need:
- memory limit: ["workloads", "{workload_type}", "{app_name}", "containers", "{app_name}", "resources", "memory", "limitMiB"]
- memory request: ["workloads", "{workload_type}", "{app_name}", "containers", "{app_name}", "resources", "memory", "requestMiB"]
- cpu limit: ["workloads", "{workload_type}", "{app_name}", "containers", "{app_name}", "resources", "cpu", "limitMilliCPU"]
- cpu request: ["workloads", "{workload_type}", "{app_name}", "containers", "{app_name}", "resources", "cpu", "requestMilliCPU"]
- environment variable: ["workloads", "{workload_type}", "{app_name}", "containers", "{app_name}", "envs", "VARIABLE_NAME"]
- replicas: ["workloads", "{workload_type}", "{app_name}", "replicas"]

output ONLY the json object, nothing else:"""

        print(f"[BotService] asking llm for change spec...")
        response = self._call_ollama(prompt)
        if not response:
            print(f"[BotService] llm didn't respond")
            return None

        print(f"[BotService] llm said: {response}")

        # try to parse the json
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # sometimes the llm adds extra text, try to extract just the json part
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            print(f"[BotService] couldn't parse llm response as json")
            return None

    def _apply_change(self, values: dict, change_spec: dict) -> dict | None:
        """apply the change spec to the values dict"""
        try:
            path = change_spec.get("path", [])
            new_value = change_spec.get("value")

            if not path:
                print(f"[BotService] no path in change spec")
                return None

            print(f"[BotService] applying: {path} = {new_value}")

            # deep copy so we don't mess up the original
            result = copy.deepcopy(values)

            # navigate to the parent of what we want to change
            current = result
            for key in path[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            # set the new value
            current[path[-1]] = new_value

            print(f"[BotService] change applied successfully")
            return result

        except Exception as e:
            print(f"[BotService] error applying change: {e}")
            return None

    def _call_ollama(self, prompt: str) -> str | None:
        """call ollama api to get llm response"""
        try:
            data = json.dumps({
                "model": "llama3.1",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # low temp for consistent output
                    "num_predict": 512,  # we don't need long responses
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "")

        except urllib.error.URLError as e:
            print(f"[BotService] ollama api error: {e}")
            return None
        except Exception as e:
            print(f"[BotService] error calling ollama: {e}")
            return None

    def _fetch_schema(self, app_name: str) -> dict | None:
        """fetch schema from schema service"""
        try:
            req = urllib.request.Request(f"{SCHEMA_SERVICE_URL}/{app_name}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[BotService] failed to fetch schema: {e}")
            return None

    def _fetch_values(self, app_name: str) -> dict | None:
        """fetch values from values service"""
        try:
            req = urllib.request.Request(f"{VALUES_SERVICE_URL}/{app_name}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[BotService] failed to fetch values: {e}")
            return None

    def _send_response(self, status: int, body: str):
        """send json response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, status: int, message: str):
        """send error response"""
        body = json.dumps({"error": message})
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        """custom logging"""
        print(f"[BotService] {args[0]}")


def parse_args():
    """parse command line args"""
    parser = argparse.ArgumentParser(description="Bot Service")
    parser.add_argument(
        "--listen",
        default="0.0.0.0:5003",
        help="host:port to listen on (default: 0.0.0.0:5003)",
    )
    return parser.parse_args()


def main():
    """main entry point"""
    args = parse_args()

    host, port = args.listen.rsplit(":", 1)
    port = int(port)

    server = HTTPServer((host, port), BotHandler)
    print(f"Bot Service listening on {host}:{port}")
    print(f"schema service url: {SCHEMA_SERVICE_URL}")
    print(f"values service url: {VALUES_SERVICE_URL}")
    print(f"ollama url: {OLLAMA_URL}")
    print(f"ollama timeout: {OLLAMA_TIMEOUT}s")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
