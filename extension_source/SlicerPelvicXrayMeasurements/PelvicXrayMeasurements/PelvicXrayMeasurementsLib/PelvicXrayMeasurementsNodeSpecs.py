"""MRML node role naming and node specifications for Pelvic X-ray Measurements.

This module owns the declarative scene-node schema. Separating it from measurement logic follows the
single-responsibility principle: geometry code computes values, while this file describes which MRML
nodes exist and how they should be labelled.
"""
from __future__ import annotations

from PelvicXrayMeasurementsConstants import (
    ACTIVE_SIDE_BADGE_ROLE,
    FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
    FEMORAL_SHAFT_CONTOUR_CLASS_LABELS,
    FEMUR_SHAFT_MORPHOLOGY_LAYOUT,
    SIDE_KEYS,
    SIDE_LABELS,
)

from PelvicXrayMeasurementsPlanning import TOOLS, node_specs

NodeSpec = dict[str, object]
NodeSpecMap = dict[str, NodeSpec]


def side_role(side_key: str, base_role: str) -> str:
    """Build the canonical MRML role name for one bilateral node. Using a deterministic side-prefixed
    role lets the logic find or recreate nodes safely across reloads and scene saves.
    """

    return f"{side_key}_{base_role}"


def side_node_name(side_key: str, label: str) -> str:
    """Build a human-readable MRML node name for one bilateral node. The displayed name stays
    descriptive for users while the internal role remains machine-stable.
    """

    return f"Hip Measurements - {SIDE_LABELS[side_key]} {label}"


def other_line_role(index: int) -> str:
    """Return the role string for one user-added free line. Numbered roles let the module keep repeated
    ad hoc measurements separate without special-case storage.
    """

    return f"otherLine_{int(index)}"


def other_point_role(index: int) -> str:
    """Return the role string for one user-added labelled point."""

    return f"otherPoint_{int(index)}"


def other_angle_points_role(index: int) -> str:
    """Return the role string for the point container of one user-added free angle. The points are
    stored separately from the derived arms so the editable input stays distinct from the visual
    construction.
    """

    return f"otherAngle_{int(index)}_points"


def other_angle_reference_arm_role(index: int) -> str:
    """Return the role string for the derived reference arm of one user-added free angle. Keeping this
    arm separate makes locked-angle visualization possible without overwriting the user points.
    """

    return f"otherAngle_{int(index)}_referenceArm"


def other_angle_free_arm_role(index: int) -> str:
    """Return the role string for the second derived arm of one user-added free angle. The extra role
    keeps export, visibility, and redraw logic consistent with the rest of the module.
    """

    return f"otherAngle_{int(index)}_freeArm"

NODE_SPECS = {
    "moduleMetadata": {
        "className": "vtkMRMLScriptedModuleNode",
        "name": "Hip Measurements - Case Metadata",
        "color": (0.0, 0.0, 0.0),
        "hideFromEditors": True,
    },
    ACTIVE_SIDE_BADGE_ROLE: {
        "className": "vtkMRMLMarkupsFiducialNode",
        "name": "Pelvic Xray Measurements - Active Side Badge",
        "color": (0.12, 0.44, 0.90),
        "labels": ["ACTIVE SIDE"],
        "pointLabelsVisible": True,
        "glyphScale": 0.8,
        "textScale": 4.0,
    },
    "calibrationPoints": {
        "className": "vtkMRMLMarkupsFiducialNode",
        "name": "Hip Measurements - Calibration Ball Points",
        "color": (0.98, 0.62, 0.12),
        "completionCount": 3,
        "labels": ["CalibrationBall_P1", "CalibrationBall_P2", "CalibrationBall_P3"],
    },
    "calibrationCircle": {
        "className": "vtkMRMLModelNode",
        "name": "Hip Measurements - Calibration Ball Circle",
        "color": (0.98, 0.62, 0.12),
    },
    "referenceLine": {
        "className": "vtkMRMLMarkupsLineNode",
        "name": "Hip Measurements - Reference Line",
        "color": (0.25, 0.63, 0.96),
        "labels": ["ReferenceLine_Start", "ReferenceLine_End"],
    },
    "lldPoints": {
        "className": "vtkMRMLMarkupsFiducialNode",
        "name": "Hip Measurements - Minor Trochanter Points",
        "color": (0.93, 0.25, 0.48),
        "completionCount": 2,
        "labels": ["MinorTrochanter_P1", "MinorTrochanter_P2"],
    },
    "lldLeftProjection": {
        "className": "vtkMRMLModelNode",
        "name": "Hip Measurements - LLD Left Projection",
        "color": (0.93, 0.25, 0.48),
    },
    "lldRightProjection": {
        "className": "vtkMRMLModelNode",
        "name": "Hip Measurements - LLD Right Projection",
        "color": (0.93, 0.25, 0.48),
    },
    "lldLeftParallel": {
        "className": "vtkMRMLMarkupsLineNode",
        "name": "Hip Measurements - LLD Left Parallel Line",
        "color": (0.93, 0.25, 0.48),
        "labels": ["LLD_LeftParallel_Start", "LLD_LeftParallel_End"],
        "locked": True,
    },
    "lldRightParallel": {
        "className": "vtkMRMLMarkupsLineNode",
        "name": "Hip Measurements - LLD Right Parallel Line",
        "color": (0.93, 0.25, 0.48),
        "labels": ["LLD_RightParallel_Start", "LLD_RightParallel_End"],
        "locked": True,
    },
    "lldHeightDifference": {
        "className": "vtkMRMLMarkupsLineNode",
        "name": "Hip Measurements - LLD Height Difference",
        "color": (0.98, 0.55, 0.18),
        "labels": ["LLD_Difference_Start", "LLD_Difference_End"],
        "locked": True,
    },
}

BILATERAL_INPUT_BASE_ROLES = [
    *(spec[1] for spec in TOOLS.values()),
    "femurHeadPoints",
    "implantHeadPoints",
    "shaftGuideProximal",
    "shaftGuideDistal",
    "neckGuideProximal",
    "neckGuideDistal",
    "implantNeckGuideProximal",
    "implantNeckGuideDistal",
    "acetabularOffsetLineA",
    "acetabularOffsetLineB",
    "femoralOffsetLine",
    "extrusionIndexMedialLine",
    "extrusionIndexMiddleLine",
    "extrusionIndexLateralLine",
    "shaftMorphologyLTPoints",
    "shaftMorphologyPoints",
    "acetabularInclinationLine",
    "cupOpeningEllipsePoints",
    "cupOpeningEllipseMajorDiameter",
    "cupOpeningEllipseMinorDiameter",
    "postOpAcetabularOffsetLineA",
    "postOpAcetabularOffsetLineB",
    "postOpFemoralOffsetLine",
    "implantAlignmentGuideProximal",
    "implantAlignmentGuideDistal",
    "tonnisAngleLine",
    "sharpAngleLine",
    "lceAnglePoint",
    "iliopectinealLine",
    "ilioischialLine",
    "shentonLine",
    "acetabularRoofSourcil",
    "anteriorAcetabularWall",
    "posteriorAcetabularWall",
    "lineaTerminalis",
    *FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
]


def build_bilateral_node_specs() -> NodeSpecMap:
    """Generate the MRML node specifications for every left and right measurement node. Building these
    specs programmatically keeps bilateral tools symmetrical and reduces hand-maintained
    duplication.
    """

    specs: NodeSpecMap = {}
    for side_key, side_label in SIDE_LABELS.items():
        specs.update(node_specs(side_key))
        specs.update(_head_node_specs(side_key, side_label))
        specs.update(_axis_node_specs(side_key, side_label))
        specs.update(_offset_and_extrusion_node_specs(side_key, side_label))
        specs.update(_shaft_morphology_node_specs(side_key, side_label))
        specs.update(_cup_and_postop_node_specs(side_key, side_label))
        specs.update(_edge_contour_node_specs(side_key, side_label))
        specs.update(_angle_node_specs(side_key, side_label))
    return specs


def _edge_contour_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral open-curve node specs for pelvis edge-contour annotations."""

    specs = {
        side_role(side_key, "iliopectinealLine"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Iliopectineal Line"),
            "color": (0.78, 0.38, 0.92),
            "labelPrefix": f"IliopectinealLine_{side_label}",
            "glyphScale": 1.2,
        },
        side_role(side_key, "ilioischialLine"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Ilioischial Line"),
            "color": (0.18, 0.70, 0.72),
            "labelPrefix": f"IlioischialLine_{side_label}",
            "glyphScale": 1.2,
        },
        side_role(side_key, "shentonLine"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Shenton Line"),
            "color": (0.90, 0.48, 0.20),
            "labelPrefix": f"ShentonLine_{side_label}",
            "glyphScale": 1.2,
        },
        side_role(side_key, "acetabularRoofSourcil"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Acetabular Roof (Sourcil)"),
            "color": (0.32, 0.58, 0.95),
            "labelPrefix": f"AcetabularRoofSourcil_{side_label}",
            "glyphScale": 1.2,
        },
        side_role(side_key, "anteriorAcetabularWall"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Anterior Acetabular Wall"),
            "color": (0.98, 0.82, 0.22),
            "labelPrefix": f"AnteriorAcetabularWall_{side_label}",
            "glyphScale": 1.2,
        },
        side_role(side_key, "posteriorAcetabularWall"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Posterior Acetabular Wall"),
            "color": (0.98, 0.32, 0.68),
            "labelPrefix": f"PosteriorAcetabularWall_{side_label}",
            "glyphScale": 1.2,
        },
        side_role(side_key, "lineaTerminalis"): {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, "Linea Terminalis"),
            "color": (0.52, 0.74, 0.25),
            "labelPrefix": f"LineaTerminalis_{side_label}",
            "glyphScale": 1.2,
        },
    }
    femoral_shaft_colors = (
        (0.93, 0.32, 0.46),
        (0.96, 0.50, 0.30),
        (0.20, 0.66, 0.84),
        (0.18, 0.54, 0.78),
    )
    for contour_index, base_role in enumerate(FEMORAL_SHAFT_CONTOUR_BASE_ROLES, start=1):
        specs[side_role(side_key, base_role)] = {
            "className": "vtkMRMLMarkupsCurveNode",
            "name": side_node_name(side_key, f"Femoral Shaft Contour {contour_index}"),
            "color": femoral_shaft_colors[contour_index - 1],
            "labelPrefix": f"FemoralShaftContour_{side_label}_{contour_index}",
            "glyphScale": 1.2,
            "classificationLabels": FEMORAL_SHAFT_CONTOUR_CLASS_LABELS,
        }
    return specs


def _head_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral node specs related to femur-head and implant-head fitting."""

    return {
        side_role(side_key, "femurHeadPoints"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Femur Head Points"),
            "color": (0.20, 0.78, 0.35),
            "completionCount": 3,
            "labels": [
                f"FemurHead_{side_label}_P1",
                f"FemurHead_{side_label}_P2",
                f"FemurHead_{side_label}_P3",
            ],
        },
        side_role(side_key, "femurHeadCenter"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Femur Head Center"),
            "color": (1.00, 0.84, 0.20),
            "labels": [f"FemurHead_{side_label}_Center"],
            "locked": True,
        },
        side_role(side_key, "femurHeadCircle"): {
            "className": "vtkMRMLModelNode",
            "name": side_node_name(side_key, "Femur Head Circle"),
            "color": (0.20, 0.78, 0.35),
        },
        side_role(side_key, "implantHeadPoints"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Implant Head Points"),
            "color": (0.84, 0.60, 0.14),
            "completionCount": 3,
            "labels": [
                f"ImplantHead_{side_label}_P1",
                f"ImplantHead_{side_label}_P2",
                f"ImplantHead_{side_label}_P3",
            ],
        },
        side_role(side_key, "implantHeadCenter"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Implant Head Center"),
            "color": (1.00, 0.89, 0.34),
            "labels": [f"ImplantHead_{side_label}_Center"],
            "locked": True,
        },
        side_role(side_key, "implantHeadCircle"): {
            "className": "vtkMRMLModelNode",
            "name": side_node_name(side_key, "Implant Head Circle"),
            "color": (0.84, 0.60, 0.14),
        },
    }


def _axis_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral node specs used to construct shaft, neck, and implant-neck axes."""

    return {
        side_role(side_key, "shaftGuideProximal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Shaft Guide Line Proximal"),
            "color": (0.96, 0.44, 0.15),
            "labels": [
                f"FemoralShaftGuide_{side_label}_Proximal_Start",
                f"FemoralShaftGuide_{side_label}_Proximal_End",
            ],
        },
        side_role(side_key, "shaftGuideDistal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Shaft Guide Line Distal"),
            "color": (0.96, 0.44, 0.15),
            "labels": [
                f"FemoralShaftGuide_{side_label}_Distal_Start",
                f"FemoralShaftGuide_{side_label}_Distal_End",
            ],
        },
        side_role(side_key, "shaftAxis"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Shaft Axis"),
            "color": (0.86, 0.15, 0.18),
            "labels": [
                f"FemoralShaftAxis_{side_label}_Start",
                f"FemoralShaftAxis_{side_label}_End",
            ],
            "locked": True,
        },
        side_role(side_key, "neckGuideProximal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Neck Guide Line Proximal"),
            "color": (0.94, 0.54, 0.18),
            "labels": [
                f"FemoralNeckGuide_{side_label}_Proximal_Start",
                f"FemoralNeckGuide_{side_label}_Proximal_End",
            ],
        },
        side_role(side_key, "neckGuideDistal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Neck Guide Line Distal"),
            "color": (0.94, 0.54, 0.18),
            "labels": [
                f"FemoralNeckGuide_{side_label}_Distal_Start",
                f"FemoralNeckGuide_{side_label}_Distal_End",
            ],
        },
        side_role(side_key, "neckAxis"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Neck Axis"),
            "color": (0.74, 0.25, 0.14),
            "labels": [
                f"FemoralNeckAxis_{side_label}_Start",
                f"FemoralNeckAxis_{side_label}_End",
            ],
            "locked": True,
        },
        side_role(side_key, "implantNeckGuideProximal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Implant Neck Guide Line Proximal"),
            "color": (0.95, 0.66, 0.22),
            "labels": [
                f"ImplantNeckGuide_{side_label}_Proximal_Start",
                f"ImplantNeckGuide_{side_label}_Proximal_End",
            ],
        },
        side_role(side_key, "implantNeckGuideDistal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Implant Neck Guide Line Distal"),
            "color": (0.95, 0.66, 0.22),
            "labels": [
                f"ImplantNeckGuide_{side_label}_Distal_Start",
                f"ImplantNeckGuide_{side_label}_Distal_End",
            ],
        },
        side_role(side_key, "implantNeckAxis"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Implant Neck Axis"),
            "color": (0.79, 0.42, 0.12),
            "labels": [
                f"ImplantNeckAxis_{side_label}_Start",
                f"ImplantNeckAxis_{side_label}_End",
            ],
            "locked": True,
        },
    }


def _offset_and_extrusion_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral node specs for offset and extrusion measurements."""

    return {
        side_role(side_key, "acetabularOffsetLineA"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Acetabular Offset Line A"),
            "color": (0.09, 0.72, 0.76),
            "labels": [
                f"AcetabularOffset_{side_label}_LineA_Start",
                f"AcetabularOffset_{side_label}_LineA_End",
            ],
        },
        side_role(side_key, "acetabularOffsetLineB"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Acetabular Offset Line B"),
            "color": (0.09, 0.72, 0.76),
            "labels": [
                f"AcetabularOffset_{side_label}_LineB_Start",
                f"AcetabularOffset_{side_label}_LineB_End",
            ],
        },
        side_role(side_key, "femoralOffsetLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Offset Line"),
            "color": (0.73, 0.33, 0.83),
            "labels": [
                f"FemoralOffset_{side_label}_Start",
                f"FemoralOffset_{side_label}_End",
            ],
        },
        side_role(side_key, "extrusionIndexMedialLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Head Extrusion Index Medial Line"),
            "color": (0.82, 0.34, 0.23),
            "labels": [
                f"FemoralHeadExtrusionIndex_{side_label}_Medial_Start",
                f"FemoralHeadExtrusionIndex_{side_label}_Medial_End",
            ],
        },
        side_role(side_key, "extrusionIndexMiddleLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Head Extrusion Index Middle Line"),
            "color": (0.82, 0.34, 0.23),
            "labels": [
                f"FemoralHeadExtrusionIndex_{side_label}_Middle_Start",
                f"FemoralHeadExtrusionIndex_{side_label}_Middle_End",
            ],
        },
        side_role(side_key, "extrusionIndexLateralLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femoral Head Extrusion Index Lateral Line"),
            "color": (0.82, 0.34, 0.23),
            "labels": [
                f"FemoralHeadExtrusionIndex_{side_label}_Lateral_Start",
                f"FemoralHeadExtrusionIndex_{side_label}_Lateral_End",
            ],
        },
    }


def _shaft_morphology_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral node specs used by the shaft-morphology workflow."""

    return {
        side_role(side_key, "shaftMorphologyLTPoints"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Femur Shaft Morphology Lesser Trochanter Points"),
            "color": (0.62, 0.36, 0.86),
            "completionCount": 2,
            "labels": [
                f"FemurShaftMorphology_{side_label}_LT_Proximal",
                f"FemurShaftMorphology_{side_label}_LT_Distal",
            ],
        },
        side_role(side_key, "shaftMorphologyMidline"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femur Shaft Morphology LT Midline"),
            "color": (0.62, 0.36, 0.86),
            "labels": [
                f"FemurShaftMorphology_{side_label}_Midline_A",
                f"FemurShaftMorphology_{side_label}_Midline_B",
            ],
            "locked": True,
        },
        side_role(side_key, "shaftMorphologyPoints"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Femur Shaft Morphology Control Points"),
            "color": (0.78, 0.51, 0.95),
            "labels": [
                f"FemurShaftMorphology_{side_label}_{suffix}"
                for suffix, _axial_mm, _transverse_mm in FEMUR_SHAFT_MORPHOLOGY_LAYOUT
            ],
        },
        side_role(side_key, "shaftMorphologyGuideLineA"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femur Shaft Morphology Guide Line A"),
            "color": (0.62, 0.36, 0.86),
            "labels": [
                f"FemurShaftMorphology_{side_label}_GuideA_Start",
                f"FemurShaftMorphology_{side_label}_GuideA_End",
            ],
            "locked": True,
        },
        side_role(side_key, "shaftMorphologyGuideLineB"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Femur Shaft Morphology Guide Line B"),
            "color": (0.62, 0.36, 0.86),
            "labels": [
                f"FemurShaftMorphology_{side_label}_GuideB_Start",
                f"FemurShaftMorphology_{side_label}_GuideB_End",
            ],
            "locked": True,
        },
    }


def _cup_and_postop_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral node specs for cup-opening and post-operative workflows."""

    return {
        side_role(side_key, "acetabularInclinationLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Acetabular Inclination Angle Line"),
            "color": (0.30, 0.68, 0.92),
            "labels": [
                f"AcetabularInclinationAngle_{side_label}_Start",
                f"AcetabularInclinationAngle_{side_label}_End",
            ],
        },
        side_role(side_key, "cupOpeningEllipsePoints"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "Cup Opening Ellipse Points"),
            "color": (0.24, 0.78, 0.88),
            "completionCount": 6,
            "labels": [
                f"CupOpeningEllipse_{side_label}_P1",
                f"CupOpeningEllipse_{side_label}_P2",
                f"CupOpeningEllipse_{side_label}_P3",
                f"CupOpeningEllipse_{side_label}_P4",
                f"CupOpeningEllipse_{side_label}_P5",
                f"CupOpeningEllipse_{side_label}_P6",
            ],
        },
        side_role(side_key, "cupOpeningEllipse"): {
            "className": "vtkMRMLModelNode",
            "name": side_node_name(side_key, "Cup Opening Ellipse"),
            "color": (0.24, 0.78, 0.88),
        },
        side_role(side_key, "cupOpeningEllipseMajorDiameter"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Cup Opening Ellipse Major Diameter"),
            "color": (0.24, 0.78, 0.88),
            "labels": [
                f"CupOpeningEllipse_{side_label}_Major_Start",
                f"CupOpeningEllipse_{side_label}_Major_End",
            ],
        },
        side_role(side_key, "cupOpeningEllipseMinorDiameter"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Cup Opening Ellipse Minor Diameter"),
            "color": (0.24, 0.78, 0.88),
            "labels": [
                f"CupOpeningEllipse_{side_label}_Minor_Start",
                f"CupOpeningEllipse_{side_label}_Minor_End",
            ],
        },
        side_role(side_key, "postOpAcetabularOffsetLineA"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Post-Op Acetabular Offset Line A"),
            "color": (0.13, 0.51, 0.91),
            "labels": [
                f"PostOpAcetabularOffset_{side_label}_LineA_Start",
                f"PostOpAcetabularOffset_{side_label}_LineA_End",
            ],
        },
        side_role(side_key, "postOpAcetabularOffsetLineB"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Post-Op Acetabular Offset Line B"),
            "color": (0.13, 0.51, 0.91),
            "labels": [
                f"PostOpAcetabularOffset_{side_label}_LineB_Start",
                f"PostOpAcetabularOffset_{side_label}_LineB_End",
            ],
        },
        side_role(side_key, "postOpFemoralOffsetLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Post-Op Femoral Offset Line"),
            "color": (0.87, 0.24, 0.61),
            "labels": [
                f"PostOpFemoralOffset_{side_label}_Start",
                f"PostOpFemoralOffset_{side_label}_End",
            ],
        },
        side_role(side_key, "implantAlignmentGuideProximal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Stem Alignment Guide Line Proximal"),
            "color": (0.98, 0.71, 0.22),
            "labels": [
                f"StemAlignmentGuide_{side_label}_Proximal_Start",
                f"StemAlignmentGuide_{side_label}_Proximal_End",
            ],
        },
        side_role(side_key, "implantAlignmentGuideDistal"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Stem Alignment Guide Line Distal"),
            "color": (0.98, 0.71, 0.22),
            "labels": [
                f"StemAlignmentGuide_{side_label}_Distal_Start",
                f"StemAlignmentGuide_{side_label}_Distal_End",
            ],
        },
        side_role(side_key, "implantAlignmentLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Stem Alignment Axis"),
            "color": (0.94, 0.61, 0.12),
            "labels": [
                f"StemAlignment_{side_label}_Start",
                f"StemAlignment_{side_label}_End",
            ],
            "locked": True,
        },
    }


def _angle_node_specs(side_key: str, side_label: str) -> NodeSpecMap:
    """Return bilateral node specs for side-specific angle measurements."""

    return {
        side_role(side_key, "tonnisAngleLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Acetabular Index (Tönnis) Line"),
            "color": (0.22, 0.56, 0.93),
            "labels": [
                f"AcetabularIndexTonnis_{side_label}_Base",
                f"AcetabularIndexTonnis_{side_label}_Roof",
            ],
        },
        side_role(side_key, "tonnisAngleReferenceArm"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Acetabular Index (Tönnis) Reference Arm"),
            "color": (0.22, 0.56, 0.93),
            "labels": [
                f"AcetabularIndexTonnis_{side_label}_Reference_Start",
                f"AcetabularIndexTonnis_{side_label}_Reference_End",
            ],
            "locked": True,
        },
        side_role(side_key, "sharpAngleLine"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Sharp Angle Line"),
            "color": (0.16, 0.65, 0.58),
            "labels": [
                f"SharpAngle_{side_label}_Base",
                f"SharpAngle_{side_label}_Lateral",
            ],
        },
        side_role(side_key, "sharpAngleReferenceArm"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "Sharp Angle Reference Arm"),
            "color": (0.16, 0.65, 0.58),
            "labels": [
                f"SharpAngle_{side_label}_Reference_Start",
                f"SharpAngle_{side_label}_Reference_End",
            ],
            "locked": True,
        },
        side_role(side_key, "lceAnglePoint"): {
            "className": "vtkMRMLMarkupsFiducialNode",
            "name": side_node_name(side_key, "LCE Angle Point"),
            "color": (0.84, 0.42, 0.13),
            "completionCount": 1,
            "labels": [f"LCEAngle_{side_label}_Point"],
        },
        side_role(side_key, "lceAngleVisual"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "LCE Angle Reference Arm"),
            "color": (0.84, 0.42, 0.13),
            "labels": [
                f"LCEAngle_{side_label}_Center",
                f"LCEAngle_{side_label}_Reference_End",
            ],
            "locked": True,
        },
        side_role(side_key, "lceAngleRadialArm"): {
            "className": "vtkMRMLMarkupsLineNode",
            "name": side_node_name(side_key, "LCE Angle Radial Arm"),
            "color": (0.84, 0.42, 0.13),
            "labels": [
                f"LCEAngle_{side_label}_Center",
                f"LCEAngle_{side_label}_Point",
            ],
            "locked": True,
        },
    }


NODE_SPECS.update(build_bilateral_node_specs())

INPUT_NODE_ROLES = [
    "calibrationPoints",
    "referenceLine",
    "lldPoints",
]
for _side_key in SIDE_KEYS:
    for _base_role in BILATERAL_INPUT_BASE_ROLES:
        INPUT_NODE_ROLES.append(side_role(_side_key, _base_role))

EXPORT_FIELDS = [
    "section",
    "name",
    "index",
    "label",
    "x_ras",
    "y_ras",
    "z_ras",
    "curve_type",
    "curve_points_per_segment",
    "raw_value",
    "corrected_value_mm",
    "units",
    "details",
]
