"""Check the publication tree, local links, notices and product archive contents."""

import argparse
import ast
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

import yaml

from project import BUILD, EXTENSION, IMPLANT_FOLDERS, ROOT, WEB, config, implant_files, implant_manifest, source_files, within

PRIVATE = re.compile(
    r"/Users/[^\s<\"']+|/Volumes/[^\s<\"']+|C:\\\\Users\\|/home/(?:runner|[a-z][a-z0-9_-]*)/|\b(?:ghp|github_pat)_[A-Za-z0-9_]{15,}|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
)
OBSOLETE = re.compile(
    r"\bstand[ -]?alone\b|\b(?:Mac|macOS|Windows|Linux|native|desktop) (?:app(?:lication)?s?|kits?)\b|trame|pyside|pyobjc|MedUni|Medical University of Vienna",
    re.I,
)
TEXT = {
    ".md",
    ".py",
    ".html",
    ".css",
    ".js",
    ".json",
    ".yml",
    ".yaml",
    ".cff",
    ".cmake",
    ".txt",
    ".xml",
    ".csv",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.links.append(value)


def scan_text(name, content):
    if Path(name).name == "audit_release.py":
        return  # The literal search patterns are the audit rules, not release prose.
    if PRIVATE.search(content):
        raise ValueError(f"Private path or credential pattern in {name}")
    # Preserve unmodified upstream licence texts; inspect project prose and code.
    if "LICENSE" not in Path(name).name and OBSOLETE.search(content):
        raise ValueError(f"Removed-edition or affiliation reference in {name}")


def audit_source():
    from io import BytesIO

    assets = implant_files(IMPLANT_FOLDERS[0])
    assert assets == implant_files(IMPLANT_FOLDERS[1])
    records = json.loads(assets["planning_templates.json"])["items"]
    limits = implant_manifest()
    assert len(records) == len({item["id"] for item in records}) == limits["entries"]
    drawings = {item["image"] + ".png" for item in records}
    with ZipFile(BytesIO(assets["planning_artwork.zip"])) as artwork:
        assert len(artwork.namelist()) == len(drawings) == limits["drawings"]
        assert set(artwork.namelist()) == drawings
        for name in drawings:
            data = artwork.read(name)
            assert data.startswith(b"\x89PNG\r\n\x1a\n") and hashlib.sha256(data).hexdigest() + ".png" == name
    for edition in (EXTENSION, WEB):
        reports = edition / "test_reports"
        if sorted(path.name for path in reports.iterdir()) != ["current"]:
            raise ValueError("Each edition must contain exactly one selected test run: " + str(reports.relative_to(ROOT)))
    files = list(source_files())
    for path in files:
        if path.suffix in TEXT or path.name.startswith((".git", "CMake")):
            text = path.read_text()
            scan_text(str(path.relative_to(ROOT)), text)
            if path.suffix == ".py":
                ast.parse(text, filename=str(path))
        if path.suffix == ".mrb":
            with ZipFile(path) as archive:
                for name in archive.namelist():
                    if name.endswith((".mrml", ".json", ".xml", ".txt")):
                        if PRIVATE.search(
                            archive.read(name).decode("utf-8", "replace")
                        ):
                            raise ValueError(
                                f"Private metadata in synthetic fixture: {path.name}/{name}"
                            )
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        doc = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
        assert doc.get("on") and doc.get("jobs"), workflow.name
        for action in re.findall(r"uses:\s+(actions/[^\s]+)", workflow.read_text()):
            assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action), action
    version = config()["version"]
    assert f'VERSION = "{version}"' in (WEB / "core/engine.py").read_text()
    constants = (
        EXTENSION
        / "PelvicXrayMeasurements/PelvicXrayMeasurementsLib/PelvicXrayMeasurementsConstants.py"
    )
    assert f'MODULE_VERSION = "V{version}"' in constants.read_text()
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text())
    assert citation["version"] == version and citation["license"] == "Apache-2.0"
    assert citation["authors"][0]["family-names"] == "Same"
    for doc in (
        ROOT / "README.md",
        ROOT / "NOTICE.md",
        ROOT / "docs/web-manual.md",
        EXTENSION / "documentation.md",
    ):
        text = doc.read_text().lower()
        assert "research use only" in text and "not a medical device" in text, doc
    for name in (
        "LICENSE.txt",
        "NOTICE.md",
        "CREDITS.md",
        "CITATION.cff",
        "THIRD_PARTY.md",
    ):
        assert (ROOT / name).read_bytes() == (EXTENSION / name).read_bytes(), name
    models = json.loads((ROOT / "model-assets.json").read_text())
    resolver = (EXTENSION / "ResolveModels.cmake").read_text()
    for name, record in models["files"].items():
        assert record["sha256"] in resolver
        for path in (
            WEB / "assets" / name,
            EXTENSION / "PelvicXrayMeasurements/Resources/AutoPlacement" / name,
        ):
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    return len(files)


def audit_site():
    site = BUILD / "site"
    count = 0
    for path in site.rglob("*.html"):
        text = path.read_text()
        # App licence appendices may contain the ordinary English word standalone.
        if path != site / "app/index.html":
            scan_text(str(path.relative_to(site)), text)
        elif PRIVATE.search(text):
            raise ValueError("Private text in compiled application")
        parser = Links()
        parser.feed(text)
        for value in parser.links:
            parts = urlsplit(value)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            target = (path.parent / unquote(parts.path)).resolve()
            if not target.is_relative_to(site.resolve()):
                raise ValueError(f"Website link escapes site: {path.name}: {value}")
            if target.is_dir():
                target /= "index.html"
            if not target.exists():
                raise ValueError(
                    f"Broken website link: {path.relative_to(site)}: {value}"
                )
            count += 1
    landing = (site / "index.html").read_text()
    assert (
        "How the website works" in landing and "Validation study in progress" in landing
    )
    assert (
        "established medical software" in landing and "not a medical device" in landing
    )
    assert "hospital networks" in landing and 'id="network-notice"' in landing
    for name, record in json.loads((BUILD / "build_manifest.json").read_text())["files"].items():
        deployed = (site / "app" / name).read_bytes()
        assert deployed == (BUILD / "web" / name).read_bytes()
        assert hashlib.sha256(deployed).hexdigest() == record["sha256"]
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    report = {"status": "passed", "source_files_checked": audit_source()}
    if not args.source_only:
        report["local_site_links_checked"] = audit_site()
        release = BUILD / "releases" / ("v" + config()["version"])
        archives = list(release.glob("*.zip"))
        assert len(archives) == 2
        for path in archives:
            with ZipFile(path) as archive:
                assert archive.testzip() is None
                if path.name.endswith("_Slicer_extension.zip"):
                    for name in implant_manifest()["files"]:
                        assert "SlicerPelvicXrayMeasurements/PelvicXrayMeasurements/Resources/" + name in archive.namelist()
                assert not any(
                    "test_reports/" in n or "test_runs/" in n or "__pycache__" in n
                    for n in archive.namelist()
                )
                for member in archive.namelist():
                    prefix = "SlicerPelvicXrayMeasurements/"
                    if member.startswith(prefix):
                        current = EXTENSION / member[len(prefix) :]
                        assert (
                            current.is_file()
                            and archive.read(member) == current.read_bytes()
                        ), member
                    elif member == "index.html" or member.startswith("components/"):
                        assert (
                            archive.read(member)
                            == (BUILD / "web" / member).read_bytes()
                        ), member
                    if Path(member).suffix in {".md", ".cff", ".py"}:
                        scan_text(
                            path.name + "/" + member, archive.read(member).decode()
                        )
        report["product_archives_checked"] = len(archives)
    BUILD.mkdir(exist_ok=True)
    within(BUILD / "release_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
