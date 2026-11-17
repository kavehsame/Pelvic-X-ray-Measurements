"""Download the official hash-pinned Linux Slicer package into the CI checkout."""

import hashlib
import json
import platform
import subprocess
import tarfile
from urllib.request import urlopen

from project import BUILD, ROOT, within


def main():
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise SystemExit("This CI dependency is the Linux amd64 Slicer runtime.")
    spec = json.loads((ROOT / "slicer-ci.json").read_text())
    cache = within(ROOT / ".cache/slicer")
    cache.mkdir(parents=True, exist_ok=True)
    archive = within(cache / "slicer-linux.tar.gz")
    if not archive.exists():
        temporary = within(cache / "download.partial")
        with (
            urlopen(spec["url"], timeout=180) as source,
            temporary.open("wb") as destination,
        ):
            total = 0
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > 2_000_000_000:
                    raise ValueError("Unexpected Slicer download size")
                destination.write(chunk)
        with temporary.open("rb") as stream:
            if hashlib.file_digest(stream, "sha512").hexdigest() != spec["sha512"]:
                raise ValueError("Slicer archive checksum mismatch")
        temporary.rename(archive)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != spec["sha512"]:
            raise ValueError("Cached Slicer archive checksum mismatch")
    target = within(cache / spec["revision"])
    if not target.exists():
        target.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(target, filter="data")
    candidates = list(target.glob("*/Slicer"))
    if len(candidates) != 1:
        raise ValueError("Slicer executable was not uniquely identified")
    python_launcher = candidates[0].parent / "bin/PythonSlicer"
    probe = subprocess.run(
        [str(python_launcher), "--launcher-dump-environment"],
        capture_output=True, text=True, timeout=30,
    )
    if probe.returncode:
        raise RuntimeError(
            "Slicer runtime preflight failed: "
            + (probe.stderr.strip() or probe.stdout.strip()
               or f"exit {probe.returncode}")
        )
    BUILD.mkdir(exist_ok=True)
    (BUILD / "slicer_executable.txt").write_text(str(candidates[0].resolve()) + "\n")
    print("Official Slicer CI runtime verified.")


if __name__ == "__main__":
    main()
