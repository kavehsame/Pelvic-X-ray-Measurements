"""Serve only the compiled website on loopback for local review."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from shutil import copyfileobj
from urllib.parse import urlsplit

DIST = Path(__file__).resolve().parents[2] / "build" / "web"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/implant-overlays.html": ("implant-overlays.html", "text/html; charset=utf-8"),
}


def asset_for(route):
    if route in ASSETS:
        return ASSETS[route]
    if re.fullmatch(r"/components/[0-9a-f]{64}/[0-9]{3}\.json", route):
        return route.removeprefix("/"), "application/json; charset=utf-8"
    return None


class SiteHandler(BaseHTTPRequestHandler):
    def handle_asset(self, body):
        path = urlsplit(self.path)
        asset = asset_for(path.path)
        if path.query or not asset:
            self.send_error(404)
            return
        name, content_type = asset
        file = DIST / name
        if not file.resolve().is_relative_to(DIST.resolve()) or not file.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(file.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        self.end_headers()
        if body:
            with file.open("rb") as stream:
                try:
                    copyfileobj(stream, self.wfile)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def do_GET(self):
        self.handle_asset(True)

    def do_HEAD(self):
        self.handle_asset(False)

    def reject(self):
        self.send_error(405, "This host serves static app files")

    do_POST = do_PUT = do_PATCH = do_DELETE = reject

    def log_request(self, code="-", size="-"):
        # Record only the method and allowlisted asset, never arbitrary paths.
        route = urlsplit(self.path).path
        asset = (asset_for(route) or ("unknown", ""))[0]
        self.log_message("%s %s %s", self.command, asset, code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18999)
    args = parser.parse_args()
    if not all((DIST / value[0]).is_file() for value in ASSETS.values()):
        raise SystemExit("Run build_web.py before starting the local preview.")
    with ThreadingHTTPServer(("127.0.0.1", args.port), SiteHandler) as server:
        print(f"Local website: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
