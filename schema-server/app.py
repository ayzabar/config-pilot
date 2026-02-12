#!/usr/bin/env python3
"""schema service, serves json schemas for different apps"""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class SchemaHandler(BaseHTTPRequestHandler):
    """handles http requests for schemas"""

    schema_dir = "/data/schemas"

    def do_GET(self):
        """handles GET /{app_name} requests"""
        # get the app name from the url path
        app_name = self.path.strip("/")

        if not app_name:
            self._send_error(404, "Not Found")
            return

        # construct the file path
        schema_file = os.path.join(self.schema_dir, f"{app_name}.schema.json")

        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                content = f.read()

            self._send_response(200, content)
        except FileNotFoundError:
            self._send_error(404, "Not Found")
        except Exception as e:
            self._send_error(500, f"Internal Server Error: {str(e)}")

    def _send_response(self, status: int, body: str):
        """send json response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, status: int, message: str):
        """send error response as json"""
        body = json.dumps({"error": message})
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        """custom logging for requests"""
        print(f"[SchemaService] {args[0]}")


def parse_args():
    """parse command line args"""
    parser = argparse.ArgumentParser(description="Schema Service")
    parser.add_argument(
        "--schema-dir",
        default="/data/schemas",
        help="Directory containing schema files (default: /data/schemas)",
    )
    parser.add_argument(
        "--listen",
        default="0.0.0.0:5001",
        help="Host:port to listen on (default: 0.0.0.0:5001)",
    )
    return parser.parse_args()


def main():
    """main entry point"""
    args = parse_args()

    # set the schema directory
    SchemaHandler.schema_dir = args.schema_dir

    # parse host and port
    host, port = args.listen.rsplit(":", 1)
    port = int(port)

    # start the server
    server = HTTPServer((host, port), SchemaHandler)
    print(f"Schema Service listening on {host}:{port}")
    print(f"Serving schemas from: {args.schema_dir}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
