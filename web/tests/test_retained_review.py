"""Geometry and local session contract for retained-bone extraction and reviewed implants."""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from core import planning
from test_planning import open_case, place


@pytest.mark.parametrize("sign,side", [(1, "left"), (-1, "right")])
def test_trochanter_and_shaft_clearance_goes_to_edge(sign, side):
    mirror = lambda xy: np.column_stack(
        ((np.asarray(xy)[:, 0] - 50) * sign + 50, np.asarray(xy)[:, 1])
    )
    cut = mirror([[43, 35], [47, 32], [54, 31]])
    boundary = planning.retained_boundary(
        cut,
        (100, 120),
        (0.7, 1.2),
        side=side,
        lesser=mirror([[39, 43], [38, 50]]),
        shaft=mirror([[46, 89], [68, 89]]),
        cortex=mirror([[67, 14], [36, 99]]),
    )
    limits = mirror(boundary)
    assert limits[0, 1] < 14 and limits[1, 0] >= 100 and limits[2, 1] >= 120
    assert limits[-1, 0] < 38 and limits[-1, 1] > 50
    assert limits[0, 0] > 54 and limits[-2, 0] < limits[-1, 0]
    vertical = planning.retained_boundary(
        cut[:, ::-1],
        (120, 100),
        (1.2, 0.7),
        side=side,
        lesser=mirror([[39, 43], [38, 50]])[:, ::-1],
        shaft=mirror([[46, 89], [68, 89]])[:, ::-1],
        cortex=mirror([[67, 14], [36, 99]])[:, ::-1],
    )
    np.testing.assert_allclose(np.asarray(vertical)[:, ::-1], boundary)
    np.testing.assert_allclose(mirror(mirror(cut)), cut)


def test_medial_head_offset_does_not_turn_the_shaft_sideways():
    boundary = np.asarray(
        planning.retained_boundary(
            [[45, 32], [55, 32]], (100, 100), (1, 1), side="left", head=[[30, 25]]
        )
    )
    np.testing.assert_allclose(boundary[2], [100, 100])
    assert boundary[1, 0] == 100 and boundary[1, 1] < 32
    assert boundary[-2, 1] == 100 and boundary[-1, 1] > 32


def test_cut_choice_reset_and_manual_outside():
    s = open_case()
    c = s.controller
    place(c, "stepped_resection", [(35, 28), (40, 33), (50, 30)])
    c.retained_bone()
    snap = s.snapshot()
    assert len(snap["fragments"]) == 1 and not any(
        m["role"].endswith("fragmentBoundary") for m in snap["markups"]
    )
    np.testing.assert_array_equal(
        s.image.pixels, planning.compose_fragments(s.image.pixels, snap["fragments"])
    )
    assert c.fragment_options("left")[0] == "stepped"
    c.retained_bone()
    assert not s.snapshot()["fragments"]
    assert len(c.points_for_role("left_resectionStepped")) == 3
    place(c, "straight_resection", [(36, 26), (51, 27)])
    with pytest.raises(ValueError, match="Choose"):
        c.retained_bone()
    c.retained_bone("manual", "stepped")
    assert c.place(104, 14) and c.place(105, 104) and c.place(15, 103)
    c.expire_placement()
    f = s.snapshot()["fragments"][0]
    np.testing.assert_allclose(f["polygon"][:3], [(35, 28), (40, 33), (50, 30)])
    np.testing.assert_allclose(f["polygon"][-3:], [(104, 14), (105, 104), (15, 103)])
    assert not s.snapshot()["active_role"]
    c.move("left_fragmentTarget", 0, 67, 42)
    assert not np.allclose(
        s.snapshot()["fragments"][0]["matrix"], [[1, 0, 0], [0, 1, 0]]
    )


@pytest.mark.parametrize("side", ["left", "right"])
def test_fragment_handle_follows_saved_angle_and_pivot(side):
    s = open_case()
    c = s.controller
    s.settings.pelvic_active_side = side
    c.update_derived()
    place(c, "straight_resection", [(40, 29), (55, 34)])
    c.retained_bone()
    role = f"{side}_fragmentTarget"
    assert c.move(role, 0, 63.5, 54)
    initial = s.snapshot()
    pivot = np.asarray(initial["rotation_handles"][role][0])
    source = np.mean(initial["fragments"][0]["polygon"][:2], axis=0)
    for value in (85.5, -137.3):
        angle = np.radians(value)
        pointer = pivot + 18 * np.array([np.cos(angle), np.sin(angle)])
        assert c.move(role + "Rotation", 0, *pointer)
        snap = s.snapshot()
        assert snap["state"]["pelvic_fragment_angle"] == pytest.approx(value)
        np.testing.assert_allclose(snap["rotation_handles"][role][0], pivot)
        matrix = np.asarray(snap["fragments"][0]["matrix"])
        np.testing.assert_allclose(matrix[:, :2] @ source + matrix[:, 2], pivot)
        np.testing.assert_allclose(matrix[:, 0], [np.cos(angle), np.sin(angle)])
        c.planning_options({"key": "fragment_pose", "angle": value})
        np.testing.assert_allclose(s.snapshot()["fragments"][0]["matrix"], matrix)
    saved = s.serialize()
    saved["settings"]["hidden_workflows"] = ["fragment_pose"]
    s.restore(saved)
    assert (
        s.snapshot()["state"]["pelvic_hide_bone_fragment"]
        and role not in s.snapshot()["rotation_handles"]
    )
    c.set_workflow_hidden("bone_fragment", False)
    resumed = s.snapshot()
    np.testing.assert_allclose(resumed["fragments"][0]["matrix"], matrix)
    assert resumed["state"]["pelvic_fragment_angle"] == pytest.approx(value)
    c.retained_bone()
    assert role not in s.snapshot()["rotation_handles"]


def test_fragment_rotation_preserves_handedness_after_mirrored_import():
    s = open_case()
    c = s.controller
    place(c, "straight_resection", [(40, 35), (55, 32)])
    c.retained_bone()
    role = "left_fragmentTarget"
    node = c.node_for_role(role)
    node.SetAttribute(planning.VIEW_AXES, json.dumps([[1, 0, 0], [0, 1, 0]]))
    before = s.snapshot()["rotation_handles"][role]
    pivot = np.array(before[0])
    # The stored positive-x ray points left on this film. A clockwise quarter-turn ends above it.
    assert before[1][0] < before[0][0]
    assert c.move(role + "Rotation", 0, pivot[0], pivot[1] - 20)
    snap = s.snapshot()
    assert snap["state"]["pelvic_fragment_angle"] == pytest.approx(-90)
    np.testing.assert_allclose(
        np.array(snap["fragments"][0]["matrix"])[:, 0], [0, 1], atol=1e-8
    )
    assert snap["rotation_handles"][role][1][1] < pivot[1]


def test_session_pack_validation_is_atomic_and_idempotent(monkeypatch):
    monkeypatch.setattr(planning, "ITEMS", dict(planning.ITEMS))
    monkeypatch.setattr(planning, "CATALOG", deepcopy(planning.CATALOG))
    pack = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/overlay-example.json").read_text()
    )
    pack["items"][0]["pivot"] = [2, 3]
    ident = pack["items"][0]["id"]
    assert planning.import_overlays(json.dumps(pack)) == 1
    assert planning.import_overlays(json.dumps(pack)) == 1
    assert planning.ITEMS[ident]["outline"][0] == [-8, 2]
    for change in (
        {"outline": [[0, 0], [1, 1], [2, 2], [0, 0]]},
        {"outline": [[0, 0], [0, 3], [3, 3], [4, 0]]},
        {"outline": [[0, 0], [5, 5], [0, 6], [7, 0], [0, 0]]},
        {"side": "unspecified"},
        {"pivot": [float("nan"), 0]},
        {"source": ""},
    ):
        bad = deepcopy(pack)
        bad["items"][0].update(change)
        bad["items"].insert(0, {**pack["items"][0], "id": "synthetic/transaction"})
        with pytest.raises(ValueError):
            planning.import_overlays(json.dumps(bad))
        assert "synthetic/transaction" not in planning.ITEMS
    collision = deepcopy(pack)
    collision["items"][0]["size"] = "two"
    with pytest.raises(ValueError, match="different template"):
        planning.import_overlays(json.dumps(collision))
