"""Build the static, install-free site from source and pinned local assets."""

import ast
import base64
import hashlib
from html import escape
from io import BytesIO
import json
from pathlib import Path
import struct
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from markdown import markdown

SCRIPTS = Path(__file__).resolve().parents[1]
CORE = SCRIPTS / "core"
REFERENCE_ASSETS = SCRIPTS / "assets"
STEP = SCRIPTS.parent
WEB = SCRIPTS / "ui"
RUNTIME = SCRIPTS / "runtime"
OUTPUT = STEP / "build"
OUTPUT.mkdir(exist_ok=True)
DIST = OUTPUT / "web"
ASSETS = REFERENCE_ASSETS
MODEL_FILES = ("auto_point_model.json", "auto_point_image_model.npz")
PYDICOM_WHEEL = "pydicom-3.0.2-py3-none-any.whl"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def write(path, data):
    if not path.resolve().is_relative_to(STEP):
        raise RuntimeError(f"Output path escapes this repository: {path}")
    path.write_bytes(data)


def data_uri(path):
    return (
        f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    )


def archive_core(model_files):
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        sources = {f"core/{p.name}": p.read_bytes() for p in CORE.glob("*.py")}
        sources["core/__init__.py"] = b""
        sources.update(
            {f"core/resources/{name}": content for name, content in model_files.items()}
        )
        for entry, content in sorted(sources.items()):
            info = ZipInfo(entry, date_time=(2026, 11, 17, 0, 0, 0))
            archive.writestr(info, content, compress_type=ZIP_DEFLATED)
    return buf.getvalue()


def pydicom_code(wheel):
    """Keep the decoder and licence. Omit the upstream medical test files."""
    buffer = BytesIO()
    omitted = 0
    with (
        ZipFile(BytesIO(wheel)) as original,
        ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive,
    ):
        for info in original.infolist():
            name = info.filename
            if info.is_dir() or name.endswith(".dist-info/RECORD"):
                continue
            if name.startswith(
                ("pydicom/data/charset_files/", "pydicom/data/test_files/")
            ) or name.lower().endswith(
                (
                    ".dcm",
                    ".dicom",
                    ".ima",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".tif",
                    ".tiff",
                    ".nrrd",
                    ".nii",
                )
            ):
                omitted += 1
                continue
            archive.writestr(info, original.read(info))
    return buffer.getvalue(), omitted


def build_payload(runtime, model_files):
    items = {
        name: content for name, content in runtime.items() if not name.endswith(".txt")
    }
    items["pydicom-code.zip"], omitted = pydicom_code(items.pop(PYDICOM_WHEEL))
    items["worker.js"] = (WEB / "worker.js").read_bytes()
    items["core.zip"] = archive_core(model_files)
    offsets, size = {}, 0
    for name, content in sorted(items.items()):
        offsets[name] = [size, len(content)]
        size += len(content)
    manifest = json.dumps(offsets, separators=(",", ":")).encode()
    return struct.pack("<I", len(manifest)) + manifest + b"".join(
        items[name] for name in offsets
    ), omitted


def read_help():
    constants = {}
    for node in ast.parse((ASSETS / "hover_help.py").read_text()).body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            for name in set(names) & {"HELP", "RESULTS"}:
                constants[name] = ast.literal_eval(node.value)
    help_map = {
        **constants["HELP"],
        **{f"result_{key}": pair for key, pair in constants["RESULTS"].items()},
    }
    help_map["post_shaft_axis"] = help_map["shaft_axis"]
    for key in (
        "tonnis",
        "sharp",
        "lce",
        "acetabular_offset",
        "femoral_offset",
        "extrusion",
    ):
        label, body = help_map[key]
        help_map[key] = (
            label,
            body + " Redraws alternate between shared and manual landmarks.",
        )
    help_map.update(
        {
            "browse_input": (
                "Input Folder",
                "Choose a folder to read radiographs from this device.",
            ),
            "browse_output": (
                "Output Folder",
                "Choose the local folder where the app should write exports and look for saved work.",
            ),
            "fit": ("Fit", "Fit the whole radiograph in the viewer."),
            "pan": (
                "Pan",
                "Drag the image while keeping the current placement. Toggle Pan off to continue placing points, or hold Space and drag for temporary panning.",
            ),
            "rotate": ("Rotate", "Rotate 90° clockwise before placing annotations."),
            "mirror": ("Mirror", "Flip left and right before placing annotations."),
            "view_window": (
                "Window",
                "Adjust grayscale limits or invert the display. Hold Shift and drag up or down over the image to move both limits together.",
            ),
            "auto": (
                "Smart Point Placement",
                "Review and place selected suggestions after fitting the calibration ball, reference line and one head type.",
            ),
            "export_all": ("Export All", "Save an MRB scene, CSV and annotated PNG."),
            "export_csv": (
                "Export CSV",
                "Save measurement values, coordinates and comments.",
            ),
            "export_image": (
                "Export Image",
                "Save the radiograph with visible annotations and optional measurement values.",
            ),
            "export_scene": (
                "Export Scene",
                "Save the radiograph and annotations as a single MRB scene.",
            ),
        }
    )
    return help_map


def licences(runtime):
    notices = [
        ("Pelvic X-ray Measurements licence", (ASSETS / "LICENSE.txt").read_text()),
        ("Project notices", (ASSETS / "NOTICE.md").read_text()),
    ]
    for name, content in sorted(runtime.items()):
        if name.endswith("-LICENSE.txt"):
            notices.append((name, content.decode("utf-8")))
        if name.endswith(".whl"):
            with ZipFile(BytesIO(content)) as archive:
                for item in archive.namelist():
                    if ".dist-info/licenses/" in item and not item.endswith("/"):
                        text = archive.read(item).decode("utf-8", "replace")
                        label = (
                            name.split("-")[0]
                            + " · "
                            + item.split(".dist-info/licenses/")[1]
                        )
                        notices.append((label, text))
    return "<h2>Software licences</h2>" + "".join(
        f"<details><summary>{escape(title)}</summary><pre>{escape(content)}</pre></details>"
        for title, content in notices
    )


def main():
    manifest = json.loads((RUNTIME / "manifest.json").read_text())
    binaries = {name: (RUNTIME / name).read_bytes() for name in manifest}
    for name, contents in binaries.items():
        assert digest(contents) == manifest[name]["sha256"], name
    version = next(
        node.value.value
        for node in ast.parse((CORE / "engine.py").read_text()).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "VERSION"
    )
    models = {name: (ASSETS / name).read_bytes() for name in MODEL_FILES}
    assert json.loads(models[MODEL_FILES[0]])["shaft_image_model_sha256"] == digest(
        models[MODEL_FILES[1]]
    )
    payload, omitted = build_payload(binaries, models)
    app_config = {
        "payload": "runtime.bin",
        "payloadSize": len(payload),
        "payloadHash": digest(payload),
        "help": read_help(),
        "schematic": data_uri(ASSETS / "morphology_parameters_pothong_2023.png"),
    }
    js = "\n".join(
        [
            f"const APP_CONFIG = {json.dumps(app_config).replace('<', chr(92) + 'u003c')};",
            (WEB / "viewer.js").read_text(),
            (WEB / "app.js").read_text(),
        ]
    )
    assert "</script" not in js.lower()
    template = (WEB / "index.html").read_text()
    manual = markdown((STEP / "docs/web-manual.md").read_text(), extensions=("tables",))
    replacements = {
        "VERSION": version,
        "ICON": data_uri(ASSETS / "favicon.png"),
        "ART": data_uri(ASSETS / "application_icon.png"),
        "STYLE": (WEB / "style.css").read_text(),
        "MANUAL": manual,
        "LICENCES": licences(binaries),
        "APPLICATION": js,
        "SCRIPT_HASH": base64.b64encode(hashlib.sha256(js.encode()).digest()).decode(),
    }
    for key, value in replacements.items():
        template = template.replace("@@" + key + "@@", value)
    assert "@@APPLICATION@@" not in template
    if not DIST.resolve().is_relative_to(STEP):
        raise RuntimeError("The distribution folder escapes this repository.")
    DIST.mkdir(exist_ok=True)
    files = {"runtime.bin": payload, "index.html": template.encode()}
    for name, data in files.items():
        write(DIST / name, data)
    report = {
        "version": version,
        "distribution": "build/web",
        "models": {n: digest(b) for n, b in models.items()},
        "pydicom_test_assets_excluded": omitted,
        "files": {
            name: {"bytes": len(data), "sha256": digest(data)}
            for name, data in files.items()
        },
    }
    write(
        OUTPUT / "build_manifest.json", (json.dumps(report, indent=2) + "\n").encode()
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
