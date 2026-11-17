"""Repository paths and checked output locations shared by development commands."""

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
EXTENSION = ROOT / "extension_source/SlicerPelvicXrayMeasurements"
BUILD = ROOT / "build"


def within(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError("Generated files must stay inside the repository.")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config():
    return json.loads((ROOT / "release.json").read_text())


def source_files():
    ignored = {
        ".git",
        ".cache",
        ".venv",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "test_runs",
    }
    models = {"auto_point_model.json", "auto_point_image_model.npz"}
    paths = []
    for folder, directories, names in os.walk(ROOT, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in ignored)
        for name in directories:
            path = Path(folder) / name
            if path.is_symlink():
                raise ValueError(
                    f"Source symlink is not permitted: {path.relative_to(ROOT)}"
                )
        for name in names:
            path = Path(folder) / name
            rel = path.relative_to(ROOT)
            if name in models or name == ".DS_Store":
                continue
            if rel.parts[:2] == ("web", "runtime") and name != "manifest.json":
                continue
            if path.is_symlink():
                raise ValueError(f"Source symlink is not permitted: {rel}")
            if path.is_file():
                paths.append(path)
    yield from sorted(paths)


def source_hashes():
    return {
        str(p.relative_to(ROOT)): sha(p)
        for p in source_files()
        if "test_reports" not in p.parts
    }
