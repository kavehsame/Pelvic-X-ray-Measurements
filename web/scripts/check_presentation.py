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


def canvas_mouse(browser, event, point, *, held=False):
    left, top = browser.js("(() => {const r=viewer.canvas.getBoundingClientRect(); return [r.left,r.top];})()")
    browser.call(
        "Input.dispatchMouseEvent",
        type=event, x=left + point[0], y=top + point[1],
        button="left" if held or event != "mouseMoved" else "none",
        buttons=int(held or event == "mousePressed"),
        clickCount=int(event != "mouseMoved"),
    )


def check_landmark_selection(browser, root):
    focus = "viewer.landmarkFocus?.target"
    cursor = "getComputedStyle(viewer.canvas).cursor"
    # The four wall tracks placed above have coincident control points.
    x, y = browser.js("viewer.position(snap.markups.find(m=>m.role==='left_anteriorAcetabularWall').points[1])")
    near = (x + 5, y)
    canvas_mouse(browser, "mouseMoved", (x + 10, y))
    assert not browser.js(focus)
    canvas_mouse(browser, "mouseMoved", near)
    first = browser.js(focus)
    assert first and browser.js("viewer.landmarkFocus.multiple")
    assert browser.js(cursor) == "default"
    original = browser.js("snap.markups")
    choices = {first["role"]}
    for _ in range(3):
        canvas_mouse(browser, "mousePressed", near)
        canvas_mouse(browser, "mouseReleased", near)
        choices.add(browser.js(focus)["role"])
    assert choices == {f"{side}_{wall}AcetabularWall" for side in ("left", "right") for wall in ("anterior", "posterior")}
    assert browser.js("snap.markups") == original
    selected = browser.js(focus)
    browser.screenshot(root / "overlapping_landmarks.png")
    start = (near[0] + 0.8, near[1])
    canvas_mouse(browser, "mouseMoved", start)
    assert browser.js(focus) == selected
    canvas_mouse(browser, "mousePressed", start)
    assert browser.js("viewer.gesture.target") == selected
    end = (start[0] - 22, start[1] + 11)
    canvas_mouse(browser, "mouseMoved", end, held=True)
    assert browser.js("viewer.gesture.target") == selected
    assert browser.js(cursor) == "default"
    canvas_mouse(browser, "mouseReleased", end)
    browser.wait("!busy && !viewer.previewInFlight")
    moved = {item["role"]: item["points"] for item in browser.js("snap.markups")}
    for item in original:
        expected = item["points"].copy()
        if item["role"] == selected["role"]:
            zoom = browser.js("viewer.zoom")
            px, py = expected[selected["index"]]
            expected[selected["index"]] = [px - 22 / zoom, py + 11 / zoom]
            for actual, goal in zip(moved[item["role"]], expected, strict=True):
                assert all(math.isclose(a, b, abs_tol=0.09) for a, b in zip(actual, goal, strict=True))
        else:
            assert moved[item["role"]] == expected

    # Two distinguishable points keep their focus when the pointer moves just
    # across the midpoint, and switch when it gets clearly closer to the other.
    zoom = browser.js("viewer.zoom")
    browser.annotate("other_point", [(95, 37)])
    browser.annotate("other_point", [(95 + 5.5 / zoom, 37)])
    left, right = browser.js("['otherPoint_1','otherPoint_2'].map(role=>viewer.position(snap.markups.find(m=>m.role===role).points[0]))")
    canvas_mouse(browser, "mouseMoved", left)
    assert browser.js(focus)["role"] == "otherPoint_1"
    canvas_mouse(browser, "mouseMoved", ((left[0] + right[0]) / 2 + 0.4, left[1]))
    assert browser.js(focus)["role"] == "otherPoint_1"
    canvas_mouse(browser, "mouseMoved", right)
    assert browser.js(focus)["role"] == "otherPoint_2"


def check_magnified_pan(browser):
    cursor = "getComputedStyle(viewer.canvas).cursor"
    # Read the two stripe values after the default grayscale window.
    source_shades = browser.js("""(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 2;
      canvas.height = 1;
      const context = canvas.getContext("2d");
      context.drawImage(viewer.bitmap, 60, 24, 2, 1, 0, 0, 2, 1);
      const pixels = context.getImageData(0, 0, 2, 1).data;
      return [pixels[0], pixels[4]].sort((a, b) => a - b);
    })()""")
    assert source_shades[1] - source_shades[0] > 100
    # Sample across pixel boundaries where smoothing would introduce new ones.
    shades = """(() => {
      const start = viewer.position([54.5, 24]), end = viewer.position([65.5, 24]);
      const scale = viewer.ratio;
      const x = Math.ceil(start[0] * scale), y = Math.floor(start[1] * scale);
      const width = Math.floor(end[0] * scale) - x;
      const rgba = viewer.ctx.getImageData(x, y, width, 1).data;
      return Array.from(new Set(rgba.filter((_, i) => i % 4 === 0))).sort((a, b) => a - b);
    })()"""
    browser.js("viewer.zoomAt(1 / (viewer.zoom * viewer.ratio), viewer.position([60, 24]))")
    assert browser.js("viewer.ctx.imageSmoothingEnabled")
    browser.js("viewer.zoomAt(11.3 / viewer.zoom, viewer.position([60, 24]))")
    browser.click("#pan-button")
    start = browser.js("viewer.position([60, 24])")
    before = browser.js("[viewer.x, viewer.y]")
    canvas_mouse(browser, "mouseMoved", start)
    assert browser.js(cursor) == "default"
    observed = browser.js(shades)
    assert observed == source_shades, observed
    canvas_mouse(browser, "mousePressed", start)
    assert browser.js(cursor) == "default"
    end = (start[0] + 28.5, start[1] + 16.25)
    canvas_mouse(browser, "mouseMoved", end, held=True)
    assert browser.js(cursor) == "grabbing"
    assert browser.js("[viewer.x, viewer.y]") != before
    observed = browser.js(shades)
    assert observed == source_shades, observed
    canvas_mouse(browser, "mouseReleased", end)
    assert browser.js(cursor) == "default"
    observed = browser.js(shades)
    assert observed == source_shades, observed
    browser.click("#pan-button")


def check_case_jump(browser, root):
    assert browser.js("document.querySelector('#case-jump').hidden")
    browser.js("""(() => {
      const source = entries[0].file;
      const list = new DataTransfer();
      for (let i = 1; i <= 1000; i++) {
        list.items.add(new File([source], `Study${i}.png`, {type: "image/png"}));
      }
      const chooser = document.querySelector("#file-input");
      chooser.files = list.files;
      chooser.dispatchEvent(new Event("change", {bubbles: true}));
    })()""")
    browser.wait("document.querySelector('#decision-dialog').open")
    browser.click("#decision-actions .primary")
    browser.wait("!busy && document.querySelector('#case-count').textContent === '1 of 1000'")
    assert browser.js("""(() => {
      const count = document.querySelector("#case-count").getBoundingClientRect();
      const field = document.querySelector("#case-number").getBoundingClientRect();
      return field.top >= count.bottom && field.width > 0;
    })()""")
    browser.annotate("other_point", [(15, 59)])
    original = browser.js("snap.markups.find(mark => mark.role === 'otherPoint_1').points")
    browser.js("document.querySelector('#comments').value = 'Keep this working case'")
    browser.js("document.querySelector('#case-number').focus()")
    browser.call("Input.insertText", text="500")
    assert browser.js("document.querySelector('#case-number').valueAsNumber") == 500
    enter = dict(key="Enter", code="Enter", windowsVirtualKeyCode=13)
    browser.call("Input.dispatchKeyEvent", type="keyDown", text="\r", **enter)
    browser.call("Input.dispatchKeyEvent", type="keyUp", **enter)
    browser.wait("!busy && document.querySelector('#case-count').textContent === '500 of 1000'")
    assert browser.js("document.querySelector('#case-name').textContent") == "Study500.png"
    assert not browser.js("snap.markups.length")
    browser.screenshot(root / "case_jump.png")

    for invalid in ("", "0", "1.5", "1001"):
        browser.js(f"document.querySelector('#case-number').value = {json.dumps(invalid)}")
        browser.click("#case-go")
        assert browser.js("document.querySelector('#case-number').getAttribute('aria-invalid')") == "true"
        assert browser.js("document.querySelector('#case-count').textContent") == "500 of 1000"
    browser.js("document.querySelector('#case-number').value = '1000'")
    browser.click("#case-go")
    browser.wait("!busy && document.querySelector('#case-count').textContent === '1000 of 1000'")
    assert browser.js("document.querySelector('#case-next').disabled")
    assert browser.js("document.querySelector('#case-jump-error').hidden")
    browser.js("document.querySelector('#case-number').value = '1'")
    browser.click("#case-go")
    browser.wait("!busy && document.querySelector('#case-count').textContent === '1 of 1000'")
    assert browser.js("snap.markups.find(mark => mark.role === 'otherPoint_1').points") == original
    assert browser.js("document.querySelector('#comments').value") == "Keep this working case"


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
    for y in range(18, 31):
        for x in range(51, 70):
            pixels.putpixel((x, y), 32 if x % 2 else 224)
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
                browser.js("document.querySelector('#tool-morphology').focus()")
                # Disabled buttons cannot receive focus. A result field carries
                # the same help entry without requiring calibration first.
                browser.js("queueHelp(document.querySelector('[data-help=result_ccr]'))")
                browser.wait("!document.querySelector('#hover-help').hidden", seconds=5)
                browser.wait("document.querySelector('#hover-help img').complete")
                box = browser.js("(()=>{const r=document.querySelector('#hover-help').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,vw:innerWidth,vh:innerHeight};})()")
                assert box["w"] >= min(900, box["vw"] - 20)
                assert 0 <= box["x"] and box["x"] + box["w"] <= box["vw"]
                assert 0 <= box["y"] and box["y"] + box["h"] <= box["vh"]
                browser.screenshot(root / "morphology_help.png")
                browser.js("hideHelp()")
                checked.append("The morphology help image opens at a readable width and remains inside the viewport.")
                check_landmark_selection(browser, root)
                checked.append("Nearby points focus without flicker, coincident points cycle through their labels and a drag moves only the chosen point from its original position.")
                check_magnified_pan(browser)
                checked.append("The hand appears only during panning; high-zoom pixel boundaries stay sharp before, during and after a fractional pan.")
                check_case_jump(browser, root)
                checked.append("The jump field below the case count accepts Enter and Go, jumps directly to cases 500 and 1,000, rejects invalid numbers and restores unsaved work on return.")

        finally:
            host.shutdown()
            thread.join(timeout=3)
    (QA / "presentation_checks.json").write_text(json.dumps({"status": "passed", "tests": checked,
        "patient_data_used": False, "run": root.name}, indent=2) + "\n")
    print("PASS: presentation checks", len(checked))


if __name__ == "__main__":
    main()
