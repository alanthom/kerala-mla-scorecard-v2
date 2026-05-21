#!/usr/bin/env python3
import http.server
import os

SERVE_DIR = "/Users/thomas.alan._/kerala-mla-scorecard/output"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", 8090), Handler)
    print(f"Serving {SERVE_DIR} on http://localhost:8090", flush=True)
    server.serve_forever()
