"""Fetch and hash-check the public, pinned browser dependencies at build time."""

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "runtime"
VERSION = "314.0.8"
CDN = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
CORE = f"pyodide-core-{VERSION}.tar.bz2"
WHEELS = {
    "numpy": (
        "numpy-2.4.6-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
        "a292c1f5d7d8a2208cd5e94fc467604c131cabcd2fc14fed6eefde121e7fabdf",
    ),
    "pillow": (
        "pillow-12.2.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
        "e29838b7a756e4ee0f27a9cfa9a387ee0dfa2e9dd44be2dd595130b9f9d93ac3",
    ),
}
PYDICOM = "pydicom-3.0.2-py3-none-any.whl"


def checked_download(url, digest, algorithm="sha256"):
    with urlopen(
        Request(url, headers={"User-Agent": "PelvicXrayLocal-build"}), timeout=45
    ) as stream:
        content = stream.read(60_000_001)
    computed = hashlib.new(algorithm, content)
    actual = (
        computed.hexdigest()
        if algorithm == "sha256"
        else base64.b64encode(computed.digest()).decode()
    )
    if len(content) > 60_000_000 or actual != digest:
        raise ValueError(f"Download failed its size or checksum check: {url}")
    return content


def fetch():
    files = {}
    core_url = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/{CORE}"
    data = checked_download(
        core_url, "ff3e5f9d9bc8e98ff30b99515535fc24d375994f47a978c61975d653e162ca37"
    )
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as archive:
        for member in archive:
            name = Path(member.name).name
            if member.isfile() and (
                name
                in {
                    "pyodide.js",
                    "pyodide.asm.mjs",
                    "pyodide.asm.wasm",
                    "python_stdlib.zip",
                    "pyodide-lock.json",
                }
                or name.startswith("LICENSE")
            ):
                files[name] = archive.extractfile(member).read()
    with urlopen(
        Request(CDN + "pyodide-lock.json", headers={"User-Agent": "pelvic-web-build"}),
        timeout=25,
    ) as stream:
        lock = json.load(stream)
    assert (
        lock["info"]["abi_version"] == "2026_0" and lock["info"]["arch"] == "wasm32"
    ), lock["info"]
    selected = {}
    for package, (filename, digest) in WHEELS.items():
        entry = lock["packages"][package]
        assert (
            not entry["depends"]
            and entry["file_name"] == filename
            and entry["sha256"] == digest
        )
        selected[package] = entry
        files[filename] = checked_download(CDN + filename, digest)
    # An allowlist keeps the embedded loader from resolving any other package.
    files["pyodide-lock.json"] = json.dumps(
        {"info": lock["info"], "packages": selected}
    ).encode()
    files[PYDICOM] = checked_download(
        "https://files.pythonhosted.org/packages/46/e0/60466c6d712dad2cf807df315e39863e91609ffd1064ecb835994460bbda/"
        + PYDICOM,
        "abf971a5440f84dbaf42c4b6758e30e62480902584f8b270b9a5d146e278a07b",
    )
    jpeg = checked_download(
        "https://registry.npmjs.org/jpeg-lossless-decoder-js/-/jpeg-lossless-decoder-js-2.1.2.tgz",
        "fYf/plymnuKwVw+s8gJ8O/BPw8y8OLaN11MBvEcT05kuy3m45o7BEC4J0JbxMNUYyO+MdK/I/jq0q1gkVYZm2Q==",
        "sha512",
    )
    with tarfile.open(fileobj=io.BytesIO(jpeg), mode="r:gz") as archive:
        files["jpeg-lossless.cjs"] = archive.extractfile(
            "package/release/cjs/lossless.cjs"
        ).read()
        license_member = next(
            m
            for m in archive.getmembers()
            if Path(m.name).name.upper() in {"LICENSE", "LICENSE.MD", "LICENSE.TXT"}
        )
        files["JPEG-LOSSLESS-LICENSE.txt"] = archive.extractfile(license_member).read()
    for name, url in (
        (
            "PYODIDE-LICENSE.txt",
            f"https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE",
        ),
        (
            "CPYTHON-LICENSE.txt",
            "https://raw.githubusercontent.com/python/cpython/v3.14.2/LICENSE",
        ),
    ):
        with urlopen(url, timeout=20) as stream:
            files[name] = stream.read(500_000)
    ROOT.mkdir(exist_ok=True)
    assert ROOT.resolve().parent == Path(__file__).resolve().parents[1]
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for name, data in files.items():
        if hashlib.sha256(data).hexdigest() != manifest[name]["sha256"]:
            raise ValueError(f"Pinned runtime content changed: {name}")
        path = ROOT / name
        assert path.resolve().parent == ROOT
        path.write_bytes(data)
    print("Verified and bundled", len(files), "runtime files")


if __name__ == "__main__":
    fetch()
