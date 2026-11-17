"""Keep distribution credits, notices and citation aligned with repository metadata."""

import argparse
import shutil

from project import EXTENSION, ROOT, WEB, within


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
