"""Build the browser app and its static GitHub Pages landing/documentation site."""

import argparse
from html import escape
import json
import shutil
import subprocess
import sys

from markdown import markdown

from project import BUILD, EXTENSION, ROOT, WEB, config, within

NOTICE = "Research use only. This software is not a medical device. It is not intended for diagnosis, treatment planning or other clinical decision-making."

STYLE = """
:root{color-scheme:light;--ink:#18303c;--muted:#536a76;--accent:#12685e;--line:#dce5e6}
*{box-sizing:border-box}body{margin:0;background:#f8faf9;color:var(--ink);font:17px/1.65 system-ui,-apple-system,sans-serif}
a{color:#11665e;text-underline-offset:3px}header,main,footer{max-width:1100px;margin:auto;padding:24px}
header{display:flex;align-items:center;justify-content:space-between;gap:18px;border-bottom:1px solid var(--line)}
nav{display:flex;flex-wrap:wrap;gap:18px}.brand{display:flex;gap:12px;align-items:center;text-decoration:none;color:var(--ink);font-weight:650}.brand img{width:42px;height:42px}
h1,h2,h3{line-height:1.2;letter-spacing:-.02em}h1{font-size:clamp(2.1rem,5vw,3.6rem);max-width:850px;margin:.35em 0}h2{font-size:1.7rem;margin-top:1.6em}h3{font-size:1.15rem}
p{max-width:900px}.lead{font-size:1.2rem;color:var(--muted);max-width:750px}.eyebrow{color:var(--accent);font-weight:650;font-size:.9rem}.hero{padding:32px 0 16px}
.actions{display:flex;flex-wrap:wrap;gap:12px;margin:26px 0}.button{display:inline-block;padding:12px 20px;border:1px solid var(--accent);border-radius:7px;text-decoration:none;font-weight:650;background:var(--accent);color:white}.secondary{background:transparent;color:var(--accent)}
.notice{border-left:4px solid #a56b1b;background:#fff5e3;padding:14px 18px;font-size:.95rem;border-radius:0 6px 6px 0}.study{padding:22px;border:1px solid #bfd8d2;border-radius:8px;background:#eef7f4;margin:30px 0}.study h2{margin-top:0}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:white;border:1px solid var(--line);padding:22px;border-radius:8px}.card h3{margin-top:10px}.number{font-weight:700;color:var(--accent)}.small{font-size:.9rem;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:.94rem;display:block;overflow:auto}td,th{border-bottom:1px solid var(--line);padding:10px 14px;text-align:left}code{font-size:.9em;overflow-wrap:anywhere}pre{overflow:auto;background:#eaf0f0;padding:18px;border-radius:6px}
article{max-width:920px}article h1{font-size:2.4rem}li{margin:6px 0}details{padding:14px;border:1px solid var(--line);margin:14px 0;background:white;border-radius:6px}summary{font-weight:600;cursor:pointer}img{max-width:100%}footer{border-top:1px solid var(--line);margin-top:35px;font-size:.9rem;color:var(--muted)}
@media(max-width:720px){header{align-items:flex-start;flex-direction:column}.cards{grid-template-columns:1fr}main{padding-top:12px}.hero{padding-top:18px}nav{gap:12px}}
"""


def shell(title, body, prefix=""):
    repo = "https://github.com/" + config()["repository"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Editable pelvic radiograph measurements for research. Use the browser app with local image processing or the 3D Slicer extension.">
<meta name="referrer" content="no-referrer"><title>{escape(title)}</title>
<link rel="icon" href="{prefix}assets/icon.png"><link rel="stylesheet" href="{prefix}assets/site.css"></head>
<body><header><a class="brand" href="{prefix}index.html"><img src="{prefix}assets/icon.png" alt=""><span>Pelvic X-ray Measurements</span></a>
<nav aria-label="Main navigation"><a href="{prefix}manuals.html">Manuals</a><a href="{prefix}tests/">Software checks</a><a href="{repo}">GitHub</a></nav></header>
<main>{body}</main><footer><p>{NOTICE}</p><p>Developed by Kaveh Same, MD, MPH, PhD Candidate · Michael Ogon Laboratory for Orthopedic Research, Orthopedic Hospital Speising, Vienna, Austria.</p>
<p>In collaboration with ImageBiopsy Lab GmbH, Vienna, Austria. Code backbone created by Codex, OpenAI, California, USA.</p>
<p><a href="{prefix}docs/privacy.html">Privacy and files</a> · <a href="{prefix}docs/third-party.html">Licences and notices</a> · <a href="{repo}/issues">Support</a></p></footer></body></html>"""


def put(path, content):
    path = within(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy(source, destination):
    destination = within(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def render_site():
    site = within(BUILD / "site")
    if site.exists():
        shutil.rmtree(
            site
        )  # Only this command's generated site, never retained source or releases.
    site.mkdir(parents=True)
    for name in ("index.html", "runtime.bin"):
        copy(BUILD / "web" / name, site / "app" / name)
    put(site / ".nojekyll", "")
    put(site / "assets/site.css", STYLE)
    copy(WEB / "assets/favicon.png", site / "assets/icon.png")
    settings = config()
    release_url = "https://github.com/" + settings["repository"] + "/releases/latest"
    download_mb = (
        json.loads((BUILD / "build_manifest.json").read_text())["files"]["runtime.bin"][
            "bytes"
        ]
        / 1_000_000
    )
    landing = f"""<section class="hero"><p class="eyebrow">Version {settings["version"]} · Web and 3D Slicer</p>
<h1>Pelvic X-ray Measurements</h1><p class="lead">Place editable landmarks, check the measurement geometry and save your research results. Use the web app or work inside 3D Slicer.</p>
<div class="actions"><a class="button" href="app/">Start the web app</a><a class="button secondary" href="{release_url}">Download the Slicer extension</a></div>
<p class="notice"><strong>Research use only. This software is not a medical device.</strong> It is not intended for diagnosis, treatment planning or other clinical decision-making.</p></section>
<section aria-labelledby="how"><h2 id="how">How the website works</h2><div class="cards">
<div class="card"><span class="number">1</span><h3>Start the tool</h3><p>Open the web app and select Start. Your browser prepares the software in the background. No separate installation is needed.</p></div>
<div class="card"><span class="number">2</span><h3>Open images from your computer</h3><p>Choose an image or folder. Place and adjust the landmarks while the browser calculates the measurements on your device.</p></div>
<div class="card"><span class="number">3</span><h3>Save your work locally</h3><p>Export measurements, an annotated image or an editable scene to your computer. Your images and annotations are not uploaded to the website.</p></div></div>
<p class="small">The first Start downloads about {download_mb:.1f} MB of software and models. The browser reuses the verified package when it remains cached. Folder exports work best in Chrome or Edge. <a href="docs/privacy.html">Read about local files and website access logs.</a></p></section>
<section class="study" aria-labelledby="study"><h2 id="study">Validation study in progress</h2><p>A validation study is being performed to compare the tool with established medical software. This ongoing study is separate from the automated software checks and does not imply completed clinical validation.</p><a href="tests/">View the software test evidence</a></section>
<section><h2>What can you measure?</h2><p>The tools cover native and implant head fitting, shaft and neck axes, acetabular angles, offsets, leg-length discrepancy, femoral morphology, cup opening geometry and contours. Custom points, lines and angles support additional annotations.</p><p>Smart Point Placement suggests editable landmarks after calibration, reference and head fitting. Inspect each suggestion and adjust it to the image before using the measurements.</p><a href="manuals.html">Read the user manuals</a></section>
<section><h2>Prefer to work in Slicer?</h2><p>The extension adds the measurement panel to an existing 3D Slicer installation. The release bundle includes its resources and Smart Point Placement models. Installation through the Slicer extension catalogue remains a separate publication step.</p><a href="docs/installation.html">Installation and download guide</a></section>"""
    put(site / "index.html", shell(settings["name"], landing))
    put(
        site / "manuals.html",
        shell(
            "User manuals",
            '<h1>User manuals</h1><p>Choose the guide for the edition you are using.</p><div class="actions"><a class="button" href="docs/web-manual.html">Web manual</a><a class="button secondary" href="docs/slicer-manual.html">Slicer manual</a></div><p><a href="docs/installation.html">Installation</a> · <a href="docs/models.html">Smart Point Placement</a> · <a href="docs/testing.html">Testing and validation</a></p>',
        ),
    )
    articles = {
        p.name: p for p in (ROOT / "docs").glob("*.md") if p.name != "README.md"
    }
    articles.update(
        {
            "slicer-manual.md": EXTENSION / "documentation.md",
            "third-party.md": ROOT / "THIRD_PARTY.md",
        }
    )
    for name, source in articles.items():
        body = markdown(source.read_text(), extensions=("tables", "fenced_code"))
        body = (
            body.replace('href="LICENSE.txt"', 'href="../licences/LICENSE.txt"')
            .replace('href="NOTICE.md"', 'href="../licences/NOTICE.md"')
            .replace('href="THIRD_PARTY.md"', 'href="third-party.html"')
        )
        for other in articles:
            body = body.replace(f'href="{other}"', f'href="{other[:-3]}.html"')
            body = body.replace(f'href="docs/{other}"', f'href="{other[:-3]}.html"')
        body = body.replace(
            'href="../extension_source/SlicerPelvicXrayMeasurements/documentation.md"',
            'href="slicer-manual.html"',
        )
        body = body.replace(
            'href="releases/v1.6.0.md"',
            f'href="https://github.com/{settings["repository"]}/releases/tag/v1.6.0"',
        )
        put(
            site / "docs" / (name[:-3] + ".html"),
            shell(
                source.read_text().splitlines()[0].lstrip("# "),
                "<article>" + body + "</article>",
                "../",
            ),
        )
    for name in ("LICENSE.txt", "NOTICE.md"):
        copy(ROOT / name, site / "licences" / name)
    test_sources = {
        "slicer": EXTENSION / "test_reports/current",
        "web": WEB / "test_reports/current",
    }
    for name, source in test_sources.items():
        if not (source / "index.html").is_file():
            raise FileNotFoundError(
                f"Select the passing {name} test evidence before building the publication site."
            )
        shutil.copytree(source, within(site / "tests" / name))
    summary = '<h1>Software checks</h1><p>The selected results cover unit tests, synthetic measurement replay and interaction workflows. They do not establish clinical validity.</p><div class="actions"><a class="button" href="slicer/">Slicer evidence</a><a class="button secondary" href="web/">Web evidence</a></div><p>A validation study is being performed to compare the tool with established medical software.</p><p><a href="../docs/testing.html">Methods, coverage and limitations</a></p>'
    put(site / "tests/index.html", shell("Software checks", summary, "../"))
    print(f"GitHub Pages site: {site}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-only", action="store_true")
    args = parser.parse_args()
    if not args.site_only:
        subprocess.run(
            [sys.executable, "-B", str(WEB / "scripts/build_web.py")],
            cwd=ROOT,
            check=True,
        )
    render_site()


if __name__ == "__main__":
    main()
