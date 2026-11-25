"""Check the generated website and app under a GitHub Pages-style project path."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from mimetypes import guess_type
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import unquote, urlsplit

from project import BUILD, WEB, implant_manifest, within

sys.path[:0] = [str(WEB), str(WEB / "scripts")]
from check_chrome import CHROME, isolated_chrome  # noqa: E402

PREFIX = "/Pelvic-X-ray-Measurements/"
SITE = BUILD / "site"


def check_implant_catalogue(browser):
    """Verify the published menu and load a processed overlay from each collection offline."""
    catalogue = json.loads((WEB / "core/planning_templates.json").read_bytes())["items"]
    ids = sorted(browser.js("implantCatalog.map(item => item.id)"))
    assert len(ids) == implant_manifest()["entries"]
    assert ids == sorted(item["id"] for item in catalogue)
    checked = {}
    for vendor, component in (("Medacta", "cup"), ("Mathys", "stem")):
        item = next(i for i in catalogue if i["id"].startswith(vendor + "/") and i["component"] == component)
        digest = item["image"]
        response = browser.js("""(async (digest) => {
          const {files} = await request("template_image", {digest});
          const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", files.png));
          const img = await createImageBitmap(new Blob([files.png], {type:"image/png"}));
          const dims = [img.width, img.height];
          img.close();
          return [Array.from(hash, b => b.toString(16).padStart(2, "0")).join(""), dims];
        })(%s)""" % json.dumps(digest))
        assert response == [digest, item["pixels"]], item["id"]
        checked[item["id"]] = digest
    return {"entries_in_running_browser": len(ids), "processed_pngs_checked_offline": checked}


class Host(BaseHTTPRequestHandler):
    def do_GET(self):
        route = unquote(urlsplit(self.path).path)
        if not route.startswith(PREFIX):
            self.send_error(404)
            return
        path = (SITE / route[len(PREFIX) :]).resolve()
        if path.is_dir():
            path /= "index.html"
        if not path.is_relative_to(SITE.resolve()) or not path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header(
            "Content-Type", guess_type(path.name)[0] or "application/octet-stream"
        )
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, default=CHROME)
    parser.add_argument("--output", type=Path, default=BUILD / "site-check")
    args = parser.parse_args()
    out = within(args.output)
    out.mkdir(parents=True, exist_ok=False)
    with ThreadingHTTPServer(("127.0.0.1", 0), Host) as host:
        thread = Thread(target=host.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{host.server_port}{PREFIX}"
        try:
            with isolated_chrome(out, url, args.chrome) as browser:
                browser.wait(
                    "document.readyState === 'complete' && !!document.querySelector('h1')"
                )
                text = browser.js("document.body.innerText")
                assert (
                    "How the website works" in text
                    and "Validation study in progress" in text
                )
                assert (
                    "established medical software" in text
                    and "not a medical device" in text
                )
                assert "not uploaded" in text
                assert "hospital networks" in text and "may not work" in text
                browser.screenshot(out / "landing-wide.png")
                browser.call(
                    "Emulation.setDeviceMetricsOverride",
                    width=390,
                    height=844,
                    deviceScaleFactor=1,
                    mobile=False,
                )
                assert browser.js("document.documentElement.scrollWidth <= innerWidth")
                browser.screenshot(out / "landing-narrow.png")
                browser.call("Emulation.clearDeviceMetricsOverride")
                browser.click('a[href="app/"]')
                browser.wait("!!document.querySelector('#start')")
                browser.click("#start")
                browser.wait(
                    "!document.querySelector('#workspace').hidden && !!snap && !busy",
                    "workspace at project subpath",
                    55,
                )
                assert browser.js(
                    "document.querySelector('#open-files').textContent.trim() === 'Open a file...'"
                )
                assert browser.js(
                    "document.querySelector('#import-csv').textContent.trim() === 'Open a CSV...'"
                )
                assert browser.js(
                    "location.pathname.endsWith('/Pelvic-X-ray-Measurements/app/')"
                )
                cache = browser.js(
                    "(async()=> (await (await caches.open('pelvic-xray-software')).keys()).map(k=>new URL(k.url).pathname))()"
                )
                assert cache == [PREFIX + "app/runtime.bin"]
                host.shutdown()
                browser.call(
                    "Network.emulateNetworkConditions",
                    offline=True,
                    latency=0,
                    downloadThroughput=0,
                    uploadThroughput=0,
                )
                browser.files(
                    "#file-input", [WEB / "tests/fixtures/SyntheticFullCase.mrb"]
                )
                browser.wait("!!snap?.image && !busy", "offline synthetic scene", 30)
                templates = check_implant_catalogue(browser)
                browser.screenshot(out / "app-subpath-offline.png")
                report = {
                    "status": "passed",
                    "project_subpath": PREFIX,
                    "landing_research_notice": True,
                    "restricted_network_notice": True,
                    "validation_study_notice": True,
                    "how_it_works": True,
                    "narrow_layout_no_horizontal_overflow": True,
                    "app_start_and_cache_at_subpath": True,
                    "offline_synthetic_scene_load": True,
                    **templates,
                }
                (out / "site_checks.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
                print(json.dumps(report, indent=2))
        finally:
            host.shutdown()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()
