"""Unit tests for the synthetic replay scenario builder."""
# ruff: noqa: I001
from __future__ import annotations

import pytest

from PelvicXrayMeasurementsConstants import OtherAngleLockMode
from scenario_definition import (
    CUSTOM_ANGLES,
    CUSTOM_LINES,
    NECK_AXIS_OPTIONS,
    SCENARIO_OMITTED_ROLES,
    STATIC_ROLE_POINTS,
    build_randomized_full_scenario,
    circle_points,
    ellipse_points,
    point,
    transform_point,
    transform_points,
)


def test_circle_points_and_ellipse_points_sample_expected_shapes() -> None:
    """Synthetic point samplers should stay mathematically exact."""

    circle = circle_points(point(0.0, 0.0), 5.0, (0.0, 90.0, 180.0))
    assert circle[0] == (5.0, 0.0, 0.0)
    assert circle[1] == pytest.approx((0.0, 5.0, 0.0))
    assert circle[2] == pytest.approx((-5.0, 0.0, 0.0))

    ellipse = ellipse_points(point(0.0, 0.0), 4.0, 2.0, 0.0, (0.0, 90.0))
    assert ellipse[0] == pytest.approx((4.0, 0.0, 0.0))
    assert ellipse[1] == pytest.approx((0.0, 2.0, 0.0))


def test_transform_helpers_apply_similarity_transform() -> None:
    """Shared scenario transforms should preserve geometric coherence."""

    transformed = transform_point(point(1.0, 0.0), scale=2.0, rotation_degrees=90.0, translation_xy=(3.0, 4.0))
    assert transformed == pytest.approx((3.0, 6.0, 0.0))

    transformed_points = transform_points(
        [point(1.0, 0.0), point(0.0, 1.0)],
        scale=1.0,
        rotation_degrees=180.0,
        translation_xy=(1.0, -1.0),
    )
    assert transformed_points[0] == pytest.approx((0.0, -1.0, 0.0))
    assert transformed_points[1] == pytest.approx((1.0, -2.0, 0.0))


def test_randomized_full_scenario_is_seeded_and_omits_expected_roles() -> None:
    """Scenario regeneration should be reproducible per seed and vary across seeds."""

    scenario_a = build_randomized_full_scenario(seed=123)
    scenario_b = build_randomized_full_scenario(seed=123)
    scenario_c = build_randomized_full_scenario(seed=124)

    assert scenario_a == scenario_b
    assert scenario_a["translationXY"] != scenario_c["translationXY"]
    assert set(SCENARIO_OMITTED_ROLES).isdisjoint(set(scenario_a["staticRolePoints"]))
    assert scenario_a["neckAxisOptions"] == NECK_AXIS_OPTIONS
    assert len(scenario_a["customLines"]) == len(CUSTOM_LINES)
    assert len(scenario_a["customAngles"]) == len(CUSTOM_ANGLES)
    assert {
        line_data["lockMode"] for line_data in scenario_a["customLines"].values()
    } == {
        OtherAngleLockMode.NONE,
        OtherAngleLockMode.PARALLEL,
        OtherAngleLockMode.PERPENDICULAR,
    }
    assert {
        angle_data["lockMode"] for angle_data in scenario_a["customAngles"].values()
    } == {
        OtherAngleLockMode.NONE,
        OtherAngleLockMode.PARALLEL,
        OtherAngleLockMode.PERPENDICULAR,
    }


def test_randomized_scenario_preserves_relative_point_offsets() -> None:
    """The shared transform should preserve local geometry within each role."""

    scenario = build_randomized_full_scenario(seed=999)
    role_name = next(iter(STATIC_ROLE_POINTS))
    original_points = STATIC_ROLE_POINTS[role_name]
    transformed_points = scenario["staticRolePoints"][role_name]

    original_dx = original_points[1][0] - original_points[0][0]
    original_dy = original_points[1][1] - original_points[0][1]
    transformed_dx = transformed_points[1][0] - transformed_points[0][0]
    transformed_dy = transformed_points[1][1] - transformed_points[0][1]

    assert transformed_dx == pytest.approx(original_dx)
    assert transformed_dy == pytest.approx(original_dy)
