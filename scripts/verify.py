"""Run the shared web and Slicer software checks in a new evidence directory."""

import argparse
from datetime import datetime, timezone
import json
import os
import platform
import subprocess
import sys

from project import BUILD, EXTENSION, ROOT, WEB, source_hashes, within


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--slicer", help="Installed Slicer executable or application bundle"
    )
    mode.add_argument(
        "--web-only",
        action="store_true",
        help="Omit live Slicer tests; retain its unit suite",
    )
    parser.add_argument("--chrome", help="Chrome executable; otherwise use discovery")
    parser.add_argument("--output")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = within(args.output or BUILD / ("verification_" + stamp))
    out.mkdir(parents=True, exist_ok=False)
    scratch = out / "tmp"
    scratch.mkdir()
    sources = source_hashes()
    (out / "source_hashes.json").write_text(json.dumps(sources, indent=2) + "\n")
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=os.pathsep.join((str(WEB), str(WEB / "scripts"))),
        TMPDIR=str(scratch),
        TMP=str(scratch),
        TEMP=str(scratch),
        PELVIC_QA_OUTPUT=str(out / "web"),
    )
    python = [sys.executable, "-B"]
    commands = [
        ("assets", [*python, str(ROOT / "scripts/fetch_assets.py")]),
        (
            "static",
            [
                *python,
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--no-respect-gitignore",
                "--select",
                "F,E9,B",
                "--config",
                "exclude=[]",
                str(ROOT / "scripts"),
                str(WEB / "core"),
                str(WEB / "scripts"),
                str(WEB / "tests"),
                str(EXTENSION),
            ],
        ),
        (
            "web_unit",
            [
                *python,
                "-m",
                "pytest",
                str(WEB / "tests"),
                "-q",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(out / "web_unit_tmp"),
                "--junitxml",
                str(out / "web_unit.xml"),
            ],
        ),
    ]
    if args.slicer:
        commands.append(
            (
                "slicer",
                [
                    *python,
                    str(EXTENSION / "Testing/Python/verify.py"),
                    "--slicer",
                    args.slicer,
                    "--output",
                    str(out / "slicer"),
                ],
            )
        )
    else:
        commands.append(
            (
                "slicer_unit",
                [
                    *python,
                    "-m",
                    "pytest",
                    str(EXTENSION / "Testing/Python/unit"),
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--basetemp",
                    str(out / "slicer_unit_tmp"),
                    "--junitxml",
                    str(out / "slicer_unit.xml"),
                ],
            )
        )
    commands.extend(
        [
            ("core_replay", [*python, str(WEB / "scripts/check_core.py")]),
            ("build", [*python, str(WEB / "scripts/build_web.py")]),
            (
                "chrome",
                [
                    *python,
                    str(WEB / "scripts/check_chrome.py"),
                    *(["--chrome", args.chrome] if args.chrome else []),
                ],
            ),
        ]
    )
    report = {
        "status": "running",
        "mode": "full" if args.slicer else "web-and-all-unit-tests",
        "live_slicer": bool(args.slicer),
        "clinical_validation_completed": False,
        "validation_study": "in progress; comparison with established medical software",
        "started_utc": stamp,
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "checks": [],
    }
    for name, command in commands:
        print(f"Checking {name}…", flush=True)
        try:
            with (out / (name + ".log")).open("w") as log:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=1800,
                )
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
        report["checks"].append({"stage": name, "exit_code": code})
        report["status"] = "running" if code == 0 else "failed"
        (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        if code:
            raise SystemExit(f"{name} failed. See {out / (name + '.log')}")
    report["source_unchanged"] = sources == source_hashes()
    report["status"] = "passed" if report["source_unchanged"] else "failed"
    (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["source_unchanged"]:
        raise SystemExit("Source changed during verification.")
    print(f"Software checks passed: {out}")


if __name__ == "__main__":
    main()
