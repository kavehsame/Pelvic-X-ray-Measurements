"""Run the pytest unit-test suite and capture artifacts under test_runs/."""

from __future__ import annotations

import argparse
import importlib.util
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
REPLAY_DIR = THIS_DIR.parent / "end_to_end_replay"

if str(REPLAY_DIR) not in sys.path:
    sys.path.insert(0, str(REPLAY_DIR))

from common import create_timestamped_run_dir, display_path


def write_log_text(logs_dir: Path, filename: str, content: str) -> None:
    """Write one text log into the unit-test run folder."""

    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / filename).write_text(content)


def resolve_pytest_command() -> list[str]:
    """Resolve a working pytest invocation for the current shell environment."""

    if importlib.util.find_spec("pytest") is not None:
        return [sys.executable, "-m", "pytest"]

    pytest_executable = shutil.which("pytest")
    if pytest_executable is not None:
        return [pytest_executable]

    raise SystemExit(
        "Could not find pytest in the current Python environment or on PATH."
    )


def main() -> None:
    """CLI entry point for the pytest unit-test runner."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output folder. When omitted, the runner creates a new timestamped folder under test_runs/.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Optional extra pytest arguments. Prefix them with '--' to pass them through unchanged.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve() if args.output_dir is not None else create_timestamped_run_dir("pytest_unit")
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    junit_xml_path = output_dir / "pytest.junit.xml"

    passthrough_args = list(args.pytest_args)
    if passthrough_args[:1] == ["--"]:
        passthrough_args = passthrough_args[1:]

    command = [
        *resolve_pytest_command(),
        str(THIS_DIR),
        "--junitxml",
        str(junit_xml_path),
        *passthrough_args,
    ]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    write_log_text(logs_dir, "pytest.stdout.txt", completed.stdout)
    write_log_text(logs_dir, "pytest.stderr.txt", completed.stderr)
    write_log_text(logs_dir, "pytest.command.txt", " ".join(shlex.quote(part) for part in command))

    if completed.returncode != 0:
        raise SystemExit(
            "Pytest unit tests failed. "
            f"See {display_path(logs_dir)} and {display_path(junit_xml_path)}."
        )

    print(
        "PASS: pytest unit tests completed.\n"
        f"Output folder: {display_path(output_dir)}\n"
        f"JUnit XML: {display_path(junit_xml_path)}"
    )


if __name__ == "__main__":
    main()
