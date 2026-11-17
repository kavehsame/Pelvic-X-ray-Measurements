"""Create a new GitHub release draft from checked product assets in CI."""

import os
import re
import subprocess

from project import BUILD, ROOT, config


def main():
    settings = config()
    version = settings["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Unexpected software version")
    if os.environ.get("GITHUB_REPOSITORY") != settings["repository"]:
        raise ValueError(
            "Run this publishing workflow only in the configured repository."
        )
    commit = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("The release must identify a complete source commit")
    tag = "v" + version
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", settings["repository"]],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if existing.returncode == 0:
        raise ValueError(
            "This release already exists; existing releases are never replaced."
        )
    folder = BUILD / "releases" / tag
    assets = [
        folder / f"PelvicXrayMeasurements_{version}_{edition}.zip"
        for edition in ("Slicer_extension", "web")
    ]
    assets.append(folder / "SHA256SUMS.txt")
    assert all(path.is_file() for path in assets)
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            *map(str, assets),
            "--repo",
            settings["repository"],
            "--draft",
            "--target",
            commit,
            "--title",
            settings["name"] + " " + version,
            "--notes-file",
            str(ROOT / "docs/releases" / (tag + ".md")),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
