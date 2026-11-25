"""The physical reference on every original AP sheet must survive placement."""
import json
from pathlib import Path

import numpy as np
import pytest

import PelvicXrayMeasurementsPlanning as planning


def test_reference_interval_on_every_bundled_sheet():
    path = Path(planning.__file__).resolve().parents[1] / 'Resources' / 'planning_templates.json'
    if not path.exists():
        pytest.skip("Optional manufacturer catalogue is absent")
    catalog = json.loads(path.read_bytes())
    if catalog["format"] != "pxm-ap-png-1":
        pytest.skip("This catalogue contains vector templates")
    sheets = catalog["scaleSheets"]
    assert sheets and {item["scaleSheet"] for item in catalog["items"]} == set(sheets)
    for item in catalog["items"]:
        ref = sheets[item["scaleSheet"]]
        dx, dy = ref["pixelVector"]
        w, h = item["pixels"]
        sides = ("left", "right") if item["side"] == "both" else (item["side"],)
        for side in sides:
            for ball, angle in ((1., 0.), (1.25, 31.)):
                choice = planning.template_choice(item["component"], {"id": item["id"], "angle": angle}, side)
                a, b, _, d = planning.outline(choice, [20, 80, 0], side, [1, 0, 0], [0, 1, 0], ball)
                measured = np.linalg.norm(dx * (b-a) / w + dy * (d-a) / h) * ball
                # The landmark TXT coordinates are rounded by their author.
                atol = .2 if ref["method"] == "dimensioned head-centre marks" else 1e-6
                assert abs(measured-ref["referenceMm"]) < atol, item["id"]
