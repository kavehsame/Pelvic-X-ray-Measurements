"""Check byte-preserving component delivery, boundaries and static route limits."""

import base64
import gzip
import hashlib
import json
import random

import pytest

from build_web import component_documents
from serve_local import asset_for


@pytest.mark.parametrize("size", [1, 512 * 1024, 512 * 1024 + 1, 1_200_001])
def test_json_components_reconstruct_the_exact_runtime(size):
    payload = random.Random(1234).randbytes(size)
    expected = hashlib.sha256(payload).hexdigest()
    transport = gzip.compress(payload, mtime=0)
    records, files = component_documents(transport, expected)
    restored = bytearray(len(transport))
    for record in records:
        document = json.loads(files[record["path"]])
        block = base64.b64decode(document["data"], validate=True)
        assert document["compression"] == "gzip"
        assert document["payloadSha256"] == expected
        assert len(files[record["path"]]) == record["documentBytes"] < 1024 * 1024
        assert hashlib.sha256(block).hexdigest() == record["sha256"]
        assert len(block) == record["bytes"] <= 512 * 1024
        restored[record["offset"] : record["offset"] + len(block)] = block
    assert bytes(restored) == transport
    assert gzip.decompress(restored) == payload
    assert (records, files) == component_documents(transport, expected)


@pytest.mark.parametrize("content,size", [(b"", 512), (b"data", 0), (b"data", -1)])
def test_invalid_component_inputs_are_rejected(content, size):
    with pytest.raises(ValueError):
        component_documents(content, "0" * 64, size)


def test_static_host_serves_only_expected_component_paths():
    assert asset_for("/implant-overlays.html") == ("implant-overlays.html", "text/html; charset=utf-8")
    assert asset_for("/other-guide.html") is None
    path = "/components/" + "a" * 64 + "/000.json"
    assert asset_for(path) == (path[1:], "application/json; charset=utf-8")
    for rejected in ("/runtime.bin", "/components/../private.json", path + "/extra", "/components/not-a-hash/000.json"):
        assert asset_for(rejected) is None
