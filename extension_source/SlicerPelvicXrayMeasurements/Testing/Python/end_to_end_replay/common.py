"""Shared paths and small utilities for the Pelvic X-ray Measurements automation bundle.

The bundle is intentionally isolated from the extension itself. These helpers keep path discovery,
CSV loading, and Slicer executable lookup in one place so every script behaves consistently.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import os
import platform
import shutil
from datetime import datetime
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parent
AUTOMATED_TESTS_DIR = BUNDLE_DIR.parent
REPO_ROOT = AUTOMATED_TESTS_DIR.parent

DEFAULT_CASE_NAME = "SyntheticFullCase.dcm"
EXPECTED_CSV_FILENAME = "dummy_expected_full_export.csv"


def bundle_path(*parts: str) -> Path:
    """Return an absolute path inside the automation bundle directory."""

    return BUNDLE_DIR.joinpath(*parts)


def discover_extension_dir() -> Path:
    """Return the extension root from either a source checkout or packaged extension."""

    for candidate in [BUNDLE_DIR] + list(BUNDLE_DIR.parents):
        if (candidate / "PelvicXrayMeasurements").is_dir() and (candidate / "documentation.md").is_file():
            return candidate
        if (candidate / 'PelvicXrayMeasurements.py').is_file() and (candidate / 'PelvicXrayMeasurementsLib').is_dir():
            return candidate

    for candidate in [BUNDLE_DIR] + list(BUNDLE_DIR.parents):
        sibling = candidate / "SlicerPelvicXrayMeasurements"
        if (sibling / "PelvicXrayMeasurements").is_dir() and (sibling / "documentation.md").is_file():
            return sibling

    raise RuntimeError(f"Could not locate the SlicerPelvicXrayMeasurements extension root from {BUNDLE_DIR}")


EXTENSION_DIR = discover_extension_dir()
MODULE_DIR = EXTENSION_DIR / "PelvicXrayMeasurements" if (EXTENSION_DIR / 'PelvicXrayMeasurements').is_dir() else EXTENSION_DIR
LIB_DIR = MODULE_DIR / "PelvicXrayMeasurementsLib"
PROJECT_ROOT = EXTENSION_DIR.parents[1] if EXTENSION_DIR.parent.name == "extension_source" else EXTENSION_DIR
TEST_RUNS_DIR = (
    PROJECT_ROOT / "outputs" / "test_runs"
    if PROJECT_ROOT != EXTENSION_DIR
    else AUTOMATED_TESTS_DIR / "test_runs"
)


def expected_csv_path() -> Path:
    """Return the canonical path of the golden dummy CSV shipped with the bundle."""

    return bundle_path(EXPECTED_CSV_FILENAME)


def display_path(path: Path, preferred_base: Path | None = None) -> str:
    """Return a publish-safe display path without leaking workstation-specific roots.

    Reports and logs should stay readable and reproducible, but they should not embed machine-local
    absolute paths. When possible this helper shows a path relative to a useful project root;
    otherwise it falls back to the leaf name.
    """

    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate

    base_candidates = []
    if preferred_base is not None:
        base_candidates.append(Path(preferred_base).expanduser())
    base_candidates.extend([Path.cwd(), EXTENSION_DIR, REPO_ROOT, AUTOMATED_TESTS_DIR, BUNDLE_DIR])

    seen = set()
    for base in base_candidates:
        try:
            base_resolved = base.resolve()
        except OSError:
            continue
        base_key = str(base_resolved)
        if base_key in seen:
            continue
        seen.add(base_key)
        try:
            return str(resolved.relative_to(base_resolved))
        except ValueError:
            continue

    if not candidate.is_absolute():
        return str(candidate)
    return candidate.name


def mac_slicer_candidates() -> list[Path]:
    """Return common macOS Slicer locations without hardcoding one full path literal."""

    app_bundle = Path(os.sep) / "Applications" / "Slicer.app"
    return [
        app_bundle,
        app_bundle / "Contents" / "bin" / "PythonSlicer",
        app_bundle / "Contents" / "MacOS" / "Slicer",
    ]


def detect_slicer_executable() -> Path | None:
    """Return a likely Slicer launcher path when one can be found locally."""

    candidates = []
    for env_name in ["SLICER_EXECUTABLE", "SLICER_HOME"]:
        env_value = os.environ.get(env_name)
        if env_value:
            candidates.append(env_value)

    candidates.extend(
        [
            shutil.which("PythonSlicer"),
            shutil.which("PythonSlicer.exe"),
            shutil.which("Slicer"),
            shutil.which("Slicer.exe"),
            shutil.which("SlicerApp-real"),
            shutil.which("3DSlicer"),
        ]
    )
    candidates.extend(mac_slicer_candidates())

    windows_roots = [
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramW6432"),
        os.environ.get("ProgramFiles(x86)"),
    ]
    for root in windows_roots:
        if not root:
            continue
        candidates.extend(
            sorted(glob.glob(os.path.join(root, "NA-MIC", "Slicer *")))
            + sorted(glob.glob(os.path.join(root, "Slicer *")))
        )

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.exists():
            continue
        try:
            resolved = normalize_slicer_input_path(path)
        except ValueError:
            continue
        if resolved.exists():
            return resolved
    return None


def normalize_slicer_input_path(slicer_path: Path) -> Path:
    """Normalize a user-supplied Slicer path into a concrete executable-style path.

    Accepted inputs include a main Slicer executable, `PythonSlicer`, a macOS `.app` bundle, or a
    Windows install directory containing either `Slicer.exe` or `bin/PythonSlicer.exe`.
    """

    slicer_path = slicer_path.expanduser()
    if slicer_path.suffix.lower() == ".app" and slicer_path.is_dir():
        return slicer_path / "Contents" / "MacOS" / "Slicer"

    if slicer_path.is_dir():
        directory_candidates = [
            slicer_path / "Slicer.exe",
            slicer_path / "Slicer",
            slicer_path / "bin" / "PythonSlicer.exe",
            slicer_path / "bin" / "PythonSlicer",
            slicer_path / "Contents" / "bin" / "PythonSlicer",
            slicer_path / "Contents" / "MacOS" / "Slicer",
        ]
        for candidate in directory_candidates:
            if candidate.exists():
                return candidate

    return slicer_path


def resolve_slicer_runtime(slicer_path: Path) -> tuple[Path, Path]:
    """Resolve the launcher used to dump Slicer's environment and the Python runtime to execute.

    The test bundle intentionally uses Slicer's own Python runtime in a headless way. That keeps the
    extension logic inside a real Slicer environment while avoiding GUI-launch problems.
    """

    slicer_path = normalize_slicer_input_path(slicer_path).expanduser().resolve()
    lower_name = slicer_path.name.lower()

    if lower_name.startswith("pythonslicer"):
        launcher = slicer_path
        python_name = "python-real.exe" if platform.system() == "Windows" else "python-real"
        python_real = slicer_path.parent / python_name
        if not python_real.exists():
            raise ValueError(f"Could not find the bundled Python runtime beside {launcher}")
        return launcher, python_real

    if slicer_path.name == "Slicer" and slicer_path.parent.name == "MacOS":
        launcher = slicer_path.parent.parent / "bin" / "PythonSlicer"
        python_real = slicer_path.parent.parent / "bin" / "python-real"
        if not launcher.exists() or not python_real.exists():
            raise ValueError(f"Could not find the bundled Python runtime inside {slicer_path.parent.parent}")
        return launcher, python_real

    if slicer_path.name.lower() == "slicer.exe":
        launcher = slicer_path.parent / "bin" / "PythonSlicer.exe"
        python_real = slicer_path.parent / "bin" / "python-real.exe"
        if not launcher.exists() or not python_real.exists():
            raise ValueError(f"Could not find the bundled Python runtime under {slicer_path.parent}")
        return launcher, python_real

    if slicer_path.name == "Slicer":
        # Installed Linux packages keep launchers in the root and Python in bin.
        launcher = slicer_path.parent / "bin" / "PythonSlicer"
        python_real = launcher.parent / "python-real"
        if not launcher.exists() or not python_real.exists():
            raise ValueError(f"Could not find the bundled Python runtime under {slicer_path.parent}")
        return launcher, python_real

    raise ValueError(f"Could not infer Slicer runtime paths from {slicer_path}")


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    """Load a CSV file as a list of dictionaries."""

    with csv_path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def sha256_of_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_timestamped_run_dir(prefix: str, parent_dir: Path | None = None) -> Path:
    """Create and return a new run-output directory using a timestamped name."""

    output_parent = TEST_RUNS_DIR if parent_dir is None else Path(parent_dir).expanduser().resolve()
    output_parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = output_parent / f"{prefix}_{timestamp}"
    counter = 1
    while candidate.exists():
        candidate = output_parent / f"{prefix}_{timestamp}_{counter:02d}"
        counter += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate
