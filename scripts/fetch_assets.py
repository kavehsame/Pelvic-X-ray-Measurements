"""Restore the pinned models, processed implant assets and browser runtime."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

from project import EXTENSION, IMPLANT_FOLDERS, ROOT, WEB, implant_manifest, within


def restore_assets(manifest, folders, local=None):
    for name, record in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("Invalid release asset filename")
        destinations = [within(folder / name) for folder in folders]
        content = None
        for dest in destinations:
            if dest.exists():
                existing = dest.read_bytes()
                if hashlib.sha256(existing).hexdigest() != record["sha256"]:
                    raise ValueError(
                        f"Existing asset differs from its published checksum: {dest.name}"
                    )
                content = existing
        if content is None:
            if local:
                content = (Path(local) / name).read_bytes()
            else:
                with urlopen(
                    Request(record["url"], headers={"User-Agent": "PelvicXray-build"}),
                    timeout=120,
                ) as stream:
                    content = stream.read(record["bytes"] + 1)
        if (
            len(content) != record["bytes"]
            or hashlib.sha256(content).hexdigest() != record["sha256"]
        ):
            raise ValueError(f"Asset failed its size or checksum check: {name}")
        for dest in destinations:
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=dest.parent) as temp:
                    staged = Path(temp) / name
                    staged.write_bytes(content)
                    staged.replace(dest)


def runtime_ready():
    folder = WEB / "runtime"
    manifest = json.loads((folder / "manifest.json").read_text())
    return all(
        (folder / name).is_file()
        and hashlib.sha256((folder / name).read_bytes()).hexdigest() == record["sha256"]
        for name, record in manifest.items()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-models",
        type=Path,
        help="Existing release assets, still checked against fixed hashes",
    )
    parser.add_argument("--models-only", action="store_true")
    parser.add_argument("--local-implants", type=Path, help="Folder containing the two processed release assets")
    args = parser.parse_args()
    restore_assets(json.loads((ROOT / "model-assets.json").read_bytes()),
                   (EXTENSION / "PelvicXrayMeasurements/Resources/AutoPlacement", WEB / "assets"), args.local_models)
    if not args.models_only:
        restore_assets(implant_manifest(), IMPLANT_FOLDERS, args.local_implants)
    if not args.models_only and not runtime_ready():
        for script in ("fetch_runtime.py", "fetch_codecs.py"):
            subprocess.run(
                [sys.executable, "-B", str(WEB / "scripts" / script)],
                cwd=ROOT,
                check=True,
            )
        if not runtime_ready():
            raise RuntimeError("The restored runtime differs from the pinned manifest.")
    print("Pinned assets verified.")


if __name__ == "__main__":
    main()
