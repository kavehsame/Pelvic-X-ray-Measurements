"""Bundle the pinned OpenJPEG and CharLS browser decoders."""

import hashlib
import io
import json
import tarfile

from fetch_runtime import ROOT, checked_download

COMPONENTS = {
    "openjpeg": (
        "1.3.6",
        "bSdZXF+2GxfBkWHUr7yGLQtIwbAm9wOl3e4ARee/9Z9lfKyVqhUCixI6+ZjIn9YKTIuDcn/NZNK94XEUg1SBtw==",
    ),
    "charls": (
        "1.2.7",
        "kNfQ7J8LIrfQUbt56fPJ0SEvevLlAAbsLHjqPS4DUDWVSuAHb5Fn0cMIV/U0SYkJRJqKvzyLJYF1hl7/xQGqLQ==",
    ),
}
UPSTREAM_NOTICES = {
    "OPENJPEG-UPSTREAM-LICENSE.txt": "https://raw.githubusercontent.com/uclouvain/openjpeg/v2.5.4/LICENSE",
    "CHARLS-UPSTREAM-LICENSE.txt": "https://raw.githubusercontent.com/team-charls/charls/2.4.2/LICENSE.md",
}


def fetch_codecs():
    from urllib.request import urlopen

    manifest = json.loads((ROOT / "manifest.json").read_text())
    assets = {}
    for name, (version, integrity) in COMPONENTS.items():
        url = f"https://registry.npmjs.org/@cornerstonejs/codec-{name}/-/codec-{name}-{version}.tgz"
        content = checked_download(url, integrity, "sha512")
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            take = lambda entry: archive.extractfile(entry).read()
            for extension in ("js", "wasm"):
                assets[f"{name}.{extension}"] = take(
                    f"package/dist/{name}wasm_decode.{extension}"
                )
            notices = [
                m
                for m in archive.getmembers()
                if m.isfile()
                and m.name.rsplit("/", 1)[-1].upper().startswith("LICENSE")
            ]
            for i, notice in enumerate(notices, 1):
                assets[f"{name.upper()}-{i}-LICENSE.txt"] = take(notice)
    for name, url in UPSTREAM_NOTICES.items():
        with urlopen(url, timeout=18) as stream:
            assets[name] = stream.read(500_000)
    for name, data in assets.items():
        output = ROOT / name
        assert output.resolve().parent == ROOT
        if hashlib.sha256(data).hexdigest() != manifest[name]["sha256"]:
            raise ValueError(f"Pinned codec content changed: {name}")
        output.write_bytes(data)
    print("Verified and bundled", len(assets), "codec and licence files")


if __name__ == "__main__":
    fetch_codecs()
