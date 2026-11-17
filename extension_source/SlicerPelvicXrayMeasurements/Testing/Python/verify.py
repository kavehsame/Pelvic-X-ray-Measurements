"""Run unit tests, full CSV replay and live Slicer interaction checks."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slicer", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tests = Path(__file__).resolve().parent
    sys.path.insert(0, str(tests / "end_to_end_replay"))
    from common import MODULE_DIR, normalize_slicer_input_path

    slicer = normalize_slicer_input_path(args.slicer.resolve())
    if slicer.name.lower().startswith("pythonslicer"):
        slicer = (
            slicer.parent.parent / "MacOS/Slicer"
            if sys.platform == "darwin"
            else slicer.parent.parent / ("Slicer.exe" if sys.platform == "win32" else "Slicer")
        )
    commands = [
        (
            "unit",
            [
                sys.executable,
                "-m",
                "pytest",
                str(tests / "unit"),
                "-q",
                "-p",
                "no:cacheprovider",
                "--junitxml",
                str(out / "unit.junit.xml"),
            ],
        ),
        (
            "end_to_end",
            [
                sys.executable,
                str(tests / "end_to_end_replay/run_end_to_end_test.py"),
                "--slicer",
                str(args.slicer.resolve()),
                "--output-dir",
                str(out / "replay"),
            ],
        ),
        (
            "end_to_end_auto_placement",
            [
                str(slicer),
                "--no-splash",
                "--ignore-slicerrc",
                "--disable-settings",
                "--testing",
                "--additional-module-paths",
                str(MODULE_DIR),
                "--python-script",
                str(tests / "end_to_end_replay/slicer_auto_place_smoke.py"),
            ],
        ),
        (
            "interactive_workflows",
            [
                str(slicer),
                "--no-splash",
                "--ignore-slicerrc",
                "--disable-settings",
                "--testing",
                "--additional-module-paths",
                str(MODULE_DIR),
                "--python-script",
                str(tests / "end_to_end_replay/slicer_workflow_smoke.py"),
            ],
        ),
    ]
    records = []
    runtime = {}
    for stage, command in commands:
        try:
            with (out / f"{stage}.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            record = {"stage": stage, "exit_code": result.returncode}
        except subprocess.TimeoutExpired:
            record = {"stage": stage, "exit_code": 124, "error": "Verification exceeded its time limit."}
        records.append(record)
        print(f"{stage}: {'passed' if record['exit_code'] == 0 else 'FAILED'}", flush=True)
        if record["exit_code"]:
            break
        if stage == "interactive_workflows":
            rows = [line.removeprefix("SLICER_RUNTIME ")
                    for line in (out / f"{stage}.log").read_text().splitlines()
                    if line.startswith("SLICER_RUNTIME ")]
            if len(rows) != 1:
                raise RuntimeError("The live Slicer check did not identify its runtime.")
            runtime = json.loads(rows[0])
    passed = len(records) == len(commands) and all(row["exit_code"] == 0 for row in records)
    (out / "verification.json").write_text(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "checks": records,
                "runtime": runtime,
                "clinical_validation": "in progress separately against established medical software",
            },
            indent=2,
        )
        + "\n"
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
