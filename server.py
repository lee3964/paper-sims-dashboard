#!/usr/bin/env python3
"""Local static server on :8765 + live /api/snapshot.json from aggregate()."""
from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
PORT = 8765

sys.path.insert(0, str(ROOT))
from aggregate import aggregate  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/api/snapshot.json", "/api/snapshot"):
            body = json.dumps(aggregate(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"sim-compare listening on http://127.0.0.1:{PORT}/")
    print(f"  live API: http://127.0.0.1:{PORT}/api/snapshot.json")
    print(f"  static:   {DOCS}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
