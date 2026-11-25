"""Complete browser measurement, preference, contour and coordinate CSV schema."""

import csv
import json
from datetime import datetime, timezone
import numpy as np
from .planning import COMPONENTS, LENGTH_FIELDS
from .scene import vtkStringArray
from .geometry import angle_deviation_from_perpendicular

MEASUREMENTS = {
    **{key: name for key, name, _label in LENGTH_FIELDS},
    "head": "FemurHead_Diameter",
    "ccd": "CCDAngle",
    "tonnis": "AcetabularIndexTonnis",
    "sharp": "SharpAngle",
    "lce": "LCEAngle",
    "extrusion": "FemoralHeadExtrusionIndex",
    "ccr": "CCR",
    "cti": "CTI",
    "cfi": "CFI",
    "acetabular_offset": "PreOp_AcetabularOffset",
    "femoral_offset": "PreOp_FemoralOffset",
    "global_offset": "PreOp_GlobalOffset",
    "inclination": "AcetabularInclinationAngle_FreeHand_PostOp",
    "ellipse_inclination": "CupOpeningEllipseFit_Inclination_PostOp",
    "cup_version": "CupAnteversionRetroversionAngle_PostOp",
    "implant_ccd": "ImplantFemoralCCD_PostOp",
    "implant_head": "PostOp_ImplantHead_Diameter",
    "post_acetabular_offset": "PostOp_AcetabularOffset",
    "post_femoral_offset": "PostOp_FemoralOffset",
    "post_global_offset": "PostOp_GlobalOffset",
    "stem_alignment": "StemAlignment",
}
FIELDS = (
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
    "role",
    "point_index",
    "r",
    "a",
    "s",
    "annotator",
)


def write_case_csv(path, controller, case_name, annotator):
    from .cases import coordinate_rows

    controller.update_derived()
    state = controller.server.state
    scale = controller._calibration_scale()
    rows = []

    def metadata(name, value, *, flag=False):
        rows.append(
            dict(
                section="metadata",
                name=name,
                details=str(value),
                raw_value=str(int(value)) if flag else "",
                units="flag" if flag else "",
            )
        )

    def measurement(name, value, suffix, *, corrected=False, details=""):
        if value is None or not np.isfinite(value):
            return
        length = suffix in (" mm", " px", " su", "length")
        raw = value / scale if corrected and scale is not None and length else value
        rows.append(
            dict(
                section="measurement",
                name=name,
                raw_value=repr(float(raw)),
                corrected_value_mm=repr(float(raw * scale)) if length and scale is not None else "",
                units="su -> mm"
                if length and scale is not None
                else "su"
                if length
                else "degrees"
                if suffix == "°"
                else "percent"
                if suffix == "%"
                else "ratio",
                details=details,
            )
        )

    metadata("CaseName", case_name)
    metadata("ImageNode", case_name)
    metadata("Annotator", annotator)
    metadata("Comments", str(state.pelvic_comments or "").strip())
    metadata("CalibrationBall_NotPresent", scale is None, flag=True)
    metadata("Timestamp", datetime.now(timezone.utc).isoformat())
    metadata("BrowserCSVSchema", 2)
    metadata("CalibrationBall_KnownDiameter", float(state.pelvic_ball_diameter))
    metadata("ActiveSide", state.pelvic_active_side)
    volume = controller.scene.GetFirstNodeByClass("vtkMRMLVolumeNode")
    if volume is not None:
        from .scene import vtkMatrix4x4

        matrix = vtkMatrix4x4()
        volume.GetIJKToRASMatrix(matrix)
        metadata("ImageIJKToRAS", json.dumps([[matrix.GetElement(i, j) for j in range(4)] for i in range(4)]))
    for side in ("left", "right"):
        for component in COMPONENTS:
            implant = state.get(f"pelvic_placed_{side}_{component}")
            if implant:
                for name, value in implant["metadata"].items():
                    # Treat text supplied by a session pack as a spreadsheet label.
                    metadata(name, "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value)
        for kind in ("neck", "implant_neck"):
            lock, single = controller.axis_options(side, kind)
            metadata(f"{side}_{kind}_options", json.dumps({"lockToCenter": lock, "useSingleGuide": single}))
            family = "FemoralNeckAxis" if kind == "neck" else "ImplantNeckAxis"
            metadata(f"{family}_{side.title()}_LockToCenter", lock, flag=True)
            metadata(f"{family}_{side.title()}_UseSingleGuide", single, flag=True)
        for key, name in MEASUREMENTS.items():
            value, suffix = controller._numeric_results.get(f"pelvic_result_{side}_{key}", (None, ""))
            details = (
                "Canal-calcar ratio (B/A): distal inner-canal width at 10 cm divided by proximal mid-LT guide-cap width."
                if key == "ccr"
                else "Projected head-to-shell centre distance on this film (inlay wear estimate)." if key == "inlay_wear" else ""
            )
            measurement(f"{side.title()}_{name}", value, suffix, corrected=True, details=details)
        shaft = controller.points_for_role(f"{side}_shaftAxis")
        for letter, guide in (("A", "shaftGuideProximal"), ("B", "shaftGuideDistal")):
            points = controller.points_for_role(f"{side}_{guide}")
            if len(shaft) >= 2 and len(points) >= 2:
                measurement(
                    f"{side.title()}_FemoralShaftAxis_DeviationGuide{letter}",
                    angle_deviation_from_perpendicular(shaft[1] - shaft[0], points[1] - points[0]),
                    "°",
                )
    try:
        _, diameter = controller.circle_from_three(controller.points_for_role("calibrationPoints"))
        measurement("CalibrationBall_MeasuredDiameter", diameter, "length")
    except ValueError:
        pass
    if scale is not None:
        rows.append(
            dict(
                section="measurement",
                name="CalibrationBall_KnownDiameter",
                corrected_value_mm=repr(float(state.pelvic_ball_diameter)),
                units="mm",
            )
        )
        rows.append(
            dict(
                section="measurement",
                name="CalibrationScaleFactor",
                raw_value=repr(float(scale)),
                units="mm per scene unit",
            )
        )
    reference = controller.points_for_role("referenceLine")
    if len(reference) >= 2:
        measurement("ReferenceLine_Length", np.linalg.norm(reference[1] - reference[0]), "length")
    value, suffix = controller._numeric_results.get("pelvic_result_lld", (None, ""))
    measurement("LLD", value, suffix, corrected=True)
    points = controller.points_for_role("lldPoints")
    lateral, superior = controller._reference_directions("left")
    if len(points) >= 2 and lateral is not None:
        left, right = sorted(points[:2], key=lambda p: np.dot(p[:2], lateral), reverse=True)
        measurement("LLD_Signed_LeftMinusRight", np.dot((left - right)[:2], superior), "length")
    for kind in ("line", "angle"):
        for result in controller._custom_measurements[kind]:
            index = result["index"]
            role = f"otherLine_{index}" if kind == "line" else f"otherAngle_{index}_points"
            node = controller.node_for_role(role)
            attribute = (
                "PelvicXrayMeasurements.OtherLineLockToReference"
                if kind == "line"
                else "PelvicXrayMeasurements.OtherAngleLockToReference"
            )
            metadata(f"{role}_lock", node.GetAttribute(attribute) or "none")
            mode = node.GetAttribute(attribute) or "none"
            description = (
                "Custom line measurement created from two placed points."
                if kind == "line"
                else "Custom three-point angle measurement."
            )
            if mode != "none":
                description += (
                    f" Orientation locked {mode} to the reference line."
                    if kind == "line"
                    else f" First arm locked {mode} to the reference line."
                )
            measurement(
                f"Line_{index}_Length" if kind == "line" else f"Angle_{index}",
                result["rawValue"],
                "length" if kind == "line" else "°",
                details=description,
            )
    for row in coordinate_rows(controller.scene):
        role = row["role"]
        if role == "activeSideBadge":
            continue
        node = controller.node_for_role(role)
        names = vtkStringArray()
        node.GetAttributeNames(names)
        attributes = {names.GetValue(i): node.GetAttribute(names.GetValue(i)) for i in range(names.GetNumberOfValues())}
        # Preserve per-node reconstruction options, shared/manual alternation and contour classification.
        if row["point_index"] == 1 or str(row["point_index"]) == "1":
            metadata(f"{role}_attributes", json.dumps(attributes, sort_keys=True))
        curve = node.IsA("vtkMRMLMarkupsCurveNode")
        rows.append(
            dict(
                **row,
                section="derived_point" if node.GetLocked() else "point",
                name=node.GetName(),
                index=int(row["point_index"]) - 1,
                x_ras=row["r"],
                y_ras=row["a"],
                z_ras=row["s"],
                details=role,
                curve_type=node.GetCurveType() if curve else "",
                curve_points_per_segment=node.GetNumberOfPointsPerInterpolatingSegment() if curve else "",
            )
        )

    # Analytic construction records match the extension's additional derived
    # rows, including fitted ellipse diameters and axis origins.
    def derived(name, points):
        for index, point in enumerate(points):
            rows.append(
                dict(
                    section="derived_point",
                    name=name,
                    index=index,
                    label=name,
                    x_ras=repr(float(point[0])),
                    y_ras=repr(float(point[1])),
                    z_ras=repr(float(point[2])),
                )
            )

    try:
        center, _ = controller.circle_from_three(controller.points_for_role("calibrationPoints"))
        derived("CalibrationBall_Center", [center])
    except ValueError:
        pass
    for side in ("left", "right"):
        for base, name in (
            ("shaftAxis", "FemoralShaftAxis"),
            ("neckAxis", "FemoralNeckAxis"),
            ("implantNeckAxis", "ImplantNeckAxis"),
            ("implantAlignmentLine", "StemAlignmentAxis"),
        ):
            points = controller.points_for_role(f"{side}_{base}")
            if len(points) >= 2:
                derived(f"{side.title()}_{name}", points[:2])
                derived(f"{side.title()}_{name}_Origin", [0.5 * (points[0] + points[1])])
        ellipse = controller._ellipses.get(side)
        if ellipse is not None:
            derived(f"{side.title()}_CupOpeningEllipse_Center", [ellipse.center])
            derived(f"{side.title()}_CupOpeningEllipse_MajorAxis", ellipse.major_endpoints)
            derived(f"{side.title()}_CupOpeningEllipse_MinorAxis", ellipse.minor_endpoints)
    if len(points := controller.points_for_role("lldPoints")) >= 2 and len(reference) >= 2 and lateral is not None:
        left, right = sorted(points[:2], key=lambda p: np.dot(p[:2], lateral), reverse=True)
        direction = (reference[1] - reference[0]) / np.linalg.norm(reference[1] - reference[0])
        for name, point in (("LLD_LeftProjection", left), ("LLD_RightProjection", right)):
            derived(name, [reference[0] + direction * np.dot(point - reference[0], direction)])
    with path.open("x", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({**row, "annotator": annotator} for row in rows)
