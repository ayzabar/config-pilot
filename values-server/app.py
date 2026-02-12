#!/usr/bin/env python3
"""values service, serves current config values for apps"""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class ValuesHandler(BaseHTTPRequestHandler):
    """handles http requests for values"""

    values_dir = "/data/values"

    def do_GET(self):
        """handles GET /{app_name} requests"""
        # get app name from url
        app_name = self.path.strip("/")

        if not app_name:
            self._send_error(404, "Not Found")
            return

        # build file path
        values_file = os.path.join(self.values_dir, f"{app_name}.value.json")

        try:
            with open(values_file, "r", encoding="utf-8") as f:
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
        """send error as json"""
        body = json.dumps({"error": message})
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        """custom logging"""
        print(f"[ValuesService] {args[0]}")


def parse_args():
    """parse command line args"""
    parser = argparse.ArgumentParser(description="Values Service")
    parser.add_argument(
        "--schema-dir",
        default="/data/values",
        help="Directory containing value files (default: /data/values)",
    )
    parser.add_argument(
        "--listen",
        default="0.0.0.0:5002",
        help="Host:port to listen on (default: 0.0.0.0:5002)",
    )
    return parser.parse_args()


def main():
    """main entry point"""
    args = parse_args()

    # set values directory
    ValuesHandler.values_dir = args.schema_dir

    # parse listen address
    host, port = args.listen.rsplit(":", 1)
    port = int(port)

    # start server
    server = HTTPServer((host, port), ValuesHandler)
    print(f"Values Service listening on {host}:{port}")
    print(f"Serving values from: {args.schema_dir}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
