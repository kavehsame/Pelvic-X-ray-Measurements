"""Pure geometry and VTK construction helpers for Pelvic X-ray Measurements.

The functions here intentionally avoid Slicer widget state. They convert points, vectors, fitted
shapes, and image-plane conventions into reusable operations that the module logic can compose.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import vtk
except ImportError:  # pragma: no cover - exercised in non-Slicer unit-test environments
    vtk = None

from PelvicXrayMeasurementsConstants import EPSILON, SideKey


@dataclass(frozen=True)
class CircleFit:
    """Circle-fit output used internally by measurement calculations."""

    center: Any
    radius: float
    diameter: float
    normal: Any


@dataclass(frozen=True)
class EllipseConicParameters:
    """Ellipse parameters recovered from a fitted conic in 2D plane coordinates."""

    center_2d: Any
    major_radius: float
    minor_radius: float
    major_direction_2d: Any
    minor_direction_2d: Any
    angle_radians: float


@dataclass(frozen=True)
class EllipseFit:
    """Ellipse-fit output used internally by measurement calculations and drawing helpers."""

    center: Any
    major_radius: float
    minor_radius: float
    major_direction: Any
    minor_direction: Any
    major_endpoints: tuple[Any, Any]
    minor_endpoints: tuple[Any, Any]
    angle_radians: float | None = None


def canal_calcar_ratio(*, distal_canal_width: float, proximal_calcar_width: float) -> float | None:
    """Return CCR = B/A, distal canal width divided by proximal calcar width.

    A zero, negative or non-finite proximal width cannot define this ratio.
    Widths must use the same units; the resulting ratio is dimensionless.
    """
    if (not math.isfinite(proximal_calcar_width) or proximal_calcar_width <= EPSILON
            or not math.isfinite(distal_canal_width) or distal_canal_width < 0):
        return None
    return float(distal_canal_width) / float(proximal_calcar_width)


def _require_vtk() -> None:
    """Raise a clear error when a VTK-backed helper is used outside a VTK runtime.

    The pure math and geometry helpers are intentionally unit-testable in a normal Python
    environment. VTK-specific construction helpers still require Slicer's VTK runtime when they are
    actually called.
    """

    if vtk is None:
        raise ImportError("VTK is required for this geometry helper.")


def as_array(values: Any) -> Any:
    """Convert a numeric point or vector into a NumPy array. The geometry helpers standardize on NumPy
    so vector math stays compact and less error-prone.
    """

    return np.asarray(values, dtype=float)


def vector_length(vector: Any) -> Any:
    """Return the Euclidean magnitude of a vector. A dedicated helper keeps geometric intent obvious
    and avoids repeating low-level norm calls throughout the module.
    """

    return float(np.linalg.norm(vector))


def unit_vector(vector: Any) -> Any:
    """Normalize a vector when it is long enough to be meaningful. Degenerate vectors are returned as
    None so downstream calculations can fail safely instead of producing unstable directions.
    """

    norm = vector_length(vector)
    if norm < EPSILON:
        return None
    return as_array(vector) / norm


def vtk_vector3d(point: Any) -> Any:
    """Convert a point into a vtkVector3d for Slicer markup APIs. This isolates VTK-specific object
    creation from the rest of the geometry code.
    """

    _require_vtk()
    return vtk.vtkVector3d(float(point[0]), float(point[1]), float(point[2]))


def clamp(value: Any, minimum: Any=-1.0, maximum: Any=1.0) -> Any:
    """Clamp a scalar into a safe numeric interval. This is especially important before inverse-
    trigonometric calls, where tiny floating-point overshoots can otherwise produce invalid values.
    """

    return max(minimum, min(maximum, float(value)))


def pretty_value(value: Any, digits: Any=2) -> Any:
    """Format a numeric value for user-facing text while tolerating missing values. Centralizing the
    formatting keeps the panel, CSV, and export overlay consistent.
    """

    if value is None:
        return "Not defined"
    return f"{float(value):.{digits}f}"


def sanitize_filename(text: Any) -> Any:
    """Turn a node or case label into a filesystem-safe name. Export paths are sanitized in one place
    so scene names from DICOM or user edits do not create invalid folders.
    """

    clean_text = re.sub(r"[^\w\-\.]+", "_", text or "")
    clean_text = clean_text.strip("._")
    if re.match(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", clean_text, re.IGNORECASE):
        clean_text = "SlicerCase_" + clean_text
    return clean_text or "SlicerCase"


def polydata_from_points(points: Any, closed: Any=False) -> Any:
    """Create polyline vtkPolyData from ordered points. The module uses lightweight polydata builders
    so helper geometry can be displayed without introducing heavier model pipelines.
    """

    _require_vtk()
    if not points or len(points) < 2:
        return vtk.vtkPolyData()

    vtk_points = vtk.vtkPoints()
    for point in points:
        vtk_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))

    poly_line = vtk.vtkPolyLine()
    line_point_count = len(points) + (1 if closed else 0)
    poly_line.GetPointIds().SetNumberOfIds(line_point_count)
    for index in range(len(points)):
        poly_line.GetPointIds().SetId(index, index)
    if closed:
        poly_line.GetPointIds().SetId(line_point_count - 1, 0)

    cells = vtk.vtkCellArray()
    cells.InsertNextCell(poly_line)

    poly_data = vtk.vtkPolyData()
    poly_data.SetPoints(vtk_points)
    poly_data.SetLines(cells)
    return poly_data


def circle_polydata(center: Any, radius: Any, normal: Any, resolution: Any=96) -> Any:
    """Create line-based circle polydata in an arbitrary plane. This is useful for export drawing and
    any workflow that only needs an outline rather than a surface.
    """

    _require_vtk()
    if radius is None or radius < EPSILON or normal is None:
        return vtk.vtkPolyData()

    circle_source = vtk.vtkRegularPolygonSource()
    circle_source.GeneratePolygonOff()
    circle_source.SetNumberOfSides(int(resolution))
    circle_source.SetRadius(float(radius))
    circle_source.SetCenter(float(center[0]), float(center[1]), float(center[2]))
    circle_source.SetNormal(float(normal[0]), float(normal[1]), float(normal[2]))
    circle_source.Update()
    return circle_source.GetOutput()


def sphere_polydata(center: Any, radius: Any, theta_resolution: Any=72, phi_resolution: Any=72) -> Any:
    """Create a sphere surface centered on a fitted circle. A surface is used instead of a line when
    slice intersections need a visible circular contour in 2D views.
    """

    _require_vtk()
    if radius is None or radius < EPSILON:
        return vtk.vtkPolyData()

    sphere_source = vtk.vtkSphereSource()
    sphere_source.SetCenter(float(center[0]), float(center[1]), float(center[2]))
    sphere_source.SetRadius(float(radius))
    sphere_source.SetThetaResolution(int(theta_resolution))
    sphere_source.SetPhiResolution(int(phi_resolution))
    sphere_source.Update()
    return sphere_source.GetOutput()


def ellipse_polydata(
    center: Any,
    major_direction: Any,
    minor_direction: Any,
    major_radius: Any,
    minor_radius: Any,
    resolution: Any=180,
) -> Any:
    """Create a line-based sampled ellipse outline. The outline is useful for export rendering, where a
    crisp drawn contour is preferable to relying on slice intersections.
    """

    _require_vtk()
    if (
        center is None
        or major_direction is None
        or minor_direction is None
        or major_radius is None
        or minor_radius is None
        or major_radius < EPSILON
        or minor_radius < EPSILON
    ):
        return vtk.vtkPolyData()

    points = []
    for angle in np.linspace(0.0, 2.0 * math.pi, int(max(24, resolution)), endpoint=False):
        points.append(
            center
            + major_direction * (float(major_radius) * math.cos(angle))
            + minor_direction * (float(minor_radius) * math.sin(angle))
        )
    return polydata_from_points(points, closed=True)


def ellipsoid_surface_polydata(
    center: Any,
    major_direction: Any,
    minor_direction: Any,
    major_radius: Any,
    minor_radius: Any,
    thickness_radius: Any=None,
    theta_resolution: Any=96,
    phi_resolution: Any=72,
) -> Any:
    """Create a thin ellipsoid surface whose slice intersection appears as an ellipse. The live Slicer
    views render surface intersections more reliably than line-only model geometry, which is why the
    cup ellipse uses this representation.
    """

    _require_vtk()
    if (
        center is None
        or major_direction is None
        or minor_direction is None
        or major_radius is None
        or minor_radius is None
        or major_radius < EPSILON
        or minor_radius < EPSILON
    ):
        return vtk.vtkPolyData()

    normal_direction = unit_vector(np.cross(major_direction, minor_direction))
    if normal_direction is None:
        return vtk.vtkPolyData()

    if thickness_radius is None:
        thickness_radius = max(0.5, 0.08 * float(min(major_radius, minor_radius)))

    sphere_source = vtk.vtkSphereSource()
    sphere_source.SetCenter(0.0, 0.0, 0.0)
    sphere_source.SetRadius(1.0)
    sphere_source.SetThetaResolution(int(theta_resolution))
    sphere_source.SetPhiResolution(int(phi_resolution))
    sphere_source.Update()

    transform_matrix = vtk.vtkMatrix4x4()
    for row in range(3):
        transform_matrix.SetElement(row, 0, float(major_direction[row]) * float(major_radius))
        transform_matrix.SetElement(row, 1, float(minor_direction[row]) * float(minor_radius))
        transform_matrix.SetElement(row, 2, float(normal_direction[row]) * float(thickness_radius))
        transform_matrix.SetElement(row, 3, float(center[row]))
    transform_matrix.SetElement(3, 0, 0.0)
    transform_matrix.SetElement(3, 1, 0.0)
    transform_matrix.SetElement(3, 2, 0.0)
    transform_matrix.SetElement(3, 3, 1.0)

    transform = vtk.vtkTransform()
    transform.SetMatrix(transform_matrix)
    transform_filter = vtk.vtkTransformPolyDataFilter()
    transform_filter.SetInputConnection(sphere_source.GetOutputPort())
    transform_filter.SetTransform(transform)
    transform_filter.Update()
    return transform_filter.GetOutput()


def circle_from_three_points(
    point_a: Any,
    point_b: Any,
    point_c: Any,
) -> CircleFit | None:
    """Fit a circle through three points in 3D space. Three points are the smallest interactive input
    that still defines a circle robustly for head and calibration workflows.
    """

    p1 = as_array(point_a)
    p2 = as_array(point_b)
    p3 = as_array(point_c)

    axis_u = p2 - p1
    axis_v = p3 - p1
    normal = unit_vector(np.cross(axis_u, axis_v))
    if normal is None:
        return None

    local_x = unit_vector(axis_u)
    local_y = unit_vector(np.cross(normal, local_x))
    if local_x is None or local_y is None:
        return None

    x1, y1 = 0.0, 0.0
    x2, y2 = float(np.dot(axis_u, local_x)), float(np.dot(axis_u, local_y))
    x3, y3 = float(np.dot(axis_v, local_x)), float(np.dot(axis_v, local_y))

    denominator = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(denominator) < EPSILON:
        return None

    x1_sq_y1_sq = x1 * x1 + y1 * y1
    x2_sq_y2_sq = x2 * x2 + y2 * y2
    x3_sq_y3_sq = x3 * x3 + y3 * y3

    center_x = (
        x1_sq_y1_sq * (y2 - y3)
        + x2_sq_y2_sq * (y3 - y1)
        + x3_sq_y3_sq * (y1 - y2)
    ) / denominator
    center_y = (
        x1_sq_y1_sq * (x3 - x2)
        + x2_sq_y2_sq * (x1 - x3)
        + x3_sq_y3_sq * (x2 - x1)
    ) / denominator

    center = p1 + local_x * center_x + local_y * center_y
    radius = vector_length(center - p1)
    if radius < EPSILON:
        return None

    return CircleFit(
        center=center,
        radius=radius,
        diameter=2.0 * radius,
        normal=normal,
    )


def ellipse_from_points_in_plane(
    points: Any,
    axis_i: Any,
    axis_j: Any,
) -> EllipseFit | None:
    """Fit a best-fit ellipse to points expressed in the image plane. The fit is done in image axes so
    radiographic measurements remain tied to the displayed x-ray geometry rather than arbitrary
    world axes.
    """

    if points is None or len(points) < 6 or axis_i is None or axis_j is None:
        return None

    origin = np.mean(np.asarray(points, dtype=float), axis=0)
    coordinates = np.array(
        [
            [
                float(np.dot(point - origin, axis_i)),
                float(np.dot(point - origin, axis_j)),
            ]
            for point in points
        ],
        dtype=float,
    )
    x_values = coordinates[:, 0:1]
    y_values = coordinates[:, 1:2]
    design_quadratic = np.hstack([x_values * x_values, x_values * y_values, y_values * y_values])
    design_linear = np.hstack([x_values, y_values, np.ones_like(x_values)])

    try:
        scatter_quadratic = design_quadratic.T @ design_quadratic
        scatter_mixed = design_quadratic.T @ design_linear
        scatter_linear = design_linear.T @ design_linear
        transform = -np.linalg.solve(scatter_linear, scatter_mixed.T)
        reduced_matrix = scatter_quadratic + scatter_mixed @ transform
        constraint_matrix = np.array([[0.0, 0.0, 2.0], [0.0, -1.0, 0.0], [2.0, 0.0, 0.0]], dtype=float)
        _, eigenvectors = np.linalg.eig(np.linalg.solve(constraint_matrix, reduced_matrix))
    except np.linalg.LinAlgError:
        return None

    ellipse_parameters = None
    validity = 4.0 * eigenvectors[0, :] * eigenvectors[2, :] - eigenvectors[1, :] ** 2
    valid_indices = np.nonzero(np.real(validity) > EPSILON)[0]
    for eigen_index in valid_indices:
        conic_quadratic = np.real(eigenvectors[:, eigen_index])
        conic_coefficients = np.concatenate([conic_quadratic, np.real(transform @ conic_quadratic)])
        ellipse_parameters = ellipse_parameters_from_conic(*conic_coefficients)
        if ellipse_parameters is not None:
            break
    if ellipse_parameters is None:
        return None

    center_2d = ellipse_parameters.center_2d
    center = origin + axis_i * center_2d[0] + axis_j * center_2d[1]
    major_direction_2d = ellipse_parameters.major_direction_2d
    minor_direction_2d = ellipse_parameters.minor_direction_2d
    major_direction = unit_vector(axis_i * major_direction_2d[0] + axis_j * major_direction_2d[1])
    minor_direction = unit_vector(axis_i * minor_direction_2d[0] + axis_j * minor_direction_2d[1])
    if major_direction is None or minor_direction is None:
        return None

    return EllipseFit(
        center=center,
        major_radius=ellipse_parameters.major_radius,
        minor_radius=ellipse_parameters.minor_radius,
        major_direction=major_direction,
        minor_direction=minor_direction,
        major_endpoints=(
            center - major_direction * ellipse_parameters.major_radius,
            center + major_direction * ellipse_parameters.major_radius,
        ),
        minor_endpoints=(
            center - minor_direction * ellipse_parameters.minor_radius,
            center + minor_direction * ellipse_parameters.minor_radius,
        ),
        angle_radians=ellipse_parameters.angle_radians,
    )


def ellipse_parameters_from_conic(
    a_coeff: Any,
    b_coeff: Any,
    c_coeff: Any,
    d_coeff: Any,
    e_coeff: Any,
    f_coeff: Any,
) -> EllipseConicParameters | None:
    """Convert conic coefficients into ellipse center, axes, and radii. Separating this algebra keeps
    the fitting code readable and makes numerical failure modes easier to guard.
    """

    quadratic_matrix = np.array(
        [
            [float(a_coeff), 0.5 * float(b_coeff)],
            [0.5 * float(b_coeff), float(c_coeff)],
        ],
        dtype=float,
    )
    if abs(float(np.linalg.det(quadratic_matrix))) < EPSILON:
        return None

    linear_vector = np.array([float(d_coeff), float(e_coeff)], dtype=float)
    try:
        center_2d = -0.5 * np.linalg.solve(quadratic_matrix, linear_vector)
    except np.linalg.LinAlgError:
        return None

    translated_constant = float(
        center_2d.T @ quadratic_matrix @ center_2d + linear_vector.T @ center_2d + float(f_coeff)
    )
    eigenvalues, eigenvectors = np.linalg.eigh(quadratic_matrix)
    if np.min(np.abs(eigenvalues)) < EPSILON:
        return None

    radii_squared = -translated_constant / eigenvalues
    if np.any(radii_squared <= EPSILON):
        return None

    radii = np.sqrt(radii_squared)
    order = np.argsort(radii)[::-1]
    major_radius = float(radii[order[0]])
    minor_radius = float(radii[order[1]])
    major_direction_2d = as_array(eigenvectors[:, order[0]])
    minor_direction_2d = as_array(eigenvectors[:, order[1]])
    angle_radians = float(math.atan2(major_direction_2d[1], major_direction_2d[0]))

    return EllipseConicParameters(
        center_2d=center_2d,
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_direction_2d=major_direction_2d,
        minor_direction_2d=minor_direction_2d,
        angle_radians=angle_radians,
    )


def version_angle(d_major: Any, d_minor: Any, degrees: Any=True) -> Any:
    """Convert major and minor ellipse diameters into an opening or version angle. The helper
    encapsulates the chosen trigonometric convention so post-op reporting stays consistent
    everywhere.
    """

    if d_major is None or d_minor is None:
        return None
    if float(d_minor) > float(d_major):
        raise ValueError("Minor diameter cannot exceed major diameter.")

    theta = math.asin(clamp(float(d_minor) / float(d_major), minimum=-1.0, maximum=1.0))
    if degrees:
        return math.degrees(theta)
    return theta


def ellipse_sample_points(
    center: Any,
    major_direction: Any,
    minor_direction: Any,
    major_radius: Any,
    minor_radius: Any,
    resolution: Any=72,
) -> Any:
    """Sample points along an ellipse defined by center, axes, and radii. Sampling is used when the
    module needs a stable visual approximation instead of an analytic object.
    """

    if (
        center is None
        or major_direction is None
        or minor_direction is None
        or major_radius is None
        or minor_radius is None
        or major_radius < EPSILON
        or minor_radius < EPSILON
    ):
        return []
    return [
        center
        + major_direction * (float(major_radius) * math.cos(angle))
        + minor_direction * (float(minor_radius) * math.sin(angle))
        for angle in np.linspace(0.0, 2.0 * math.pi, int(max(24, resolution)), endpoint=False)
    ]


def ellipse_from_major_minor_diameters(
    major_points: Any,
    minor_points: Any,
    plane_normal: Any,
) -> EllipseFit | None:
    """Reconstruct ellipse parameters from explicit major and minor diameter endpoints. This helper
    exists so ellipse geometry can be re-derived from editable handles when that interaction mode is
    needed.
    """

    if len(major_points) < 2 or len(minor_points) < 2:
        return None

    major_vector = major_points[1] - major_points[0]
    major_direction = unit_vector(major_vector)
    major_radius = 0.5 * vector_length(major_vector)
    if major_direction is None or major_radius < EPSILON:
        return None

    center_major = 0.5 * (major_points[0] + major_points[1])
    center_minor = 0.5 * (minor_points[0] + minor_points[1])
    center = 0.5 * (center_major + center_minor)

    minor_direction = in_plane_perpendicular(major_direction, plane_normal)
    if minor_direction is None:
        return None

    minor_vector = minor_points[1] - minor_points[0]
    if float(np.dot(minor_vector, minor_direction)) < 0.0:
        minor_direction = -minor_direction
    minor_radius = 0.5 * abs(float(np.dot(minor_vector, minor_direction)))
    if minor_radius < EPSILON:
        return None

    return EllipseFit(
        center=center,
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_direction=major_direction,
        minor_direction=minor_direction,
        major_endpoints=(
            center - major_direction * major_radius,
            center + major_direction * major_radius,
        ),
        minor_endpoints=(
            center - minor_direction * minor_radius,
            center + minor_direction * minor_radius,
        ),
    )


def project_points_onto_ellipse(points: Any, ellipse: EllipseFit | None) -> Any:
    """Project arbitrary points back onto a fitted ellipse. Reprojection is useful when derived handles
    or rim points need to stay coherent after an ellipse update.
    """

    if points is None or ellipse is None:
        return []
    center = ellipse.center
    major_direction = ellipse.major_direction
    minor_direction = ellipse.minor_direction
    major_radius = ellipse.major_radius
    minor_radius = ellipse.minor_radius
    if (
        center is None
        or major_direction is None
        or minor_direction is None
        or major_radius is None
        or minor_radius is None
        or major_radius < EPSILON
        or minor_radius < EPSILON
    ):
        return []

    projected_points = []
    for point in points:
        offset = point - center
        x_coord = float(np.dot(offset, major_direction))
        y_coord = float(np.dot(offset, minor_direction))
        parameter = math.atan2(y_coord / float(minor_radius), x_coord / float(major_radius))
        projected_points.append(
            center
            + major_direction * (float(major_radius) * math.cos(parameter))
            + minor_direction * (float(minor_radius) * math.sin(parameter))
        )
    return projected_points


def plane_normal_from_volume(volume_node: Any) -> Any:
    """Estimate the displayed slice-plane normal from the selected image volume. Many measurements are
    intended to live in the x-ray plane, so the module needs a stable in-plane versus out-of-plane
    reference.
    """

    _require_vtk()
    if volume_node is None:
        return None

    ijk_to_ras = vtk.vtkMatrix4x4()
    volume_node.GetIJKToRASMatrix(ijk_to_ras)
    axis_i = np.array([ijk_to_ras.GetElement(row, 0) for row in range(3)], dtype=float)
    axis_j = np.array([ijk_to_ras.GetElement(row, 1) for row in range(3)], dtype=float)
    return unit_vector(np.cross(axis_i, axis_j))


def image_axes_from_volume(volume_node: Any) -> Any:
    """Return the image right and image up directions in RAS space. The module uses image axes, not
    generic world axes, so side-aware radiographic signs follow the displayed x-ray.
    """

    _require_vtk()
    if volume_node is None:
        return None, None

    ijk_to_ras = vtk.vtkMatrix4x4()
    volume_node.GetIJKToRASMatrix(ijk_to_ras)
    axis_i = unit_vector(np.array([ijk_to_ras.GetElement(row, 0) for row in range(3)], dtype=float))
    axis_j = unit_vector(np.array([ijk_to_ras.GetElement(row, 1) for row in range(3)], dtype=float))
    return axis_i, axis_j


def plane_normal_from_points(points: Any) -> Any:
    """Estimate a plane normal from user-defined points. This serves as a fallback when volume-derived
    orientation is unavailable or a local construction plane is more stable.
    """

    if points is None or len(points) < 3:
        return None
    for first_index in range(len(points) - 2):
        for second_index in range(first_index + 1, len(points) - 1):
            for third_index in range(second_index + 1, len(points)):
                normal = unit_vector(
                    np.cross(
                        as_array(points[second_index]) - as_array(points[first_index]),
                        as_array(points[third_index]) - as_array(points[first_index]),
                    )
                )
                if normal is not None:
                    return normal
    return None


def in_plane_perpendicular(direction: Any, plane_normal: Any) -> Any:
    """Compute a perpendicular direction constrained to a measurement plane. Explicit in-plane
    perpendiculars keep guide lines faithful to radiographic constructions instead of drifting in
    3D.
    """

    if direction is None:
        return None
    if plane_normal is not None:
        perpendicular = unit_vector(np.cross(plane_normal, direction))
        if perpendicular is not None:
            return perpendicular
    fallback = np.array([-direction[1], direction[0], 0.0], dtype=float)
    perpendicular = unit_vector(fallback)
    if perpendicular is not None:
        return perpendicular
    fallback = np.array([0.0, -direction[2], direction[1]], dtype=float)
    return unit_vector(fallback)


def best_common_perpendicular(line_directions: Any, plane_normal: Any) -> Any:
    """Find a direction that is as perpendicular as possible to multiple guide lines in one plane.
    Shaft and neck axes use this to turn two short cortical guides into a single long anatomical
    axis.
    """

    normals = []
    for direction in line_directions:
        perpendicular = in_plane_perpendicular(direction, plane_normal)
        if perpendicular is None:
            continue
        if normals and np.dot(perpendicular, normals[0]) < 0.0:
            perpendicular = -perpendicular
        normals.append(perpendicular)

    if not normals:
        return None

    if len(normals) == 1:
        return normals[0]

    combined = unit_vector(np.sum(normals, axis=0))
    return combined if combined is not None else normals[0]


def angle_deviation_from_perpendicular(direction_a: Any, direction_b: Any) -> Any:
    """Measure how far two directions depart from perfect orthogonality. This is a small diagnostic
    helper that keeps axis-fitting math easier to reason about.
    """

    if direction_a is None or direction_b is None:
        return None
    angle = math.degrees(math.acos(clamp(abs(float(np.dot(direction_a, direction_b))))))
    return abs(90.0 - angle)


def acute_angle_between_directions(direction_a: Any, direction_b: Any) -> Any:
    """Return the smaller angle between two directions. Clinical angle reporting typically uses the
    acute solution unless a signed convention is explicitly required.
    """

    if direction_a is None or direction_b is None:
        return None
    return math.degrees(math.acos(clamp(abs(float(np.dot(direction_a, direction_b))))))


def unsigned_angle_between_directions(direction_a: Any, direction_b: Any) -> Any:
    """Return the unsigned geometric angle between two directions across the full 0..180 range. This
    is useful for free-angle tools that should not carry a sign but still must not fold back after
    90 degrees.
    """

    if direction_a is None or direction_b is None:
        return None
    return math.degrees(math.acos(clamp(float(np.dot(direction_a, direction_b)))))


def direction_aligned_to_hint(direction: Any, hint_direction: Any) -> Any:
    """Orient a direction so it points toward a preferred hint direction.

    This keeps line-like axes sign-agnostic internally while still allowing downstream measurements
    to choose a clinically meaningful ray on each axis.
    """

    direction_unit = unit_vector(direction)
    hint_unit = unit_vector(hint_direction)
    if direction_unit is None or hint_unit is None:
        return None
    if float(np.dot(direction_unit, hint_unit)) < 0.0:
        return -direction_unit
    return direction_unit


def oriented_angle_between_directions(
    direction_a: Any,
    hint_direction_a: Any,
    direction_b: Any,
    hint_direction_b: Any,
) -> Any:
    """Return the angle between two directions after orienting each toward a preferred ray."""

    oriented_a = direction_aligned_to_hint(direction_a, hint_direction_a)
    oriented_b = direction_aligned_to_hint(direction_b, hint_direction_b)
    if oriented_a is None or oriented_b is None:
        return None
    return unsigned_angle_between_directions(oriented_a, oriented_b)


def obtuse_angle_between_directions(direction_a: Any, direction_b: Any) -> Any:
    """Return the larger supplementary angle between two directions. Some constructions need the
    exterior relationship, so the companion helper keeps intent explicit.
    """

    acute_angle = acute_angle_between_directions(direction_a, direction_b)
    if acute_angle is None:
        return None
    return 180.0 - acute_angle


def rightward_reference_direction(reference_direction: Any) -> Any:
    """Choose a consistent rightward direction from a reference line. Normalizing the reference
    orientation prevents sign changes when users draw the same line in opposite point order.
    """

    if reference_direction is None:
        return None
    direction = unit_vector(reference_direction)
    if direction is None:
        return None
    if float(np.dot(direction, np.array([1.0, 0.0, 0.0], dtype=float))) < 0.0:
        direction = -direction
    return direction


def normalized_side_key(side_key: Any) -> SideKey:
    """Normalize a side identifier into the stable bilateral enum or raise on unknown values."""

    normalized = str(side_key).strip().lower()
    if normalized == SideKey.LEFT.value:
        return SideKey.LEFT
    if normalized == SideKey.RIGHT.value:
        return SideKey.RIGHT
    raise ValueError(f"Unknown side key: {side_key}")


def image_right_direction(volume_node: Any) -> Any:
    """Return the displayed image-right direction in RAS coordinates. This matters because radiographs
    follow image-viewing conventions rather than anatomical left-right alone.
    """

    if volume_node is None:
        return None
    axis_i, _axis_j = image_axes_from_volume(volume_node)
    return axis_i


def image_up_direction(volume_node: Any) -> Any:
    """Return the displayed image-up direction in RAS coordinates. Using image up keeps above-versus-
    below angle signs tied to what the operator sees.
    """

    if volume_node is None:
        return None
    _axis_i, axis_j = image_axes_from_volume(volume_node)
    return -axis_j if axis_j is not None else None


def lateral_reference_direction(reference_direction: Any, side_key: Any, volume_node: Any=None) -> Any:
    """Return the lateral direction for the requested side relative to the reference line. The logic
    deliberately respects radiograph viewing conventions so side-aware signs match the image
    presentation.
    """

    direction = unit_vector(reference_direction)
    if direction is None:
        return None
    normalized_side = normalized_side_key(side_key)

    image_right = image_right_direction(volume_node)
    if image_right is not None:
        desired_lateral = image_right if normalized_side == SideKey.LEFT else -image_right
    else:
        rightward = rightward_reference_direction(reference_direction)
        if rightward is None:
            return None
        desired_lateral = rightward if normalized_side == SideKey.LEFT else -rightward

    if float(np.dot(direction, desired_lateral)) < 0.0:
        direction = -direction
    return direction


def superior_reference_direction(reference_direction: Any, plane_normal: Any, volume_node: Any=None) -> Any:
    """Return the superior direction perpendicular to the reference line inside the image plane.
    Several measurements depend on above-versus-below logic, so superior is derived once in a
    consistent way.
    """

    perpendicular = in_plane_perpendicular(reference_direction, plane_normal)
    if perpendicular is None:
        return None

    image_up = image_up_direction(volume_node)
    if image_up is not None:
        if float(np.dot(perpendicular, image_up)) < 0.0:
            perpendicular = -perpendicular
        return perpendicular

    if float(np.dot(perpendicular, np.array([0.0, 0.0, 1.0], dtype=float))) < 0.0:
        perpendicular = -perpendicular
    return perpendicular


def signed_angle_from_base(direction: Any, base_direction: Any, sign_direction: Any) -> Any:
    """Return a signed angle from a base direction using a separate sign direction. The helper uses
    `atan2` over the supplied in-plane basis so signed clinical angles can sweep continuously to
    +/-180 degrees instead of folding back after +/-90. When the signed component is numerically
    tiny, the helper snaps to exactly 0 or 180 degrees to suppress floating-point noise at the
    branch cut.
    """

    direction_unit = unit_vector(direction)
    base_unit = unit_vector(base_direction)
    sign_unit = unit_vector(sign_direction)
    if direction_unit is None or base_unit is None or sign_unit is None:
        return None

    base_component = float(np.dot(direction_unit, base_unit))
    sign_component = float(np.dot(direction_unit, sign_unit))
    if abs(sign_component) < EPSILON:
        return 180.0 if base_component < 0.0 else 0.0

    angle = math.degrees(math.atan2(sign_component, base_component))
    return 0.0 if abs(angle) < EPSILON else angle


def closest_point_on_line(point: Any, line_origin: Any, line_direction: Any) -> Any:
    """Project a point onto a line. Projection is used repeatedly for offsets and LLD because
    radiographic distances are defined relative to reference constructions, not raw point spacing.
    """

    if line_direction is None:
        return None
    return line_origin + line_direction * float(np.dot(point - line_origin, line_direction))


def signed_distance_to_line_in_plane(point: Any, line_origin: Any, line_direction: Any, plane_normal: Any) -> Any:
    """Measure signed in-plane distance from a point to a line. The sign is preserved so side-aware or
    superior-versus-inferior relationships can be reported instead of only absolute gaps.
    """

    perpendicular = in_plane_perpendicular(line_direction, plane_normal)
    if perpendicular is None:
        return None
    return float(np.dot(point - line_origin, perpendicular))
