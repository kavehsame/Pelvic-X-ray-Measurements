"""Check the geometry and safety gate used by coordinate-only point suggestions."""
from __future__ import annotations

import numpy as np
import pytest
import hashlib

from PelvicXrayMeasurementsAutoPlacement import (
    enforce_morphology_side_constraints,
    feature_specs,
    make_frame,
    normalized_point,
    predict_feature,
    predict_shaft_from_image,
    shaft_image_features,
    world_point,
)


def test_morphology_includes_saved_cortex_points():
    morphology = next(item for item in feature_specs("pre") if item[0] == "shaft_morphology")
    assert morphology[2] == (("shaftMorphologyLTPoints", 2), ("shaftMorphologyPoints", 10))


@pytest.mark.parametrize("side,lateral_indices,medial_indices", [
    ("left", (1, 3, 6, 7, 9), (0, 2, 4, 5, 8)),
    ("right", (0, 2, 4, 5, 8), (1, 3, 6, 7, 9)),
])
def test_morphology_side_constraints_keep_lateral_and_medial_points_on_their_side(
    side, lateral_indices, medial_indices
):
    frame = (
        np.zeros(3),
        50.0,
        np.eye(2),
        np.array([1.0, 0.0, 0.0]),
    )
    morphology = np.array([[4.0, float(index), 0.0] for index in range(10)], dtype=float)
    corrected = np.asarray(enforce_morphology_side_constraints(
        morphology, [0.0, 0.0, 0.0], [0.0, 1.0, 0.0], frame, side
    ))
    assert np.all(corrected[list(lateral_indices), 0] > 0.0)
    assert np.all(corrected[list(medial_indices), 0] < 0.0)
    np.testing.assert_allclose(corrected[:, 1], morphology[:, 1])
    np.testing.assert_allclose(corrected[list(lateral_indices)], morphology[list(lateral_indices)])


def test_shaft_prediction_depends_on_radiograph_and_fails_without_coverage(tmp_path):
    yy, xx = np.mgrid[:600, :600]
    image_a = (30 + 170 * (np.abs(xx - 300) < 35)).astype(np.uint8)
    image_b = (30 + 170 * (np.abs(xx - 340) < 35)).astype(np.uint8)
    matrix = np.eye(4)
    matrix[0, 3] = matrix[1, 3] = 300
    frame = make_frame("right", [[-50, -25, 0], [50, -25, 0]], [0, 0, 0], 50)
    positions = [[-.3, -2], [.3, -2], [-.4, -3], [.4, -3]]
    prior_points = np.array([world_point(point, frame) for point in positions])
    features_a = shaft_image_features(image_a, matrix, prior_points, frame, 1)
    features_b = shaft_image_features(image_b, matrix, prior_points, frame, 1)
    assert features_a is not None and features_b is not None
    index = int(np.argmax(np.abs(features_a - features_b)))
    assert abs(features_a[index] - features_b[index]) > .01
    coefficients = np.zeros((8, len(features_a)), dtype=np.float32)
    coefficients[0, index] = 2.0
    resource = tmp_path / "auto_point_image_model.npz"
    np.savez_compressed(resource, pre_coef=coefficients, pre_intercept=np.zeros(8, dtype=np.float32))
    matrix_for_point = lambda xy: [[xy[0], xy[1]], [0, 0], [0, 0]]
    model = {"shaft_image_model_sha256": hashlib.sha256(resource.read_bytes()).hexdigest(), "modes": {"pre": {
        "anchor_mean": frame[3][1:].tolist(), "anchor_cov_inverse": np.eye(2).tolist(),
        "features": {"shaft_axis": {"requires_radiograph": True, "roles": {
            "shaftGuideProximal": [matrix_for_point(p) for p in positions[:2]],
            "shaftGuideDistal": [matrix_for_point(p) for p in positions[2:]],
        }}},
    }}}
    predicted_a = predict_shaft_from_image(model, "pre", frame, image_a, matrix, 1, resource)
    predicted_b = predict_shaft_from_image(model, "pre", frame, image_b, matrix, 1, resource)
    assert not np.allclose(predicted_a["shaftGuideProximal"][0], predicted_b["shaftGuideProximal"][0])
    with pytest.raises(ValueError, match="enough of the shaft"):
        predict_shaft_from_image(model, "pre", frame, np.zeros_like(image_a), matrix, 1, resource)


@pytest.mark.parametrize("side,sign", [("left", -1), ("right", 1)])
def test_mirrored_frame_round_trip(side, sign):
    center = np.array([100.0 * sign, -90.0, 0.0])
    reference = np.array([[50.0 * sign, -115.0, 0.0], [150.0 * sign, -115.0, 0.0]])
    frame = make_frame(side, reference, center, 50.0)
    anatomical = np.array([135.0 * sign, -60.0, 0.0])
    normalized = normalized_point(anatomical, frame)
    assert normalized[0] == pytest.approx(0.7)
    assert normalized[1] == pytest.approx(0.6)
    np.testing.assert_allclose(world_point(normalized, frame), anatomical)


def test_prediction_uses_reference_anchor_and_rejects_misplaced_line():
    model = {"modes": {"pre": {
        "anchor_mean": [1.0, -0.5],
        "anchor_cov_inverse": [[1.0, 0.0], [0.0, 1.0]],
        "features": {"sharp": {"roles": {"sharpAngleLine": [
            [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
            [[1.0, 0.5], [0.0, 0.0], [0.0, 0.0]],
        ]}}},
    }}}
    center = [0.0, 0.0, 0.0]
    frame = make_frame("right", [[50, -25, 0], [-50, -25, 0]], center, 50)
    predicted = predict_feature(model, "pre", "sharp", frame)["sharpAngleLine"]
    np.testing.assert_allclose(predicted[0], [50, -25, 0])
    np.testing.assert_allclose(predicted[1], [50, 25, 0])
    low_reference = make_frame("right", [[50, -300, 0], [-50, -300, 0]], center, 50)
    with pytest.raises(ValueError, match="teardrop level"):
        predict_feature(model, "pre", "sharp", low_reference)
