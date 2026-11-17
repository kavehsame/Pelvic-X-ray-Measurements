"""Unit tests for opportunistic shared-landmark seeding."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import numpy as np


sys.modules.setdefault("slicer", SimpleNamespace())

from PelvicXrayMeasurementsConstants import SideKey
from PelvicXrayMeasurementsWorkflow import WorkflowActionsMixin


class FakeMarkupNode:
    """Small markups-node stand-in for workflow seeding tests."""

    def __init__(self, points: list[Any] | None=None) -> None:
        self.points = [np.asarray(point, dtype=float) for point in (points or [])]
        self.labels: list[str] = []
        self.visible = False
        self.selectable = False
        self.locked = True
        self.point_locks: list[bool] = [True for _point in self.points]
        self.display_node = SimpleNamespace(
            selectable=False,
            visible=False,
            visible_2d=False,
            handles_interactive=False,
            translation_handle_visible=False,
            rotation_handle_visible=True,
            scale_handle_visible=True,
            interaction_handle_scale=0.0,
            SetSelectable=lambda value: setattr(self.display_node, "selectable", bool(value)),
            SetVisibility=lambda value: setattr(self.display_node, "visible", bool(value)),
            SetVisibility2D=lambda value: setattr(self.display_node, "visible_2d", bool(value)),
            SetHandlesInteractive=lambda value: setattr(self.display_node, "handles_interactive", bool(value)),
            SetTranslationHandleVisibility=(
                lambda value: setattr(self.display_node, "translation_handle_visible", bool(value))
            ),
            SetRotationHandleVisibility=(
                lambda value: setattr(self.display_node, "rotation_handle_visible", bool(value))
            ),
            SetScaleHandleVisibility=(
                lambda value: setattr(self.display_node, "scale_handle_visible", bool(value))
            ),
            SetInteractionHandleScale=(
                lambda value: setattr(self.display_node, "interaction_handle_scale", float(value))
            ),
        )

    def IsA(self, class_name: str) -> bool:
        return class_name == "vtkMRMLMarkupsNode"

    def GetNumberOfDefinedControlPoints(self) -> int:
        return len(self.points)

    def SetDisplayVisibility(self, visible: bool) -> None:
        self.visible = bool(visible)

    def SetSelectable(self, selectable: bool) -> None:
        self.selectable = bool(selectable)

    def SetLocked(self, locked: bool) -> None:
        self.locked = bool(locked)

    def SetNthControlPointLocked(self, index: int, locked: bool) -> None:
        while len(self.point_locks) < len(self.points):
            self.point_locks.append(True)
        self.point_locks[index] = bool(locked)

    def GetNumberOfControlPoints(self) -> int:
        return len(self.points)

    def GetDisplayNode(self) -> Any:
        return self.display_node


class FakeLogic:
    """Logic shim exposing only the private helpers used by WorkflowActionsMixin."""

    def __init__(self) -> None:
        self.nodes: dict[str, FakeMarkupNode] = {}
        self.latest_results = {
            "referenceLine": {
                "defined": True,
                "direction": np.array([1.0, 0.0, 0.0]),
                "points": [np.array([0.0, 0.0, 0.0]), np.array([100.0, 0.0, 0.0])],
            },
            "sides": {
                SideKey.LEFT: {
                    "femurHead": {
                        "defined": True,
                        "center": np.array([10.0, 0.0, 0.0]),
                        "rawValue": 20.0,
                    },
                    "femoralShaftAxis": {
                        "defined": True,
                        "direction": np.array([0.0, 1.0, 0.0]),
                    },
                }
            },
        }

    def side_role(self, base_role: str, side_key: Any) -> str:
        return f"{str(side_key)}_{base_role}"

    def get_node(self, role: str, create_if_missing: bool=False) -> FakeMarkupNode | None:
        if role not in self.nodes and create_if_missing:
            self.nodes[role] = FakeMarkupNode()
        return self.nodes.get(role)

    def _defined_points(self, node: FakeMarkupNode | None) -> list[np.ndarray]:
        return [] if node is None else list(node.points)

    def _node_spec_for_role(self, _role: str) -> dict[str, list[str]]:
        return {"labels": ["A", "B"]}

    def _set_named_points(self, node: FakeMarkupNode, points: list[Any], labels: list[str]) -> None:
        node.points = [np.asarray(point, dtype=float) for point in points]
        node.labels = list(labels[: len(points)])
        node.point_locks = [True for _point in node.points]

    def _display_span(self, _image_node: Any, _fallback_points: list[Any]) -> float:
        return 1000.0


class WorkflowHarness(WorkflowActionsMixin):
    """Workflow mixin harness with no Qt/Slicer dependencies."""

    def __init__(self) -> None:
        self.logic = FakeLogic()
        self.pending_auto_line_endpoints: dict[str, np.ndarray] = {}

    def current_image_node(self) -> None:
        return None


def test_sharp_line_seeds_from_offset_teardrop_and_known_lateral_sourcil() -> None:
    """Sharp can be fully seeded only when the teardrop and lateral sourcil are both known."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_acetabularOffsetLineA"] = FakeMarkupNode(
        [
            np.array([2.0, -7.0, 0.0]),
            np.array([2.0, 13.0, 0.0]),
        ]
    )
    harness.logic.nodes["left_tonnisAngleLine"] = FakeMarkupNode(
        [
            np.array([6.0, 3.0, 0.0]),
            np.array([20.0, 8.0, 0.0]),
        ]
    )

    assert harness._seed_acetabular_angle_line("sharpAngleLine", SideKey.LEFT)

    seeded = harness.logic.nodes["left_sharpAngleLine"]
    np.testing.assert_allclose(seeded.points[0], np.array([2.0, 3.0, 0.0]))
    np.testing.assert_allclose(seeded.points[1], np.array([20.0, 8.0, 0.0]))
    assert seeded.visible


def test_existing_seed_target_is_not_overwritten() -> None:
    """Smart seeding must never replace a partially or fully user-edited target."""

    harness = WorkflowHarness()
    target = FakeMarkupNode([np.array([9.0, 9.0, 0.0])])
    harness.logic.nodes["left_tonnisAngleLine"] = target
    harness.logic.nodes["left_sharpAngleLine"] = FakeMarkupNode(
        [
            np.array([2.0, 3.0, 0.0]),
            np.array([20.0, 8.0, 0.0]),
        ]
    )

    assert not harness._seed_acetabular_angle_line("tonnisAngleLine", SideKey.LEFT)

    np.testing.assert_allclose(target.points[0], np.array([9.0, 9.0, 0.0]))


def test_acetabular_angle_line_does_not_seed_from_lateral_sourcil_only() -> None:
    """Sharp/Tonnis-style lines need both the teardrop and lateral sourcil."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_lceAnglePoint"] = FakeMarkupNode([np.array([20.0, 8.0, 0.0])])

    assert not harness._seed_acetabular_angle_line("sharpAngleLine", SideKey.LEFT)
    assert "left_sharpAngleLine" not in harness.logic.nodes


def test_seeded_markup_is_explicitly_editable() -> None:
    """Programmatically inserted user markups should be unlocked and interactable."""

    harness = WorkflowHarness()

    assert harness._seed_side_role_if_empty(
        "femoralOffsetLine",
        SideKey.LEFT,
        [np.array([0.0, -1.0, 0.0]), np.array([0.0, 1.0, 0.0])],
    )

    node = harness.logic.nodes["left_femoralOffsetLine"]
    assert node.selectable
    assert not node.locked
    assert node.point_locks == [False, False]
    assert node.visible
    assert node.display_node.selectable
    assert node.display_node.visible
    assert node.display_node.visible_2d
    assert not node.display_node.handles_interactive
    assert not node.display_node.translation_handle_visible
    assert not node.display_node.rotation_handle_visible
    assert not node.display_node.scale_handle_visible
    assert node.display_node.interaction_handle_scale == 0.0


def test_pending_lateral_sourcil_completes_angle_line_after_base_point() -> None:
    """If only the lateral sourcil is known, one user base point should complete the line."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_lceAnglePoint"] = FakeMarkupNode([np.array([20.0, 8.0, 0.0])])

    assert harness._queue_acetabular_angle_lateral_endpoint("sharpAngleLine", SideKey.LEFT)
    harness.logic.nodes["left_sharpAngleLine"] = FakeMarkupNode([np.array([2.0, 3.0, 0.0])])

    assert harness._complete_pending_auto_line_endpoint("left_sharpAngleLine")

    points = harness.logic.nodes["left_sharpAngleLine"].points
    np.testing.assert_allclose(points[0], np.array([2.0, 3.0, 0.0]))
    np.testing.assert_allclose(points[1], np.array([20.0, 8.0, 0.0]))
    assert harness.pending_auto_line_endpoints == {}


def test_sharp_queues_lateral_sourcil_from_tonnis_without_using_tonnis_base() -> None:
    """Tonnis base is medial sourcil, so Sharp should still ask for teardrop."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_tonnisAngleLine"] = FakeMarkupNode(
        [
            np.array([6.0, 3.0, 0.0]),
            np.array([20.0, 8.0, 0.0]),
        ]
    )

    assert not harness._seed_acetabular_angle_line("sharpAngleLine", SideKey.LEFT)
    assert harness._queue_acetabular_angle_lateral_endpoint("sharpAngleLine", SideKey.LEFT)
    np.testing.assert_allclose(
        harness.pending_auto_line_endpoints["left_sharpAngleLine"],
        np.array([20.0, 8.0, 0.0]),
    )


def test_tonnis_queues_lateral_sourcil_from_sharp_without_using_sharp_teardrop() -> None:
    """Sharp base is teardrop, so Tonnis should still ask for medial sourcil."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_sharpAngleLine"] = FakeMarkupNode(
        [
            np.array([2.0, 3.0, 0.0]),
            np.array([20.0, 8.0, 0.0]),
        ]
    )

    assert not harness._seed_acetabular_angle_line("tonnisAngleLine", SideKey.LEFT)
    assert harness._queue_acetabular_angle_lateral_endpoint("tonnisAngleLine", SideKey.LEFT)
    np.testing.assert_allclose(
        harness.pending_auto_line_endpoints["left_tonnisAngleLine"],
        np.array([20.0, 8.0, 0.0]),
    )


def test_acetabular_offset_uses_sharp_base_and_femur_center() -> None:
    """Sharp's teardrop and the fitted femur center should seed both acetabular offset lines."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_sharpAngleLine"] = FakeMarkupNode(
        [
            np.array([2.0, 3.0, 0.0]),
            np.array([20.0, 8.0, 0.0]),
        ]
    )

    assert harness._seed_acetabular_offset_lines(SideKey.LEFT)

    teardrop_line = harness.logic.nodes["left_acetabularOffsetLineA"].points
    center_line = harness.logic.nodes["left_acetabularOffsetLineB"].points
    np.testing.assert_allclose(0.5 * (teardrop_line[0] + teardrop_line[1]), np.array([2.0, 3.0, 0.0]))
    np.testing.assert_allclose(0.5 * (center_line[0] + center_line[1]), np.array([10.0, 0.0, 0.0]))


def test_acetabular_offset_does_not_use_tonnis_base_as_teardrop() -> None:
    """Acetabular offset must not treat the Tonnis medial sourcil as the teardrop."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_tonnisAngleLine"] = FakeMarkupNode(
        [
            np.array([6.0, 3.0, 0.0]),
            np.array([20.0, 8.0, 0.0]),
        ]
    )

    assert harness._seed_acetabular_offset_lines(SideKey.LEFT)

    assert "left_acetabularOffsetLineA" not in harness.logic.nodes
    center_line = harness.logic.nodes["left_acetabularOffsetLineB"].points
    np.testing.assert_allclose(0.5 * (center_line[0] + center_line[1]), np.array([10.0, 0.0, 0.0]))


def test_extrusion_index_seeds_from_head_circle_and_lateral_sourcil() -> None:
    """FEI should reuse head-circle tangents and the known lateral sourcil line station."""

    harness = WorkflowHarness()
    harness.logic.nodes["left_lceAnglePoint"] = FakeMarkupNode([np.array([30.0, 5.0, 0.0])])

    assert harness._seed_extrusion_index_lines(SideKey.LEFT)

    medial = harness.logic.nodes["left_extrusionIndexMedialLine"].points
    middle = harness.logic.nodes["left_extrusionIndexMiddleLine"].points
    lateral = harness.logic.nodes["left_extrusionIndexLateralLine"].points

    np.testing.assert_allclose(0.5 * (medial[0] + medial[1]), np.array([0.0, 0.0, 0.0]))
    np.testing.assert_allclose(0.5 * (middle[0] + middle[1]), np.array([30.0, 5.0, 0.0]))
    np.testing.assert_allclose(0.5 * (lateral[0] + lateral[1]), np.array([20.0, 0.0, 0.0]))
    np.testing.assert_allclose(medial[1] - medial[0], np.array([0.0, 240.0, 0.0]))


def test_femoral_offset_seeds_through_femur_center_parallel_to_shaft() -> None:
    """Femoral offset should get an editable shaft-parallel line through the fitted head center."""

    harness = WorkflowHarness()

    assert harness._seed_femoral_offset_line(SideKey.LEFT)

    points = harness.logic.nodes["left_femoralOffsetLine"].points
    np.testing.assert_allclose(0.5 * (points[0] + points[1]), np.array([10.0, 0.0, 0.0]))
    np.testing.assert_allclose(points[1] - points[0], np.array([0.0, 240.0, 0.0]))
