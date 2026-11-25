"""Create product downloads and immutable model assets, excluding generated reports."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from project import BUILD, EXTENSION, IMPLANT_FOLDERS, ROOT, WEB, config, implant_files, within


def archive(destination, files):
    destination = within(destination)
    if destination.exists():
        raise FileExistsError(f"An existing release is retained: {destination.name}")
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as bundle:
        for name, content in sorted(files.items()):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("Unsafe archive member")
            info = ZipInfo(name, date_time=(2026, 11, 17, 0, 0, 0))
            info.external_attr = 0o644 << 16
            bundle.writestr(info, content, compress_type=ZIP_DEFLATED)
    with ZipFile(destination) as bundle:
        assert bundle.testzip() is None
        assert not any(
            "test_reports/" in name or "test_runs/" in name
            for name in bundle.namelist()
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="New release directory inside the repository"
    )
    args = parser.parse_args()
    for folder in IMPLANT_FOLDERS:
        implant_files(folder)
    version = config()["version"]
    out = within(args.output or BUILD / "releases" / ("v" + version))
    out.mkdir(parents=True, exist_ok=False)
    exclude = {
        "test_reports",
        "test_runs",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".DS_Store",
    }
    extension_files = {}
    for path in sorted(EXTENSION.rglob("*")):
        rel = path.relative_to(EXTENSION)
        if path.is_file() and not any(part in exclude for part in rel.parts):
            if path.is_symlink() or not path.resolve().is_relative_to(EXTENSION):
                raise ValueError("Unsafe extension source path")
            extension_files["SlicerPelvicXrayMeasurements/" + str(rel)] = (
                path.read_bytes()
            )
    models = json.loads((ROOT / "model-assets.json").read_text())
    for name, record in models["files"].items():
        key = (
            "SlicerPelvicXrayMeasurements/PelvicXrayMeasurements/Resources/AutoPlacement/"
            + name
        )
        assert hashlib.sha256(extension_files[key]).hexdigest() == record["sha256"]
    archive(
        out / f"PelvicXrayMeasurements_{version}_Slicer_extension.zip", extension_files
    )
    web_files = {
        name: (BUILD / "web" / name).read_bytes()
        for name in json.loads((BUILD / "build_manifest.json").read_text())["files"]
    }
    web_files.update(
        {
            name: (ROOT / name).read_bytes()
            for name in ("LICENSE.txt", "NOTICE.md", "CREDITS.md", "THIRD_PARTY.md", "CITATION.cff")
        }
    )
    web_files["README.md"] = (
        b"# Pelvic X-ray Measurements web application\n\nServe index.html and the complete components folder together over HTTPS. Open the\nsite and select Start. The JSON component files must be served as application/json.\nFor local testing, a loopback HTTP server is supported. Opening the HTML directly\nfrom disk is not the supported launch method. Normal website visitors do not need\nto download this ZIP. The app processes selected images on the user's device.\nSome restricted networks, including hospital networks, may prevent startup.\n\nResearch use only. This software is not a medical device. It is not intended for\ndiagnosis, treatment planning or other clinical decision-making.\n\nRead the User Manual inside the app for tools, workflows and third-party licences.\n"
    )
    archive(out / f"PelvicXrayMeasurements_{version}_web.zip", web_files)
    sums = [
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name
        for p in sorted(out.glob("*.zip"))
    ]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    model_out = within(out / "model-release")
    model_out.mkdir()
    for name in models["files"]:
        shutil.copyfile(WEB / "assets" / name, model_out / name)
    for name in ("LICENSE.txt", "NOTICE.md"):
        shutil.copyfile(ROOT / name, model_out / name)
    (model_out / "README.md").write_text(
        "# Smart Point Placement models\n\nModel release: "
        + models["version"]
        + ". Licence: Apache-2.0.\n\nThese aggregate model assets support the Slicer extension and web application.\nInspect every suggested landmark. They do not provide an autonomous anatomical\nassessment. Research use only; not a medical device or intended for clinical\ndecision-making.\n\nKeep this release separate from the main software release and do not replace\nits files. Changed weights require a new model version.\n"
    )
    (model_out / "SHA256SUMS.txt").write_text(
        "\n".join(
            record["sha256"] + "  " + name for name, record in models["files"].items()
        )
        + "\n"
    )
    print(f"Release assets: {out}")


if __name__ == "__main__":
    main()
