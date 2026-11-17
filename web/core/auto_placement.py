"""Lightweight, image-free priors for editable landmark placement.

The reference line supplies orientation and its endpoint nearest the active head supplies a
teardrop-level anchor. Coordinates are normalized by the fitted head diameter and mirrored to
one lateral/superior frame. The saved model contains aggregate regression coefficients only.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np


# Candidate targets are user-editable input roles with repeatable point order.
# Derived axes, bilateral LLD, and contours are not predicted independently.
FEATURES = {
    "pre": (
        (
            "shaft_axis",
            "Femoral shaft axis (image-guided rough estimate)",
            (("shaftGuideProximal", 2), ("shaftGuideDistal", 2)),
        ),
        ("neck_axis", "Femoral neck axis", (("neckGuideProximal", 2),)),
        ("tonnis", "Acetabular Index (Tönnis)", (("tonnisAngleLine", 2),)),
        ("sharp", "Sharp angle", (("sharpAngleLine", 2),)),
        ("lce", "LCE angle", (("lceAnglePoint", 1),)),
        ("acetabular_offset", "Acetabular offset", (("acetabularOffsetLineA", 2), ("acetabularOffsetLineB", 2))),
        ("femoral_offset", "Femoral offset", (("femoralOffsetLine", 2),)),
        (
            "extrusion_index",
            "Femoral head extrusion index",
            (("extrusionIndexMedialLine", 2), ("extrusionIndexMiddleLine", 2), ("extrusionIndexLateralLine", 2)),
        ),
        # Saved annotations include both LT landmarks and all ten adjustable
        # morphology points. The calculation later respects their lateral offsets.
        (
            "shaft_morphology",
            "Femur shaft morphology (learned rough estimate)",
            (("shaftMorphologyLTPoints", 2), ("shaftMorphologyPoints", 10)),
        ),
    ),
    "post": (
        (
            "shaft_axis",
            "Femoral shaft axis (image-guided rough estimate)",
            (("shaftGuideProximal", 2), ("shaftGuideDistal", 2)),
        ),
        ("inclination", "Acetabular inclination", (("acetabularInclinationLine", 2),)),
        ("cup_opening", "Cup opening ellipse", (("cupOpeningEllipsePoints", 6),)),
        ("implant_neck_axis", "Implant neck axis", (("implantNeckGuideProximal", 2),)),
        (
            "implant_alignment",
            "Stem alignment",
            (("implantAlignmentGuideProximal", 2), ("implantAlignmentGuideDistal", 2)),
        ),
        (
            "post_acetabular_offset",
            "Post-op acetabular offset",
            (("postOpAcetabularOffsetLineA", 2), ("postOpAcetabularOffsetLineB", 2)),
        ),
        ("post_femoral_offset", "Post-op femoral offset", (("postOpFemoralOffsetLine", 2),)),
    ),
}

# The saved morphology point order follows the image-side annotation convention. In the source
# annotations A/OuterA/InnerA are medial on the left and lateral on the right; B is the converse.
MORPHOLOGY_A_POINT_INDICES = frozenset((0, 2, 4, 5, 8))
MORPHOLOGY_B_POINT_INDICES = frozenset((1, 3, 6, 7, 9))


def feature_specs(mode):
    return FEATURES[mode]


def make_frame(side, reference_points, head_center, diameter):
    """Return an invertible frame and anchor predictors, or reject invalid prerequisites."""
    head = np.asarray(head_center, dtype=float)
    reference = np.asarray(reference_points, dtype=float)
    diameter = float(diameter)
    if (
        head.shape != (3,)
        or reference.shape != (2, 3)
        or not np.isfinite(head).all()
        or not np.isfinite(reference).all()
        or not np.isfinite(diameter)
        or diameter <= 0
    ):
        raise ValueError("A fitted head, positive diameter, and two reference points are required.")
    lateral = reference[1, :2] - reference[0, :2]
    length = np.linalg.norm(lateral)
    if length < 1e-6 or abs(lateral[0]) < 0.25 * length:
        raise ValueError("The reference line must be approximately horizontal in the image.")
    lateral /= length
    if lateral[0] * (-1 if side == "left" else 1) < 0:
        lateral *= -1
    superior = np.array([-lateral[1], lateral[0]])
    if superior[1] < 0:
        superior *= -1
    near = reference[np.argmin(np.abs(reference[:, 0] - head[0]))]
    axes = np.stack([lateral, superior])
    anchor = axes @ (near[:2] - head[:2]) / diameter
    return head, diameter, axes, np.array([1.0, anchor[0], anchor[1]])


def normalized_point(point, frame):
    head, diameter, axes, _ = frame
    return axes @ (np.asarray(point, dtype=float)[:2] - head[:2]) / diameter


def world_point(normalized, frame):
    head, diameter, axes, _ = frame
    xy = head[:2] + diameter * (axes.T @ np.asarray(normalized, dtype=float))
    return np.array([xy[0], xy[1], head[2]])


def shaft_image_features(image, ras_to_ijk, predicted_points, frame, calibration_scale):
    """Sample a side-normalized radiograph patch around the proposed shaft guides.

    Returns None when the image does not cover enough of the shaft region. Sampling
    uses the pelvic reference frame, so right and left images have the same anatomy-
    oriented coordinates without retaining a patient image in the model.
    """
    image = np.asarray(image)
    matrix = np.asarray(ras_to_ijk, dtype=float)
    points = np.asarray(predicted_points, dtype=float)
    scale = float(calibration_scale)
    if image.ndim != 2 or matrix.shape != (4, 4) or points.shape != (4, 3) or not np.isfinite(scale) or scale <= 0:
        return None
    if not np.isfinite(matrix).all() or not np.isfinite(points).all():
        return None
    midpoint = points.mean(axis=0)
    lateral, superior = frame[2]
    x_mm = np.linspace(-90.0, 90.0, 64)[None, :]
    y_mm = np.linspace(-120.0, 120.0, 80)[:, None]
    world_x = midpoint[0] + (lateral[0] * x_mm - superior[0] * y_mm) / scale
    world_y = midpoint[1] + (lateral[1] * x_mm - superior[1] * y_mm) / scale
    ij_x = matrix[0, 0] * world_x + matrix[0, 1] * world_y + matrix[0, 2] * midpoint[2] + matrix[0, 3]
    ij_y = matrix[1, 0] * world_x + matrix[1, 1] * world_y + matrix[1, 2] * midpoint[2] + matrix[1, 3]
    valid = (ij_x >= 0) & (ij_x < image.shape[1] - 1) & (ij_y >= 0) & (ij_y < image.shape[0] - 1)
    if np.mean(valid) < 0.55:
        return None
    clipped_x = np.clip(ij_x, 0, image.shape[1] - 2)
    clipped_y = np.clip(ij_y, 0, image.shape[0] - 2)
    ix, iy = clipped_x.astype(int), clipped_y.astype(int)
    wx, wy = clipped_x - ix, clipped_y - iy
    patch = (
        (1 - wx) * (1 - wy) * image[iy, ix]
        + wx * (1 - wy) * image[iy, ix + 1]
        + (1 - wx) * wy * image[iy + 1, ix]
        + wx * wy * image[iy + 1, ix + 1]
    )
    lo, hi = np.percentile(patch[valid], [5, 95])
    if hi - lo < 10:
        return None
    patch = np.clip((patch - lo) / (hi - lo), 0, 1)
    patch[~valid] = 0
    gradient_y, gradient_x = np.gradient(patch)
    return np.concatenate([patch.ravel(), gradient_x.ravel() * 5, gradient_y.ravel() * 5]).astype(np.float32)


def read_model(path):
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if model.get("schema_version") != 1:
        raise ValueError("Unsupported automatic placement model schema.")
    return model


def predict_feature(model, mode, feature_key, frame):
    """Predict points and reject anchor geometry unlike the annotated training examples."""
    mode_model = model["modes"].get(mode, {})
    entry = mode_model.get("features", {}).get(feature_key)
    if entry is None:
        raise ValueError("No validated model is available for this feature.")
    anchor = frame[3][1:]
    center = np.asarray(mode_model["anchor_mean"], dtype=float)
    inverse = np.asarray(mode_model["anchor_cov_inverse"], dtype=float)
    distance = float(np.sqrt(max(0.0, (anchor - center) @ inverse @ (anchor - center))))
    if distance > 4.0:
        raise ValueError(
            "Reference line/head relationship is outside the training range; check that the line is at teardrop level."
        )
    predictions = {}
    for role, coefficients in entry["roles"].items():
        predictions[role] = [world_point(frame[3] @ np.asarray(matrix, dtype=float), frame) for matrix in coefficients]
    return predictions


def predict_shaft_from_image(model, mode, frame, image, ras_to_ijk, calibration_scale, image_model_path):
    """Correct the coordinate prior using aggregate radiograph-trained coefficients.

    There is deliberately no coordinate-only fallback for this low-accuracy feature.
    """
    entry = model["modes"][mode]["features"].get("shaft_axis")
    if entry is None or not entry.get("requires_radiograph"):
        raise ValueError("No image-guided shaft model is available.")
    image_model_path = Path(image_model_path)
    if hashlib.sha256(image_model_path.read_bytes()).hexdigest() != model.get("shaft_image_model_sha256"):
        raise ValueError("The shaft image model does not match its coordinate model.")
    prior = predict_feature(model, mode, "shaft_axis", frame)
    roles = ("shaftGuideProximal", "shaftGuideDistal")
    predicted = np.asarray([point for role in roles for point in prior[role]], dtype=float)
    features = shaft_image_features(image, ras_to_ijk, predicted, frame, calibration_scale)
    if features is None:
        raise ValueError("The radiograph does not show enough of the shaft for image-guided placement.")
    with np.load(image_model_path, allow_pickle=False) as arrays:
        coefficients = arrays[f"{mode}_coef"]
        intercept = arrays[f"{mode}_intercept"]
    if coefficients.shape != (8, len(features)) or intercept.shape != (8,):
        raise ValueError("Invalid shaft image model dimensions.")
    correction_mm = (coefficients @ features + intercept).reshape(4, 2)
    if not np.isfinite(correction_mm).all() or np.max(np.linalg.norm(correction_mm, axis=1)) > 60:
        raise ValueError("Shaft image correction is outside its safe range.")
    scale = float(calibration_scale)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("A valid calibration scale is required for shaft placement.")
    adjusted = [
        world_point(normalized_point(point, frame) + delta / (frame[1] * scale), frame)
        for point, delta in zip(predicted, correction_mm, strict=True)
    ]
    return {roles[0]: adjusted[:2], roles[1]: adjusted[2:]}


def enforce_morphology_side_constraints(morphology_points, axis_origin, axis_direction, frame, side):
    """Reflect only inferred cortex points that cross the *derived* shaft axis.

    The learned positions and distances are retained when they lie on the correct side. A
    misplaced point is reflected at its current axial station, preserving its learned distance
    from the axis. The A/B anatomical assignment follows the saved annotations for each side.
    """

    points = np.asarray(morphology_points, dtype=float)
    origin = np.asarray(axis_origin, dtype=float)
    direction = np.asarray(axis_direction, dtype=float)
    if points.shape != (10, 3) or origin.shape != (3,) or direction.shape != (3,):
        raise ValueError("The ten morphology points and a derived shaft axis are required.")
    if not np.isfinite(points).all() or not np.isfinite(origin).all() or not np.isfinite(direction).all():
        raise ValueError("Morphology points and shaft axis must be finite.")
    axis_length = float(np.linalg.norm(direction))
    if axis_length < 1e-6:
        raise ValueError("The derived shaft axis has no direction.")
    direction /= axis_length

    lateral = np.array([float(frame[2][0][0]), float(frame[2][0][1]), 0.0], dtype=float)
    lateral -= direction * float(np.dot(lateral, direction))
    lateral_length = float(np.linalg.norm(lateral))
    if lateral_length < 1e-6:
        raise ValueError("The derived shaft axis has no medial-lateral direction.")
    lateral /= lateral_length

    if str(side) == "left":
        lateral_indices = MORPHOLOGY_B_POINT_INDICES
    elif str(side) == "right":
        lateral_indices = MORPHOLOGY_A_POINT_INDICES
    else:
        raise ValueError("A left or right side is required for morphology placement.")
    minimum_offset = max(1e-3, 0.01 * float(frame[1]))
    corrected = []
    for index, point in enumerate(points):
        transverse_offset = float(np.dot(point - origin, lateral))
        desired_sign = 1.0 if index in lateral_indices else -1.0
        if desired_sign * transverse_offset >= minimum_offset:
            corrected.append(point.copy())
        else:
            corrected.append(
                point + (desired_sign * max(abs(transverse_offset), minimum_offset) - transverse_offset) * lateral
            )
    return corrected
