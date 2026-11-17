"""Restore fixed model and browser dependencies; never accept changed content."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

from project import EXTENSION, ROOT, WEB, within


def models(local=None):
    manifest = json.loads((ROOT / "model-assets.json").read_text())
    for name, record in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("Invalid model asset filename")
        destinations = (
            EXTENSION / "PelvicXrayMeasurements/Resources/AutoPlacement" / name,
            WEB / "assets" / name,
        )
        content = None
        for dest in destinations:
            within(dest)
            if dest.exists():
                existing = dest.read_bytes()
                if hashlib.sha256(existing).hexdigest() != record["sha256"]:
                    raise ValueError(
                        f"Existing model differs from its published checksum: {dest.name}"
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
            raise ValueError(f"Model failed its size or checksum check: {name}")
        for dest in destinations:
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as stream:
                    stream.write(content)


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
    args = parser.parse_args()
    models(args.local_models)
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
