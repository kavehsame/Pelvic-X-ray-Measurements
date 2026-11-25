"""Keep distribution credits, notices and citation aligned with repository metadata."""

import argparse
import base64
import re
import shutil

from project import EXTENSION, ROOT, WEB, within


def sync_guide(check):
    docs = ROOT / "docs"
    name = "implant-overlays.html"
    guide = (docs / name).read_text(encoding="utf-8")
    for filename in ("overlay-example.json", "overlay.schema.json"):
        data = base64.b64encode((docs / filename).read_bytes()).decode("ascii")
        pattern = rf'href="[^"]+" download="{re.escape(filename)}"'
        guide, matches = re.subn(pattern, f'href="data:application/json;base64,{data}" download="{filename}"', guide)
        if matches != 1:
            raise ValueError(f"Expected one downloadable {filename} in the implant guide.")
    native_resource = EXTENSION / "PelvicXrayMeasurements" / "Resources" / name
    standard = (docs / "overlay-standard.md").read_text(encoding="utf-8")
    targets = {
        docs / name: guide,
        native_resource: guide,
        EXTENSION / "overlay-standard.md": standard.replace(f"({name})", f"(PelvicXrayMeasurements/Resources/{name})"),
    }
    for target, content in targets.items():
        within(target)
        data = content.encode("utf-8")
        if target.is_file() and target.read_bytes() == data:
            continue
        if check:
            raise SystemExit(f"Implant guide or pack standard differs: {target.relative_to(ROOT)}")
        target.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sync_guide(args.check)
    for name in (
        "LICENSE.txt",
        "NOTICE.md",
        "CREDITS.md",
        "CITATION.cff",
        "THIRD_PARTY.md",
    ):
        source = ROOT / name
        targets = [EXTENSION / name]
        if name in {"LICENSE.txt", "NOTICE.md"}:
            targets.append(WEB / "assets" / name)
        for target in targets:
            within(target)
            if args.check:
                if target.read_bytes() != source.read_bytes():
                    raise SystemExit(
                        f"Distribution metadata differs: {target.relative_to(ROOT)}"
                    )
            else:
                shutil.copyfile(source, target)
    print("Distribution metadata is aligned.")


if __name__ == "__main__":
    main()
