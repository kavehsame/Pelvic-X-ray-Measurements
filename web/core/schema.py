"""Self-contained MRML naming schema for the browser fork.

Role strings intentionally remain compatible with exported pelvic-measurement
scenes, but this module has no source or runtime dependency on the desktop
extension.
"""

from __future__ import annotations


from .planning import node_specs as planning_specs

ROLE_ATTRIBUTE = "PelvicXrayMeasurements.Role"
POINT_GLYPH_FACTOR = 0.55 * 1.25
EXPORTED_POINT_RADIUS = 4.4 * 1.25
SIDE_LABELS = {"left": "Left", "right": "Right"}


def side_role(side: str, base_role: str) -> str:
    """Return the browser fork's stable bilateral MRML role identifier."""

    if side not in SIDE_LABELS:
        raise ValueError(f"Unsupported side: {side}")
    return f"{side}_{base_role}"


def _line(name: str, color: tuple[float, float, float], labels: tuple[str, str]) -> dict:
    return {
        "className": "vtkMRMLMarkupsLineNode",
        "name": name,
        "color": color,
        "labels": list(labels),
    }


def _points(
    name: str,
    color: tuple[float, float, float],
    labels: tuple[str, ...],
) -> dict:
    return {
        "className": "vtkMRMLMarkupsFiducialNode",
        "name": name,
        "color": color,
        "completionCount": len(labels),
        "labels": list(labels),
    }


def _model(name: str, color: tuple[float, float, float]) -> dict:
    """Describe a derived model with the desktop extension's compatible role."""

    return {"className": "vtkMRMLModelNode", "name": name, "color": color}


NODE_SPECS: dict[str, dict] = {
    "calibrationPoints": _points(
        "Hip Measurements - Calibration Ball Points",
        (0.98, 0.62, 0.12),
        ("CalibrationBall_P1", "CalibrationBall_P2", "CalibrationBall_P3"),
    ),
    "calibrationCircle": _model(
        "Hip Measurements - Calibration Ball Circle",
        (0.98, 0.62, 0.12),
    ),
    "referenceLine": _line(
        "Hip Measurements - Reference Line",
        (0.25, 0.63, 0.96),
        ("ReferenceLine_Start", "ReferenceLine_End"),
    ),
    "lldPoints": _points(
        "Hip Measurements - Minor Trochanter Points",
        (0.93, 0.25, 0.48),
        ("MinorTrochanter_P1", "MinorTrochanter_P2"),
    ),
    "activeSideBadge": _points(
        "Hip Measurements - Active Side",
        (0.10, 0.42, 0.90),
        ("ACTIVE SIDE",),
    ),
    "lldLeftParallel": _line(
        "Hip Measurements - LLD Left Parallel Line",
        (0.93, 0.25, 0.48),
        ("LLD_LeftParallel_Start", "LLD_LeftParallel_End"),
    ),
    "lldRightParallel": _line(
        "Hip Measurements - LLD Right Parallel Line",
        (0.93, 0.25, 0.48),
        ("LLD_RightParallel_Start", "LLD_RightParallel_End"),
    ),
    "lldHeightDifference": _line(
        "Hip Measurements - LLD Height Difference",
        (0.98, 0.55, 0.18),
        ("LLD_Difference_Start", "LLD_Difference_End"),
    ),
}


def _side_name(side: str, label: str) -> str:
    return f"Hip Measurements - {SIDE_LABELS[side]} {label}"


def _side_labels(side: str, prefix: str, count: int) -> tuple[str, ...]:
    side_label = SIDE_LABELS[side]
    return tuple(f"{prefix}_{side_label}_P{index}" for index in range(1, count + 1))


def _add_bilateral_specs() -> None:
    """Build the browser fork's bilateral input-node definitions."""

    for side, side_label in SIDE_LABELS.items():

        def role(base: str, side=side) -> str:
            return side_role(side, base)

        def line(base: str, label: str, color, prefix: str, side=side, side_label=side_label, role=role) -> None:
            NODE_SPECS[role(base)] = _line(
                _side_name(side, label),
                color,
                (f"{prefix}_{side_label}_Start", f"{prefix}_{side_label}_End"),
            )

        NODE_SPECS[role("femurHeadPoints")] = _points(
            _side_name(side, "Femur Head Points"),
            (0.20, 0.78, 0.35),
            _side_labels(side, "FemurHead", 3),
        )
        NODE_SPECS[role("implantHeadPoints")] = _points(
            _side_name(side, "Implant Head Points"),
            (0.84, 0.60, 0.14),
            _side_labels(side, "ImplantHead", 3),
        )
        NODE_SPECS[role("femurHeadCenter")] = _points(
            _side_name(side, "Femur Head Center"),
            (1.0, 0.84, 0.2),
            (f"FemurHead_{side_label}_Center",),
        )
        NODE_SPECS[role("femurHeadCircle")] = _model(
            _side_name(side, "Femur Head Circle"),
            (0.20, 0.78, 0.35),
        )
        NODE_SPECS[role("implantHeadCenter")] = _points(
            _side_name(side, "Implant Head Center"),
            (1.0, 0.89, 0.34),
            (f"ImplantHead_{side_label}_Center",),
        )
        NODE_SPECS[role("implantHeadCircle")] = _model(
            _side_name(side, "Implant Head Circle"),
            (0.84, 0.60, 0.14),
        )
        NODE_SPECS[role("lceAnglePoint")] = _points(
            _side_name(side, "LCE Angle Point"),
            (0.35, 0.82, 0.45),
            (f"LCEAngle_{side_label}_Point",),
        )
        NODE_SPECS[role("shaftMorphologyLTPoints")] = _points(
            _side_name(side, "Femur Shaft Morphology Lesser Trochanter Points"),
            (0.62, 0.36, 0.86),
            (
                f"FemurShaftMorphology_{side_label}_LT_Proximal",
                f"FemurShaftMorphology_{side_label}_LT_Distal",
            ),
        )
        NODE_SPECS[role("shaftMorphologyPoints")] = _points(
            _side_name(side, "Femur Shaft Morphology Control Points"),
            (0.78, 0.51, 0.95),
            tuple(f"FemurShaftMorphology_{side_label}_P{index}" for index in range(1, 11)),
        )
        NODE_SPECS[role("cupOpeningEllipsePoints")] = _points(
            _side_name(side, "Cup Opening Ellipse Points"),
            (0.24, 0.78, 0.88),
            _side_labels(side, "CupOpeningEllipse", 6),
        )
        NODE_SPECS[role("cupOpeningEllipse")] = _model(
            _side_name(side, "Cup Opening Ellipse"),
            (0.24, 0.78, 0.88),
        )

        line(
            "shaftGuideProximal", "Femoral Shaft Guide Line Proximal", (0.96, 0.44, 0.15), "FemoralShaftGuide_Proximal"
        )
        line("shaftGuideDistal", "Femoral Shaft Guide Line Distal", (0.96, 0.44, 0.15), "FemoralShaftGuide_Distal")
        line("neckGuideProximal", "Femoral Neck Guide Line Proximal", (0.94, 0.54, 0.18), "FemoralNeckGuide_Proximal")
        line("neckGuideDistal", "Femoral Neck Guide Line Distal", (0.94, 0.54, 0.18), "FemoralNeckGuide_Distal")
        line(
            "implantNeckGuideProximal",
            "Implant Neck Guide Line Proximal",
            (0.95, 0.66, 0.22),
            "ImplantNeckGuide_Proximal",
        )
        line("implantNeckGuideDistal", "Implant Neck Guide Line Distal", (0.95, 0.66, 0.22), "ImplantNeckGuide_Distal")
        line("tonnisAngleLine", "Acetabular Index (Tönnis) Line", (0.26, 0.70, 0.94), "TonnisAngle")
        line("sharpAngleLine", "Sharp Angle Line", (0.33, 0.76, 0.82), "SharpAngle")
        line("acetabularOffsetLineA", "Acetabular Offset Line A", (0.09, 0.72, 0.76), "AcetabularOffset_LineA")
        line("acetabularOffsetLineB", "Acetabular Offset Line B", (0.09, 0.72, 0.76), "AcetabularOffset_LineB")
        line("femoralOffsetLine", "Femoral Offset Line", (0.73, 0.33, 0.83), "FemoralOffset")
        line(
            "extrusionIndexMedialLine",
            "Femoral Head Extrusion Index Medial Line",
            (0.82, 0.34, 0.23),
            "FemoralHeadExtrusionIndex_Medial",
        )
        line(
            "extrusionIndexMiddleLine",
            "Femoral Head Extrusion Index Middle Line",
            (0.82, 0.34, 0.23),
            "FemoralHeadExtrusionIndex_Middle",
        )
        line(
            "extrusionIndexLateralLine",
            "Femoral Head Extrusion Index Lateral Line",
            (0.82, 0.34, 0.23),
            "FemoralHeadExtrusionIndex_Lateral",
        )
        line(
            "acetabularInclinationLine",
            "Acetabular Inclination Angle Line",
            (0.30, 0.68, 0.92),
            "AcetabularInclinationAngle",
        )
        line(
            "implantAlignmentGuideProximal",
            "Stem Alignment Guide Line Proximal",
            (0.98, 0.71, 0.22),
            "StemAlignmentGuide_Proximal",
        )
        line(
            "implantAlignmentGuideDistal",
            "Stem Alignment Guide Line Distal",
            (0.98, 0.71, 0.22),
            "StemAlignmentGuide_Distal",
        )
        line(
            "postOpAcetabularOffsetLineA",
            "Post-Op Acetabular Offset Line A",
            (0.13, 0.51, 0.91),
            "PostOpAcetabularOffset_LineA",
        )
        line(
            "postOpAcetabularOffsetLineB",
            "Post-Op Acetabular Offset Line B",
            (0.13, 0.51, 0.91),
            "PostOpAcetabularOffset_LineB",
        )
        line("postOpFemoralOffsetLine", "Post-Op Femoral Offset Line", (0.87, 0.24, 0.61), "PostOpFemoralOffset")
        line("shaftAxis", "Femoral Shaft Axis", (0.86, 0.15, 0.18), "FemoralShaftAxis")
        line("neckAxis", "Femoral Neck Axis", (0.74, 0.25, 0.14), "FemoralNeckAxis")
        line("implantNeckAxis", "Implant Neck Axis", (0.79, 0.42, 0.12), "ImplantNeckAxis")
        line("implantAlignmentLine", "Stem Alignment Axis", (0.98, 0.71, 0.22), "StemAlignment")
        line(
            "shaftMorphologyMidline",
            "Femur Shaft Morphology LT Midline",
            (0.62, 0.36, 0.86),
            "FemurShaftMorphology_Midline",
        )
        line(
            "shaftMorphologyGuideLineA",
            "Femur Shaft Morphology Guide Line A",
            (0.62, 0.36, 0.86),
            "FemurShaftMorphology_GuideA",
        )
        line(
            "shaftMorphologyGuideLineB",
            "Femur Shaft Morphology Guide Line B",
            (0.62, 0.36, 0.86),
            "FemurShaftMorphology_GuideB",
        )
        line(
            "tonnisAngleReferenceArm",
            "Acetabular Index (Tönnis) Reference Arm",
            (0.26, 0.70, 0.94),
            "TonnisAngleReference",
        )
        line("sharpAngleReferenceArm", "Sharp Angle Reference Arm", (0.33, 0.76, 0.82), "SharpAngleReference")
        line("lceAngleVisual", "LCE Angle Reference Arm", (0.35, 0.82, 0.45), "LCEAngleReference")
        line("lceAngleRadialArm", "LCE Angle Radial Arm", (0.35, 0.82, 0.45), "LCEAngleRadial")

        curve_specs = (
            ("iliopectinealLine", "Iliopectineal Line", (0.78, 0.38, 0.92)),
            ("ilioischialLine", "Ilioischial Line", (0.18, 0.70, 0.72)),
            ("shentonLine", "Shenton Line", (0.90, 0.48, 0.20)),
            ("acetabularRoofSourcil", "Acetabular Roof (Sourcil)", (0.32, 0.58, 0.95)),
            ("anteriorAcetabularWall", "Anterior Acetabular Wall", (0.98, 0.82, 0.22)),
            ("posteriorAcetabularWall", "Posterior Acetabular Wall", (0.98, 0.32, 0.68)),
            ("lineaTerminalis", "Linea Terminalis", (0.52, 0.74, 0.25)),
            ("femoralShaftContour1", "Femoral Shaft Contour 1", (0.93, 0.32, 0.46)),
            ("femoralShaftContour2", "Femoral Shaft Contour 2", (0.96, 0.50, 0.30)),
            ("femoralShaftContour3", "Femoral Shaft Contour 3", (0.20, 0.66, 0.84)),
            ("femoralShaftContour4", "Femoral Shaft Contour 4", (0.18, 0.54, 0.78)),
        )
        for base, label, color in curve_specs:
            NODE_SPECS[role(base)] = {
                "className": "vtkMRMLMarkupsCurveNode",
                "name": _side_name(side, label),
                "color": color,
                "glyphScale": 1.2,
            }


_add_bilateral_specs()
for _side in SIDE_LABELS:
    NODE_SPECS.update(planning_specs(_side))
