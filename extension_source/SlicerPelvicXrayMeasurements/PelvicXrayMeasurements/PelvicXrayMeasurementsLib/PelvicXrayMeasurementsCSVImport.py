"""Restore editable measurements on the open radiograph from a named PXM CSV."""

import json
import re

import numpy as np
import vtk

from PelvicXrayMeasurementsCaseWorkflow import load_export_csv_rows, parse_saved_case_metadata
from PelvicXrayMeasurementsConstants import OTHER_ANGLE_LOCK_ATTRIBUTE, OTHER_LINE_LOCK_ATTRIBUTE
from PelvicXrayMeasurementsNodeSpecs import BILATERAL_INPUT_BASE_ROLES, NODE_SPECS
from PelvicXrayMeasurementsSavedCSV import indexed_coordinates
from PelvicXrayMeasurementsPlanning import (
    FRAGMENT_ANGLE,
    FRAGMENT_CUT,
    TEMPLATE_ATTRIBUTE,
    VIEW_AXES,
    transformed_attributes,
    validate_attributes,
)


def _input_specs():
    roles = {"calibrationPoints", "referenceLine", "lldPoints"}
    roles.update(f"{side}_{base}" for side in ("left", "right") for base in BILATERAL_INPUT_BASE_ROLES)
    return {role: NODE_SPECS[role] for role in roles if not NODE_SPECS[role].get("locked")}


def _saved_transform(metadata, volume):
    if not metadata.get("ImageIJKToRAS"):
        return np.eye(4)
    saved_frame = np.asarray(json.loads(metadata["ImageIJKToRAS"]), dtype=float)
    layout = json.loads(metadata.get("WebSceneState", "{}")).get("web_layout", {})
    width, height, _ = volume.GetImageData().GetDimensions()
    turns = int(layout.get("turns", 0)) % 4
    expected = [width, height] if turns % 2 else [height, width]
    if "ImageDimensions" in metadata and json.loads(metadata["ImageDimensions"]) != [width, height]:
        raise ValueError("The CSV and the open image have different dimensions.")
    if layout.get("shape", expected) != expected:
        raise ValueError("The CSV and the open image have different dimensions.")
    # Displayed column and row back to the original image indices.
    mapping = np.eye(4)
    mapping[:2] = (
        [[1, 0, 0, 0], [0, 1, 0, 0]],
        [[0, 1, 0, 0], [-1, 0, 0, height - 1]],
        [[-1, 0, 0, width - 1], [0, -1, 0, height - 1]],
        [[0, -1, 0, width - 1], [1, 0, 0, 0]],
    )[turns]
    if layout.get("mirrored"):
        flip = np.eye(4)
        flip[0, 0], flip[0, 3] = -1, expected[1] - 1
        mapping = mapping @ flip
    matrix = vtk.vtkMatrix4x4()
    volume.GetIJKToRASMatrix(matrix)
    target = np.array([[matrix.GetElement(i, j) for j in range(4)] for i in range(4)])
    if (
        saved_frame.shape != (4, 4)
        or not np.isfinite(saved_frame).all()
        or not np.allclose(saved_frame[3], [0, 0, 0, 1])
    ):
        raise ValueError("The CSV image coordinate frame is invalid.")
    return target @ mapping @ np.linalg.inv(saved_frame)


def prepare_csv(logic, path, volume):
    """Validate every supported input before replacing any existing annotation."""
    rows = load_export_csv_rows(path)
    settings = parse_saved_case_metadata(rows)
    metadata = {row["name"]: row.get("details") or "" for row in rows if row["section"] == "metadata"}
    specs = _input_specs()
    records = indexed_coordinates(rows, specs, logic._dynamic_other_spec_for_role)
    if not records and not any(key in metadata for key in ("ImageNode", "CaseName")):
        raise ValueError("This CSV contains no recognisable PXM annotations or case information.")
    transform = _saved_transform(metadata, volume)
    tracks = {}
    for role, items in records.items():
        points = [(transform @ [*point, 1.0])[:3] for point, _row in items]
        labels = [row.get("label") or "" for _, row in items]
        row = items[0][1]
        interpolation = row.get("curve_type") or ""
        modes = {"linear": 0, "spline": 1, "cardinalspline": 1, "kochanekspline": 2}
        mode = modes.get(interpolation.lower(), interpolation)
        segments = int(row.get("curve_points_per_segment") or 30)
        if mode != "" and (str(mode) not in ("0", "1", "2") or not 1 <= segments <= 1000):
            raise ValueError(f"Invalid saved contour settings for {role}.")
        attrs = json.loads(metadata.get(role + "_attributes", "{}"))
        validate_attributes(role, attrs)
        attrs = transformed_attributes(attrs, transform)
        tracks[role] = (points, labels, mode, segments, attrs)
    locks = {}
    for row in rows:
        if row["section"] != "measurement":
            continue
        match = re.fullmatch(r"(Line|Angle)_(\d+)(?:_Length)?", row["name"])
        if match:
            kind, index = match.groups()
            role = f"otherLine_{index}" if kind == "Line" else f"otherAngle_{index}_points"
            locks[role] = next(
                (k for k in ("parallel", "perpendicular") if f"locked {k}" in (row.get("details") or "")),
                "none",
            )
    return settings, tracks, locks


def apply_csv(logic, prepared, volume):
    settings, tracks, locks = prepared
    logic._updating = True
    try:
        logic.ensure_nodes()
        for role in _input_specs():
            node = logic.get_node(role)
            node.RemoveAllControlPoints()
            for attr in (
                TEMPLATE_ATTRIBUTE,
                VIEW_AXES,
                FRAGMENT_ANGLE,
                FRAGMENT_CUT,
                "PelvicXrayMeasurements.NextUseSharedPoints",
            ):
                node.SetAttribute(attr, None)
        for role in (*logic.other_point_roles(), *logic.other_line_roles(), *logic.other_angle_roles()):
            logic._remove_dynamic_role(role)
        logic.set_calibration_ball_present(settings["calibrationBallPresent"])
        logic.set_calibration_ball_diameter_mm(settings["calibrationBallDiameterMm"])
        logic.set_case_comments(settings["comments"])
        logic.set_case_export_timestamp(settings["exportTimestamp"])
        if not logic.annotator_name:
            logic.set_annotator_name(settings["annotatorName"])
        for key, sides in settings["neckAxisOptions"].items():
            for side, options in sides.items():
                logic.set_axis_lock_to_center_enabled(key, side, options["lockToCenter"])
                logic.set_axis_use_single_guide_enabled(key, side, options["useSingleGuide"])
        for role, (points, labels, mode, segments, attrs) in tracks.items():
            node = logic.get_node(role, create_if_missing=True)
            if role.startswith("otherAngle_"):
                for suffix in ("referenceArm", "freeArm"):
                    logic.get_node(role.removesuffix("points") + suffix, create_if_missing=True)
            if role in locks:
                node.SetAttribute(
                    OTHER_LINE_LOCK_ATTRIBUTE
                    if role.startswith("otherLine_")
                    else OTHER_ANGLE_LOCK_ATTRIBUTE,
                    locks[role],
                )
            for attr, value in attrs.items():
                if attr.startswith("PelvicXrayMeasurements.") and attr != "PelvicXrayMeasurements.Role":
                    node.SetAttribute(attr, str(value))
            if mode != "":
                node.SetCurveType(int(mode))
                node.SetNumberOfPointsPerInterpolatingSegment(segments)
            logic._set_named_points(node, points, labels)
            node.SetDisplayVisibility(True)
    finally:
        logic._updating = False
    return logic.update_all_derived_measurements(volume)
