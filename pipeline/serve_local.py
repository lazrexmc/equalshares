#!/usr/bin/env python3
"""serve_local.py - view the exported site locally before Pages exists.

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


def parse_site_headers():
    """Parse the /* block of site/_headers so local dev serves the SAME
    security headers as production (static-publication-site module section 5.4:
    one source of truth, no hand-kept copy to drift). Review finding
    2026-08-28: without this the CSP was enforced nowhere except production -
    the exact 'local dev hid it entirely' failure class."""
    headers = []
    hf = SITE / "_headers"
    if not hf.exists():
        log("WARNING: site/_headers not found - serving WITHOUT the "
            "production security headers")
        return headers
    in_star = False
    for line in hf.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            in_star = (stripped == "/*")
            continue
        if in_star and ":" in stripped:
            name, _, value = stripped.partition(":")
            headers.append((name.strip(), value.strip()))
    return headers


SECURITY_HEADERS = None  # populated in main() after SITE is validated


class SiteHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path):
        ext = Path(str(path)).suffix.lower()
        if ext in MIME:
            return MIME[ext]
        return super().guess_type(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        for name, value in (SECURITY_HEADERS or []):
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, format, *args):
        log(f"{self.address_string()} {format % args}")


def main():
    if not SITE.is_dir():
        log(f"ERROR: site directory not found: {SITE}")
        sys.exit(1)
    meta = SITE / "data" / "meta.json"
    if not meta.exists():
        log(f"note: {meta} does not exist yet - the page will show its loud error box until export_site.py runs")
    global SECURITY_HEADERS
    SECURITY_HEADERS = parse_site_headers()
    log(f"serving {len(SECURITY_HEADERS)} security header(s) from site/_headers "
        f"on every response (production parity)")
    handler = functools.partial(SiteHandler, directory=str(SITE))
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), handler)
    except OSError as e:
        log(f"ERROR: cannot bind {HOST}:{PORT} ({e}) - is another serve_local.py already running?")
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
