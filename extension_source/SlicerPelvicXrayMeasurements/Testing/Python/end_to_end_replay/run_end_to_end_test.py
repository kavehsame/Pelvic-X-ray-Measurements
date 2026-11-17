"""Run the full dummy-CSV replay test against the Pelvic X-ray Measurements extension."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Union

from common import (
    BUNDLE_DIR,
    EXTENSION_DIR,
    create_timestamped_run_dir,
    detect_slicer_executable,
    display_path,
    expected_csv_path,
    resolve_slicer_runtime,
    sha256_of_file,
)

ConfigValue = Union[str, int, float, bool, None, Path]
RunConfig = Mapping[str, ConfigValue]


def write_log_text(logs_dir: Path, filename: str, content: str) -> None:
    """Write one text log into the run's dedicated logs directory.

    Keeping transient stdout, stderr, and config artifacts under `logs/` makes test runs easier to
    inspect without mixing debug files into the top level of each output folder.
    """

    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / filename).write_text(content)


def serialize_config_for_log(config: RunConfig, base_dir: Path) -> dict[str, str | int | float | bool | None]:
    """Convert config values into JSON-friendly relative paths for publish-safe run artifacts.

    The Slicer-side scripts resolve these paths back to absolute locations at runtime, so the test
    behavior stays unchanged while the checked-in log artifacts avoid workstation-specific roots.
    """

    serialized: dict[str, str | int | float | bool | None] = {}
    for key, value in config.items():
        if isinstance(value, Path):
            serialized[key] = os.path.relpath(str(value.resolve()), str(base_dir))
        else:
            serialized[key] = value
    return serialized


def run_slicer_script(
    slicer_executable: Path, script_path: Path, config: RunConfig, logs_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run one headless Slicer automation script inside Slicer's bundled Python runtime."""

    logs_dir.mkdir(parents=True, exist_ok=True)
    config_path = logs_dir / f"{script_path.stem}.config.json"
    config_path.write_text(json.dumps(serialize_config_for_log(config, logs_dir), indent=2))
    launcher_path, python_real_path = resolve_slicer_runtime(slicer_executable)
    env = dict(os.environ)
    env["HIP_TEST_CONFIG_PATH"] = str(config_path)
    launcher_dump = subprocess.run(
        [str(launcher_path), "--launcher-dump-environment"],
        cwd=str(BUNDLE_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    for line in launcher_dump.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value

    command = [
        str(python_real_path),
        str(script_path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(BUNDLE_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed


def locate_actual_csv(output_parent: Path, case_folder_name: str, case_name: str) -> Path:
    """Return the expected actual-export CSV path produced by the extension."""

    return output_parent / case_folder_name / f"{case_name}_measurements.csv"


def main() -> None:
    """CLI entry point for the full generate-or-replay-and-compare workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slicer",
        type=Path,
        default=detect_slicer_executable(),
        help="Path to Slicer.exe, PythonSlicer(.exe), a macOS Slicer.app bundle, or a Slicer install directory.",
    )
    parser.add_argument("--extension-dir", type=Path, default=EXTENSION_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output folder. When omitted, the runner creates a new timestamped folder under test_runs/.",
    )
    parser.add_argument(
        "--expected-csv",
        type=Path,
        default=expected_csv_path(),
        help="Path to the golden dummy expected export CSV. Defaults to dummy_expected_full_export.csv beside this runner.",
    )
    parser.add_argument("--regenerate-expected", action="store_true")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional seed used when regenerating the golden dummy CSV. When omitted, regeneration picks a new random seed.",
    )
    args = parser.parse_args()

    if args.slicer is None or not args.slicer.exists():
        raise SystemExit("Could not find a Slicer executable. Pass --slicer explicitly.")
    if not args.extension_dir.exists():
        raise SystemExit(f"Extension folder not found: {args.extension_dir}")

    expected_csv = args.expected_csv.expanduser().resolve()
    if args.output_dir is None:
        args.output_dir = create_timestamped_run_dir("end_to_end_replay")
    else:
        args.output_dir = args.output_dir.expanduser().resolve()
        args.output_dir.mkdir(parents=True, exist_ok=False)
    logs_dir = args.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    generated_expected_parent = args.output_dir / "generated_expected_export"
    actual_export_parent = args.output_dir / "actual_export"
    comparison_output_dir = args.output_dir / "comparison"

    reference_hash = sha256_of_file(expected_csv) if expected_csv.exists() else None
    if not args.regenerate_expected and reference_hash is None:
        raise SystemExit("Reference CSV missing. Use --regenerate-expected to generate a new run-local reference.")
    original_reference = expected_csv
    if args.regenerate_expected:
        expected_csv = args.output_dir / "generated_reference.csv"
        generated_expected_parent.mkdir(parents=True, exist_ok=True)
        generate_config = {
            "extensionDir": args.extension_dir.resolve(),
            "outputParent": generated_expected_parent.resolve(),
            "destinationCsvPath": expected_csv.resolve(),
            "randomSeed": args.seed,
        }
        generate_result = run_slicer_script(
            args.slicer.expanduser().resolve(),
            BUNDLE_DIR / "slicer_generate_dummy_expected_csv.py",
            generate_config,
            logs_dir,
        )
        write_log_text(logs_dir, "generate_expected.stdout.txt", generate_result.stdout)
        write_log_text(logs_dir, "generate_expected.stderr.txt", generate_result.stderr)
        if generate_result.returncode != 0:
            raise SystemExit(
                "Failed to regenerate the dummy expected CSV. See logs/generate_expected.stdout.txt and logs/generate_expected.stderr.txt."
            )

    actual_export_parent.mkdir(parents=True, exist_ok=True)

    replay_config = {
        "extensionDir": args.extension_dir.resolve(),
        "dummyCsvPath": expected_csv.resolve(),
        "outputParent": actual_export_parent.resolve(),
    }
    replay_result = run_slicer_script(
        args.slicer.expanduser().resolve(),
        BUNDLE_DIR / "slicer_replay_dummy_csv.py",
        replay_config,
        logs_dir,
    )
    write_log_text(logs_dir, "replay.stdout.txt", replay_result.stdout)
    write_log_text(logs_dir, "replay.stderr.txt", replay_result.stderr)
    if replay_result.returncode != 0:
        raise SystemExit("Replay export failed. See logs/replay.stdout.txt and logs/replay.stderr.txt.")

    actual_csv = locate_actual_csv(actual_export_parent, "SyntheticFullCase", "SyntheticFullCase.dcm")
    from csv_coverage import assert_csv_coverage
    coverage = assert_csv_coverage(actual_csv)
    compare_command = [
        sys.executable,
        str(BUNDLE_DIR / "compare_exports.py"),
        "--expected-csv",
        str(expected_csv.resolve()),
        "--actual-csv",
        str(actual_csv.resolve()),
        "--output-dir",
        str(comparison_output_dir.resolve()),
    ]
    compare_result = subprocess.run(compare_command, capture_output=True, text=True, check=False)
    write_log_text(logs_dir, "compare.stdout.txt", compare_result.stdout)
    write_log_text(logs_dir, "compare.stderr.txt", compare_result.stderr)
    if compare_result.returncode != 0:
        raise SystemExit(
            "Comparison found differences. See comparison/comparison_report.md or comparison/comparison_report.html."
        )

    if reference_hash is not None and sha256_of_file(original_reference) != reference_hash:
        raise RuntimeError("The input reference CSV changed during replay.")
    (args.output_dir / "verification.json").write_text(json.dumps({"status": "passed", "reference_sha256": sha256_of_file(expected_csv), "input_reference_unchanged": True, "generated_reference": args.regenerate_expected, "clinical_validation": False, "csv_coverage": coverage}, indent=2) + "\n")
    print(
        "PASS: exact replay match confirmed.\n"
        f"Expected CSV: {display_path(expected_csv)}\n"
        f"Actual CSV: {display_path(actual_csv)}\n"
        f"Reports: {display_path(comparison_output_dir)}"
    )


if __name__ == "__main__":
    main()
