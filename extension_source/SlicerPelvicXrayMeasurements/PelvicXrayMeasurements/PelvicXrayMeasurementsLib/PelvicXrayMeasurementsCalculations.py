"""Derived measurement calculations for Pelvic X-ray Measurements.

This mixin turns editable MRML inputs into calibrated measurements and derived visual geometry. It
keeps formulas separate from UI actions and export serialization so measurement behavior has one
place to live.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import vtk

from PelvicXrayMeasurementsConstants import (
    DEFAULT_CONSTRUCTION_LINE_LENGTH_SU,
    EPSILON,
    FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
    FEMORAL_SHAFT_CONTOUR_CLASS_ATTRIBUTE,
    FEMORAL_SHAFT_CONTOUR_CLASS_LABELS,
    FEMUR_SHAFT_MORPHOLOGY_FREE_POINT_INDICES,
    FEMUR_SHAFT_MORPHOLOGY_GUIDE_A_INDICES,
    FEMUR_SHAFT_MORPHOLOGY_GUIDE_B_INDICES,
    FEMUR_SHAFT_MORPHOLOGY_LAYOUT,
    FEMUR_SHAFT_MORPHOLOGY_MIDLINE_HALF_WIDTH_MM,
    OTHER_ANGLE_LOCK_ATTRIBUTE,
    OTHER_LINE_LOCK_ATTRIBUTE,
    SIDE_KEYS,
    SIDE_LABELS,
    MeasurementKey,
    OtherAngleLockMode,
)
from PelvicXrayMeasurementsGeometry import (
    acute_angle_between_directions,
    angle_deviation_from_perpendicular,
    as_array,
    best_common_perpendicular,
    canal_calcar_ratio,
    circle_from_three_points,
    closest_point_on_line,
    ellipse_from_points_in_plane,
    ellipsoid_surface_polydata,
    image_axes_from_volume,
    image_right_direction,
    image_up_direction,
    in_plane_perpendicular,
    lateral_reference_direction,
    obtuse_angle_between_directions,
    oriented_angle_between_directions,
    plane_normal_from_points,
    plane_normal_from_volume,
    polydata_from_points,
    signed_angle_from_base,
    signed_distance_to_line_in_plane,
    sphere_polydata,
    superior_reference_direction,
    unit_vector,
    unsigned_angle_between_directions,
    vector_length,
    version_angle,
    vtk_vector3d,
)
from PelvicXrayMeasurementsNodeSpecs import (
    other_angle_free_arm_role,
    other_angle_points_role,
    other_angle_reference_arm_role,
    other_line_role,
    other_point_role,
)


class MeasurementCalculationMixin:
    """Provide derived-measurement calculation behavior for the main logic class."""

    def update_all_derived_measurements(self, image_node: Any=None) -> Any:
        """Recompute every derived measurement from the current MRML scene. A full recomputation keeps
        the module deterministic and easier to debug, even though individual tools are edited
        incrementally.
        """

        if self._updating:
            return self.latest_results

        self.ensure_nodes()
        self._updating = True
        try:
            results = self._empty_results()

            self._apply_labels(self.get_node("calibrationPoints"), "calibrationPoints")
            self._apply_labels(self.get_node("referenceLine"), "referenceLine")
            self._apply_labels(self.get_node("lldPoints"), "lldPoints")
            self._apply_labels(self.get_node("lldLeftParallel"), "lldLeftParallel")
            self._apply_labels(self.get_node("lldRightParallel"), "lldRightParallel")
            self._apply_labels(self.get_node("lldHeightDifference"), "lldHeightDifference")
            for index in self.other_line_indices():
                role = other_line_role(index)
                self._apply_labels(self.get_node(role), role)
            for index in self.other_point_indices():
                role = other_point_role(index)
                self._apply_labels(self.get_node(role), role)
            for index in self.other_angle_indices():
                points_role = other_angle_points_role(index)
                reference_role = other_angle_reference_arm_role(index)
                self._apply_labels(self.get_node(points_role), points_role)
                self._apply_labels(self.get_node(reference_role), reference_role)
            for side_key in SIDE_KEYS:
                for base_role in [
                    "extrusionIndexMedialLine",
                    "extrusionIndexMiddleLine",
                    "extrusionIndexLateralLine",
                    "shaftMorphologyLTPoints",
                    "shaftMorphologyMidline",
                    "shaftMorphologyPoints",
                    "shaftMorphologyGuideLineA",
                    "shaftMorphologyGuideLineB",
                    "tonnisAngleLine",
                    "tonnisAngleReferenceArm",
                    "femurHeadPoints",
                    "femurHeadCenter",
                    "implantHeadPoints",
                    "implantHeadCenter",
                    "sharpAngleLine",
                    "sharpAngleReferenceArm",
                    "shaftGuideProximal",
                    "shaftGuideDistal",
                    "shaftAxis",
                    "neckGuideProximal",
                    "neckGuideDistal",
                    "neckAxis",
                    "implantNeckGuideProximal",
                    "implantNeckGuideDistal",
                    "implantNeckAxis",
                    "acetabularOffsetLineA",
                    "acetabularOffsetLineB",
                    "femoralOffsetLine",
                    "postOpAcetabularOffsetLineA",
                    "postOpAcetabularOffsetLineB",
                    "postOpFemoralOffsetLine",
                    "implantAlignmentGuideProximal",
                    "implantAlignmentGuideDistal",
                    "implantAlignmentLine",
                    "lceAnglePoint",
                    "lceAngleVisual",
                    "lceAngleRadialArm",
                    "acetabularInclinationLine",
                    "cupOpeningEllipsePoints",
                    "cupOpeningEllipseMajorDiameter",
                    "cupOpeningEllipseMinorDiameter",
                    "iliopectinealLine",
                    "ilioischialLine",
                    "shentonLine",
                    "acetabularRoofSourcil",
                    "anteriorAcetabularWall",
                    "posteriorAcetabularWall",
                    "lineaTerminalis",
                    *FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
                ]:
                    role = self.side_role(base_role, side_key)
                    self._apply_labels(self.get_node(role), role)

            plane_normal = plane_normal_from_volume(image_node)

            self._update_calibration(results)
            self._update_reference_line(results)
            for side_key in SIDE_KEYS:
                self._update_side_femoral_head_extrusion_index(results, side_key, image_node, plane_normal)
                self._update_side_tonnis_angle(results, side_key, image_node, plane_normal)
                self._update_side_sharp_angle(results, side_key, image_node, plane_normal)
                self._update_side_femur_head(results, side_key)
                self._update_side_implant_head(results, side_key)
                self._update_side_lce_angle(results, side_key, image_node, plane_normal)
                self._update_side_femoral_shaft_axis(results, side_key, image_node, plane_normal)
                self._update_side_femoral_shaft_contours(results, side_key, image_node, plane_normal)
                self._update_side_femur_shaft_morphology(results, side_key, image_node, plane_normal)
                self._update_side_femoral_neck_axis(results, side_key, image_node, plane_normal)
                self._update_side_implant_neck_axis(results, side_key, image_node, plane_normal)
                self._update_side_ccd_angle(results, side_key, image_node)
                self._update_side_implant_femoral_ccd(results, side_key, image_node)
                self._update_side_acetabular_offset(results, side_key, plane_normal)
                self._update_side_femoral_offset(results, side_key, plane_normal)
                self._update_side_preop_global_offset(results, side_key)
                self._update_side_acetabular_inclination_angle(results, side_key)
                self._update_side_cup_opening_ellipse_fit(results, side_key, image_node)
                self._update_side_postop_acetabular_offset(results, side_key, plane_normal)
                self._update_side_postop_femoral_offset(results, side_key, plane_normal)
                self._update_side_postop_global_offset(results, side_key)
                self._update_side_implant_alignment(results, side_key, image_node, plane_normal)
            self._update_lld(results, image_node, plane_normal)
            self._update_other_points(results)
            self._update_other_lines(results, image_node, plane_normal)
            self._update_other_angles(results, image_node, plane_normal)
            self.apply_measurement_visibility_preferences()

            self.latest_results = results
        finally:
            self._updating = False

        return self.latest_results

    def _update_calibration(self, results: Any) -> None:
        """Fit the calibration ball from three points and compute the scene-to-millimetre scale factor.
        Calibration is treated as the single source of truth for corrected lengths so every
        downstream linear result stays consistent.
        """

        points_node = self.get_node("calibrationPoints")
        circle_node = self.get_node("calibrationCircle")
        points = self._defined_points(points_node)[:3]
        results["calibration"]["ballPresent"] = self.calibration_ball_present
        results["calibration"]["knownDiameterMm"] = self.calibration_ball_diameter_mm

        if not self.calibration_ball_present:
            self._clear_model(circle_node)
            return

        if len(points) < 3:
            self._clear_model(circle_node)
            return

        circle = circle_from_three_points(points[0], points[1], points[2])
        if circle is None:
            self._clear_model(circle_node)
            return

        self._update_model_polydata(
            circle_node,
            sphere_polydata(circle.center, circle.radius),
        )

        results["calibration"]["defined"] = True
        results["calibration"]["rawDiameter"] = circle.diameter
        results["calibration"]["scaleFactor"] = self.calibration_ball_diameter_mm / circle.diameter
        results["calibration"]["center"] = circle.center
        results["calibration"]["normal"] = circle.normal

    def _update_reference_line(self, results: Any) -> None:
        """Update the reference line result from its two endpoints. Many other tools are defined
        relative to this line, so its direction and corrected length are cached early in the update
        pass.
        """

        reference_node = self.get_node("referenceLine")
        points = self._defined_points(reference_node)
        if len(points) < 2:
            return

        direction = unit_vector(points[1] - points[0])
        raw_length = vector_length(points[1] - points[0])

        results["referenceLine"]["defined"] = True
        results["referenceLine"]["points"] = points
        results["referenceLine"]["direction"] = direction
        results["referenceLine"]["rawLength"] = raw_length
        results["referenceLine"]["correctedLength"] = self._correct_value(results, raw_length)

    def _update_side_femoral_head_extrusion_index(
        self,
        results: Any,
        side_key: Any,
        image_node: Any,
        plane_normal: Any,
    ) -> None:
        """Compute the femoral head extrusion index for one side from three perpendicular guide lines.
        The ratio is evaluated along the lateral axis so it reflects coverage geometry rather than
        raw Euclidean spacing.
        """

        side_results = results["sides"][side_key]
        reference = results["referenceLine"]
        medial_node = self.get_node(self.side_role("extrusionIndexMedialLine", side_key))
        middle_node = self.get_node(self.side_role("extrusionIndexMiddleLine", side_key))
        lateral_node = self.get_node(self.side_role("extrusionIndexLateralLine", side_key))

        if not reference["defined"]:
            return

        offset_direction = superior_reference_direction(reference["direction"], plane_normal, image_node)
        lateral_direction = lateral_reference_direction(reference["direction"], side_key, image_node)
        if lateral_direction is None:
            return
        if offset_direction is None:
            return

        for line_node in [medial_node, middle_node, lateral_node]:
            self._constrain_line_direction(line_node, offset_direction)

        medial_points = self._defined_points(medial_node)
        middle_points = self._defined_points(middle_node)
        lateral_points = self._defined_points(lateral_node)
        if len(medial_points) < 2 or len(middle_points) < 2 or len(lateral_points) < 2:
            return

        origin = reference["points"][0]
        medial_position = float(np.dot(medial_points[0] - origin, lateral_direction))
        middle_position = float(np.dot(middle_points[0] - origin, lateral_direction))
        lateral_position = float(np.dot(lateral_points[0] - origin, lateral_direction))
        femoral_head_width = abs(lateral_position - medial_position)
        uncovered_width = lateral_position - middle_position
        if femoral_head_width < EPSILON:
            return

        side_results["femoralHeadExtrusionIndex"]["defined"] = True
        side_results["femoralHeadExtrusionIndex"]["rawValue"] = 100.0 * uncovered_width / femoral_head_width

    def _update_side_tonnis_angle(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Compute the signed Acetabular Index (Tönnis) for one side and maintain its visible reference arm. The
        helper arm is drawn parallel to the reference line so the numeric value and displayed
        construction stay synchronized.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        reference = results["referenceLine"]
        line_node = self.get_node(self.side_role("tonnisAngleLine", side_key))
        arm_node = self.get_node(self.side_role("tonnisAngleReferenceArm", side_key))
        points = self._defined_points(line_node)
        if not reference["defined"] or len(points) < 2:
            self._clear_markup(arm_node)
            return

        line_vector = points[1] - points[0]
        line_direction = unit_vector(line_vector)
        if line_direction is None:
            self._clear_markup(arm_node)
            return

        lateral_direction = lateral_reference_direction(reference["direction"], side_key, image_node)
        superior_direction = superior_reference_direction(reference["direction"], plane_normal, image_node)
        if lateral_direction is None or superior_direction is None:
            self._clear_markup(arm_node)
            return

        arm_length = vector_length(line_vector)
        reference_endpoint = points[0] + lateral_direction * arm_length
        self._set_line_points(
            arm_node,
            points[0],
            reference_endpoint,
            f"AcetabularIndexTonnis_{side_label}_Reference_Start",
            f"AcetabularIndexTonnis_{side_label}_Reference_End",
        )
        arm_node.SetDisplayVisibility(True)

        side_results["tonnisAngle"]["defined"] = True
        side_results["tonnisAngle"]["rawValue"] = signed_angle_from_base(
            line_direction, lateral_direction, superior_direction
        )

    def _update_side_sharp_angle(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Compute the signed Sharp angle for one side and maintain its visible reference arm. The
        module treats the reference arm as an explicit construction so users can understand the
        measured angle at a glance.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        reference = results["referenceLine"]
        line_node = self.get_node(self.side_role("sharpAngleLine", side_key))
        arm_node = self.get_node(self.side_role("sharpAngleReferenceArm", side_key))
        points = self._defined_points(line_node)
        if not reference["defined"] or len(points) < 2:
            self._clear_markup(arm_node)
            return

        line_vector = points[1] - points[0]
        line_direction = unit_vector(line_vector)
        if line_direction is None:
            self._clear_markup(arm_node)
            return

        lateral_direction = lateral_reference_direction(reference["direction"], side_key, image_node)
        superior_direction = superior_reference_direction(reference["direction"], plane_normal, image_node)
        if lateral_direction is None or superior_direction is None:
            self._clear_markup(arm_node)
            return

        arm_length = vector_length(line_vector)
        reference_endpoint = points[0] + lateral_direction * arm_length
        self._set_line_points(
            arm_node,
            points[0],
            reference_endpoint,
            f"SharpAngle_{side_label}_Reference_Start",
            f"SharpAngle_{side_label}_Reference_End",
        )
        arm_node.SetDisplayVisibility(True)

        side_results["sharpAngle"]["defined"] = True
        side_results["sharpAngle"]["rawValue"] = signed_angle_from_base(
            line_direction, lateral_direction, superior_direction
        )

    def _update_side_lce_angle(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Compute the signed LCE angle from the femoral head center, a user point, and a
        perpendicular-to-reference arm. The angle is derived from the fitted head center because
        that center is the clinically meaningful fulcrum.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        reference = results["referenceLine"]
        point_node = self.get_node(self.side_role("lceAnglePoint", side_key))
        reference_arm_node = self.get_node(self.side_role("lceAngleVisual", side_key))
        radial_arm_node = self.get_node(self.side_role("lceAngleRadialArm", side_key))
        points = self._defined_points(point_node)[:1]
        center = side_results["femurHead"]["center"]
        if not reference["defined"] or center is None or len(points) < 1:
            self._clear_markup(reference_arm_node)
            self._clear_markup(radial_arm_node)
            return

        target_point = points[0]
        radial_vector = target_point - center
        radial_direction = unit_vector(radial_vector)
        if radial_direction is None:
            self._clear_markup(reference_arm_node)
            self._clear_markup(radial_arm_node)
            return

        superior_direction = superior_reference_direction(reference["direction"], plane_normal, image_node)
        lateral_direction = lateral_reference_direction(reference["direction"], side_key, image_node)
        if superior_direction is None:
            fallback_normal = plane_normal_from_points(reference["points"] + [center, target_point])
            superior_direction = superior_reference_direction(reference["direction"], fallback_normal, image_node)
        if superior_direction is None or lateral_direction is None:
            self._clear_markup(reference_arm_node)
            self._clear_markup(radial_arm_node)
            return

        arm_length = vector_length(radial_vector)
        perpendicular_endpoint = center + superior_direction * arm_length
        self._set_line_points(
            reference_arm_node,
            center,
            perpendicular_endpoint,
            f"LCEAngle_{side_label}_Center",
            f"LCEAngle_{side_label}_Reference_End",
        )
        reference_arm_node.SetDisplayVisibility(True)
        self._set_line_points(
            radial_arm_node,
            center,
            target_point,
            f"LCEAngle_{side_label}_Center",
            f"LCEAngle_{side_label}_Point",
        )
        radial_arm_node.SetDisplayVisibility(True)

        side_results["lceAngle"]["defined"] = True
        side_results["lceAngle"]["rawValue"] = signed_angle_from_base(
            radial_direction, superior_direction, lateral_direction
        )

    def _update_side_acetabular_inclination_angle(self, results: Any, side_key: Any) -> None:
        """Compute the free-hand acetabular inclination angle from its drawn line and the reference
        line. This tool intentionally stays simple and direct because it is meant to reflect a free-
        hand post-op construction.
        """

        side_results = results["sides"][side_key]
        reference = results["referenceLine"]
        inclination_node = self.get_node(self.side_role("acetabularInclinationLine", side_key))
        points = self._defined_points(inclination_node)
        if not reference["defined"] or len(points) < 2:
            return

        direction = unit_vector(points[1] - points[0])
        angle = acute_angle_between_directions(reference["direction"], direction)
        if angle is None:
            return

        side_results["acetabularInclinationAngle"]["defined"] = True
        side_results["acetabularInclinationAngle"]["rawValue"] = angle

    def _update_side_cup_opening_ellipse_fit(self, results: Any, side_key: Any, image_node: Any) -> None:
        """Fit the cup-opening ellipse from six rim points, update its live model, and derive
        inclination and version-related values. The live model is a thin ellipsoid surface because
        slice intersections display more reliably in Slicer than line-only polydata.
        """

        side_results = results["sides"][side_key]
        reference = results["referenceLine"]
        points_node = self.get_node(self.side_role("cupOpeningEllipsePoints", side_key))
        ellipse_node = self.get_node(self.side_role("cupOpeningEllipse", side_key))
        major_node = self.get_node(self.side_role("cupOpeningEllipseMajorDiameter", side_key))
        minor_node = self.get_node(self.side_role("cupOpeningEllipseMinorDiameter", side_key))
        points = self._defined_points(points_node)[:6]
        axis_i, axis_j = image_axes_from_volume(image_node)
        self._clear_markup(major_node)
        self._clear_markup(minor_node)
        if not reference["defined"] or axis_i is None or axis_j is None:
            self._clear_model(ellipse_node)
            return

        ellipse = ellipse_from_points_in_plane(points, axis_i, axis_j) if len(points) >= 6 else None
        if ellipse is None:
            self._clear_model(ellipse_node)
            return

        self._update_model_polydata(
            ellipse_node,
            ellipsoid_surface_polydata(
                ellipse.center,
                ellipse.major_direction,
                ellipse.minor_direction,
                ellipse.major_radius,
                ellipse.minor_radius,
            ),
            visible=True,
        )

        inclination_angle = acute_angle_between_directions(
            reference["direction"], ellipse.major_direction
        )
        if inclination_angle is None:
            self._clear_model(ellipse_node)
            return

        anteversion_retroversion_angle = None
        try:
            anteversion_retroversion_angle = version_angle(
                2.0 * float(ellipse.major_radius),
                2.0 * float(ellipse.minor_radius),
                degrees=True,
            )
        except ValueError:
            anteversion_retroversion_angle = None

        self._store_cup_opening_ellipse_results(
            side_results,
            ellipse,
            inclination_angle,
            anteversion_retroversion_angle,
        )

    def _store_cup_opening_ellipse_results(
        self,
        side_results: Any,
        ellipse: Any,
        inclination_angle: float,
        anteversion_retroversion_angle: Any,
    ) -> None:
        """Persist fitted cup-opening ellipse geometry and derived angles into the results map."""

        side_results["cupOpeningEllipseFit"]["defined"] = True
        side_results["cupOpeningEllipseFit"]["center"] = ellipse.center
        side_results["cupOpeningEllipseFit"]["majorRadius"] = ellipse.major_radius
        side_results["cupOpeningEllipseFit"]["minorRadius"] = ellipse.minor_radius
        side_results["cupOpeningEllipseFit"]["majorDirection"] = ellipse.major_direction
        side_results["cupOpeningEllipseFit"]["minorDirection"] = ellipse.minor_direction
        side_results["cupOpeningEllipseFit"]["majorEndpoints"] = list(ellipse.major_endpoints)
        side_results["cupOpeningEllipseFit"]["minorEndpoints"] = list(ellipse.minor_endpoints)
        side_results["cupOpeningEllipseInclinationAngle"]["defined"] = True
        side_results["cupOpeningEllipseInclinationAngle"]["rawValue"] = inclination_angle
        if anteversion_retroversion_angle is not None:
            side_results["cupOpeningAnteversionRetroversionAngle"]["defined"] = True
            side_results["cupOpeningAnteversionRetroversionAngle"]["rawValue"] = anteversion_retroversion_angle

    def _update_side_femur_head(self, results: Any, side_key: Any) -> None:
        """Fit the native femoral head circle from three points and update its center and displayed
        circle. Using a three-point fit keeps the interaction fast while still giving a reproducible
        center and diameter.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        points_node = self.get_node(self.side_role("femurHeadPoints", side_key))
        center_node = self.get_node(self.side_role("femurHeadCenter", side_key))
        circle_node = self.get_node(self.side_role("femurHeadCircle", side_key))
        points = self._defined_points(points_node)[:3]

        if len(points) < 3:
            center_node.RemoveAllControlPoints()
            center_node.SetDisplayVisibility(False)
            self._clear_model(circle_node)
            return

        circle = circle_from_three_points(points[0], points[1], points[2])
        if circle is None:
            center_node.RemoveAllControlPoints()
            center_node.SetDisplayVisibility(False)
            self._clear_model(circle_node)
            return

        self._set_single_point(center_node, circle.center, f"FemurHead_{side_label}_Center")
        center_node.SetDisplayVisibility(True)
        self._update_model_polydata(
            circle_node,
            sphere_polydata(circle.center, circle.radius),
            visible=True,
        )

        side_results["femurHead"]["defined"] = True
        side_results["femurHead"]["rawValue"] = circle.diameter
        side_results["femurHead"]["correctedValue"] = self._correct_value(results, circle.diameter)
        side_results["femurHead"]["center"] = circle.center
        side_results["femurHead"]["normal"] = circle.normal

    def _update_side_implant_head(self, results: Any, side_key: Any) -> None:
        """Fit the implant head circle from three points and update its center and displayed circle.
        The workflow mirrors the native head fit so pre-op and post-op circle tools feel consistent
        to the user.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        points_node = self.get_node(self.side_role("implantHeadPoints", side_key))
        center_node = self.get_node(self.side_role("implantHeadCenter", side_key))
        circle_node = self.get_node(self.side_role("implantHeadCircle", side_key))
        points = self._defined_points(points_node)[:3]

        if len(points) < 3:
            center_node.RemoveAllControlPoints()
            center_node.SetDisplayVisibility(False)
            self._clear_model(circle_node)
            return

        circle = circle_from_three_points(points[0], points[1], points[2])
        if circle is None:
            center_node.RemoveAllControlPoints()
            center_node.SetDisplayVisibility(False)
            self._clear_model(circle_node)
            return

        self._set_single_point(center_node, circle.center, f"ImplantHead_{side_label}_Center")
        center_node.SetDisplayVisibility(True)
        self._update_model_polydata(
            circle_node,
            sphere_polydata(circle.center, circle.radius),
            visible=True,
        )

        side_results["implantHead"]["defined"] = True
        side_results["implantHead"]["rawValue"] = circle.diameter
        side_results["implantHead"]["correctedValue"] = self._correct_value(results, circle.diameter)
        side_results["implantHead"]["center"] = circle.center
        side_results["implantHead"]["normal"] = circle.normal

    def _update_side_axis_from_guides(
        self,
        results: Any,
        side_key: Any,
        image_node: Any,
        plane_normal: Any,
        measurement_key: Any,
        guide_a_role: Any,
        guide_b_role: Any,
        axis_role: Any,
        result_key: Any,
        center_result_key: Any,
        label_prefix: Any,
        span_scale: Any,
    ) -> None:
        """Derive one side-specific axis from guide lines and cache both its displayed line and
        geometric properties. The helper keeps shaft-, neck-, implant-neck-, and stem-axis logic
        aligned while still allowing neck-axis-specific options such as single-guide derivation or a
        forced fitted-center origin.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        guide_a_node = self.get_node(self.side_role(guide_a_role, side_key))
        guide_b_node = self.get_node(self.side_role(guide_b_role, side_key))
        axis_node = self.get_node(self.side_role(axis_role, side_key))
        axis_result = side_results[result_key]
        use_single_guide = self.axis_use_single_guide_enabled(measurement_key, side_key)
        lock_to_center = self.axis_lock_to_center_enabled(measurement_key, side_key)

        guide_a_points = self._defined_points(guide_a_node)
        guide_b_points = self._defined_points(guide_b_node)
        if len(guide_a_points) < 2 or (not use_single_guide and len(guide_b_points) < 2):
            self._clear_markup(axis_node)
            return

        direction_a = unit_vector(guide_a_points[1] - guide_a_points[0])
        direction_b = unit_vector(guide_b_points[1] - guide_b_points[0]) if len(guide_b_points) >= 2 else None

        axis_plane_normal = self._axis_plane_normal_from_guides(
            results,
            plane_normal,
            use_single_guide,
            guide_a_points,
            guide_b_points,
        )

        guide_directions = [direction_a]
        if not use_single_guide:
            guide_directions.append(direction_b)
        axis_direction = best_common_perpendicular(guide_directions, axis_plane_normal)
        if axis_direction is None:
            self._clear_markup(axis_node)
            return

        axis_origin = self._axis_origin_from_guides(
            side_results,
            center_result_key,
            lock_to_center,
            use_single_guide,
            guide_a_points,
            guide_b_points,
        )
        if axis_origin is None:
            self._clear_markup(axis_node)
            return

        span_points = list(guide_a_points)
        if not use_single_guide:
            span_points.extend(guide_b_points)
        span = self._display_span(image_node, span_points) * float(span_scale)
        endpoint_a = axis_origin - axis_direction * span
        endpoint_b = axis_origin + axis_direction * span
        self._set_line_points(
            axis_node,
            endpoint_a,
            endpoint_b,
            f"{label_prefix}_{side_label}_Start",
            f"{label_prefix}_{side_label}_End",
        )
        axis_node.SetDisplayVisibility(True)

        axis_result["defined"] = True
        axis_result["origin"] = axis_origin
        axis_result["direction"] = axis_direction
        axis_result["endpoints"] = [endpoint_a, endpoint_b]
        axis_result["deviationGuideA"] = angle_deviation_from_perpendicular(axis_direction, direction_a)
        axis_result["deviationGuideB"] = (
            angle_deviation_from_perpendicular(axis_direction, direction_b)
            if not use_single_guide and direction_b is not None
            else None
        )

    def _axis_plane_normal_from_guides(
        self,
        results: Any,
        plane_normal: Any,
        use_single_guide: Any,
        guide_a_points: Any,
        guide_b_points: Any,
    ) -> Any:
        """Return the plane normal used to derive an axis from its guide lines."""

        if plane_normal is not None:
            return plane_normal

        plane_points = list(guide_a_points)
        if not use_single_guide:
            plane_points.extend(guide_b_points)
        return plane_normal_from_points(
            plane_points + results["referenceLine"]["points"]
        )

    def _axis_origin_from_guides(
        self,
        side_results: Any,
        center_result_key: Any,
        lock_to_center: Any,
        use_single_guide: Any,
        guide_a_points: Any,
        guide_b_points: Any,
    ) -> Any:
        """Return the origin used for a derived axis from one or two guide lines."""

        if lock_to_center:
            return side_results[center_result_key]["center"]

        midpoint_a = 0.5 * (guide_a_points[0] + guide_a_points[1])
        if use_single_guide:
            return midpoint_a

        midpoint_b = 0.5 * (guide_b_points[0] + guide_b_points[1])
        return 0.5 * (midpoint_a + midpoint_b)

    def _update_side_femoral_shaft_axis(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Derive the femoral shaft axis from two guide lines and display a shortened representative
        axis. The axis is defined as the best common perpendicular because that is more stable than
        simply averaging the guide directions.
        """

        self._update_side_axis_from_guides(
            results,
            side_key,
            image_node,
            plane_normal,
            "shaftAxis",
            "shaftGuideProximal",
            "shaftGuideDistal",
            "shaftAxis",
            "femoralShaftAxis",
            None,
            "FemoralShaftAxis",
            0.48,
        )

    def _update_side_femoral_shaft_contours(
        self,
        results: Any,
        side_key: Any,
        image_node: Any,
        plane_normal: Any,
    ) -> None:
        """Classify four femoral-shaft cortex contours after all four curves are present.

        Classification is intentionally coordinate-driven: the four contour centroids are ordered
        along a side-aware lateral axis, then the two medial contours and two lateral contours are
        split into outer/inner by their relative positions. A pre-existing shaft axis only stabilizes
        that local coordinate frame; it is never required.
        """

        side_results = results["sides"][side_key]
        contour_results = side_results["femoralShaftContours"]
        records = self._femoral_shaft_contour_records(side_key)
        contour_results["records"] = records
        for record in records:
            self._set_femoral_shaft_contour_class(record["node"], None)

        complete_records = [record for record in records if record["defined"]]
        if len(complete_records) < len(FEMORAL_SHAFT_CONTOUR_BASE_ROLES):
            return

        origin, axis_direction = self._femoral_shaft_contour_axis(side_results, complete_records)
        lateral_axis = self._femoral_shaft_lateral_axis(
            side_key,
            image_node,
            axis_direction,
            plane_normal,
        )
        if origin is None or lateral_axis is None:
            return

        for record in complete_records:
            record["lateralPosition"] = float(np.dot(record["centroid"] - origin, lateral_axis))

        ordered_records = sorted(complete_records, key=lambda record: record["lateralPosition"])
        medial_records = ordered_records[:2]
        lateral_records = ordered_records[2:]
        assignments = self._femoral_shaft_contour_assignments(medial_records, lateral_records)
        if len(assignments) != len(FEMORAL_SHAFT_CONTOUR_BASE_ROLES):
            return

        contour_results["defined"] = True
        for class_key, record in assignments.items():
            self._set_femoral_shaft_contour_class(record["node"], class_key)
            record["classification"] = class_key
            record["classificationLabel"] = FEMORAL_SHAFT_CONTOUR_CLASS_LABELS[class_key]
            contour_results["classifications"][class_key] = {
                "role": record["role"],
                "label": FEMORAL_SHAFT_CONTOUR_CLASS_LABELS[class_key],
                "lateralPosition": record["lateralPosition"],
            }

    def _femoral_shaft_contour_records(self, side_key: Any) -> list[dict[str, Any]]:
        """Return femoral-shaft contour records with centroids for all four side-specific roles."""

        records = []
        for base_role in FEMORAL_SHAFT_CONTOUR_BASE_ROLES:
            role = self.side_role(base_role, side_key)
            node = self.get_node(role, create_if_missing=False)
            points = self._defined_points(node)
            defined = node is not None and len(points) >= 2
            centroid = np.mean(np.vstack(points), axis=0) if defined else None
            records.append(
                {
                    "role": role,
                    "baseRole": base_role,
                    "node": node,
                    "defined": defined,
                    "pointCount": len(points),
                    "centroid": centroid,
                    "classification": None,
                    "classificationLabel": None,
                }
            )
        return records

    def _femoral_shaft_contour_axis(self, side_results: Any, records: Any) -> tuple[Any, Any]:
        """Return the local long-axis used only to stabilize medial/lateral projection."""

        shaft_axis = side_results["femoralShaftAxis"]
        if shaft_axis["defined"]:
            direction = unit_vector(shaft_axis["direction"])
            origin = shaft_axis["origin"]
            if direction is not None and origin is not None:
                return as_array(origin), direction

        point_sets = [np.vstack(record_points) for record_points in self._femoral_shaft_record_points(records)]
        if not point_sets:
            return None, None

        all_points = np.vstack(point_sets)
        origin = np.mean(all_points, axis=0)
        centered_points = all_points - origin
        if centered_points.shape[0] < 2 or vector_length(centered_points) < EPSILON:
            return origin, None

        try:
            _u, _s, vh = np.linalg.svd(centered_points, full_matrices=False)
        except np.linalg.LinAlgError:
            return origin, None
        return origin, unit_vector(vh[0])

    def _femoral_shaft_record_points(self, records: Any) -> list[Any]:
        """Return defined contour point arrays for classifier PCA."""

        point_sets = []
        for record in records:
            node = record.get("node")
            if node is None:
                continue
            points = self._defined_points(node)
            if len(points) >= 2:
                point_sets.append(points)
        return point_sets

    def _femoral_shaft_lateral_axis(
        self,
        side_key: Any,
        image_node: Any,
        axis_direction: Any,
        plane_normal: Any,
    ) -> Any:
        """Return an axis whose positive direction is lateral for the requested side."""

        image_right = image_right_direction(image_node)
        if image_right is None:
            image_right = np.array([1.0, 0.0, 0.0], dtype=float)
        desired_lateral = image_right if str(side_key) == "left" else -image_right
        desired_lateral = unit_vector(desired_lateral)
        if desired_lateral is None:
            return None

        lateral_axis = desired_lateral
        shaft_axis = unit_vector(axis_direction)
        if shaft_axis is not None:
            projected = desired_lateral - shaft_axis * float(np.dot(desired_lateral, shaft_axis))
            lateral_axis = unit_vector(projected)
            if lateral_axis is None and plane_normal is not None:
                lateral_axis = in_plane_perpendicular(shaft_axis, plane_normal)

        lateral_axis = unit_vector(lateral_axis)
        if lateral_axis is None:
            return None
        if float(np.dot(lateral_axis, desired_lateral)) < 0.0:
            lateral_axis = -lateral_axis
        return lateral_axis

    def _femoral_shaft_contour_assignments(self, medial_records: Any, lateral_records: Any) -> dict[str, Any]:
        """Assign medial/lateral and inner/outer classes from sorted contour coordinates."""

        if len(medial_records) != 2 or len(lateral_records) != 2:
            return {}

        medial_sorted = sorted(medial_records, key=lambda record: record["lateralPosition"])
        lateral_sorted = sorted(lateral_records, key=lambda record: record["lateralPosition"])
        return {
            "medialOuter": medial_sorted[0],
            "medialInner": medial_sorted[1],
            "lateralInner": lateral_sorted[0],
            "lateralOuter": lateral_sorted[1],
        }

    def _set_femoral_shaft_contour_class(self, node: Any, class_key: Any) -> None:
        """Store and label one femoral-shaft contour classification on its MRML curve node."""

        if node is None:
            return
        node.SetAttribute(FEMORAL_SHAFT_CONTOUR_CLASS_ATTRIBUTE, class_key or "")
        class_label = FEMORAL_SHAFT_CONTOUR_CLASS_LABELS.get(class_key)
        if class_label is None:
            return
        safe_label = class_label.replace(" ", "")
        for point_index in range(node.GetNumberOfControlPoints()):
            self._set_control_point_label(
                node,
                point_index,
                f"FemoralShaft_{safe_label}_{point_index + 1}",
            )

    def _update_side_femur_shaft_morphology(
        self,
        results: Any,
        side_key: Any,
        image_node: Any,
        plane_normal: Any,
    ) -> None:
        """Build the calibrated femur-shaft morphology construction for one side. The vertical station
        distances are stored in millimetres and converted through the calibration ball so the
        generated points are clinically meaningful; the 11 cm points are seeded at their station but
        then left free because they are intended as fully adjustable distal landmarks.
        """

        side_results = results["sides"][side_key]
        side_label = SIDE_LABELS[side_key]
        lt_node = self.get_node(self.side_role("shaftMorphologyLTPoints", side_key))
        midline_node = self.get_node(self.side_role("shaftMorphologyMidline", side_key))
        control_node = self.get_node(self.side_role("shaftMorphologyPoints", side_key))
        guide_line_a_node = self.get_node(self.side_role("shaftMorphologyGuideLineA", side_key))
        guide_line_b_node = self.get_node(self.side_role("shaftMorphologyGuideLineB", side_key))

        lt_points = self._defined_points(lt_node)[:2]
        shaft_axis = side_results["femoralShaftAxis"]
        if not shaft_axis["defined"] or len(lt_points) < 2 or results["calibration"]["scaleFactor"] is None:
            self._clear_markup(midline_node)
            self._clear_markup(control_node)
            self._clear_markup(guide_line_a_node)
            self._clear_markup(guide_line_b_node)
            return

        axis_direction = unit_vector(shaft_axis["direction"])
        if axis_direction is None:
            self._clear_markup(midline_node)
            self._clear_markup(control_node)
            self._clear_markup(guide_line_a_node)
            self._clear_markup(guide_line_b_node)
            return

        image_up = image_up_direction(image_node)
        if image_up is not None:
            if float(np.dot(axis_direction, image_up)) < 0.0:
                axis_direction = -axis_direction
        else:
            lt_direction = unit_vector(lt_points[0] - lt_points[1])
            if lt_direction is not None and float(np.dot(axis_direction, lt_direction)) < 0.0:
                axis_direction = -axis_direction

        transverse_direction = in_plane_perpendicular(axis_direction, plane_normal)
        if transverse_direction is None:
            self._clear_markup(midline_node)
            self._clear_markup(control_node)
            self._clear_markup(guide_line_a_node)
            self._clear_markup(guide_line_b_node)
            return

        image_right = image_right_direction(image_node)
        if image_right is not None and float(np.dot(transverse_direction, image_right)) < 0.0:
            transverse_direction = -transverse_direction

        lt_axial_positions = [float(np.dot(point, axis_direction)) for point in lt_points]
        proximal_index = 0 if lt_axial_positions[0] >= lt_axial_positions[1] else 1
        distal_index = 1 - proximal_index
        self._set_control_point_label(
            lt_node,
            proximal_index,
            f"FemurShaftMorphology_{side_label}_LT_Proximal",
        )
        self._set_control_point_label(
            lt_node,
            distal_index,
            f"FemurShaftMorphology_{side_label}_LT_Distal",
        )

        mid_point = 0.5 * (lt_points[0] + lt_points[1])
        shaft_origin = shaft_axis["origin"]
        if shaft_origin is None and len(shaft_axis["endpoints"]) >= 2:
            shaft_origin = 0.5 * (shaft_axis["endpoints"][0] + shaft_axis["endpoints"][1])
        if shaft_origin is None:
            self._clear_markup(midline_node)
            self._clear_markup(control_node)
            self._clear_markup(guide_line_a_node)
            self._clear_markup(guide_line_b_node)
            return

        shaft_mid_point = closest_point_on_line(mid_point, as_array(shaft_origin), axis_direction)
        if shaft_mid_point is None:
            self._clear_markup(midline_node)
            self._clear_markup(control_node)
            self._clear_markup(guide_line_a_node)
            self._clear_markup(guide_line_b_node)
            return

        midline_half_width = self._scene_units_from_mm(results, FEMUR_SHAFT_MORPHOLOGY_MIDLINE_HALF_WIDTH_MM)
        if midline_half_width is None:
            self._clear_markup(midline_node)
            self._clear_markup(control_node)
            self._clear_markup(guide_line_a_node)
            self._clear_markup(guide_line_b_node)
            return

        self._set_line_points(
            midline_node,
            shaft_mid_point - transverse_direction * midline_half_width,
            shaft_mid_point + transverse_direction * midline_half_width,
            f"FemurShaftMorphology_{side_label}_Midline_A",
            f"FemurShaftMorphology_{side_label}_Midline_B",
        )
        midline_node.SetDisplayVisibility(True)

        existing_points = self._defined_points(control_node)
        free_pair_station = self._morphology_free_pair_station(
            side_key,
            existing_points,
            shaft_mid_point,
            axis_direction,
            self._scene_units_from_mm(results, -110.0),
        )
        generated_points = []
        generated_labels = []
        for point_index, (
            label_suffix,
            axial_offset_mm,
            default_transverse_mm,
        ) in enumerate(FEMUR_SHAFT_MORPHOLOGY_LAYOUT):
            axial_offset = self._scene_units_from_mm(results, axial_offset_mm)
            default_transverse_offset = self._scene_units_from_mm(results, default_transverse_mm)
            if axial_offset is None or default_transverse_offset is None:
                self._clear_markup(control_node)
                self._clear_markup(guide_line_a_node)
                self._clear_markup(guide_line_b_node)
                return

            if point_index in FEMUR_SHAFT_MORPHOLOGY_FREE_POINT_INDICES and free_pair_station is not None:
                axial_offset = free_pair_station
            station_center = shaft_mid_point + axis_direction * axial_offset
            if point_index < len(existing_points):
                transverse_offset = float(np.dot(existing_points[point_index] - station_center, transverse_direction))
            else:
                transverse_offset = default_transverse_offset
            generated_points.append(station_center + transverse_direction * transverse_offset)
            generated_labels.append(f"FemurShaftMorphology_{side_label}_{label_suffix}")

        self._set_named_points(control_node, generated_points, generated_labels)
        control_node.SetDisplayVisibility(True)

        guide_a_start_index, guide_a_end_index = FEMUR_SHAFT_MORPHOLOGY_GUIDE_A_INDICES
        guide_b_start_index, guide_b_end_index = FEMUR_SHAFT_MORPHOLOGY_GUIDE_B_INDICES
        guide_line_a = self._extended_morphology_guide_line(
            generated_points[guide_a_start_index],
            generated_points[guide_a_end_index],
            shaft_mid_point,
            axis_direction,
        )
        guide_line_b = self._extended_morphology_guide_line(
            generated_points[guide_b_start_index],
            generated_points[guide_b_end_index],
            shaft_mid_point,
            axis_direction,
        )
        self._set_line_points(
            guide_line_a_node,
            guide_line_a[0],
            guide_line_a[1],
            f"FemurShaftMorphology_{side_label}_GuideA_Start",
            f"FemurShaftMorphology_{side_label}_GuideA_End",
        )
        guide_line_a_node.SetDisplayVisibility(True)
        self._set_line_points(
            guide_line_b_node,
            guide_line_b[0],
            guide_line_b[1],
            f"FemurShaftMorphology_{side_label}_GuideB_Start",
            f"FemurShaftMorphology_{side_label}_GuideB_End",
        )
        guide_line_b_node.SetDisplayVisibility(True)

        side_results["femurShaftMorphology"]["defined"] = True
        side_results["femurShaftMorphology"]["midline"] = [
            shaft_mid_point - transverse_direction * midline_half_width,
            shaft_mid_point + transverse_direction * midline_half_width,
        ]
        side_results["femurShaftMorphology"]["points"] = generated_points
        side_results["femurShaftMorphology"]["guideLineA"] = guide_line_a
        side_results["femurShaftMorphology"]["guideLineB"] = guide_line_b
        inner_10cm_width = vector_length(generated_points[6] - generated_points[5])
        outer_10cm_width = vector_length(generated_points[7] - generated_points[4])
        width_2cm_above = vector_length(generated_points[1] - generated_points[0])
        cap_width = vector_length(guide_line_b[0] - guide_line_a[0])
        # A is the proximal mid-LT guide-cap width; B is the distal canal width.
        ccr = canal_calcar_ratio(distal_canal_width=inner_10cm_width, proximal_calcar_width=cap_width)
        if ccr is not None:
            side_results["corticalCalcarRatio"].update(defined=True, rawValue=ccr)
        self._set_ratio_result(
            side_results["canalThicknessIndex"],
            outer_10cm_width - inner_10cm_width,
            outer_10cm_width,
        )
        self._set_ratio_result(side_results["canalFlareIndex"], width_2cm_above, inner_10cm_width)

    def _extended_morphology_guide_line(
        self,
        upper_point: Any,
        lower_point: Any,
        midline_center: Any,
        axis_direction: Any,
    ) -> Any:
        """Extend a shaft morphology guide through its upper control point to end on the mid-LT line.
        The cap is placed at the exact shaft-axis height of the midline so the guide visibly anchors
        to the reference level without overshooting it.
        """

        guide_direction = unit_vector(upper_point - lower_point)
        if guide_direction is None or axis_direction is None:
            return [upper_point, lower_point]
        if float(np.dot(guide_direction, axis_direction)) < 0.0:
            guide_direction = -guide_direction
        axial_component = float(np.dot(guide_direction, axis_direction))
        if abs(axial_component) < EPSILON:
            return [upper_point, lower_point]

        distance_to_midline = float(np.dot(midline_center - lower_point, axis_direction)) / axial_component
        if distance_to_midline <= 0.0:
            return [upper_point, lower_point]
        extended_start = lower_point + guide_direction * distance_to_midline
        return [extended_start, lower_point]

    def _morphology_free_pair_station(
        self,
        side_key: Any,
        existing_points: Any,
        shaft_mid_point: Any,
        axis_direction: Any,
        default_station: Any,
    ) -> Any:
        """Return the shared shaft-axis station for the two 11 cm morphology points. Either point can
        be moved vertically by the user, but both are reprojected to the same station so their pair
        remains parallel to the mid-LT line.
        """

        if default_station is None:
            return None
        previous_station = self._morphology_free_pair_station_cache.get(side_key)
        if all(index < len(existing_points) for index in FEMUR_SHAFT_MORPHOLOGY_FREE_POINT_INDICES):
            stations = [
                float(np.dot(existing_points[index] - shaft_mid_point, axis_direction))
                for index in FEMUR_SHAFT_MORPHOLOGY_FREE_POINT_INDICES
            ]
            if previous_station is None:
                station = float(sum(stations) / len(stations))
            else:
                deltas = [abs(station - previous_station) for station in stations]
                station = stations[deltas.index(max(deltas))] if max(deltas) > EPSILON else previous_station
        else:
            station = float(default_station)

        self._morphology_free_pair_station_cache[side_key] = station
        return station

    def _set_ratio_result(self, measurement: Any, numerator: Any, denominator: Any) -> None:
        """Populate a dimensionless ratio result only when the denominator is stable. Leaving the result
        undefined for degenerate geometry prevents misleading CCR, CTI, or CFI values.
        """

        if numerator is None or denominator is None or abs(float(denominator)) < EPSILON:
            return
        measurement["defined"] = True
        measurement["rawValue"] = float(numerator) / float(denominator)

    def _update_side_femoral_neck_axis(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Derive the femoral neck axis from two guide lines and display a shorter representative axis.
        The displayed span is intentionally shorter than the shaft axis so the construction reads
        naturally on the radiograph.
        """

        self._update_side_axis_from_guides(
            results,
            side_key,
            image_node,
            plane_normal,
            MeasurementKey.NECK_AXIS,
            "neckGuideProximal",
            "neckGuideDistal",
            "neckAxis",
            "femoralNeckAxis",
            "femurHead",
            "FemoralNeckAxis",
            0.12,
        )

    def _update_side_implant_neck_axis(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Derive the implant neck axis from one or two guide lines using the same construction logic
        as the native femoral neck axis. Matching the methods makes pre-op and post-op angular
        comparison easier to interpret.
        """

        self._update_side_axis_from_guides(
            results,
            side_key,
            image_node,
            plane_normal,
            MeasurementKey.IMPLANT_NECK_AXIS,
            "implantNeckGuideProximal",
            "implantNeckGuideDistal",
            "implantNeckAxis",
            "implantNeckAxis",
            "implantHead",
            "ImplantNeckAxis",
            0.12,
        )

    def _side_medial_image_direction(self, side_key: Any, image_node: Any) -> Any:
        """Return the image-space medial direction for one side."""

        image_right = image_right_direction(image_node)
        if image_right is None:
            return None
        return -image_right if str(side_key) == "left" else image_right

    def _ccd_angle_from_axis_directions(
        self,
        shaft_direction: Any,
        neck_direction: Any,
        side_key: Any,
        image_node: Any,
    ) -> Any:
        """Return the CCD angle using the inferomedial image quadrant when available."""

        image_up = image_up_direction(image_node)
        medial_direction = self._side_medial_image_direction(side_key, image_node)
        if image_up is not None and medial_direction is not None:
            inferomedial_angle = oriented_angle_between_directions(
                shaft_direction,
                -image_up,
                neck_direction,
                medial_direction,
            )
            if inferomedial_angle is not None and inferomedial_angle < 90.0 - EPSILON:
                return inferomedial_angle
        return obtuse_angle_between_directions(shaft_direction, neck_direction)

    def _update_side_ccd_angle(self, results: Any, side_key: Any, image_node: Any) -> None:
        """Compute the CCD angle between the femoral neck and shaft axes. The module reports the medial
        interior angle in the lower part of the image because that is the clinically relevant
        neck-shaft relationship, including rare severe vara cases below 90 degrees.
        """

        side_results = results["sides"][side_key]
        shaft_axis = side_results["femoralShaftAxis"]
        neck_axis = side_results["femoralNeckAxis"]
        if not shaft_axis["defined"] or not neck_axis["defined"]:
            return

        angle = self._ccd_angle_from_axis_directions(
            shaft_axis["direction"],
            neck_axis["direction"],
            side_key,
            image_node,
        )
        if angle is None:
            return

        side_results["ccdAngle"]["defined"] = True
        side_results["ccdAngle"]["rawValue"] = angle

    def _update_side_implant_femoral_ccd(self, results: Any, side_key: Any, image_node: Any) -> None:
        """Compute the implant-femoral CCD angle between the native femoral shaft axis and the implant
        neck axis. The same inferomedial image-side rule is used as the native CCD angle so the two
        values remain directly comparable.
        """

        side_results = results["sides"][side_key]
        shaft_axis = side_results["femoralShaftAxis"]
        implant_neck_axis = side_results["implantNeckAxis"]
        if not shaft_axis["defined"] or not implant_neck_axis["defined"]:
            return

        angle = self._ccd_angle_from_axis_directions(
            shaft_axis["direction"],
            implant_neck_axis["direction"],
            side_key,
            image_node,
        )
        if angle is None:
            return

        side_results["implantFemoralCCD"]["defined"] = True
        side_results["implantFemoralCCD"]["rawValue"] = angle

    def _update_side_parallel_line_offset(
        self,
        results: Any,
        side_key: Any,
        plane_normal: Any,
        line_a_role: Any,
        line_b_role: Any,
        result_key: Any,
    ) -> None:
        """Compute the distance between two constrained parallel lines for one side. A shared helper
        avoids duplicating the same line-to-line offset logic across several tools.
        """

        side_results = results["sides"][side_key]
        reference = results["referenceLine"]
        line_a = self.get_node(self.side_role(line_a_role, side_key))
        line_b = self.get_node(self.side_role(line_b_role, side_key))

        if not reference["defined"]:
            return

        offset_direction = in_plane_perpendicular(reference["direction"], plane_normal)
        if offset_direction is None:
            return

        self._constrain_line_direction(line_a, offset_direction)
        self._constrain_line_direction(line_b, offset_direction)

        points_a = self._defined_points(line_a)
        points_b = self._defined_points(line_b)
        if len(points_a) < 2 or len(points_b) < 2:
            return

        raw_distance = vector_length(np.cross(offset_direction, points_b[0] - points_a[0]))
        side_results[result_key]["defined"] = True
        side_results[result_key]["rawValue"] = raw_distance
        side_results[result_key]["correctedValue"] = self._correct_value(results, raw_distance)

    def _update_side_axis_parallel_offset(self, results: Any, side_key: Any, line_role: Any, result_key: Any) -> None:
        """Compute the distance between a user line and a stored axis for one side. This helper is used
        when one construction comes from derived anatomy rather than another free line.
        """

        side_results = results["sides"][side_key]
        shaft_axis = side_results["femoralShaftAxis"]
        offset_line = self.get_node(self.side_role(line_role, side_key))

        if not shaft_axis["defined"]:
            return

        self._constrain_line_direction(offset_line, shaft_axis["direction"])
        points = self._defined_points(offset_line)
        if len(points) < 2:
            return

        raw_distance = vector_length(
            np.cross(shaft_axis["direction"], points[0] - shaft_axis["origin"])
        )
        side_results[result_key]["defined"] = True
        side_results[result_key]["rawValue"] = raw_distance
        side_results[result_key]["correctedValue"] = self._correct_value(results, raw_distance)

    def _update_side_global_offset(
        self,
        results: Any,
        side_key: Any,
        acetabular_key: Any,
        femoral_key: Any,
        result_key: Any,
    ) -> None:
        """Combine acetabular and femoral offsets into one global offset result. The sum is derived
        automatically so users do not need a separate construction for a value that is purely
        composite.
        """

        side_results = results["sides"][side_key]
        acetabular_offset = side_results[acetabular_key]
        femoral_offset = side_results[femoral_key]
        if not acetabular_offset["defined"] or not femoral_offset["defined"]:
            return

        raw_value = acetabular_offset["rawValue"] + femoral_offset["rawValue"]
        side_results[result_key]["defined"] = True
        side_results[result_key]["rawValue"] = raw_value
        side_results[result_key]["correctedValue"] = self._correct_value(results, raw_value)

    def _update_side_acetabular_offset(self, results: Any, side_key: Any, plane_normal: Any) -> None:
        """Update the pre-op acetabular offset using the shared parallel-line helper. The construction
        is constrained perpendicular to the reference line so it measures the intended mediolateral
        separation.
        """

        self._update_side_parallel_line_offset(
            results,
            side_key,
            plane_normal,
            "acetabularOffsetLineA",
            "acetabularOffsetLineB",
            "acetabularOffset",
        )

    def _update_side_femoral_offset(self, results: Any, side_key: Any, _plane_normal: Any) -> None:
        """Update the pre-op femoral offset relative to the shaft axis. Reusing the axis-based helper
        keeps the pre-op and post-op implementations consistent.
        """

        self._update_side_axis_parallel_offset(
            results, side_key, "femoralOffsetLine", "femoralOffset"
        )

    def _update_side_preop_global_offset(self, results: Any, side_key: Any) -> None:
        """Update the composite pre-op global offset when both component offsets are available. The
        result is only reported once both ingredients are defined to avoid misleading partial
        values.
        """

        self._update_side_global_offset(
            results, side_key, "acetabularOffset", "femoralOffset", "preopGlobalOffset"
        )

    def _update_side_postop_acetabular_offset(self, results: Any, side_key: Any, plane_normal: Any) -> None:
        """Update the post-op acetabular offset using the same geometry as the pre-op version. Separate
        result channels are kept so pre-op and THA measurements cannot be mixed accidentally.
        """

        self._update_side_parallel_line_offset(
            results,
            side_key,
            plane_normal,
            "postOpAcetabularOffsetLineA",
            "postOpAcetabularOffsetLineB",
            "postOpAcetabularOffset",
        )

    def _update_side_postop_femoral_offset(self, results: Any, side_key: Any, _plane_normal: Any) -> None:
        """Update the post-op femoral offset relative to the shaft axis. The post-op value is stored
        independently even though the underlying geometric idea matches the pre-op tool.
        """

        self._update_side_axis_parallel_offset(
            results, side_key, "postOpFemoralOffsetLine", "postOpFemoralOffset"
        )

    def _update_side_postop_global_offset(self, results: Any, side_key: Any) -> None:
        """Update the composite post-op global offset from its two THA component offsets. Keeping it
        derived avoids extra clicks while still exporting the clinically useful sum.
        """

        self._update_side_global_offset(
            results,
            side_key,
            "postOpAcetabularOffset",
            "postOpFemoralOffset",
            "postOpGlobalOffset",
        )

    def _update_side_implant_alignment(self, results: Any, side_key: Any, image_node: Any, plane_normal: Any) -> None:
        """Derive the stem axis from two guide lines and compute its angular difference from the
        femoral shaft axis. Using the same axis-construction logic as the shaft tool makes stem
        alignment less sensitive to one imperfect freehand line.
        """

        self._update_side_axis_from_guides(
            results,
            side_key,
            image_node,
            plane_normal,
            "implantAlignment",
            "implantAlignmentGuideProximal",
            "implantAlignmentGuideDistal",
            "implantAlignmentLine",
            "implantStemAxis",
            None,
            "StemAlignment",
            0.48,
        )

        side_results = results["sides"][side_key]
        shaft_axis = side_results["femoralShaftAxis"]
        stem_axis = side_results["implantStemAxis"]
        if not shaft_axis["defined"] or not stem_axis["defined"]:
            return

        angle = acute_angle_between_directions(stem_axis["direction"], shaft_axis["direction"])
        if angle is None:
            return

        side_results["implantAlignment"]["defined"] = True
        side_results["implantAlignment"]["rawValue"] = angle

    def _update_other_points(self, results: Any) -> None:
        """Update results for user-added labelled points."""

        for index in self.other_point_indices():
            role = other_point_role(index)
            node = self.get_node(role, create_if_missing=False)
            measurement = {
                "index": index,
                "defined": False,
                "point": None,
            }
            if node is not None:
                points = self._defined_points(node)
                if points:
                    measurement["defined"] = True
                    measurement["point"] = points[0]
            results["otherPoints"].append(measurement)

    def _update_other_lines(self, results: Any, image_node: Any, plane_normal: Any) -> None:
        """Update results for user-added free lines, including optional reference locking.

        Locked custom lines stay editable, but their orientation is constrained to remain parallel
        or perpendicular to the reference line when that reference is available.
        """

        reference = results["referenceLine"]
        for index in self.other_line_indices():
            role = other_line_role(index)
            node = self.get_node(role, create_if_missing=False)
            lock_mode = self._other_line_lock_mode(node)
            measurement = self._other_line_measurement(index, lock_mode)
            if node is not None:
                points = self._apply_other_line_locked_reference(
                    node,
                    lock_mode,
                    reference,
                    plane_normal,
                    image_node,
                )
                if len(points) >= 2:
                    raw_value = vector_length(points[1] - points[0])
                    measurement["defined"] = True
                    measurement["rawValue"] = raw_value
                    measurement["correctedValue"] = self._correct_value(results, raw_value)
            results["otherLines"].append(measurement)

    def _other_line_lock_mode(self, line_node: Any) -> Any:
        """Return the stored lock mode for one custom line node."""

        if line_node is None:
            return OtherAngleLockMode.NONE
        try:
            return OtherAngleLockMode(
                str(line_node.GetAttribute(OTHER_LINE_LOCK_ATTRIBUTE) or OtherAngleLockMode.NONE)
            )
        except ValueError:
            return OtherAngleLockMode.NONE

    def _other_line_measurement(self, index: Any, lock_mode: Any) -> Any:
        """Return the default measurement record for one custom line."""

        return {
            "index": index,
            "defined": False,
            "rawValue": None,
            "correctedValue": None,
            "lockMode": lock_mode,
        }

    def _locked_other_line_direction(
        self,
        lock_mode: Any,
        reference: Any,
        plane_normal: Any,
        image_node: Any,
    ) -> Any:
        """Return the constrained direction for one custom line lock mode."""

        if lock_mode == OtherAngleLockMode.PARALLEL:
            return unit_vector(reference["direction"])
        if lock_mode == OtherAngleLockMode.PERPENDICULAR:
            return superior_reference_direction(reference["direction"], plane_normal, image_node)
        return None

    def _apply_other_line_locked_reference(
        self,
        line_node: Any,
        lock_mode: Any,
        reference: Any,
        plane_normal: Any,
        image_node: Any,
    ) -> Any:
        """Constrain a custom line to its locked reference orientation while preserving midpoint."""

        points = self._defined_points(line_node)
        if (
            len(points) < 2
            or lock_mode == OtherAngleLockMode.NONE
            or not reference["defined"]
        ):
            return points

        locked_direction = self._locked_other_line_direction(
            lock_mode,
            reference,
            plane_normal,
            image_node,
        )
        if locked_direction is None:
            return points

        current_vector = points[1] - points[0]
        line_length = vector_length(current_vector)
        if line_length < EPSILON:
            line_length = DEFAULT_CONSTRUCTION_LINE_LENGTH_SU
        if (
            vector_length(current_vector) >= EPSILON
            and float(np.dot(current_vector, locked_direction)) < 0.0
        ):
            locked_direction = -locked_direction

        midpoint = (points[0] + points[1]) / 2.0
        half_vector = locked_direction * (line_length / 2.0)
        self._set_control_point_position(line_node, 0, midpoint - half_vector)
        self._set_control_point_position(line_node, 1, midpoint + half_vector)
        return self._defined_points(line_node)

    def _update_other_angles(self, results: Any, image_node: Any, plane_normal: Any) -> None:
        """Update results and helper arms for user-added free angles, including optional reference
        locking. Separating the custom-angle engine from the built-in tools keeps the module
        extensible without cluttering the main measurement logic.
        """

        reference = results["referenceLine"]
        for index in self.other_angle_indices():
            points_node, reference_node, free_arm_node = self._other_angle_nodes(index)
            lock_mode = self._other_angle_lock_mode(points_node)
            measurement = self._other_angle_measurement(index, lock_mode)
            if points_node is None:
                self._clear_other_angle_helper_nodes(reference_node, free_arm_node)
                results["otherAngles"].append(measurement)
                continue

            points = self._defined_points(points_node)
            if lock_mode != OtherAngleLockMode.NONE and not reference["defined"]:
                self._clear_other_angle_helper_nodes(reference_node, free_arm_node)
                results["otherAngles"].append(measurement)
                continue
            points = self._apply_other_angle_locked_reference(
                points_node,
                points,
                lock_mode,
                reference,
                plane_normal,
                image_node,
            )
            self._sync_other_angle_helper_arms(
                index,
                points,
                reference_node,
                free_arm_node,
            )
            self._populate_other_angle_value(measurement, points)

            results["otherAngles"].append(measurement)

    def _other_angle_nodes(self, index: Any) -> Any:
        """Return the primary and helper nodes for one custom angle measurement."""

        return (
            self.get_node(other_angle_points_role(index), create_if_missing=False),
            self.get_node(other_angle_reference_arm_role(index), create_if_missing=False),
            self.get_node(other_angle_free_arm_role(index), create_if_missing=False),
        )

    def _other_angle_lock_mode(self, points_node: Any) -> Any:
        """Return the stored lock mode for one custom angle points node."""

        if points_node is None:
            return OtherAngleLockMode.NONE
        try:
            return OtherAngleLockMode(
                str(points_node.GetAttribute(OTHER_ANGLE_LOCK_ATTRIBUTE) or OtherAngleLockMode.NONE)
            )
        except ValueError:
            return OtherAngleLockMode.NONE

    def _other_angle_measurement(self, index: Any, lock_mode: Any) -> Any:
        """Return the default measurement record for one custom angle."""

        return {
            "index": index,
            "defined": False,
            "rawValue": None,
            "lockMode": lock_mode,
        }

    def _clear_other_angle_helper_nodes(self, reference_node: Any, free_arm_node: Any) -> None:
        """Hide and clear the helper-arm nodes for one custom angle."""

        if reference_node is not None:
            self._clear_markup(reference_node)
        if free_arm_node is not None:
            self._clear_markup(free_arm_node)

    def _locked_other_angle_direction(
        self,
        lock_mode: Any,
        reference: Any,
        plane_normal: Any,
        image_node: Any,
    ) -> Any:
        """Return the locked first-arm direction for a custom angle."""

        if lock_mode == OtherAngleLockMode.PARALLEL:
            return unit_vector(reference["direction"])
        return superior_reference_direction(reference["direction"], plane_normal, image_node)

    def _apply_other_angle_locked_reference(
        self,
        points_node: Any,
        points: Any,
        lock_mode: Any,
        reference: Any,
        plane_normal: Any,
        image_node: Any,
    ) -> Any:
        """Adjust the first arm of a locked custom angle to its constrained direction."""

        if (
            len(points) < 2
            or lock_mode == OtherAngleLockMode.NONE
            or not reference["defined"]
        ):
            return points

        vertex = points[1]
        locked_vector = points[0] - vertex
        locked_length = vector_length(locked_vector)
        if locked_length < EPSILON:
            locked_length = DEFAULT_CONSTRUCTION_LINE_LENGTH_SU

        locked_direction = self._locked_other_angle_direction(
            lock_mode,
            reference,
            plane_normal,
            image_node,
        )
        if locked_direction is None:
            return points

        if (
            vector_length(locked_vector) >= EPSILON
            and float(np.dot(locked_vector, locked_direction)) < 0.0
        ):
            locked_direction = -locked_direction
        locked_endpoint = vertex + locked_direction * locked_length
        self._set_control_point_position(points_node, 0, locked_endpoint)
        return self._defined_points(points_node)

    def _sync_other_angle_helper_arm(
        self,
        node: Any,
        points: Any,
        start_index: Any,
        end_index: Any,
        label_a: Any,
        label_b: Any,
    ) -> None:
        """Show or clear one helper arm for a custom angle based on available points."""

        if node is None:
            return
        if len(points) <= max(start_index, end_index):
            self._clear_markup(node)
            return
        self._set_line_points(
            node,
            points[start_index],
            points[end_index],
            label_a,
            label_b,
        )
        node.SetDisplayVisibility(True)

    def _sync_other_angle_helper_arms(
        self,
        index: Any,
        points: Any,
        reference_node: Any,
        free_arm_node: Any,
    ) -> None:
        """Update both helper-arm markups for one custom angle."""

        self._sync_other_angle_helper_arm(
            reference_node,
            points,
            1,
            0,
            f"Angle_{index}_ArmA_Start",
            f"Angle_{index}_ArmA_End",
        )
        self._sync_other_angle_helper_arm(
            free_arm_node,
            points,
            1,
            2,
            f"Angle_{index}_ArmB_Start",
            f"Angle_{index}_ArmB_End",
        )

    def _populate_other_angle_value(self, measurement: Any, points: Any) -> None:
        """Populate the angle value for one custom angle when all required points exist."""

        if len(points) < 3:
            return
        direction_a = unit_vector(points[0] - points[1])
        direction_b = unit_vector(points[2] - points[1])
        if direction_a is None or direction_b is None:
            return
        angle = unsigned_angle_between_directions(direction_a, direction_b)
        if angle is None:
            return
        measurement["defined"] = True
        measurement["rawValue"] = angle

    def _update_lld(self, results: Any, image_node: Any, plane_normal: Any) -> None:
        """Compute leg-length discrepancy relative to the reference line and draw the associated helper
        constructions. The module uses reference-line projections because LLD is meant to reflect
        vertical discrepancy relative to pelvic orientation, not raw point-to-point distance.
        """

        lld_points_node = self.get_node("lldPoints")
        left_projection_node = self.get_node("lldLeftProjection")
        right_projection_node = self.get_node("lldRightProjection")
        left_parallel_node = self.get_node("lldLeftParallel")
        right_parallel_node = self.get_node("lldRightParallel")
        height_difference_node = self.get_node("lldHeightDifference")

        reference = results["referenceLine"]
        points = self._defined_points(lld_points_node)[:2]

        if not reference["defined"] or len(points) < 2:
            self._clear_model(left_projection_node)
            self._clear_model(right_projection_node)
            self._clear_markup(left_parallel_node)
            self._clear_markup(right_parallel_node)
            self._clear_markup(height_difference_node)
            return

        ordered_points = self._ordered_lld_points(reference, points, image_node)
        if ordered_points is None:
            self._clear_model(left_projection_node)
            self._clear_model(right_projection_node)
            self._clear_markup(left_parallel_node)
            self._clear_markup(right_parallel_node)
            self._clear_markup(height_difference_node)
            return

        self._set_control_point_label(
            lld_points_node, ordered_points["leftIndex"], "MinorTrochanter_Left"
        )
        self._set_control_point_label(
            lld_points_node, ordered_points["rightIndex"], "MinorTrochanter_Right"
        )
        left_point = ordered_points["leftPoint"]
        right_point = ordered_points["rightPoint"]

        signed_left = signed_distance_to_line_in_plane(
            left_point, reference["points"][0], reference["direction"], plane_normal
        )
        signed_right = signed_distance_to_line_in_plane(
            right_point, reference["points"][0], reference["direction"], plane_normal
        )
        if signed_left is None or signed_right is None:
            self._clear_model(left_projection_node)
            self._clear_model(right_projection_node)
            self._clear_markup(left_parallel_node)
            self._clear_markup(right_parallel_node)
            self._clear_markup(height_difference_node)
            return

        left_projection = closest_point_on_line(
            left_point, reference["points"][0], reference["direction"]
        )
        right_projection = closest_point_on_line(
            right_point, reference["points"][0], reference["direction"]
        )

        self._update_model_polydata(
            left_projection_node, polydata_from_points([left_point, left_projection])
        )
        self._update_model_polydata(
            right_projection_node, polydata_from_points([right_point, right_projection])
        )

        projected_separation = abs(float(np.dot(right_point - left_point, reference["direction"])))
        medial_span = max(
            0.2 * self._display_span(image_node, reference["points"] + points),
            0.6 * projected_separation,
        )
        left_lateral_direction = lateral_reference_direction(
            reference["direction"], "left", image_node
        )
        right_lateral_direction = lateral_reference_direction(
            reference["direction"], "right", image_node
        )
        if left_lateral_direction is None or right_lateral_direction is None:
            self._clear_markup(left_parallel_node)
            self._clear_markup(right_parallel_node)
            self._clear_markup(height_difference_node)
            return
        left_medial_direction = -left_lateral_direction
        right_medial_direction = -right_lateral_direction
        self._set_line_points(
            left_parallel_node,
            left_point,
            left_point + left_medial_direction * medial_span,
            "LLD_LeftParallel_Start",
            "LLD_LeftParallel_End",
        )
        left_parallel_node.SetDisplayVisibility(True)
        self._set_line_points(
            right_parallel_node,
            right_point,
            right_point + right_medial_direction * medial_span,
            "LLD_RightParallel_Start",
            "LLD_RightParallel_End",
        )
        right_parallel_node.SetDisplayVisibility(True)

        origin = reference["points"][0]
        left_position = float(np.dot(left_point - origin, reference["direction"]))
        right_position = float(np.dot(right_point - origin, reference["direction"]))
        midpoint_position = 0.5 * (left_position + right_position)
        left_height_point = left_point + reference["direction"] * (midpoint_position - left_position)
        right_height_point = right_point + reference["direction"] * (midpoint_position - right_position)
        self._set_line_points(
            height_difference_node,
            left_height_point,
            right_height_point,
            "LLD_Difference_Start",
            "LLD_Difference_End",
        )
        height_difference_node.SetDisplayVisibility(True)

        raw_difference = abs(signed_left - signed_right)
        signed_difference = signed_left - signed_right
        results["lld"]["defined"] = True
        results["lld"]["rawValue"] = raw_difference
        results["lld"]["correctedValue"] = self._correct_value(results, raw_difference)
        results["lld"]["signedRawValue"] = signed_difference
        results["lld"]["signedCorrectedValue"] = self._correct_value(results, signed_difference)
        results["lld"]["leftProjection"] = left_projection
        results["lld"]["rightProjection"] = right_projection

    def _display_span(self, image_node: Any, fallback_points: Any) -> Any:
        """Estimate a sensible visual span for derived helper lines. Display length is chosen from
        image or point extents so axes remain readable without needing manual sizing.
        """

        if image_node is not None:
            bounds = [0.0] * 6
            image_node.GetRASBounds(bounds)
            extents = [
                abs(bounds[1] - bounds[0]),
                abs(bounds[3] - bounds[2]),
                abs(bounds[5] - bounds[4]),
            ]
            largest_extent = max(extents)
            if largest_extent > EPSILON:
                return largest_extent * 0.75

        if fallback_points:
            points_array = np.vstack(fallback_points)
            extents = np.ptp(points_array, axis=0)
            largest_extent = float(np.max(extents))
            if largest_extent > EPSILON:
                return largest_extent * 1.5

        return 150.0

    def _correct_value(self, results: Any, raw_value: Any) -> Any:
        """Apply calibration scaling to a raw length when calibration is available. Length correction
        is isolated here so scene-unit-only mode and calibrated mode share the same callers.
        """

        scale_factor = results["calibration"]["scaleFactor"]
        if raw_value is None or scale_factor is None:
            return None
        return float(raw_value) * scale_factor

    def _scene_units_from_mm(self, results: Any, value_mm: Any) -> Any:
        """Convert a physical millimetre distance into scene units using the calibration scale. The
        morphology tool needs this inverse conversion because it generates landmarks at fixed real-
        world distances from a user-defined reference level.
        """

        scale_factor = results["calibration"]["scaleFactor"]
        if value_mm is None or scale_factor is None or abs(scale_factor) < EPSILON:
            return None
        return float(value_mm) / float(scale_factor)

    def _clear_markup(self, markup_node: Any) -> None:
        """Remove all control points from a markup node and hide it. Explicit clearing prevents stale
        helper geometry from surviving when a prerequisite measurement becomes invalid.
        """

        if markup_node is None or not markup_node.IsA("vtkMRMLMarkupsNode"):
            return
        markup_node.RemoveAllControlPoints()
        markup_node.SetDisplayVisibility(False)

    def _unlock_markup_node(self, node: Any) -> Any:
        """Temporarily unlock a markup node and return whether it was previously locked."""

        was_locked = bool(node.GetLocked()) if hasattr(node, "GetLocked") else False
        if was_locked:
            node.SetLocked(False)
        return was_locked

    def _restore_markup_lock(self, node: Any, was_locked: Any) -> None:
        """Restore a markup node's previous locked state after edits."""

        if was_locked:
            node.SetLocked(True)

    def _sync_markup_control_point_count(self, node: Any, points: Any) -> None:
        """Resize a markup node to match an ordered point list."""

        while node.GetNumberOfControlPoints() > len(points):
            node.RemoveNthControlPoint(node.GetNumberOfControlPoints() - 1)
        while node.GetNumberOfControlPoints() < len(points):
            point = points[node.GetNumberOfControlPoints()]
            if hasattr(node, "AddControlPointWorld"):
                node.AddControlPointWorld(vtk_vector3d(point))
            else:
                node.AddControlPoint(vtk_vector3d(point))

    def _set_polyline_points(self, node: Any, points: Any, label_prefix: Any=None) -> None:
        """Replace a markup polyline with a new ordered point list while respecting locked state.
        Centralizing this avoids subtle duplication around point counts, labels, and lock toggling.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return
        was_locked = self._unlock_markup_node(node)
        self._sync_markup_control_point_count(node, points)

        for index, point in enumerate(points):
            self._set_control_point_position(node, index, point)
            if label_prefix:
                self._set_control_point_label(node, index, f"{label_prefix}_{index + 1}")

        self._restore_markup_lock(node, was_locked)

    def _set_named_points(self, node: Any, points: Any, labels: Any) -> None:
        """Replace a multi-point markup with named points while preserving editability. This is used
        for generated construction points that should snap back to calibrated station heights but
        remain horizontally adjustable by the user.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return
        was_locked = bool(node.GetLocked()) if hasattr(node, "GetLocked") else False
        if was_locked:
            node.SetLocked(False)

        while node.GetNumberOfControlPoints() > len(points):
            node.RemoveNthControlPoint(node.GetNumberOfControlPoints() - 1)
        while node.GetNumberOfControlPoints() < len(points):
            point = points[node.GetNumberOfControlPoints()]
            if hasattr(node, "AddControlPointWorld"):
                node.AddControlPointWorld(vtk_vector3d(point))
            else:
                node.AddControlPoint(vtk_vector3d(point))

        for index, point in enumerate(points):
            self._set_control_point_position(node, index, point)
            if index < len(labels):
                self._set_control_point_label(node, index, labels[index])

        if was_locked:
            node.SetLocked(True)

    def _set_control_point_label(self, node: Any, index: Any, label: Any) -> None:
        """Update a control-point label only when it actually changes. Avoiding redundant label writes
        helps keep live updates responsive.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return
        if 0 <= index < node.GetNumberOfControlPoints():
            current_label = node.GetNthControlPointLabel(index)
            if current_label == label:
                return
            node.SetNthControlPointLabel(index, label)

    def _ordered_lld_points(self, reference: Any, points: Any, image_node: Any) -> Any:
        """Decide which LLD point is left versus right based on image-space lateral position. The
        ordering is derived from displayed image geometry so placement order does not matter to the
        user.
        """

        if len(points) < 2 or not reference["defined"]:
            return None

        left_lateral_direction = lateral_reference_direction(reference["direction"], "left", image_node)
        if left_lateral_direction is None:
            image_right = image_right_direction(image_node)
            if image_right is None:
                return None
            left_lateral_direction = image_right

        origin = reference["points"][0]
        lateral_positions = [
            float(np.dot(point - origin, left_lateral_direction)) for point in points[:2]
        ]
        left_index = 0 if lateral_positions[0] >= lateral_positions[1] else 1
        right_index = 1 - left_index
        return {
            "leftIndex": left_index,
            "rightIndex": right_index,
            "leftPoint": points[left_index],
            "rightPoint": points[right_index],
        }

    def _clear_model(self, model_node: Any) -> None:
        """Clear a model node and hide it. Model helpers are removed explicitly so outdated circles,
        ellipses, and projection lines do not linger in the view.
        """

        model_node.SetAndObservePolyData(vtk.vtkPolyData())
        model_node.SetDisplayVisibility(False)

    def _update_model_polydata(self, model_node: Any, poly_data: Any, visible: Any=True) -> None:
        """Replace the polydata in a model node and set its visibility. This helper keeps live model
        updates compact and consistent.
        """

        model_node.SetAndObservePolyData(poly_data)
        model_node.SetDisplayVisibility(bool(visible))

    def _defined_points(self, node: Any) -> Any:
        """Return the defined control points from a markup node as NumPy arrays. Measurement code uses
        this normalized representation so all geometry helpers can share the same math primitives.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return []
        points = []
        for index in range(node.GetNumberOfDefinedControlPoints()):
            point = [0.0, 0.0, 0.0]
            if hasattr(node, "GetNthControlPointPositionWorld"):
                node.GetNthControlPointPositionWorld(index, point)
            else:
                node.GetNthControlPointPosition(index, point)
            points.append(as_array(point))
        return points

    def _set_single_point(self, node: Any, point: Any, label: Any) -> None:
        """Set or replace a one-point markup while respecting locked state. The helper is used for
        derived centers that should behave like normal markups once created.
        """

        was_locked = bool(node.GetLocked()) if hasattr(node, "GetLocked") else False
        if was_locked:
            node.SetLocked(False)
        if node.GetNumberOfControlPoints() == 0:
            if hasattr(node, "AddControlPointWorld"):
                node.AddControlPointWorld(vtk_vector3d(point))
            else:
                node.AddControlPoint(vtk_vector3d(point))
        else:
            if hasattr(node, "SetNthControlPointPositionWorld"):
                node.SetNthControlPointPositionWorld(0, float(point[0]), float(point[1]), float(point[2]))
            else:
                node.SetNthControlPointPosition(0, float(point[0]), float(point[1]), float(point[2]))
        node.SetNthControlPointLabel(0, label)
        if was_locked:
            node.SetLocked(True)

    def _set_line_points(self, node: Any, point_a: Any, point_b: Any, label_a: Any, label_b: Any) -> None:
        """Set or replace a two-point markup line while respecting locked state. A dedicated line
        setter keeps derived construction lines consistent across the module.
        """

        was_locked = self._unlock_markup_node(node)
        points = [point_a, point_b]
        self._sync_markup_control_point_count(node, points)
        for index, point in enumerate(points):
            self._set_control_point_position(node, index, point)
        self._set_control_point_label(node, 0, label_a)
        self._set_control_point_label(node, 1, label_b)
        self._restore_markup_lock(node, was_locked)

    def _set_control_point_position(self, node: Any, index: Any, point: Any) -> None:
        """Move one markup control point only when the new position is meaningfully different. Avoiding
        redundant writes helps reduce self-triggered update churn.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return
        if not (0 <= index < node.GetNumberOfControlPoints()):
            return

        current_point = [0.0, 0.0, 0.0]
        if hasattr(node, "GetNthControlPointPositionWorld"):
            node.GetNthControlPointPositionWorld(index, current_point)
        else:
            node.GetNthControlPointPosition(index, current_point)
        if vector_length(as_array(current_point) - as_array(point)) < EPSILON:
            return

        if hasattr(node, "SetNthControlPointPositionWorld"):
            node.SetNthControlPointPositionWorld(
                index,
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )
        else:
            node.SetNthControlPointPosition(
                index,
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )

    def _constrain_line_direction(self, node: Any, direction: Any) -> None:
        """Project a line endpoint onto a required direction while preserving usable length. This lets
        offset and axis guide lines stay editable but still obey the intended construction rule.
        """

        points = self._defined_points(node)
        if len(points) < 2 or direction is None:
            return

        current_vector = points[1] - points[0]
        projected_length = float(np.dot(current_vector, direction))
        if abs(projected_length) < EPSILON:
            projected_length = DEFAULT_CONSTRUCTION_LINE_LENGTH_SU
        adjusted_endpoint = points[0] + direction * projected_length

        if hasattr(node, "SetNthControlPointPositionWorld"):
            node.SetNthControlPointPositionWorld(
                1,
                float(adjusted_endpoint[0]),
                float(adjusted_endpoint[1]),
                float(adjusted_endpoint[2]),
            )
        else:
            node.SetNthControlPointPosition(
                1,
                float(adjusted_endpoint[0]),
                float(adjusted_endpoint[1]),
                float(adjusted_endpoint[2]),
            )

    def _apply_labels(self, node: Any, role: Any) -> None:
        """Apply role-defined labels to the current points of a markup node. Labels are re-applied
        during updates so saved scenes and edited scenes retain readable semantics.
        """

        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return
        spec = self._node_spec_for_role(role)
        labels = spec.get("labels", [])
        for index, label in enumerate(labels):
            if index < node.GetNumberOfControlPoints():
                self._set_control_point_label(node, index, label)
        label_prefix = spec.get("labelPrefix")
        if label_prefix:
            for index in range(len(labels), node.GetNumberOfControlPoints()):
                self._set_control_point_label(node, index, f"{label_prefix}_{index + 1}")
