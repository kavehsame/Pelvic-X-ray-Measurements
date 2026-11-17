"""Behavioural checks for import, editing, display and shared CSV compatibility."""

import csv
from copy import deepcopy
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from core import engine
from core.csv_export import FIELDS, write_case_csv
from core.engine import Session
from core.imaging import check_plane
from core.scene_files import append_csv_metadata, read_csv, read_mrb, write_mrb

REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "extension_source/SlicerPelvicXrayMeasurements/Testing/Python/end_to_end_replay/dummy_expected_full_export.csv"
)


def png():
    buffer = io.BytesIO()
    Image.fromarray(np.arange(10000, dtype=np.uint16).reshape(100, 100)).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


@pytest.fixture
def session(tmp_path, monkeypatch):
    s = Session("Test annotator")
    s.open("Synthetic.png", png())
    s.controller.start("reference")
    s.controller.place(20, 40)
    monkeypatch.setattr(engine, "session", s)
    monkeypatch.setattr(engine, "TRANSFER_ROOT", tmp_path)
    return s


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def test_slicer_csv_import_preserves_named_curves_axes_and_calibration():
    raw = REFERENCE.read_bytes()
    saved = read_csv(raw)
    assert len(saved["points"]) == 79
    assert saved["settings"]["axis_options"]["left_neck"] == [True, True]
    assert saved["settings"]["axis_options"]["right_implant_neck"] == [False, True]
    assert saved["curve_types"]["left_iliopectinealLine"] == 1
    assert saved["curve_segments"]["left_iliopectinealLine"] == 30
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    known = next(
        r
        for r in rows
        if r["section"] == "measurement"
        and r["name"] == "CalibrationBall_KnownDiameter"
    )
    assert float(saved["settings"]["ball_diameter"]) == float(
        known["corrected_value_mm"]
    )


def test_browser_csv_without_web_metadata_keeps_axis_options(session, tmp_path):
    session.controller._axis_options["left", "neck"] = (True, True)
    path = tmp_path / "browser.csv"
    write_case_csv(path, session.controller, session.case_name, "Test annotator")
    saved = read_csv(path.read_bytes())
    assert saved["settings"]["axis_options"]["left_neck"] == [True, True]


@pytest.mark.parametrize(
    "settings",
    [
        {"axis_options": {"left_neck": []}},
        {"custom_locks": []},
        {"ball_diameter": "nan"},
        {"window": [0]},
        {"web_layout": {"turns": 0}},
    ],
)
def test_failed_csv_import_keeps_current_scene(session, tmp_path, settings):
    before = deepcopy(session.serialize())
    active = session.controller._active_node
    (tmp_path / "annotations").write_bytes(
        csv_bytes(
            [
                {
                    "section": "metadata",
                    "name": "WebSceneState",
                    "details": json.dumps(settings),
                },
                {
                    "section": "point",
                    "name": "Reference",
                    "role": "referenceLine",
                    "point_index": 1,
                    "r": 99,
                    "a": 88,
                    "s": 0,
                },
            ]
        )
    )
    result = json.loads(engine.dispatch("restore_csv", "{}"))
    assert "error" in result
    assert engine.session is session
    assert session.serialize() == before
    assert session.controller._active_node is active


def test_failed_image_preview_keeps_previous_scene(session, tmp_path, monkeypatch):
    before = deepcopy(session.serialize())
    (tmp_path / "image").write_bytes(png())

    def failed_preview(*args):
        raise ValueError("Cannot render image")

    monkeypatch.setattr(engine, "display_png", failed_preview)
    result = json.loads(engine.dispatch("load", json.dumps({"filename": "Next.png"})))
    assert "error" in result
    assert engine.session is session
    assert session.serialize() == before


def test_window_preview_does_not_commit_or_finish_placement(session, tmp_path):
    before = deepcopy(session.serialize())
    active = session.controller._active_node
    result = engine.operation(
        "preview_window", {"low": 2000, "high": 4000, "invert": False}
    )
    assert Path(result["preview"]).read_bytes().startswith(b"\x89PNG")
    assert session.serialize() == before
    assert session.controller._active_node is active
    engine.operation("window", {"low": 2000, "high": 4000, "invert": False})
    assert (session.low, session.high) == (2000, 4000)
    assert session.controller._active_node is active


@pytest.mark.parametrize(
    "low,high", [(1, 1), (2, 1), (float("nan"), 1), (0, float("inf"))]
)
def test_invalid_window_keeps_display(session, low, high):
    initial = session.low, session.high
    with pytest.raises(ValueError):
        engine.operation("window", {"low": low, "high": high, "invert": False})
    assert (session.low, session.high) == initial


def test_hidden_custom_measurements_survive_csv_and_scene_resume(session, tmp_path):
    session.controller.finish()
    session.controller.add_custom("line")
    session.controller.place(20, 20)
    session.controller.place(60, 60)
    engine.operation("hide", {"key": "other_line", "hidden": True})
    path = tmp_path / "hidden.csv"
    write_case_csv(path, session.controller, session.case_name, "Test annotator")
    append_csv_metadata(path, session.get_settings(), session.base_image)
    _, mrb = read_mrb(
        write_mrb(
            session.image, session.controller, session.case_name, session.get_settings()
        )
    )
    for saved in (read_csv(path.read_bytes()), mrb):
        restored = Session()
        restored.open("Synthetic.png", png())
        restored.restore(saved)
        assert restored.settings.pelvic_hide_other_line
        assert not restored.controller.node_for_role("otherLine_1").visible


@pytest.mark.parametrize("sizes", [(1, 50), (40, 40, 2), (20000, 2), (8000, 8000)])
def test_out_of_scope_images_are_rejected_before_allocation(sizes):
    with pytest.raises(ValueError):
        check_plane(sizes)


@pytest.mark.parametrize(
    "coordinates",
    [
        [(1, 1, 2, 0), (1, 2, 3, 0)],
        [(2, 1, 2, 0)],
        [(1, float("nan"), 2, 0)],
    ],
)
def test_invalid_csv_coordinates_are_rejected(coordinates):
    raw = csv_bytes(
        [
            {
                "section": "point",
                "name": "Reference",
                "role": "referenceLine",
                "point_index": i,
                "r": x,
                "a": y,
                "s": z,
            }
            for i, x, y, z in coordinates
        ]
    )
    with pytest.raises(ValueError):
        read_csv(raw)
