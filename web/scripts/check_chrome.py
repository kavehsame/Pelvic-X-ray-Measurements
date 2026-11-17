"""Exercise the exact static build in an isolated, real Chrome test session."""

import argparse
import base64
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
from threading import Thread
from time import monotonic, sleep
from urllib.request import urlopen
from zipfile import ZipFile

from PIL import Image
import websocket

from check_core import QA, compare, measurements
from core.scene_files import read_mrb
from serve_local import SiteHandler

CHROME = Path(
    os.environ.get("CHROME_PATH")
    or shutil.which("google-chrome")
    or shutil.which("chromium")
    or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if sys.platform == "darwin"
        else "chrome"
    )
)


class Chrome:
    def __init__(self, socket):
        self.socket = socket
        self.seq = 0
        self.events = []

    def call(self, method, **params):
        self.seq += 1
        self.socket.send(
            json.dumps({"id": self.seq, "method": method, "params": params})
        )
        while True:
            result = json.loads(self.socket.recv())
            if "method" in result:
                self.events.append(result)
                continue
            if result.get("id") == self.seq:
                if "error" in result:
                    raise RuntimeError(result["error"])
                return result.get("result", {})

    def js(self, expression):
        reply = self.call(
            "Runtime.evaluate",
            expression=expression,
            awaitPromise=True,
            returnByValue=True,
            userGesture=True,
        )
        if "exceptionDetails" in reply:
            logs = [
                x["params"].get("args", [])
                for x in self.events
                if x["method"] == "Runtime.consoleAPICalled"
                and x["params"].get("type") == "error"
            ][-2:]
            raise RuntimeError(
                f"{reply['exceptionDetails']['exception']['description']}\n{logs}"
            )
        return reply["result"].get("value")

    def wait(self, predicate, description="", seconds=12):
        end = monotonic() + seconds
        while monotonic() < end:
            if self.js(predicate):
                return
            sleep(0.06)
        state = self.js(
            "({start: document.querySelector('#start-status').textContent, "
            "instruction: document.querySelector('#instruction').textContent})"
        )
        errors = [
            event.get("params")
            for event in self.events
            if event.get("method") == "Runtime.consoleAPICalled"
            and event["params"].get("type") == "error"
        ][-2:]
        raise AssertionError(
            f"Timed out waiting for {description or predicate}. {state}. {errors}"
        )

    def click(self, selector):
        sel = json.dumps(selector)
        self.wait(
            f"document.querySelector({sel}) && !document.querySelector({sel}).disabled",
            selector,
        )
        self.js(f"document.querySelector({sel}).click()")

    def files(self, selector, files):
        root = self.call("DOM.getDocument")["root"]["nodeId"]
        node = self.call("DOM.querySelector", nodeId=root, selector=selector)["nodeId"]
        self.call("DOM.setFileInputFiles", nodeId=node, files=[str(p) for p in files])

    def mouse_at(self, event, x, y, *, button="left", modifiers=0):
        sx, sy = self.js(
            f"(() => {{const [x,y]=viewer.position([{x},{y}]); "
            "const r=viewer.canvas.getBoundingClientRect(); return [r.x+x,r.y+y];})()"
        )
        buttons = {"none": 0, "left": 1, "right": 2, "middle": 4}
        self.call(
            "Input.dispatchMouseEvent",
            type=event,
            x=sx,
            y=sy,
            button=button,
            modifiers=modifiers,
            clickCount=int(event != "mouseMoved"),
            buttons=0 if event == "mouseReleased" else buttons[button],
        )

    def point(self, x, y):
        self.mouse_at("mousePressed", x, y)
        self.mouse_at("mouseReleased", x, y)
        self.wait("!busy", "placement update")

    def finish(self):
        self.call("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape")
        self.call("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape")
        self.wait("!busy")

    def annotate(self, tool, points):
        self.click("#tool-" + tool)
        self.wait("!busy && !!snap.active_role", tool)
        for point in points:
            self.point(*point)
        self.wait("!busy && !snap.active_role", tool + " completion")

    def screenshot(self, path):
        shot = self.call("Page.captureScreenshot", format="png", fromSurface=True)[
            "data"
        ]
        path.write_bytes(base64.b64decode(shot))


class TestHost(SiteHandler):
    requests = []

    def log_request(self, code="-", size="-"):
        self.requests.append((self.command, self.path, int(code)))


@contextmanager
def socket_temp_path(directory):
    """Keep Linux socket paths short while all files remain in the test folder."""
    if sys.platform != "linux":
        yield directory
        return
    # Unix socket addresses are much shorter than filesystem paths. A procfs
    # descriptor aliases this exact directory without creating files elsewhere.
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        alias = Path(f"/proc/{os.getpid()}/fd/{descriptor}")
        if alias.resolve() != directory.resolve():
            raise RuntimeError("The short Chrome scratch path resolved outside its test folder.")
        yield alias
    finally:
        os.close(descriptor)


@contextmanager
def isolated_chrome(run_dir, url, binary):
    profile = run_dir / "profile"
    temp = run_dir / "tmp"
    temp.mkdir()
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CONDA", "PYTHON", "DYLD_", "VIRTUAL_ENV"))
    }
    environment.update(
        PATH="/usr/bin:/bin:/usr/sbin:/sbin",
        TMPDIR=str(temp),
        TMP=str(temp),
        TEMP=str(temp),
    )
    switches = [
        "--headless=new",
        "--window-size=1440,1000",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--disable-extensions",
        "--no-proxy-server",
        "--metrics-recording-only",
        "--disable-domain-reliability",
        "--disable-search-engine-choice-screen",
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
        "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ]
    with socket_temp_path(temp) as socket_temp, (run_dir / "chrome.log").open("wb") as log:
        environment.update(TMPDIR=str(socket_temp), TMP=str(socket_temp), TEMP=str(socket_temp))
        process = subprocess.Popen(
            [str(binary), *switches, "about:blank"],
            cwd=run_dir,
            env=environment,
            stdout=log,
            stderr=log,
        )
        try:
            port_file = profile / "DevToolsActivePort"
            end = monotonic() + 20
            while (
                not port_file.exists() and process.poll() is None and monotonic() < end
            ):
                sleep(0.08)
            if not port_file.exists():
                detail = (run_dir / "chrome.log").read_text(errors="replace")[-4000:]
                raise RuntimeError("Chrome testing profile did not start.\n" + detail)
            port = int(port_file.read_text().splitlines()[0])
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as stream:
                tabs = json.load(stream)
            tab = next(t for t in tabs if t["type"] == "page")
            ws = websocket.create_connection(
                tab["webSocketDebuggerUrl"], timeout=30, suppress_origin=True
            )
            try:
                browser = Chrome(ws)
                for command in ("Page.enable", "Runtime.enable", "Network.enable"):
                    browser.call(command)
                browser.call("Page.navigate", url=url)
                yield browser
            finally:
                ws.close()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def collect_folder(browser, folder, target):
    files = browser.js(f"""(async () => {{
      const d=await window.qaOutput.getDirectoryHandle({json.dumps(folder)});
      const out={{}};
      for await (const [name,handle] of d.entries()) {{
        const file=await handle.getFile();
        const buf=new Uint8Array(await file.arrayBuffer());
        let binary="";
        for(let k=0;k<buf.length;k+=8192) binary+=String.fromCharCode(...buf.subarray(k,k+8192));
        out[name]=btoa(binary);
      }}
      return out;
    }})()""")
    target.mkdir()
    for name, data in files.items():
        assert Path(name).name == name
        (target / name).write_bytes(base64.b64decode(data))
    return set(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, default=CHROME)
    args = parser.parse_args()
    fixtures = QA / "fixtures"
    assert (fixtures / "SyntheticFullCase_reference.csv").is_file(), (
        "Run check_core.py first."
    )
    run_dir = Path(tempfile.mkdtemp(prefix="chrome_run_", dir=QA))
    tests = []

    def checked(name):
        tests.append(name)
        print("PASS:", name, flush=True)

    with ThreadingHTTPServer(("127.0.0.1", 0), TestHost) as host:
        thread = Thread(target=host.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{host.server_port}/"
        try:
            with isolated_chrome(run_dir, url, args.chrome) as b:
                agent = b.js("navigator.userAgent")
                b.wait(
                    "!!document.querySelector('#start') && document.readyState === 'complete'"
                )
                assert b.js(
                    "document.querySelector('.welcome-edition').textContent === 'for the web*'"
                )
                assert b.js(
                    "document.querySelector('#export-browser-note').textContent.includes('Chrome or Edge')"
                )
                b.screenshot(run_dir / "start.png")
                assert [
                    route for _, route, status in TestHost.requests if status == 200
                ] == ["/"]
                b.click("#start")
                b.wait(
                    "!document.querySelector('#workspace').hidden",
                    "browser workspace",
                    55,
                )
                b.wait("!!snap && !busy && config.version === '1.6.0'")
                assert b.js(
                    "isSecureContext && typeof window.showDirectoryPicker === 'function'"
                )
                assert b.js("""(async () => {
                  let block=false;
                  document.addEventListener("securitypolicyviolation",(e)=>{if(e.violatedDirective==="connect-src") block=true},{once:true});
                  const result=await fetch("/privacy-probe",{method:"POST",body:"synthetic-sentinel"}).then(()=>false,()=>true);
                  await new Promise(r=>setTimeout(r,30));
                  return result && block;
                })()""")
                assert [
                    route for _, route, status in TestHost.requests if status == 200
                ] == ["/", "/runtime.bin"]
                assert all(method == "GET" for method, _, _ in TestHost.requests)
                assert b.js("""(async () => {
                  const keys=await (await caches.open("pelvic-xray-software")).keys();
                  return keys.length===1 && keys[0].url===location.origin+"/runtime.bin?sha256="+APP_CONFIG.payloadHash;
                })()""")
                b.call("Page.reload")
                b.wait(
                    "!document.querySelector('#welcome').hidden && document.readyState === 'complete'",
                    "start page on a return visit",
                )
                host.shutdown()
                b.call(
                    "Network.emulateNetworkConditions",
                    offline=True,
                    latency=0,
                    downloadThroughput=0,
                    uploadThroughput=0,
                )
                b.click("#start")
                b.wait(
                    "!document.querySelector('#workspace').hidden && !!snap && !busy",
                    "cached offline Start",
                    55,
                )
                assert [
                    route for _, route, status in TestHost.requests if status == 200
                ] == ["/", "/runtime.bin", "/"]
                checked(
                    "The first Start downloads one software package. The reloaded page starts from the verified cache after the server disconnects."
                )
                checked(
                    "The network policy blocked a same-origin POST before synthetic files were selected."
                )

                assert b.js("""(async () => {
                  const previous = outputHandle;
                  let sceneTime = 1, csvTime = 2;
                  outputHandle = {
                    getDirectoryHandle: async () => { throw new DOMException('Missing', 'NotFoundError'); },
                    async *entries() {
                      for (const [ext, time] of [['mrb', sceneTime], ['csv', csvTime]]) {
                        const name = 'Case_web_20261117000000.' + ext;
                        yield [name, {kind:'file', getFile: async () => new File(['synthetic'],name,{lastModified:time})}];
                      }
                    }
                  };
                  try {
                    const entry = {stem:'Case',legacyStem:'Case'};
                    const newerCSV = await findSaved(entry);
                    if (newerCSV.scene || !newerCSV.csv) return false;
                    sceneTime = 3;
                    const newerScene = await findSaved(entry);
                    return !!newerScene.scene && !!newerScene.csv;
                  } finally { outputHandle = previous; }
                })()""")
                checked(
                    "Resume prefers a replaced CSV over an older MRB in the same export group, and a newer MRB over an older CSV."
                )

                files = fixtures / "input"
                b.files(
                    "#file-input",
                    [files / "01-synthetic.png", files / "02-synthetic.dcm"],
                )
                b.wait("snap.loaded && caseIndex===0 && !busy", "local PNG")
                assert b.js(
                    "document.querySelector('.unit-tag').textContent === 'su = scene units'"
                )
                assert b.js(
                    "!document.querySelector('#open-files').disabled && !document.querySelector('#import-csv').disabled"
                )
                assert b.js("snap.image.dimensions.join('x')==='1000x900'")
                assert b.js("document.querySelector('#tool-lce').disabled")
                b.click("#rotate")
                b.wait(
                    "snap.image.turns===1 && snap.image.dimensions[0]===900 && !busy"
                )
                for _ in range(3):
                    b.click("#rotate")
                    b.wait("!busy")
                b.click("#mirror")
                b.wait("snap.image.mirrored && !busy")
                b.click("#mirror")
                b.wait("!snap.image.mirrored && !busy")
                zoom = b.js("viewer.zoom")
                b.click("#zoom-in")
                assert b.js("viewer.zoom") > zoom
                b.click("#fit")
                assert abs(b.js("viewer.zoom") - zoom) < 0.00001
                checked(
                    "Local PNG selection, rotate, mirror, fit, zoom and disabled prerequisites."
                )

                b.click("#tool-reference")
                b.wait("snap.active_role==='referenceLine' && !busy")
                b.point(280, 335)
                b.js(
                    "window.qaCanvasBefore = viewer.ctx.getImageData(0,0,viewer.canvas.width,viewer.canvas.height).data"
                )
                b.mouse_at("mouseMoved", 427, 369, button="none")
                assert b.js("""viewer.ctx.getImageData(0,0,viewer.canvas.width,viewer.canvas.height).data
                  .some((value,index)=> value !== window.qaCanvasBefore[index])""")
                active_reference = "snap.active_role==='referenceLine' && snap.markups.find(m=>m.role==='referenceLine').points.length===1"
                assert b.js(active_reference)
                checked(
                    "A provisional line appears at the pointer while the saved reference still has one point."
                )

                assert b.js(
                    "document.querySelector('#open-files').textContent==='Open a file...'"
                )
                assert b.js(
                    "document.querySelector('#import-csv').textContent==='Open a CSV...'"
                )
                before_window = b.js("request('serialize').then(r=>r.saved)")
                before_canvas = b.js("viewer.canvas.toDataURL()")
                b.mouse_at("mousePressed", 450, 400, modifiers=8)
                b.mouse_at("mouseMoved", 450, 300, modifiers=8)
                b.wait(
                    "!!viewer.windowPreview && !!viewer.gesture?.window",
                    "live Shift-drag window preview",
                )
                assert b.js("viewer.canvas.toDataURL()") != before_canvas
                assert b.js("request('serialize').then(r=>r.saved)") == before_window
                assert b.js(active_reference)
                assert b.js(
                    "+document.querySelector('#window-low').value < snap.image.low"
                )
                b.finish()
                b.mouse_at("mouseReleased", 450, 300, modifiers=8)
                b.wait("!viewer.windowPreviewInFlight && !viewer.gesture")
                assert b.js("viewer.windowPreview === null")
                assert b.js("request('serialize').then(r=>r.saved)") == before_window
                initial = b.js("[snap.image.low,snap.image.high]")
                b.mouse_at("mousePressed", 450, 400, modifiers=8)
                b.mouse_at("mouseMoved", 450, 460, modifiers=8)
                # Release Shift first: the gesture remains windowing until release.
                b.mouse_at("mouseReleased", 450, 480)
                b.wait(
                    "!busy && !viewer.windowPreviewInFlight && !viewer.windowPreview"
                )
                final = b.js("[snap.image.low,snap.image.high]")
                assert final[0] > initial[0]
                assert abs((final[1] - final[0]) - (initial[1] - initial[0])) < 1e-7
                assert b.js(active_reference)
                b.js(
                    f"command('window',{{low:{initial[0]},high:{initial[1]},invert:false}})"
                )
                checked(
                    "Shift-drag previews both window limits live, preserves placement and width, cancels on Escape and commits the release position."
                )

                for method in ("space", "control", "middle", "toggle"):
                    before = b.js("viewer.x")
                    modifiers = 2 if method == "control" else 0
                    button = "middle" if method == "middle" else "left"
                    if method == "space":
                        b.call(
                            "Input.dispatchKeyEvent",
                            type="keyDown",
                            key=" ",
                            code="Space",
                        )
                        assert b.js("viewer.space")
                    if method == "toggle":
                        b.click("#pan-button")
                        assert b.js(
                            "document.querySelector('#pan-button').getAttribute('aria-pressed')==='true'"
                        )
                    b.mouse_at(
                        "mousePressed", 435, 442, button=button, modifiers=modifiers
                    )
                    assert b.js("viewer.gesture?.pan"), method
                    b.mouse_at(
                        "mouseMoved", 466, 460, button=button, modifiers=modifiers
                    )
                    b.mouse_at(
                        "mouseReleased", 466, 460, button=button, modifiers=modifiers
                    )
                    if method == "space":
                        b.call(
                            "Input.dispatchKeyEvent",
                            type="keyUp",
                            key=" ",
                            code="Space",
                        )
                    if method == "control":
                        # Check a contextmenu delivered after the modified drag
                        # ends, when the modifier may already have been released.
                        b.js(
                            "viewer.canvas.dispatchEvent(new MouseEvent('contextmenu',{button:2,bubbles:true}))"
                        )
                    if method == "toggle":
                        b.finish()
                        assert not b.js("viewer.panMode")
                    assert b.js("viewer.x") > before + 5, method
                    assert b.js(active_reference), method
                b.click("#fit")
                b.point(547, 335)
                b.wait("!snap.active_role && !busy")
                assert b.js(
                    "document.querySelector('#pelvic-result-reference').textContent === '267.0 su'"
                )
                checked(
                    "Space, Ctrl, middle button and the Pan toggle preserve the active reference and its first endpoint."
                )

                b.click("#tool-calibration")
                b.wait("snap.active_role==='calibrationPoints' && !busy")
                b.point(150, 150)
                assert b.js(
                    "snap.markups.find(m=>m.role==='calibrationPoints').points.length===1 && !snap.markups.some(m=>m.role==='calibrationCircle')"
                )
                b.point(190, 110)
                b.point(230, 150)
                b.wait("snap.markups.some(m=>m.role==='calibrationCircle')")
                assert b.js(
                    "document.querySelector('#pelvic-result-reference').textContent === '267.0 su (83.4 mm)'"
                )
                checked(
                    "Reference length gains a calibrated millimetre value when the calibration circle is fitted."
                )
                b.annotate("femur_head", [(570, 300), (625, 245), (680, 300)])
                assert b.js(
                    "document.querySelector('#pelvic-result-left-head').textContent==='34.4 mm'"
                )
                original_scene = b.js("request('serialize').then(r=>r.saved)")
                original_circle = b.js(
                    "snap.markups.find(m=>m.role==='left_femurHeadCircle').points"
                )
                assert b.js(
                    "request('preview_move',{role:'left_femurHeadPoints',index:1,x:625,y:220}).then(r=>r.edited)"
                )
                b.mouse_at("mousePressed", 625, 245)
                gesture = b.js("viewer.gesture")
                assert gesture and gesture["target"] == {
                    "role": "left_femurHeadPoints",
                    "index": 1,
                }, gesture
                b.mouse_at("mouseMoved", 625, 220)
                assert b.js("viewer.gesture?.moved"), b.js(
                    "({gesture:viewer.gesture,current:viewer.current})"
                )
                b.wait(
                    "viewer.pointPreview?.state.pelvic_result_left_head !== undefined && "
                    "document.querySelector('#pelvic-result-left-head').textContent !== '34.4 mm' && !!viewer.gesture",
                    "head diameter update while still held",
                )
                assert (
                    b.js(
                        "viewer.pointPreview.markups.find(m=>m.role==='left_femurHeadCircle').points"
                    )
                    != original_circle
                )
                assert b.js("request('serialize').then(r=>r.saved)") == original_scene
                b.finish()
                b.mouse_at("mouseReleased", 625, 220)
                assert b.js(
                    "viewer.pointPreview === null && document.querySelector('#pelvic-result-left-head').textContent==='34.4 mm'"
                )
                assert b.js("request('serialize').then(r=>r.saved)") == original_scene
                b.mouse_at("mousePressed", 625, 245)
                b.mouse_at("mouseMoved", 625, 226)
                b.mouse_at("mouseMoved", 625, 220)
                b.mouse_at("mouseReleased", 625, 210)
                b.wait(
                    "!busy && !viewer.previewInFlight && !viewer.pointPreview",
                    "final drag result",
                )
                assert (
                    abs(
                        b.js(
                            "snap.markups.find(m=>m.role==='left_femurHeadPoints').points[1][1]"
                        )
                        - 210
                    )
                    < 1
                )
                b.mouse_at("mousePressed", 625, 210)
                b.mouse_at("mouseMoved", 625, 239)
                b.mouse_at("mouseReleased", 625, 245)
                b.wait("!busy && !viewer.previewInFlight")
                assert b.js(
                    "document.querySelector('#pelvic-result-left-head').textContent==='34.4 mm'"
                )
                checked(
                    "Fitted circle and displayed diameter update during mouse-down. Escape discards preview and a quick release commits the final point."
                )
                b.click("#hide-femur_head")
                b.wait(
                    "!busy && !snap.markups.some(m=>m.role==='left_femurHeadCircle')"
                )
                b.click("#hide-femur_head")
                b.wait("!busy && snap.markups.some(m=>m.role==='left_femurHeadCircle')")
                b.annotate(
                    "shaft_axis", [(615, 475), (685, 475), (617, 690), (682, 690)]
                )
                assert b.js("snap.markups.some(m=>m.role==='left_shaftAxis')")
                b.annotate("morphology", [(613, 420), (617, 440)])
                assert b.js(
                    "snap.markups.find(m=>m.role==='left_shaftMorphologyPoints').points.length===10"
                )
                assert b.js(
                    "document.querySelector('#pelvic-result-left-ccr').dataset.defined==='true'"
                )
                b.annotate("lce", [(700, 225)])
                assert b.js("snap.markups.some(m=>m.role==='left_lceAngleRadialArm')")
                b.click("#tool-lce")
                b.wait("snap.active_role==='left_lceAnglePoint' && !busy")
                assert not b.js(
                    "snap.markups.some(m=>m.role==='left_lceAngleRadialArm')"
                )
                b.point(695, 230)
                checked(
                    "Live points and fitted circles, Hide, two-guide axis, ten shaft morphology points and LCE redraw."
                )

                b.click("#tool-shaft_contour")
                for i in range(4):
                    b.wait(
                        f"snap.active_role==='left_femoralShaftContour{i + 1}' && !busy"
                    )
                    b.point(590 + i * 15, 561)
                    b.point(590 + i * 15, 670)
                    if i == 0:
                        b.mouse_at("mousePressed", 590, 670, button="right")
                        b.mouse_at("mouseReleased", 590, 670, button="right")
                        b.wait(
                            "snap.active_role==='left_femoralShaftContour2' && !busy",
                            "plain right-click to advance",
                        )
                    else:
                        b.finish()
                b.wait("!snap.active_role && !busy")
                b.click("#pelvic_other_angle_parallel")
                b.wait("!busy")
                b.annotate("other_angle", [(490, 450), (540, 455), (540, 510)])
                assert b.js("snap.state.pelvic_custom_results[0].defined")
                checked(
                    "Four sequential shaft contours and a reference-locked custom angle."
                )

                b.click("#auto-place")
                b.wait("document.querySelector('#auto-dialog').open && !busy")
                b.js(
                    "document.querySelectorAll('#auto-features input').forEach(x=>x.checked=x.value==='neck_axis')"
                )
                b.click("#apply-suggestions")
                b.wait(
                    "!busy && snap.markups.some(m=>m.role==='left_neckAxis')",
                    "native neck suggestion",
                )
                b.click("#side-right")
                b.wait("!busy && snap.state.pelvic_active_side==='right'")
                b.annotate("reference", [(443, 322), (826, 322)])
                b.annotate("implant_head", [(300, 260), (355, 205), (410, 260)])
                b.click("#auto-place")
                b.wait("document.querySelector('#auto-dialog').open && !busy")
                b.js(
                    "document.querySelectorAll('#auto-features input').forEach(x=>x.checked=x.value==='implant_neck_axis')"
                )
                b.click("#apply-suggestions")
                b.wait(
                    "!busy && snap.markups.some(m=>m.role==='right_implantNeckAxis')",
                    "implant neck axis",
                )
                assert b.js(
                    "snap.state.pelvic_implant_neck_use_single_guide && snap.state.pelvic_implant_neck_lock_to_center"
                )
                b.screenshot(run_dir / "workspace.png")
                checked(
                    "Pre-operative and post-operative Smart Point Placement derive editable neck axes locally."
                )

                b.click('[data-export="all"]:not([data-advance])')
                b.wait("!document.querySelector('#annotator-error').hidden && !busy")
                b.js(
                    """document.querySelector('#annotator').value='Synthetic test';
                  document.querySelector('#comments').value='Round trip, α\nsecond line';
                  (async () => {
                    const root=await navigator.storage.getDirectory();
                    window.qaOutput=await root.getDirectoryHandle('local-results',{create:true});
                    window.showDirectoryPicker=async ()=>window.qaOutput;
                  })()
                """.replace(
                        "'Round trip, α\nsecond line'",
                        json.dumps("Round trip, α\nsecond line"),
                    )
                )
                b.click("#browse-output")
                b.wait("!!outputHandle && !busy")
                b.annotate("other_point", [(990, 887)])
                mark = b.js("snap.markups.find(m=>m.role==='otherPoint_1')")
                sample = (991, 891)
                original_pixel = b.js(f"""(() => {{
                  const c=document.createElement('canvas');
                  c.width=c.height=1;
                  const ctx=c.getContext('2d');
                  ctx.drawImage(viewer.bitmap,{sample[0]},{sample[1]},1,1,0,0,1,1);
                  return Array.from(ctx.getImageData(0,0,1,1).data.slice(0,3));
                }})()""")
                b.click('[data-export="all"]:not([data-advance])')
                b.wait(
                    "!busy && document.querySelector('#instruction').textContent.startsWith('Saved to')",
                    "local export",
                )
                first = collect_folder(b, "01-synthetic", run_dir / "first_export")
                assert len(first) == 3 and {Path(x).suffix for x in first} == {
                    ".mrb",
                    ".csv",
                    ".png",
                }
                with Image.open(next((run_dir / "first_export").glob("*.png"))) as png:
                    assert png.size == (1000, 900)
                    ix, iy = map(round, mark["points"][0])
                    assert list(png.getpixel((ix, iy))[:3]) == mark["color"]
                    composite = png.getpixel(sample)[:3]
                    expected = [
                        round(src * 0.6 + fill * 0.4)
                        for src, fill in zip(original_pixel, [8, 12, 16], strict=True)
                    ]
                    assert all(
                        abs(a - b) <= 2
                        for a, b in zip(composite, expected, strict=True)
                    ), (composite, expected)
                checked(
                    "PNG summary keeps the radiograph visible and preserves the colour of an annotation inside the panel."
                )
                scene = next((run_dir / "first_export").glob("*.mrb"))
                with ZipFile(scene) as archive:
                    assert archive.testzip() is None
                assert (
                    read_mrb(scene.read_bytes())[1]["settings"]["comments"]
                    == "Round trip, α\nsecond line"
                )
                b.click('[data-export="all"]:not([data-advance])')
                b.wait("document.querySelector('#decision-dialog').open")
                b.click("#decision-actions button:last-child")
                b.wait(
                    "!busy && document.querySelector('#instruction').textContent.startsWith('Saved to')"
                )
                second = collect_folder(b, "01-synthetic", run_dir / "versioned_export")
                assert len(second) == 6 and first < second
                b.click("#close-scene")
                b.wait("!snap.loaded && !busy")
                b.click("#case-next")
                b.wait("!busy && snap.loaded && caseIndex===0")
                assert (
                    b.js("document.querySelector('#comments').value")
                    == "Round trip, α\nsecond line"
                )
                assert b.js("snap.markups.some(m=>m.role==='right_implantNeckAxis')")
                checked(
                    "Annotator validation, local MRB/CSV/PNG, versioning and automatic offline resume."
                )

                b.click("#case-next")
                b.wait(
                    "!busy && caseIndex===1 && snap.image.format==='DICOM'",
                    "uncompressed DICOM",
                )
                assert b.js(
                    "snap.image.invert && snap.image.spacing.join(',')==='0.5,0.7'"
                )
                for name in (
                    "test-rle.dcm",
                    "test-lossless.dcm",
                    "test-j2k.dcm",
                    "test-jls.dcm",
                ):
                    b.files("#file-input", [fixtures / name])
                    b.wait(
                        f"!busy && document.querySelector('#case-name').textContent==={json.dumps(name)}",
                        name,
                    )
                    assert b.js(
                        "snap.image.format==='DICOM' && snap.image.dimensions.join('x')==='1000x900'"
                    )
                checked(
                    "Single-frame 16-bit DICOM decoded in Chrome in native, RLE, lossless JPEG, JPEG 2000 and JPEG-LS encodings."
                )

                for name, format in (
                    ("test.nrrd", "NRRD"),
                    ("test.nhdr", "NRRD"),
                    ("test.mha", "MetaImage"),
                    ("test.mhd", "MetaImage"),
                    ("test.nii.gz", "NIfTI"),
                ):
                    paths = [fixtures / name]
                    if name.endswith((".nhdr", ".mhd")):
                        paths.append(fixtures / "pixels.raw")
                    b.files("#file-input", paths)
                    b.wait(
                        f"!busy && document.querySelector('#case-name').textContent==={json.dumps(name)}",
                        name,
                    )
                    assert b.js(
                        f"snap.image.format==={json.dumps(format)} && snap.image.dimensions.join('x')==='1000x900'"
                    )
                checked(
                    "Single-slice NRRD, NIfTI and MetaImage decode in Chrome, including detached headers."
                )

                b.files("#file-input", [fixtures / "SyntheticFullCase.mrb"])
                b.wait(
                    "!busy && document.querySelector('#case-name').textContent==='SyntheticFullCase.mrb'",
                    "legacy scene",
                )
                b.click('[data-export="csv"]')
                b.wait(
                    "!busy && document.querySelector('#instruction').textContent.startsWith('Saved to')"
                )
                collect_folder(b, "SyntheticFullCase", run_dir / "browser_replay")
                csv_file = next((run_dir / "browser_replay").glob("*.csv"))
                parity = compare(
                    measurements(
                        (fixtures / "SyntheticFullCase_reference.csv").read_text(
                            "utf-8-sig"
                        )
                    ),
                    measurements(csv_file.read_text("utf-8-sig")),
                )
                checked(
                    "Actual Chrome export reproduces the complete reference measurement table."
                )
                point = b.js("snap.markups.find(m=>m.role==='referenceLine').points[0]")
                b.mouse_at("mousePressed", *point)
                assert b.js("viewer.gesture?.target?.role === 'referenceLine'")
                b.mouse_at("mouseMoved", point[0], point[1] + 45)
                b.wait(
                    "!!viewer.pointPreview && !!viewer.gesture && "
                    "document.querySelector('#pelvic-result-left-lce').textContent !== snap.state.pelvic_result_left_lce",
                    "dependent LCE update in the complete scene",
                )
                b.finish()
                b.mouse_at("mouseReleased", point[0], point[1] + 45)
                assert b.js(
                    "document.querySelector('#pelvic-result-left-lce').textContent === snap.state.pelvic_result_left_lce"
                )
                checked(
                    "Dragging the reference line in the full replay updates a dependent angle before release."
                )
                network = [
                    item
                    for item in b.events
                    if item["method"] == "Network.responseReceived"
                    and item["params"]["response"]["url"].startswith(
                        ("http://", "https://")
                    )
                ]
                assert {x["params"]["response"]["url"] for x in network} == {
                    url,
                    url + "runtime.bin",
                }
                evidence = {
                    "status": "passed",
                    "patient_data": False,
                    "chrome": agent,
                    "tests": tests,
                    "http_requests_received": TestHost.requests,
                    "http_responses_in_browser": len(network),
                    "network_disconnected_before_image_selection": True,
                    "blocked_same_origin_post": True,
                    "runtime_gets": 1,
                    "warm_start_from_cache_offline": True,
                    "chrome_process_environment": "OS-only PATH and no inherited Conda, Python or dynamic loader overrides",
                    "chrome_replay": parity,
                    "output_test_mode": "Chrome FileSystemDirectoryHandle (origin-private test folder)",
                    "run": run_dir.name,
                }
                (QA / "chrome_checks.json").write_text(
                    json.dumps(evidence, indent=2) + "\n"
                )
                print(json.dumps(evidence, indent=2))
        finally:
            if thread.is_alive():
                host.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
