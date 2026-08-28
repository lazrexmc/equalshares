#!/usr/bin/env python3
"""serve_local.py — view the exported site locally before Pages exists.

Serves site/ at http://127.0.0.1:8765/ with a correct MIME type for .json
(Windows registry entries can poison mimetypes into text/plain) and
Cache-Control: no-store so an export_site.py re-run shows up on refresh.
Stdlib only (Python 3.14).
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import functools
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
SITE = Path(__file__).resolve().parent.parent / "site"

MIME = {
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
}


def log(msg=""):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


class SiteHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path):
        ext = Path(str(path)).suffix.lower()
        if ext in MIME:
            return MIME[ext]
        return super().guess_type(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        log(f"{self.address_string()} {format % args}")


def main():
    if not SITE.is_dir():
        log(f"ERROR: site directory not found: {SITE}")
        sys.exit(1)
    meta = SITE / "data" / "meta.json"
    if not meta.exists():
        log(f"note: {meta} does not exist yet — the page will show its loud error box until export_site.py runs")
    handler = functools.partial(SiteHandler, directory=str(SITE))
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), handler)
    except OSError as e:
        log(f"ERROR: cannot bind {HOST}:{PORT} ({e}) — is another serve_local.py already running?")
        sys.exit(1)
    log(f"serving {SITE}")
    log(f"open  http://{HOST}:{PORT}/   (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("stopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
