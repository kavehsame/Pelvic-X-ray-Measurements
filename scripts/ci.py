"""Run the full common verifier with the pinned Slicer installation on Linux CI."""

import subprocess
import sys

from project import BUILD, ROOT


def main():
    slicer = (BUILD / "slicer_executable.txt").read_text().strip()
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/verify.py"),
            "--slicer",
            slicer,
            "--output",
            str(BUILD / "ci-verification"),
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
