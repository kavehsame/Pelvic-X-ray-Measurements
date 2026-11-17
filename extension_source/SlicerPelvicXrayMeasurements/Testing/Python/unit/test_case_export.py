"""Unit tests for Slicer-independent pieces of case export."""
from __future__ import annotations

import sys
from types import SimpleNamespace


sys.modules.setdefault(
    "slicer",
    SimpleNamespace(util=SimpleNamespace(saveScene=lambda _path: True)),
)

from PelvicXrayMeasurementsCaseExport import CaseExportMixin


class FakeVtkPoints:
    """Small vtkPoints stand-in for sampled curve export tests."""

    def __init__(self, points: list[tuple[float, float, float]]) -> None:
        self._points = points

    def GetNumberOfPoints(self) -> int:
        return len(self._points)

    def GetPoint(self, index: int) -> tuple[float, float, float]:
        return self._points[index]


class FakeCurveNode:
    """Small Slicer curve-node stand-in for export tests."""

    def __init__(
        self,
        name: str,
        control_points: list[tuple[float, float, float]],
        curve_points: list[tuple[float, float, float]],
    ) -> None:
        self._name = name
        self._control_points = control_points
        self._curve_points = FakeVtkPoints(curve_points)

    def IsA(self, class_name: str) -> bool:
        return class_name in {"vtkMRMLMarkupsNode", "vtkMRMLMarkupsCurveNode"}

    def GetName(self) -> str:
        return self._name

    def GetCurveType(self) -> int:
        return 2

    def GetCurveTypeAsString(self, _curve_type: int | None=None) -> str:
        return "CardinalSpline"

    def GetNumberOfPointsPerInterpolatingSegment(self) -> int:
        return 12

    def GetCurvePointsWorld(self) -> FakeVtkPoints:
        return self._curve_points

    def GetNumberOfDefinedControlPoints(self) -> int:
        return len(self._control_points)

    def GetNthControlPointLabel(self, index: int) -> str:
        return f"P{index + 1}"


class FakeImageNode:
    """Small image-node stand-in for export naming tests."""

    def __init__(self, name: str) -> None:
        self._name = name

    def GetName(self) -> str:
        return self._name


class FakeExportLogic(CaseExportMixin):
    """CaseExportMixin harness with only the Slicer-facing pieces stubbed."""

    def __init__(self, nodes: dict[str, FakeCurveNode]) -> None:
        self._nodes = nodes

    def _all_node_roles(self) -> list[str]:
        return list(self._nodes)

    def get_node(self, role: str, create_if_missing: bool=False) -> FakeCurveNode | None:
        return self._nodes.get(role)

    def _defined_points(self, node: FakeCurveNode | None) -> list[tuple[float, float, float]]:
        if node is None:
            return []
        return node._control_points

    def update_all_derived_measurements(self, _image_node: object=None) -> None:
        return None


def test_curve_control_point_rows_include_reconstruction_settings() -> None:
    """Curve control-point CSV rows should carry the settings needed to recreate interpolation."""

    logic = FakeExportLogic(
        {
            "leftIliopectinealLine": FakeCurveNode(
                "Left_Iliopectineal_Line",
                [(1.0, 2.0, 3.0)],
                [(1.0, 2.0, 3.0), (1.5, 2.5, 3.5)],
            )
        }
    )

    rows = logic._point_rows_for_role("leftIliopectinealLine")

    assert rows[0]["curve_type"] == "CardinalSpline"
    assert rows[0]["curve_points_per_segment"] == 12


def test_curve_points_txt_export_uses_slicer_sampled_curve_points() -> None:
    """The TXT companion should export generated curve points, not only placed control points."""

    logic = FakeExportLogic(
        {
            "rightShentonLine": FakeCurveNode(
                "Right_Shenton_Line",
                [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
                [(1.0, 2.0, 3.0), (2.5, 3.5, 4.5), (4.0, 5.0, 6.0)],
            )
        }
    )

    text = logic._curve_points_txt_export_text(FakeImageNode("Example Case.dcm"))

    assert "ImageNode: Example Case.dcm" in text
    assert "Role: rightShentonLine" in text
    assert "CurveType: CardinalSpline" in text
    assert "PointsPerInterpolatingSegment: 12" in text
    assert "ControlPointCount: 2" in text
    assert "CurvePointCount: 3" in text
    assert "1\t2.500000\t3.500000\t4.500000" in text


def test_curve_points_txt_versions_with_csv_when_txt_exists(tmp_path) -> None:
    """When exporting CSV plus TXT, either existing file should push the pair to a new suffix."""

    logic = FakeExportLogic({})
    image_node = FakeImageNode("Example Case.dcm")
    default_txt_path = logic.default_curve_points_txt_path(tmp_path, image_node)
    with open(default_txt_path, "w", encoding="utf-8") as stream:
        stream.write("old curve points")

    csv_path, txt_path = logic.csv_and_curve_points_txt_output_paths(
        tmp_path,
        image_node,
        conflict_policy="version",
    )

    assert csv_path.endswith("Example_Case.dcm_measurements_2.csv")
    assert txt_path.endswith("Example_Case.dcm_measurements_2_curve_points.txt")
