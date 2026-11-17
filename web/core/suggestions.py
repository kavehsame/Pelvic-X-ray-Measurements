"""Fork-owned guided placement from the trained aggregate point model."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from .scene import vtk_to_numpy
from .scene import vtkMatrix4x4

from .auto_placement import (
    enforce_morphology_side_constraints,
    feature_specs,
    make_frame,
    predict_feature,
    predict_shaft_from_image,
    read_model,
)
from .schema import side_role


RESOURCE_DIR = Path(__file__).with_name("resources")
MODEL_PATH = RESOURCE_DIR / "auto_point_model.json"
IMAGE_MODEL_PATH = RESOURCE_DIR / "auto_point_image_model.npz"


def _volume_pixels_and_matrix(volume):
    """Read a single-slice radiograph and its RAS-to-IJK transform."""

    image = volume.GetImageData()
    if image is None:
        raise ValueError("The current volume has no image data.")
    dimensions = image.GetDimensions()
    if dimensions[2] != 1:
        raise ValueError("Automatic placement requires a single-slice radiograph.")
    pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape((dimensions[1], dimensions[0]))
    matrix = vtkMatrix4x4()
    volume.GetRASToIJKMatrix(matrix)
    return pixels, np.asarray([[matrix.GetElement(row, column) for column in range(4)] for row in range(4)])


def _inside_image(point, volume) -> bool:
    matrix = vtkMatrix4x4()
    volume.GetRASToIJKMatrix(matrix)
    ijk = matrix.MultiplyPoint([float(point[0]), float(point[1]), float(point[2]), 1.0])
    extent = volume.GetImageData().GetExtent()
    return all(extent[2 * axis] - 1e-5 <= ijk[axis] <= extent[2 * axis + 1] + 1e-5 for axis in range(3))


class SuggestionController:
    """Validate anchors, offer selected features, and place editable MRML points."""

    def __init__(self, server, placement, cases):
        self.server = server
        self.placement = placement
        self.cases = cases
        self.model = None
        self.mode = None
        self.side = None
        self.frame = None
        self.scale = None
        self.available = {}

    def open_dialog(self) -> None:
        try:
            self._prepare()
        except (OSError, KeyError, TypeError, ValueError) as error:
            self.server.state.pelvic_instruction = f"Automatic placement unavailable: {error}"
            return
        for key, _label, _roles in feature_specs(self.mode):
            self.server.state[f"pelvic_auto_{key}"] = key in self.available
            self.server.state[f"pelvic_auto_available_{key}"] = key in self.available
        self.server.state.pelvic_auto_mode = "Pre-operative" if self.mode == "pre" else "Post-operative"
        self.server.state.pelvic_auto_dialog = True

    def _prepare(self) -> None:
        self.placement.update_derived()
        if not MODEL_PATH.is_file():
            raise ValueError("The fork's trained coordinate model is missing.")
        side = str(self.server.state.pelvic_active_side or "left")
        calibration = self.placement.points_for_role("calibrationPoints")
        reference = self.placement.points_for_role("referenceLine")
        native = self.placement.points_for_role(side_role(side, "femurHeadPoints"))
        implant = self.placement.points_for_role(side_role(side, "implantHeadPoints"))
        if len(calibration) < 3 or len(reference) < 2 or (len(native) >= 3) == (len(implant) >= 3):
            raise ValueError(
                "Place the calibration ball, teardrop-level reference line, and exactly one native or implant head on the active side first."
            )
        _ball_center, ball_diameter = self.placement.circle_from_three(calibration)
        if ball_diameter <= 0:
            raise ValueError("The calibration ball is invalid.")
        expected_ball_mm = float(self.server.state.pelvic_ball_diameter)
        if not np.isfinite(expected_ball_mm) or expected_ball_mm <= 0:
            raise ValueError("Enter a positive calibration-ball diameter in millimeters.")
        mode = "pre" if len(native) >= 3 else "post"
        head_center, head_diameter = self.placement.circle_from_three(native if mode == "pre" else implant)
        frame = make_frame(side, reference[:2], head_center, head_diameter)
        model = read_model(MODEL_PATH)
        available = model["modes"][mode]["features"]
        if not available:
            raise ValueError("No trained feature groups are available for this case type.")
        # Reject incompatible anchor geometry once, before offering a dialog in
        # which every selected feature would fail for the same reason.
        predict_feature(model, mode, next(iter(available)), frame)
        self.side, self.mode, self.frame, self.model = side, mode, frame, model
        self.scale = expected_ball_mm / ball_diameter
        self.available = available

    def place_selected(self) -> None:
        if self.model is None or self.mode is None:
            return
        selected = [
            key
            for key, _label, _roles in feature_specs(self.mode)
            if key in self.available and self.server.state[f"pelvic_auto_{key}"]
        ]
        self.server.state.pelvic_auto_dialog = False
        if not selected:
            self.server.state.pelvic_instruction = "No features selected."
            return
        volume = self.cases.current_volume()
        if volume is None:
            self.server.state.pelvic_instruction = "Load a radiograph before automatic placement."
            return
        self.placement.finish(silent=True)
        placed, skipped = [], []
        for key in sorted(selected, key=lambda item: (item != "shaft_axis", item == "shaft_morphology")):
            try:
                if key == "shaft_axis":
                    pixels, matrix = _volume_pixels_and_matrix(volume)
                    proposal = predict_shaft_from_image(
                        self.model,
                        self.mode,
                        self.frame,
                        pixels,
                        matrix,
                        self.scale,
                        IMAGE_MODEL_PATH,
                    )
                else:
                    proposal = predict_feature(self.model, self.mode, key, self.frame)
                if key == "shaft_morphology":
                    axis_points = self.placement.points_for_role(side_role(self.side, "shaftAxis"))
                    if len(axis_points) < 2:
                        raise ValueError("Place the shaft guides first to derive the shaft axis.")
                    origin = 0.5 * (axis_points[0] + axis_points[1])
                    direction = axis_points[1] - axis_points[0]
                    proposal["shaftMorphologyPoints"] = enforce_morphology_side_constraints(
                        proposal["shaftMorphologyPoints"],
                        origin,
                        direction,
                        self.frame,
                        self.side,
                    )
                prepared = []
                for base_role, points in proposal.items():
                    role = side_role(self.side, base_role)
                    existing = self.placement.points_for_role(role)
                    if len(existing) > len(points):
                        raise ValueError("Existing markup has an unexpected number of points.")
                    merged = [*existing, *points[len(existing) :]]
                    if not all(_inside_image(point, volume) for point in merged):
                        raise ValueError("Suggested points extend outside the radiograph.")
                    prepared.append((role, merged))
                with self.placement.scene_edit():
                    for role, points in prepared:
                        self.placement.put_points(role, points)
                    if key == "neck_axis":
                        self.server.state.pelvic_neck_use_single_guide = True
                        self.server.state.pelvic_neck_lock_to_center = True
                    if key == "implant_neck_axis":
                        self.server.state.pelvic_implant_neck_lock_to_center = True
                        self.server.state.pelvic_implant_neck_use_single_guide = True
                    if key in {"neck_axis", "implant_neck_axis"}:
                        self.placement.store_axis_options()
                self.placement.update_derived()
                placed.append(key)
            except (OSError, KeyError, TypeError, ValueError) as error:
                skipped.append(f"{key}: {error}")
        message = f"Placed {len(placed)} editable feature group(s) on the {self.side} side. Review all suggested points on the image."
        if skipped:
            message += " Skipped: " + "; ".join(skipped)
        self.server.state.pelvic_instruction = message
