"""Check exported annotation resolution and browser presentation in real Chrome."""

import argparse
import base64
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
import math
from pathlib import Path
import tempfile
from threading import Thread

from PIL import Image, ImageChops

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
    pixels = Image.new("L", (128, 96), 180)
    pixels.putpixel((0, 0), 0)
    pixels.putpixel((127, 0), 255)
    pixels.save(source)
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
                band = image.crop((0, image.height - 180, image.width, image.height))
                background = Image.new("RGB", band.size, image.getpixel((0, image.height - 1)))
                bounds = ImageChops.difference(band, background).getbbox()
                assert bounds and abs((bounds[0] + bounds[2]) / 2 - image.width / 2) <= 2, bounds
                # A gap near the panel's left padding samples the background,
                # away from text, and must retain visible grayscale information.
                x, y = bounds[0] + 3, image.height - 180 + bounds[1] + 3
                assert 0 < image.getpixel((x, y))[0] < image.getpixel((0, image.height - 1))[0]
                checked.append("The translucent PNG summary is centred at the bottom.")
                keys = browser.js("Array.from(document.querySelectorAll('[id^=tool-]')).map(button=>button.id)")
                roof = keys.index("tool-sourcil")
                assert keys[roof + 1:roof + 3] == ["tool-anterior_wall", "tool-posterior_wall"]
                colors = []
                for side in ("left", "right"):
                    browser.click("#side-" + side)
                    browser.wait("!busy")
                    for wall in ("anterior", "posterior"):
                        role = side + "_" + wall + "AcetabularWall"
                        browser.click("#tool-" + wall + "_wall")
                        browser.wait("!busy && !!snap.active_role")
                        assert browser.js("snap.active_role") == role
                        for point in ((20, 70), (40, 45), (80, 60)):
                            browser.point(*point)
                        browser.finish()
                        mark = browser.js(f"snap.markups.find(mark=>mark.role==={json.dumps(role)})")
                        assert mark["kind"] == "curve" and len(mark["points"]) == 3
                        colors.append(mark["color"])
                        browser.click(f'#hide-{wall}_wall')
                        browser.wait("!busy")
                        assert not browser.js(f"snap.markups.some(mark=>mark.role==={json.dumps(role)})")
                        browser.click(f'#hide-{wall}_wall')
                        browser.wait("!busy")
                assert colors[0] != colors[1] and colors[:2] == colors[2:]
                browser.screenshot(root / "wall_contours.png")
                checked.append("Both wall contours follow the roof in the UI; bilateral placement, finish, distinct colours and Hide work.")
                browser.click("#tool-shenton")
                browser.wait("!busy && !!snap.active_role")
                browser.point(30, 70)
                browser.point(45, 40)
                browser.mouse_at("mouseMoved", 85, 65, button="none")
                paths = browser.js("""(()=>{
                  const original=JSON.stringify(viewer.marks), mark=viewer.marks.find(m=>m.role===viewer.active);
                  const record=()=>{const calls=[];return {calls,ctx:new Proxy({}, {
                    get:(_,name)=>(...args)=>{if(['lineTo','bezierCurveTo'].includes(name))calls.push([name,...args]);},
                    set:()=>true})};};
                  const solid=record(),guide=record(),complete=record(),plain=record();
                  const next=viewer.placementContinuation(),pos=p=>viewer.position(p);
                  drawMarks(solid.ctx,[mark],pos,1.65,3.05,null,next);
                  viewer.drawPlacementGuide(guide.ctx,next);
                  drawMarks(complete.ctx,[{...mark,points:[...mark.points,viewer.imagePoint(viewer.current)]}],pos,1.65,3.05);
                  viewer.drawPlacementGuide(plain.ctx,{...next,mark:{...mark,kind:'line'}});
                  return {solid:solid.calls,guide:guide.calls,complete:complete.calls,plain:plain.calls,
                    unchanged:original===JSON.stringify(viewer.marks)};
                })()""")
                assert len(paths["guide"]) == 1 and paths["guide"][0][0] == "bezierCurveTo"
                combined = paths["solid"] + paths["guide"]
                assert len(combined) == len(paths["complete"]), paths
                for actual, expected in zip(combined, paths["complete"], strict=True):
                    assert actual[0] == expected[0]
                    assert all(math.isclose(a, b, abs_tol=1e-8) for a, b in zip(actual[1:], expected[1:], strict=True)), paths
                assert len(paths["plain"]) == 1 and paths["plain"][0][0] == "lineTo"
                assert paths["unchanged"]
                browser.screenshot(root / "curved_continuation.png")
                browser.finish()
                checked.append("The dashed contour continuation and preceding segment match the complete provisional curve, leave saved points unchanged and keep line previews straight.")
    
        finally:
            host.shutdown()
            thread.join(timeout=3)
    (QA / "presentation_checks.json").write_text(json.dumps({"status": "passed", "tests": checked,
        "patient_data_used": False, "run": root.name}, indent=2) + "\n")
    print("PASS: presentation checks", len(checked))


if __name__ == "__main__":
    main()
