"""Exercise component delivery failures and recovery in an isolated real browser."""

import argparse
from collections import Counter
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
from time import sleep
from urllib.parse import urlsplit

from check_chrome import CHROME, isolated_chrome
from check_core import QA
from serve_local import DIST, SiteHandler, asset_for


class DownloadHost(SiteHandler):
    mode = "normal"
    target = ""
    requests = []
    attempts = Counter()

    def reply(self, status, content_type, content):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        route = urlsplit(self.path).path
        type(self).attempts[route] += 1
        if route.endswith((".bin", ".zip", ".whl", ".wasm")):
            self.reply(403, "text/plain", b"Binary and archive downloads are blocked in this test.")
            return
        if route == self.target:
            if self.mode in {"denied", "resume"}:
                self.reply(403, "text/plain", b"Component blocked in this test.")
                return
            if self.mode == "html":
                self.reply(200, "text/html", b"<!doctype html><title>Network sign-in required</title>")
                return
            if self.mode == "temporary" and self.attempts[route] == 1:
                self.reply(503, "text/plain", b"Temporary service failure.")
                return
            if self.mode == "timeout":
                sleep(0.5)
            asset = asset_for(route)
            if asset and self.mode in {"corrupt", "truncated", "oversize"}:
                content = (DIST / asset[0]).read_bytes()
                if self.mode == "corrupt":
                    document = json.loads(content)
                    document["data"] = ("A" if document["data"][0] != "A" else "B") + document["data"][1:]
                    content = json.dumps(document, separators=(",", ":")).encode() + b"\n"
                elif self.mode == "truncated":
                    content = content[: len(content) // 2]
                else:
                    content += b" " * 8192
                self.reply(200, "application/json", content)
                return
        super().do_GET()

    def log_request(self, code="-", size="-"):
        type(self).requests.append((self.command, urlsplit(self.path).path, int(code)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, default=CHROME)
    args = parser.parse_args()
    QA.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="delivery_", dir=QA))
    tests = []
    with ThreadingHTTPServer(("127.0.0.1", 0), DownloadHost) as host:
        thread = Thread(target=host.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{host.server_port}/"
        try:
            for mode in ("normal", "temporary", "denied", "html", "corrupt", "truncated", "oversize", "timeout", "resume", "cache_unavailable", "corrupt_cache"):
                folder = root / mode
                folder.mkdir()
                DownloadHost.mode, DownloadHost.target = mode, ""
                DownloadHost.requests, DownloadHost.attempts = [], Counter()
                with isolated_chrome(folder, url, args.chrome) as browser:
                    browser.wait("document.readyState==='complete' && !!document.querySelector('#start')")
                    components = browser.js("APP_CONFIG.components.map(part => '/' + part.path)")
                    DownloadHost.target = components[-1] if mode == "resume" else components[0]
                    if mode == "timeout":
                        browser.js("APP_CONFIG.componentTimeoutMs=100")
                    if mode == "cache_unavailable":
                        browser.js("Object.defineProperty(globalThis,'caches',{value:{open:async()=>{throw new Error('Storage unavailable in this test');}}});true")
                    if mode == "corrupt_cache":
                        browser.js("""(async()=>{const cache=await caches.open('pelvic-xray-software');
                          const key=new URL(APP_CONFIG.payload,location.href);key.searchParams.set('sha256',APP_CONFIG.payloadHash);
                          await cache.put(key.href,new Response(new Uint8Array([1,2,3])));})()""")
                    browser.click("#start")
                    failures = {"denied": "HTTP 403", "html": "web page", "corrupt": "verification",
                                "truncated": "verification", "oversize": "could not download", "timeout": "timed out", "resume": "HTTP 403"}
                    if mode in failures:
                        browser.wait("!document.querySelector('#start-error-details').hidden && !document.querySelector('#start').disabled",
                                     "recoverable component error", 35)
                        message = browser.js("document.querySelector('#start-status').textContent")
                        assert failures[mode] in message, (mode, message)
                        assert browser.js("document.querySelector('#workspace').hidden && !startLocked && !worker && !snap")
                        detail = browser.js("JSON.parse(document.querySelector('#start-error-text').textContent)")
                        assert detail["component"] == url + DownloadHost.target[1:]
                        if mode == "denied":
                            assert detail["httpStatus"] == 403
                            browser.screenshot(folder / "blocked-download.png")
                        if mode == "resume":
                            cached = browser.js("(async()=> (await (await caches.open('pelvic-xray-software')).keys()).map(key=>new URL(key.url).pathname))()")
                            assert cached and all(path in components for path in cached)
                            attempts = DownloadHost.attempts.copy()
                            DownloadHost.mode = "normal"
                            browser.click("#start")
                            browser.wait("!document.querySelector('#workspace').hidden && !!snap && !busy", "resumed startup", 60)
                            for path in cached:
                                assert DownloadHost.attempts[path] == attempts[path], path
                    else:
                        browser.wait("!document.querySelector('#workspace').hidden && !!snap && !busy", "verified component startup", 60)
                        assert browser.js("config.version === APP_CONFIG.version")
                        if mode == "temporary":
                            assert DownloadHost.attempts[DownloadHost.target] == 2
                        if mode != "cache_unavailable":
                            assert browser.js("(async()=> (await (await caches.open('pelvic-xray-software')).keys()).length===1)()")
                    assert all(method == "GET" for method, _, _ in DownloadHost.requests)
                    assert all(path == "/" or path in components for _, path, _ in DownloadHost.requests)
                    (folder / "requests.json").write_text(json.dumps(DownloadHost.requests, indent=2) + "\n")
                    tests.append(mode)
                    print("PASS: component delivery", mode, flush=True)
        finally:
            host.shutdown()
            thread.join(timeout=3)
    report = {"status": "passed", "tests": tests, "binary_and_archive_routes_blocked": True,
              "unverified_components_never_started": True, "partial_download_reused": True,
              "patient_data_used": False, "run": root.name}
    (QA / "download_checks.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
