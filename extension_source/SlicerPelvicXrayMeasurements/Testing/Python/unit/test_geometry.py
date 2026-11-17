"""Unit tests for VTK-independent geometry helpers."""
from __future__ import annotations


import math
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import PelvicXrayMeasurementsGeometry as geometry  # noqa: N813


def test_as_array_and_vector_length() -> None:
    """Numeric helpers should normalize values into NumPy-friendly form."""

    vector = geometry.as_array([3, 4, 0])
    assert isinstance(vector, np.ndarray)
    assert geometry.vector_length(vector) == pytest.approx(5.0)


def test_unit_vector_handles_zero_length() -> None:
    """Degenerate vectors should return None instead of unstable directions."""

    assert geometry.unit_vector(np.array([0.0, 0.0, 0.0])) is None
    unit = geometry.unit_vector(np.array([3.0, 4.0, 0.0]))
    np.testing.assert_allclose(unit, np.array([0.6, 0.8, 0.0]))


@pytest.mark.parametrize(
    ("value", "minimum", "maximum", "expected"),
    [
        (2.0, -1.0, 1.0, 1.0),
        (-3.0, -1.0, 1.0, -1.0),
        (0.25, -1.0, 1.0, 0.25),
    ],
)
def test_clamp(value: float, minimum: float, maximum: float, expected: float) -> None:
    """Clamp should saturate values only outside the configured interval."""

    assert geometry.clamp(value, minimum, maximum) == expected


def test_circle_from_three_points_returns_expected_fit() -> None:
    """Three exact circle points should recover the original circle."""

    fit = geometry.circle_from_three_points(
        np.array([6.0, 2.0, 0.0]),
        np.array([1.0, 7.0, 0.0]),
        np.array([-4.0, 2.0, 0.0]),
    )
    assert fit is not None
    np.testing.assert_allclose(fit.center, np.array([1.0, 2.0, 0.0]))
    assert fit.radius == pytest.approx(5.0)
    assert fit.diameter == pytest.approx(10.0)
    np.testing.assert_allclose(fit.normal, np.array([0.0, 0.0, 1.0]))


def test_circle_from_three_points_rejects_collinear_input() -> None:
    """Collinear points cannot define a stable circle."""

    assert (
        geometry.circle_from_three_points(
            np.array([0.0, 0.0, 0.0]),
            np.array([1.0, 1.0, 0.0]),
            np.array([2.0, 2.0, 0.0]),
        )
        is None
    )


def test_ellipse_parameters_from_conic_recovers_axes() -> None:
    """Analytic ellipse coefficients should recover center and radii."""

    parameters = geometry.ellipse_parameters_from_conic(4.0, 0.0, 9.0, 0.0, 0.0, -36.0)
    assert parameters is not None
    np.testing.assert_allclose(parameters.center_2d, np.array([0.0, 0.0]))
    assert parameters.major_radius == pytest.approx(3.0)
    assert parameters.minor_radius == pytest.approx(2.0)


def test_ellipse_from_points_in_plane_recovers_known_ellipse() -> None:
    """Best-fit ellipse recovery should be stable for exact sampled points."""

    center = np.array([10.0, -5.0, 0.0])
    major_direction = np.array([1.0, 0.0, 0.0])
    minor_direction = np.array([0.0, 1.0, 0.0])
    points = geometry.ellipse_sample_points(
        center=center,
        major_direction=major_direction,
        minor_direction=minor_direction,
        major_radius=4.0,
        minor_radius=2.0,
        resolution=24,
    )

    fit = geometry.ellipse_from_points_in_plane(
        [np.asarray(point, dtype=float) for point in points],
        axis_i=np.array([1.0, 0.0, 0.0]),
        axis_j=np.array([0.0, 1.0, 0.0]),
    )
    assert fit is not None
    np.testing.assert_allclose(fit.center, center, atol=1e-6)
    assert fit.major_radius == pytest.approx(4.0, abs=1e-5)
    assert fit.minor_radius == pytest.approx(2.0, abs=1e-5)


def test_version_angle_and_projection_helpers() -> None:
    """Ellipse utilities should keep their trigonometric convention stable."""

    assert geometry.version_angle(10.0, 6.0) == pytest.approx(math.degrees(math.asin(0.6)))

    ellipse = geometry.EllipseFit(
        center=np.array([0.0, 0.0, 0.0]),
        major_radius=4.0,
        minor_radius=2.0,
        major_direction=np.array([1.0, 0.0, 0.0]),
        minor_direction=np.array([0.0, 1.0, 0.0]),
        major_endpoints=(np.array([-4.0, 0.0, 0.0]), np.array([4.0, 0.0, 0.0])),
        minor_endpoints=(np.array([0.0, -2.0, 0.0]), np.array([0.0, 2.0, 0.0])),
    )
    projected = geometry.project_points_onto_ellipse(
        [np.array([8.0, 0.0, 0.0]), np.array([0.0, 3.0, 0.0])],
        ellipse,
    )
    assert len(projected) == 2
    np.testing.assert_allclose(projected[0], np.array([4.0, 0.0, 0.0]), atol=1e-6)
    np.testing.assert_allclose(projected[1], np.array([0.0, 2.0, 0.0]), atol=1e-6)


def test_ellipse_from_major_minor_diameters() -> None:
    """Explicit diameter endpoints should reconstruct the same ellipse."""

    fit = geometry.ellipse_from_major_minor_diameters(
        major_points=[np.array([-4.0, 0.0, 0.0]), np.array([4.0, 0.0, 0.0])],
        minor_points=[np.array([0.0, -2.0, 0.0]), np.array([0.0, 2.0, 0.0])],
        plane_normal=np.array([0.0, 0.0, 1.0]),
    )
    assert fit is not None
    np.testing.assert_allclose(fit.center, np.array([0.0, 0.0, 0.0]))
    assert fit.major_radius == pytest.approx(4.0)
    assert fit.minor_radius == pytest.approx(2.0)


def test_ellipse_and_circle_helpers_reject_degenerate_inputs() -> None:
    """Degenerate geometry inputs should fail safely instead of producing unstable fits."""

    assert geometry.ellipse_from_points_in_plane([], np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])) is None
    degenerate_points = [np.array([float(index), 0.0, 0.0]) for index in range(6)]
    assert geometry.ellipse_from_points_in_plane(
        degenerate_points,
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) is None
    assert geometry.circle_from_three_points(
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
    ) is None


def test_ellipse_parameters_and_version_angle_edge_cases() -> None:
    """Conic and version-angle helpers should guard invalid ellipse cases explicitly."""

    assert geometry.ellipse_parameters_from_conic(1.0, 2.0, 1.0, 0.0, 0.0, 1.0) is None
    assert geometry.ellipse_parameters_from_conic(1.0, 0.0, -1.0, 0.0, 0.0, -1.0) is None
    assert geometry.version_angle(None, 2.0) is None
    with pytest.raises(ValueError):
        geometry.version_angle(4.0, 5.0)
    assert geometry.version_angle(10.0, 6.0, degrees=False) == pytest.approx(math.asin(0.6))


def test_ellipse_sampling_projection_and_diameter_edge_cases() -> None:
    """Ellipse sampling, reconstruction, and projection should handle invalid inputs cleanly."""

    assert geometry.ellipse_sample_points(None, None, None, None, None) == []
    sampled = geometry.ellipse_sample_points(
        center=np.array([0.0, 0.0, 0.0]),
        major_direction=np.array([1.0, 0.0, 0.0]),
        minor_direction=np.array([0.0, 1.0, 0.0]),
        major_radius=3.0,
        minor_radius=1.0,
        resolution=4,
    )
    assert len(sampled) == 24

    assert geometry.ellipse_from_major_minor_diameters(
        major_points=[np.array([0.0, 0.0, 0.0])],
        minor_points=[np.array([0.0, 1.0, 0.0])],
        plane_normal=np.array([0.0, 0.0, 1.0]),
    ) is None
    assert geometry.ellipse_from_major_minor_diameters(
        major_points=[np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0])],
        minor_points=[np.array([0.0, -2.0, 0.0]), np.array([0.0, 2.0, 0.0])],
        plane_normal=np.array([0.0, 0.0, 1.0]),
    ) is None
    flipped_minor = geometry.ellipse_from_major_minor_diameters(
        major_points=[np.array([-4.0, 0.0, 0.0]), np.array([4.0, 0.0, 0.0])],
        minor_points=[np.array([0.0, 2.0, 0.0]), np.array([0.0, -2.0, 0.0])],
        plane_normal=np.array([0.0, 0.0, 1.0]),
    )
    assert flipped_minor is not None
    assert flipped_minor.minor_radius == pytest.approx(2.0)

    assert geometry.project_points_onto_ellipse(None, None) == []
    assert geometry.project_points_onto_ellipse(
        [np.array([1.0, 0.0, 0.0])],
        geometry.EllipseFit(
            center=None,
            major_radius=3.0,
            minor_radius=1.0,
            major_direction=np.array([1.0, 0.0, 0.0]),
            minor_direction=np.array([0.0, 1.0, 0.0]),
            major_endpoints=(np.array([-3.0, 0.0, 0.0]), np.array([3.0, 0.0, 0.0])),
            minor_endpoints=(np.array([0.0, -1.0, 0.0]), np.array([0.0, 1.0, 0.0])),
        ),
    ) == []


def test_plane_and_direction_helpers() -> None:
    """Plane, perpendicular, and angle helpers should preserve radiographic conventions."""

    normal = geometry.plane_normal_from_points(
        [
            np.array([0.0, 0.0, 0.0]),
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
        ]
    )
    np.testing.assert_allclose(normal, np.array([0.0, 0.0, 1.0]))

    perpendicular = geometry.in_plane_perpendicular(
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    )
    np.testing.assert_allclose(perpendicular, np.array([0.0, 1.0, 0.0]))

    combined = geometry.best_common_perpendicular(
        [np.array([1.0, 0.0, 0.0]), np.array([1.0, 0.1, 0.0])],
        np.array([0.0, 0.0, 1.0]),
    )
    assert combined is not None
    assert combined[1] > 0.9

    assert geometry.angle_deviation_from_perpendicular(
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(0.0)
    assert geometry.acute_angle_between_directions(
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(90.0)
    assert geometry.unsigned_angle_between_directions(
        np.array([1.0, 0.0, 0.0]),
        np.array([-1.0, 0.0, 0.0]),
    ) == pytest.approx(180.0)
    assert geometry.unsigned_angle_between_directions(
        np.array([1.0, 0.0, 0.0]),
        np.array([-1.0, 1.0, 0.0]) / math.sqrt(2.0),
    ) == pytest.approx(135.0)
    np.testing.assert_allclose(
        geometry.direction_aligned_to_hint(
            np.array([1.0, 1.0, 0.0]) / math.sqrt(2.0),
            np.array([-1.0, 0.0, 0.0]),
        ),
        np.array([-1.0, -1.0, 0.0]) / math.sqrt(2.0),
    )
    assert geometry.oriented_angle_between_directions(
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, -1.0, 0.0]),
        np.array([-1.0, 1.0, 0.0]) / math.sqrt(2.0),
        np.array([-1.0, 0.0, 0.0]),
    ) == pytest.approx(135.0)
    assert geometry.oriented_angle_between_directions(
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, -1.0, 0.0]),
        np.array([-1.0, -1.0, 0.0]) / math.sqrt(2.0),
        np.array([-1.0, 0.0, 0.0]),
    ) == pytest.approx(45.0)
    assert geometry.obtuse_angle_between_directions(
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(90.0)


def test_plane_and_direction_edge_cases() -> None:
    """Plane and perpendicular helpers should keep their fallback logic stable."""

    assert geometry.plane_normal_from_points([np.array([0.0, 0.0, 0.0])]) is None
    assert geometry.plane_normal_from_points(
        [
            np.array([0.0, 0.0, 0.0]),
            np.array([1.0, 1.0, 1.0]),
            np.array([2.0, 2.0, 2.0]),
        ]
    ) is None

    assert geometry.in_plane_perpendicular(None, np.array([0.0, 0.0, 1.0])) is None
    np.testing.assert_allclose(
        geometry.in_plane_perpendicular(np.array([1.0, 0.0, 0.0]), None),
        np.array([0.0, 1.0, 0.0]),
    )
    np.testing.assert_allclose(
        geometry.in_plane_perpendicular(np.array([0.0, 0.0, 1.0]), None),
        np.array([0.0, -1.0, 0.0]),
    )

    assert geometry.best_common_perpendicular([], np.array([0.0, 0.0, 1.0])) is None
    np.testing.assert_allclose(
        geometry.best_common_perpendicular(
            [np.array([1.0, 0.0, 0.0]), np.array([-1.0, 0.0, 0.0])],
            np.array([0.0, 0.0, 1.0]),
        ),
        np.array([0.0, 1.0, 0.0]),
    )


def test_reference_and_distance_helpers() -> None:
    """Reference-direction and signed-distance helpers should stay deterministic."""

    np.testing.assert_allclose(
        geometry.rightward_reference_direction(np.array([-1.0, 0.0, 0.0])),
        np.array([1.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(
        geometry.lateral_reference_direction(np.array([1.0, 0.0, 0.0]), "left"),
        np.array([1.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(
        geometry.lateral_reference_direction(np.array([1.0, 0.0, 0.0]), "right"),
        np.array([-1.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(
        geometry.superior_reference_direction(
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        ),
        np.array([0.0, 1.0, 0.0]),
    )
    assert geometry.signed_angle_from_base(
        np.array([0.0, 1.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(90.0)
    assert geometry.signed_angle_from_base(
        np.array([0.0, -1.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(-90.0)
    assert geometry.signed_angle_from_base(
        np.array([-1.0, 1.0, 0.0]) / math.sqrt(2.0),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(135.0)
    assert geometry.signed_angle_from_base(
        np.array([-1.0, -1.0, 0.0]) / math.sqrt(2.0),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(-135.0)
    assert geometry.signed_angle_from_base(
        np.array([-1.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) == pytest.approx(180.0)

    closest = geometry.closest_point_on_line(
        np.array([3.0, 4.0, 0.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(closest, np.array([3.0, 0.0, 0.0]))
    assert geometry.signed_distance_to_line_in_plane(
        np.array([0.0, 2.0, 0.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    ) == pytest.approx(2.0)


def test_reference_and_distance_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reference, sign, and projection helpers should guard tricky input combinations."""

    assert geometry.angle_deviation_from_perpendicular(None, np.array([1.0, 0.0, 0.0])) is None
    assert geometry.acute_angle_between_directions(None, np.array([1.0, 0.0, 0.0])) is None
    assert geometry.unsigned_angle_between_directions(None, np.array([1.0, 0.0, 0.0])) is None
    assert geometry.obtuse_angle_between_directions(None, np.array([1.0, 0.0, 0.0])) is None
    assert geometry.rightward_reference_direction(None) is None
    assert geometry.rightward_reference_direction(np.array([-1.0, 0.0, 0.0])) is not None

    monkeypatch.setattr(
        geometry,
        "image_axes_from_volume",
        lambda _volume: (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
    )
    np.testing.assert_allclose(
        geometry.image_right_direction(object()),
        np.array([1.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(
        geometry.image_up_direction(object()),
        np.array([0.0, -1.0, 0.0]),
    )
    assert geometry.image_right_direction(None) is None
    assert geometry.image_up_direction(None) is None

    assert geometry.lateral_reference_direction(np.array([0.0, 0.0, 0.0]), "left") is None
    with pytest.raises(ValueError):
        geometry.lateral_reference_direction(np.array([1.0, 0.0, 0.0]), "unexpected-side")
    assert geometry.superior_reference_direction(None, np.array([0.0, 0.0, 1.0])) is None
    np.testing.assert_allclose(
        geometry.superior_reference_direction(
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 0.0, -1.0]),
            None,
        ),
        np.array([0.0, -1.0, 0.0]),
    )

    assert geometry.signed_angle_from_base(
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ) is None
    assert geometry.closest_point_on_line(
        np.array([1.0, 2.0, 3.0]),
        np.array([0.0, 0.0, 0.0]),
        None,
    ) is None
    assert geometry.signed_distance_to_line_in_plane(
        np.array([1.0, 2.0, 3.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    ) is None


def test_mocked_vtk_geometry_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock-friendly VTK-backed helpers should still behave deterministically in unit tests."""

    class FakeVector3d:
        def __init__(self, x: float, y: float, z: float) -> None:
            self.values = (x, y, z)

    class FakePoints:
        def __init__(self) -> None:
            self.items: list[tuple[float, float, float]] = []

        def insert_next_point(self, x: float, y: float, z: float) -> None:
            self.items.append((x, y, z))

    class FakePointIds:
        def __init__(self) -> None:
            self.ids: list[int | None] = []

        def set_number_of_ids(self, count: int) -> None:
            self.ids = [None] * count

        def set_id(self, index: int, value: int) -> None:
            self.ids[index] = value

    class FakePolyLine:
        def __init__(self) -> None:
            self.point_ids = FakePointIds()

        def get_point_ids(self) -> FakePointIds:
            return self.point_ids

    class FakeCellArray:
        def __init__(self) -> None:
            self.cells: list[FakePolyLine] = []

        def insert_next_cell(self, poly_line: FakePolyLine) -> None:
            self.cells.append(poly_line)

    class FakePolyData:
        def __init__(self) -> None:
            self.points = None
            self.lines = None

        def set_points(self, points: FakePoints) -> None:
            self.points = points

        def set_lines(self, lines: FakeCellArray) -> None:
            self.lines = lines

    class FakeRegularPolygonSource:
        def generate_polygon_off(self) -> None:
            self.generate_polygon = False

        def set_number_of_sides(self, number: int) -> None:
            self.number_of_sides = number

        def set_radius(self, radius: float) -> None:
            self.radius = radius

        def set_center(self, x: float, y: float, z: float) -> None:
            self.center = (x, y, z)

        def set_normal(self, x: float, y: float, z: float) -> None:
            self.normal = (x, y, z)

        def update(self) -> None:
            self.updated = True

        def get_output(self) -> Any:
            return self

    class FakeSphereSource:
        def set_center(self, x: float, y: float, z: float) -> None:
            self.center = (x, y, z)

        def set_radius(self, radius: float) -> None:
            self.radius = radius

        def set_theta_resolution(self, resolution: int) -> None:
            self.theta_resolution = resolution

        def set_phi_resolution(self, resolution: int) -> None:
            self.phi_resolution = resolution

        def update(self) -> None:
            self.updated = True

        def get_output(self) -> Any:
            return self

        def get_output_port(self) -> Any:
            return self

    class FakeMatrix4x4:
        def __init__(self) -> None:
            self.values = [[0.0] * 4 for _ in range(4)]

        def set_element(self, row: int, column: int, value: float) -> None:
            self.values[row][column] = value

        def get_element(self, row: int, column: int) -> float:
            return self.values[row][column]

    class FakeTransform:
        def set_matrix(self, matrix: FakeMatrix4x4) -> None:
            self.matrix = matrix

    class FakeTransformPolyDataFilter:
        def set_input_connection(self, connection: Any) -> None:
            self.connection = connection

        def set_transform(self, transform: FakeTransform) -> None:
            self.transform = transform

        def update(self) -> None:
            self.updated = True

        def get_output(self) -> Any:
            return self

    FakePoints.InsertNextPoint = FakePoints.insert_next_point
    FakePointIds.SetNumberOfIds = FakePointIds.set_number_of_ids
    FakePointIds.SetId = FakePointIds.set_id
    FakePolyLine.GetPointIds = FakePolyLine.get_point_ids
    FakeCellArray.InsertNextCell = FakeCellArray.insert_next_cell
    FakePolyData.SetPoints = FakePolyData.set_points
    FakePolyData.SetLines = FakePolyData.set_lines
    FakeRegularPolygonSource.GeneratePolygonOff = FakeRegularPolygonSource.generate_polygon_off
    FakeRegularPolygonSource.SetNumberOfSides = FakeRegularPolygonSource.set_number_of_sides
    FakeRegularPolygonSource.SetRadius = FakeRegularPolygonSource.set_radius
    FakeRegularPolygonSource.SetCenter = FakeRegularPolygonSource.set_center
    FakeRegularPolygonSource.SetNormal = FakeRegularPolygonSource.set_normal
    FakeRegularPolygonSource.Update = FakeRegularPolygonSource.update
    FakeRegularPolygonSource.GetOutput = FakeRegularPolygonSource.get_output
    FakeSphereSource.SetCenter = FakeSphereSource.set_center
    FakeSphereSource.SetRadius = FakeSphereSource.set_radius
    FakeSphereSource.SetThetaResolution = FakeSphereSource.set_theta_resolution
    FakeSphereSource.SetPhiResolution = FakeSphereSource.set_phi_resolution
    FakeSphereSource.Update = FakeSphereSource.update
    FakeSphereSource.GetOutput = FakeSphereSource.get_output
    FakeSphereSource.GetOutputPort = FakeSphereSource.get_output_port
    FakeMatrix4x4.SetElement = FakeMatrix4x4.set_element
    FakeMatrix4x4.GetElement = FakeMatrix4x4.get_element
    FakeTransform.SetMatrix = FakeTransform.set_matrix
    FakeTransformPolyDataFilter.SetInputConnection = FakeTransformPolyDataFilter.set_input_connection
    FakeTransformPolyDataFilter.SetTransform = FakeTransformPolyDataFilter.set_transform
    FakeTransformPolyDataFilter.Update = FakeTransformPolyDataFilter.update
    FakeTransformPolyDataFilter.GetOutput = FakeTransformPolyDataFilter.get_output

    fake_vtk = SimpleNamespace(
        vtkVector3d=FakeVector3d,
        vtkPoints=FakePoints,
        vtkPolyLine=FakePolyLine,
        vtkCellArray=FakeCellArray,
        vtkPolyData=FakePolyData,
        vtkRegularPolygonSource=FakeRegularPolygonSource,
        vtkSphereSource=FakeSphereSource,
        vtkMatrix4x4=FakeMatrix4x4,
        vtkTransform=FakeTransform,
        vtkTransformPolyDataFilter=FakeTransformPolyDataFilter,
    )
    monkeypatch.setattr(geometry, "vtk", fake_vtk)

    vector = geometry.vtk_vector3d((1.0, 2.0, 3.0))
    assert vector.values == (1.0, 2.0, 3.0)

    poly_data = geometry.polydata_from_points(
        [np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])],
        closed=True,
    )
    assert poly_data.points.items == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert poly_data.lines.cells[0].point_ids.ids == [0, 1, 0]

    circle = geometry.circle_polydata(
        np.array([0.0, 0.0, 0.0]),
        4.0,
        np.array([0.0, 0.0, 1.0]),
    )
    assert circle.radius == 4.0

    sphere = geometry.sphere_polydata(np.array([0.0, 0.0, 0.0]), 2.0)
    assert sphere.radius == 2.0

    recorded = {}
    monkeypatch.setattr(
        geometry,
        "polydata_from_points",
        lambda points, closed=False: recorded.setdefault("polyline", (points, closed)),
    )
    ellipse_polyline = geometry.ellipse_polydata(
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        3.0,
        1.5,
        resolution=12,
    )
    assert ellipse_polyline[1] is True
    assert len(ellipse_polyline[0]) == 24

    class FakeVolume:
        def get_ijk_to_ras_matrix(self, matrix: FakeMatrix4x4) -> None:
            matrix.SetElement(0, 0, 2.0)
            matrix.SetElement(1, 0, 0.0)
            matrix.SetElement(2, 0, 0.0)
            matrix.SetElement(0, 1, 0.0)
            matrix.SetElement(1, 1, -3.0)
            matrix.SetElement(2, 1, 0.0)

    FakeVolume.GetIJKToRASMatrix = FakeVolume.get_ijk_to_ras_matrix

    volume = FakeVolume()
    np.testing.assert_allclose(
        geometry.plane_normal_from_volume(volume),
        np.array([0.0, 0.0, -1.0]),
    )
    axis_i, axis_j = geometry.image_axes_from_volume(volume)
    np.testing.assert_allclose(axis_i, np.array([1.0, 0.0, 0.0]))
    np.testing.assert_allclose(axis_j, np.array([0.0, -1.0, 0.0]))

    ellipsoid = geometry.ellipsoid_surface_polydata(
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        4.0,
        2.0,
    )
    assert isinstance(ellipsoid, FakeTransformPolyDataFilter)


def test_vtk_backed_helpers_are_guarded_without_vtk(monkeypatch) -> None:
    """The module should still import without VTK while guarding VTK-only helpers."""

    monkeypatch.setattr(geometry, "vtk", None)

    with pytest.raises(ImportError):
        geometry.vtk_vector3d((0.0, 0.0, 0.0))
    with pytest.raises(ImportError):
        geometry.polydata_from_points([np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])])


@pytest.mark.parametrize("distal, proximal, expected", [(12., 24., .5), (21., 41., 21./41.), (24., 24., 1.), (0., 24., 0.)])
def test_canal_calcar_ratio_is_distal_over_proximal(distal, proximal, expected):
    assert geometry.canal_calcar_ratio(distal_canal_width=distal, proximal_calcar_width=proximal) == pytest.approx(expected)


@pytest.mark.parametrize("distal, proximal", [(12., 0.), (12., -1.), (12., float('nan')), (float('inf'), 24.)])
def test_canal_calcar_ratio_rejects_degenerate_widths(distal, proximal):
    assert geometry.canal_calcar_ratio(distal_canal_width=distal, proximal_calcar_width=proximal) is None


def test_export_names_avoid_windows_reserved_devices():
    from PelvicXrayMeasurementsGeometry import sanitize_filename

    for name in ("CON", "aux.dcm", "LPT1", "nul.csv", "COM9.dcm"):
        assert sanitize_filename(name) == "SlicerCase_" + name
    assert sanitize_filename("AUXILIARY.dcm") == "AUXILIARY.dcm"
