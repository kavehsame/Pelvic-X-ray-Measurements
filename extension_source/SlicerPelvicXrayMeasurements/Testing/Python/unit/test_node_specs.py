"""Unit tests for MRML role and node-spec helpers."""
from __future__ import annotations

from PelvicXrayMeasurementsConstants import (
    ANATOMY_EDGE_CONTOUR_ROLES,
    FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
    MeasurementKey,
    SideKey,
)
from PelvicXrayMeasurementsNodeSpecs import (
    INPUT_NODE_ROLES,
    NODE_SPECS,
    build_bilateral_node_specs,
    other_angle_free_arm_role,
    other_angle_points_role,
    other_angle_reference_arm_role,
    other_line_role,
    other_point_role,
    side_node_name,
    side_role,
)


def test_role_name_helpers() -> None:
    """Role helpers should keep the module's stable naming scheme intact."""

    assert side_role(SideKey.LEFT, "femurHeadPoints") == "left_femurHeadPoints"
    assert side_node_name(SideKey.RIGHT, "Femur Head Points") == "Hip Measurements - Right Femur Head Points"
    assert other_point_role(2) == "otherPoint_2"
    assert other_line_role(3) == "otherLine_3"
    assert other_angle_points_role(4) == "otherAngle_4_points"
    assert other_angle_reference_arm_role(4) == "otherAngle_4_referenceArm"
    assert other_angle_free_arm_role(4) == "otherAngle_4_freeArm"


def test_bilateral_node_specs_include_expected_roles() -> None:
    """The generated bilateral schema should contain representative left/right roles and labels."""

    specs = build_bilateral_node_specs()
    left_head_points = specs["left_femurHeadPoints"]
    right_head_center = specs["right_femurHeadCenter"]
    left_tonnis_line = specs["left_tonnisAngleLine"]
    right_implant_axis = specs["right_implantNeckAxis"]

    assert left_head_points["completionCount"] == 3
    assert left_head_points["labels"][0] == "FemurHead_Left_P1"
    assert right_head_center["labels"] == ["FemurHead_Right_Center"]
    assert left_tonnis_line["name"] == "Hip Measurements - Left Acetabular Index (Tönnis) Line"
    assert right_implant_axis["labels"][0] == "ImplantNeckAxis_Right_Start"


def test_named_edge_contours_are_curve_inputs() -> None:
    """Anatomic contours should be first-class bilateral curve input nodes."""

    for measurement_key in [
        MeasurementKey.ILIOPECTINEAL_LINE,
        MeasurementKey.ILIOISCHIAL_LINE,
        MeasurementKey.SHENTON_LINE,
        MeasurementKey.ACETABULAR_ROOF_SOURCIL,
        MeasurementKey.LINEA_TERMINALIS,
    ]:
        assert measurement_key.value in ANATOMY_EDGE_CONTOUR_ROLES
    for role in ANATOMY_EDGE_CONTOUR_ROLES:
        for side_key in (SideKey.LEFT, SideKey.RIGHT):
            side_specific_role = side_role(side_key, role)
            assert NODE_SPECS[side_specific_role]["className"] == "vtkMRMLMarkupsCurveNode"
            assert side_specific_role in INPUT_NODE_ROLES
    for role in FEMORAL_SHAFT_CONTOUR_BASE_ROLES:
        assert role in ANATOMY_EDGE_CONTOUR_ROLES
