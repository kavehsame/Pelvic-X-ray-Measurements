"""Planning through browser placement, both legacy CSV dialects and reconstructed overlays."""

import csv
import io
import json
from pathlib import Path
import random

import numpy as np
from PIL import Image
import pytest

from core import planning
from core.csv_export import write_case_csv
from core.engine import Session
from core.scene_files import read_csv, append_csv_metadata, read_mrb, write_mrb


def open_case():
    image = io.BytesIO()
    Image.fromarray(np.arange(10000, dtype=np.uint16).reshape(100, 100)).save(image, format="PNG")
    session = Session("Research Reader")
    session.open("planning-phantom.png", image.getvalue())
    return session


def place(controller, key, coordinates):
    controller.start(key)
    for x, y in coordinates:
        assert controller.place(x, y), key
    if key == "bone_fragment":
        controller.expire_placement()
    assert controller._active_node is None, key


def shuffle_csv(raw, future=True):
    source = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows = list(source)
    if future:
        rows.append(dict(section="point", name="Future curve", details="right_futureCurve"))
    random.Random(490).shuffle(rows)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["future_column", *reversed(source.fieldnames)])
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


@pytest.mark.parametrize("fixture", ["dummy_expected_full_export.csv", "SyntheticFullCase_reference.csv"])
def test_older_exports_restore_the_same_after_reordering(fixture):
    path = (
        Path(__file__).resolve().parents[2]
        / "extension_source/SlicerPelvicXrayMeasurements/Testing/Python/end_to_end_replay"
        / fixture
    )
    if not path.is_file():
        path = Path(__file__).parent / "fixtures" / fixture
    original = read_csv(path.read_bytes())
    shuffled = read_csv(shuffle_csv(path.read_bytes()))
    assert len(original["points"]) > 70
    for key in ("settings", "attributes", "curve_types", "curve_segments"):
        assert shuffled[key] == original[key]
    assert sorted(shuffled["points"]) == sorted(original["points"])
    for role, points in original["points"].items():
        np.testing.assert_array_equal(shuffled["points"][role], points)


def test_planning_and_wear_bilateral_csv_and_scene(tmp_path):
    s = open_case()
    c = s.controller
    assert c.missing_dependencies("template_cup")
    assert c.missing_dependencies("bone_fragment")
    place(c, "calibration", [(10, 20), (20, 10), (30, 20)])  # 25 mm / 20 px
    place(c, "implant_head", [(40, 40), (50, 30), (60, 40)])
    place(c, "cup_center", [(35, 44), (53, 26), (71, 44)])  # 3–4–5 px eccentricity
    value = lambda side, key: c._numeric_results.get(f"pelvic_result_{side}_{key}", (None, ""))[0]
    assert value("left", "inlay_wear") == pytest.approx(6.25)
    assert value("right", "inlay_wear") is None
    place(c, "straight_resection", [(40, 60), (50, 60)])
    place(c, "stepped_resection", [(40, 65), (43, 69), (51, 69)])
    assert value("left", "stepped_resection") == pytest.approx(16.25)
    assert value("left", "step_medial") == pytest.approx(6.25)
    c.planning_options({"key": "bone_fragment", "cut": "stepped"})
    place(c, "bone_fragment", [(51, 78), (40, 78)])
    assert c.planning_node("left", "bone_fragment").curve_type == 0
    place(c, "fragment_pose", [(70, 69)])
    c.planning_options({"key": "fragment_pose", "angle": 30})
    assert len(s.snapshot()["fragments"]) == 1
    for component in ("cup", "stem"):
        choices = [
            i
            for i in planning.ITEMS.values()
            if i["component"] == component and i["side"] in ("both", "left")
        ]
        if choices:
            key = "template_" + component
            c.planning_options({"key": key, "choice": {"id": choices[-1]["id"], "angle": -15}})
            place(c, key, [(53, 44)])
            shell = c._existing_model_for_role("left_" + planning.TOOLS[key][1] + "Outline")
            item = choices[-1]
            assert len(shell.path.points) == (4 if "image" in item else len(item["outline"]))
            assert shell.GetAttribute("PXM.TemplateArtwork") == item.get("image")
    s.settings.pelvic_active_side = "right"
    c.update_derived()
    place(c, "cup_center", [(20, 50), (30, 40), (40, 50)])
    place(c, "implant_head", [(25, 50), (30, 45), (35, 50)])
    assert value("right", "inlay_wear") == 0
    s.settings.pelvic_comments = "Planning, bilateral\nmasked case"
    path = tmp_path / "planning.csv"
    write_case_csv(path, c, s.case_name, "Research Reader")
    append_csv_metadata(path, s.get_settings(), s.image)
    native_rows = list(csv.DictReader(io.StringIO(path.read_text("utf-8-sig"))))
    measure = {r["name"]: r for r in native_rows if r["section"] == "measurement"}
    assert float(measure["Left_PostOp_ProjectedHeadPenetration"]["corrected_value_mm"]) == pytest.approx(6.25)
    assert float(measure["Right_PostOp_ProjectedHeadPenetration"]["raw_value"]) == 0
    assert all("Left_" + suffix in measure for _, suffix, _ in planning.LENGTH_FIELDS)
    _, scene = read_mrb(write_mrb(s.image, c, s.case_name, s.get_settings()))
    before = s.snapshot()
    for saved in [read_csv(shuffle_csv(path.read_bytes())), scene]:
        resumed = open_case()
        resumed.restore(saved)
        again = resumed.snapshot()
        assert again["fragments"] == before["fragments"]
        assert resumed.settings.pelvic_comments == s.settings.pelvic_comments
        for role in (
            "left_cupShellCenter",
            "right_cupShellCenter",
            "left_resectionSteppedOutline",
            "left_planningCupAnchorOutline",
            "left_planningStemAnchorOutline",
        ):

            def coords(snapshot, target):
                return next((m["points"] for m in snapshot["markups"] if m["role"] == target), [])

            np.testing.assert_allclose(coords(again, role), coords(before, role), atol=1e-6)
    place(c, "cup_center", [(15, 20), (20, 20), (25, 20)])
    assert value("right", "inlay_wear") is None
    assert not c.points_for_role("right_inlayWearLine")
    assert value("left", "inlay_wear") == pytest.approx(6.25)


def test_moved_fragment_samples_the_intact_source():
    image = np.arange(256, dtype=np.uint16).reshape(16, 16)
    source = image.copy()
    plan = planning.fragment_projection(
        [(2, 2), (6, 2)], [(6, 6), (2, 6)], [(8, 8)], 0, lambda p: p, (1, 1), rows_down=True
    )
    result = planning.compose_fragments(image, [plan])
    assert result[3, 3] == image.min()
    assert result[9, 7] == source[3, 3]
    np.testing.assert_array_equal(image, source)
    plan = planning.fragment_projection(
        [(2, 2), (6, 2)], [(6, 6), (2, 6)], [(4, 2)], 90, lambda p: p, (2, 1), rows_down=True
    )
    rotated = np.array(plan["matrix"]) @ [5, 2, 1]
    np.testing.assert_allclose(rotated, [4, 4], atol=1e-10)


def test_unavailable_template_does_not_erase_other_measurements():
    s = open_case()
    role = "left_planningStemAnchor"
    saved = {
        "points": {role: [[1, 2, 0]], "referenceLine": [[0, 1, 0], [1, 1, 0]]},
        "settings": {},
        "attributes": {
            role: {planning.TEMPLATE_ATTRIBUTE: json.dumps({"id": "external-unknown", "angle": 5})}
        },
    }
    s.restore(saved)
    assert s.settings.pelvic_template_stem == {"id": "external-unknown", "angle": 5}
    assert s.controller._existing_model_for_role(role + "Outline") is None
    assert len(s.controller.points_for_role("referenceLine")) == 2
