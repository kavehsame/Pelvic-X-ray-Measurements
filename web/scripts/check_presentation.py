"""Check exported annotation resolution and browser presentation in real Chrome."""

import argparse
import base64
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import Thread

from PIL import Image

from check_chrome import CHROME, isolated_chrome
from check_core import QA
from serve_local import SiteHandler


def export_png(browser, summary, target):
    content = browser.js("""(async()=>{
      const blob=await viewer.exportPNG({markups:[{role:'qa',kind:'points',points:[[64,48]],
        color:[255,80,160],labels:[],locked:false}]},%s,'Synthetic check',true);
      const bytes=new Uint8Array(await blob.arrayBuffer());
      let result='';for(let i=0;i<bytes.length;i+=8192)result+=String.fromCharCode(...bytes.subarray(i,i+8192));
      return btoa(result);
    })()""" % json.dumps(summary))
    data = base64.b64decode(content)
    target.write_bytes(data)
    return Image.open(BytesIO(data)).convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, default=CHROME)
    args = parser.parse_args()
    QA.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="presentation_", dir=QA))
    source = root / "LowResolution.png"
    Image.new("L", (128, 96), 180).save(source)
    checked = []
    with ThreadingHTTPServer(("127.0.0.1", 0), SiteHandler) as host:
        thread = Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            with isolated_chrome(root, f"http://127.0.0.1:{host.server_port}/", args.chrome) as browser:
                browser.wait("document.readyState==='complete' && !!document.querySelector('#start')")
                browser.click("#start")
                browser.wait("!document.querySelector('#workspace').hidden && !!snap && !busy", seconds=60)
                browser.files("#file-input", [source])
                browser.wait("!!snap?.image && !busy")
                dimensions = browser.js("[[128,96],[96,128],[3000,2000],[10000,10000],[20000,1000]].map(shape=>exportImageDimensions(shape,[1,1]))")
                assert dimensions[:3] == [[2048, 1536], [1536, 2048], [3000, 2000]]
                assert all(max(pair) <= 15500 and pair[0] * pair[1] <= 40_000_000 for pair in dimensions)
                before = browser.js("snap.markups")
                image = export_png(browser, ["Ref: 80 su"], root / "low_resolution_export.png")
                assert image.size == (2048, 1536)
                center = (round(64.5 * 16), round(48.5 * 16))
                assert image.getpixel(center) == (255, 80, 160)
                assert browser.js("snap.markups") == before
                assert browser.js("snap.image.dimensions") == [128, 96]
                checked.append("Low-resolution PNG is rendered at 2,048 pixels on its long edge with crisp annotation colours; source pixels and landmarks are unchanged.")
    
        finally:
            host.shutdown()
            thread.join(timeout=3)
    (QA / "presentation_checks.json").write_text(json.dumps({"status": "passed", "tests": checked,
        "patient_data_used": False, "run": root.name}, indent=2) + "\n")
    print("PASS: presentation checks", len(checked))


if __name__ == "__main__":
    main()
