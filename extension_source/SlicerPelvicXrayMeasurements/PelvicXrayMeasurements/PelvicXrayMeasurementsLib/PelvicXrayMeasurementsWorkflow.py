"""Guided placement workflows and button actions for Pelvic X-ray Measurements.

This mixin keeps the workflow state machine and measurement-button callbacks separate from UI
layout and geometry calculations. The widget owns the controls; this mixin owns how user actions
start, advance, reset, and export workflows.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import slicer

from PelvicXrayMeasurementsConstants import (
    DEFAULT_CONSTRUCTION_LINE_LENGTH_SU,
    EPSILON,
    FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
    SIDE_LABELS,
    MeasurementKey,
    OtherAngleLockMode,
)
from PelvicXrayMeasurementsGeometry import (
    as_array,
    lateral_reference_direction,
    plane_normal_from_volume,
    superior_reference_direction,
    unit_vector,
    vector_length,
)


class WorkflowActionsMixin:
    """Provide guided placement and command handlers for the main widget."""

    def _selected_reference_lock_mode(self, parallel_check: Any, perpendicular_check: Any) -> Any:
        """Return the selected reference-lock mode from one pair of mutually exclusive checkboxes."""

        if bool(parallel_check.isChecked()):
            return OtherAngleLockMode.PARALLEL
        if bool(perpendicular_check.isChecked()):
            return OtherAngleLockMode.PERPENDICULAR
        return OtherAngleLockMode.NONE

    def _sync_reference_lock_checkboxes(self, primary_check: Any, secondary_check: Any, checked: Any) -> None:
        """Keep one reference-lock checkbox pair mutually exclusive."""

        if not checked:
            return
        secondary_check.blockSignals(True)
        secondary_check.setChecked(False)
        secondary_check.blockSignals(False)

    def _role_points(self, role: Any) -> list[Any]:
        """Return defined world points for one role without creating new scene nodes."""

        node = self.logic.get_node(role, create_if_missing=False)
        if node is None:
            return []
        return self.logic._defined_points(node)

    def _side_role_points(self, base_role: str, side_key: Any) -> list[Any]:
        """Return defined world points for one side-specific role."""

        return self._role_points(self.logic.side_role(base_role, side_key))

    def _side_roles_have_defined_points(self, base_roles: Any, side_key: Any) -> bool:
        """Return whether any role in one measurement already has user-input points."""

        return any(self._side_role_points(base_role, side_key) for base_role in base_roles)

    def _pending_auto_line_endpoint_map(self) -> dict[Any, Any]:
        """Return the widget-local map of line roles waiting for an automatic second endpoint."""

        if not hasattr(self, "pending_auto_line_endpoints"):
            self.pending_auto_line_endpoints = {}
        return self.pending_auto_line_endpoints

    def _line_midpoint(self, base_role: str, side_key: Any) -> Any:
        """Return the midpoint of a side-specific line, if that line is defined."""

        points = self._side_role_points(base_role, side_key)
        if len(points) < 2:
            return None
        return 0.5 * (points[0] + points[1])

    def _first_side_point(self, base_role: str, side_key: Any) -> Any:
        """Return the first defined control point for one side-specific role."""

        points = self._side_role_points(base_role, side_key)
        if not points:
            return None
        return points[0]

    def _reference_direction(self) -> Any:
        """Return the current pelvic reference-line direction when available."""

        reference = self.logic.latest_results.get("referenceLine", {})
        if not reference.get("defined"):
            return None
        return reference.get("direction")

    def _reference_superior_direction(self) -> Any:
        """Return the reference-perpendicular image-superior direction used by line-based tools."""

        reference_direction = self._reference_direction()
        if reference_direction is None:
            return None
        image_node = self.current_image_node()
        plane_normal = plane_normal_from_volume(image_node) if image_node is not None else None
        return superior_reference_direction(
            reference_direction,
            plane_normal,
            image_node,
        )

    def _reference_lateral_direction(self, side_key: Any) -> Any:
        """Return the side-aware lateral direction along the pelvic reference line."""

        reference_direction = self._reference_direction()
        if reference_direction is None:
            return None
        return lateral_reference_direction(
            reference_direction,
            side_key,
            self.current_image_node(),
        )

    def _seed_line_half_length(self, anchor_point: Any=None) -> float:
        """Choose a readable seeded-line half length, matching the existing derived-axis scale."""

        fallback_points = [as_array(anchor_point)] if anchor_point is not None else []
        span = self.logic._display_span(self.current_image_node(), fallback_points)
        return max(float(DEFAULT_CONSTRUCTION_LINE_LENGTH_SU), float(span) * 0.12)

    def _line_points_through(self, anchor_point: Any, direction: Any) -> list[Any]:
        """Return two endpoints for an editable helper line centered on an anatomical landmark."""

        direction = unit_vector(direction)
        if direction is None:
            return []
        anchor = as_array(anchor_point)
        half_length = self._seed_line_half_length(anchor)
        return [anchor - direction * half_length, anchor + direction * half_length]

    def _seed_role_if_empty(self, role: Any, points: Any) -> bool:
        """Pre-fill one empty markup role without overwriting existing user input."""

        if not points:
            return False
        node = self.logic.get_node(role, create_if_missing=True)
        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return False
        if node.GetNumberOfDefinedControlPoints() > 0:
            return False
        labels = self.logic._node_spec_for_role(role).get("labels", [])
        self.logic._set_named_points(
            node,
            [as_array(point) for point in points],
            labels,
        )
        self._make_seeded_markup_editable(node)
        return True

    def _make_seeded_markup_editable(self, node: Any) -> None:
        """Make a programmatically seeded user markup immediately draggable in slice views."""

        if node is None:
            return
        if hasattr(node, "SetSelectable"):
            node.SetSelectable(True)
        if hasattr(node, "SetLocked"):
            node.SetLocked(False)
        if hasattr(node, "SetNthControlPointLocked") and hasattr(node, "GetNumberOfControlPoints"):
            for point_index in range(node.GetNumberOfControlPoints()):
                node.SetNthControlPointLocked(point_index, False)
        node.SetDisplayVisibility(True)
        display_node = node.GetDisplayNode() if hasattr(node, "GetDisplayNode") else None
        if display_node is not None:
            if hasattr(display_node, "SetSelectable"):
                display_node.SetSelectable(True)
            if hasattr(display_node, "SetVisibility"):
                display_node.SetVisibility(True)
            if hasattr(display_node, "SetHandlesInteractive"):
                display_node.SetHandlesInteractive(False)
            if hasattr(display_node, "SetTranslationHandleVisibility"):
                display_node.SetTranslationHandleVisibility(False)
            if hasattr(display_node, "SetRotationHandleVisibility"):
                display_node.SetRotationHandleVisibility(False)
            if hasattr(display_node, "SetScaleHandleVisibility"):
                display_node.SetScaleHandleVisibility(False)
            if hasattr(display_node, "SetInteractionHandleScale"):
                display_node.SetInteractionHandleScale(0.0)
            if hasattr(display_node, "SetVisibility2D"):
                display_node.SetVisibility2D(True)

    def _queue_acetabular_angle_lateral_endpoint(self, base_role: str, side_key: Any) -> bool:
        """Use a known lateral sourcil as the second endpoint after the user places the base point."""

        lateral_sourcil = self._lateral_sourcil_point(side_key)
        if lateral_sourcil is None:
            return False
        role = self.logic.side_role(base_role, side_key)
        self._pending_auto_line_endpoint_map()[role] = as_array(lateral_sourcil)
        return True

    def _complete_pending_auto_line_endpoint(self, role: Any) -> bool:
        """Complete a one-point line using a queued anatomical endpoint."""

        if role is None:
            return False
        pending_endpoints = self._pending_auto_line_endpoint_map()
        lateral_endpoint = pending_endpoints.get(role)
        if lateral_endpoint is None:
            return False
        node = self.logic.get_node(role, create_if_missing=False)
        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            pending_endpoints.pop(role, None)
            return False
        points = self.logic._defined_points(node)
        if len(points) >= 2:
            pending_endpoints.pop(role, None)
            return False
        if len(points) != 1:
            return False
        base_point = points[0]
        if vector_length(as_array(lateral_endpoint) - as_array(base_point)) <= EPSILON:
            return False
        pending_endpoints.pop(role, None)
        labels = self.logic._node_spec_for_role(role).get("labels", [])
        self.logic._set_named_points(node, [base_point, lateral_endpoint], labels)
        self._make_seeded_markup_editable(node)
        return True

    def _seed_side_role_if_empty(self, base_role: str, side_key: Any, points: Any) -> bool:
        """Pre-fill one side-specific markup role without overwriting existing user input."""

        return self._seed_role_if_empty(self.logic.side_role(base_role, side_key), points)

    def _sharp_teardrop_point(self, side_key: Any) -> Any:
        """Infer the Sharp-angle teardrop point for the active side.

        Sharp stores the teardrop explicitly as its first endpoint. The acetabular-offset medial
        line passes through the teardrop, so its midpoint is the best available editable fallback
        when the offset line was generated from a teardrop seed.
        """

        point = self._first_side_point("sharpAngleLine", side_key)
        if point is not None:
            return point
        return self._line_midpoint("acetabularOffsetLineA", side_key)

    def _tonnis_medial_sourcil_point(self, side_key: Any) -> Any:
        """Infer the Tonnis medial-sourcil/base point for the active side."""

        return self._first_side_point("tonnisAngleLine", side_key)

    def _acetabular_angle_base_point(self, base_role: str, side_key: Any) -> Any:
        """Return the correct base landmark for one acetabular angle line role."""

        if base_role == "sharpAngleLine":
            return self._sharp_teardrop_point(side_key)
        if base_role == "tonnisAngleLine":
            return self._tonnis_medial_sourcil_point(side_key)
        return None

    def _lateral_sourcil_from_contour(self, side_key: Any) -> Any:
        """Infer the lateral sourcil from the lateral-most point of the sourcil contour."""

        points = self._side_role_points("acetabularRoofSourcil", side_key)
        if not points:
            return None
        lateral_direction = self._reference_lateral_direction(side_key)
        if lateral_direction is None:
            return None
        reference_points = self.logic.latest_results.get("referenceLine", {}).get("points", [])
        origin = reference_points[0] if reference_points else np.zeros(3, dtype=float)
        return max(
            points,
            key=lambda point: float(np.dot(as_array(point) - origin, lateral_direction)),
        )

    def _lateral_sourcil_point(self, side_key: Any) -> Any:
        """Infer the lateral sourcil/acetabular edge point from existing measurements."""

        explicit_candidates = [
            self._first_side_point("lceAnglePoint", side_key),
        ]
        for base_role in ["tonnisAngleLine", "sharpAngleLine"]:
            points = self._side_role_points(base_role, side_key)
            if len(points) >= 2:
                explicit_candidates.append(points[1])
        explicit_candidates.append(self._lateral_sourcil_from_contour(side_key))

        for candidate in explicit_candidates:
            if candidate is not None:
                return candidate
        return self._line_midpoint("extrusionIndexMiddleLine", side_key)

    def _femur_head_radius(self, side_key: Any) -> Any:
        """Return the fitted native femoral-head radius in scene units, if available."""

        side_results = self.logic.latest_results.get("sides", {}).get(side_key, {})
        femur_head = side_results.get("femurHead", {})
        diameter = femur_head.get("rawValue")
        if not femur_head.get("defined") or diameter is None or float(diameter) <= EPSILON:
            return None
        return 0.5 * float(diameter)

    def _femur_center_point(self, side_key: Any) -> Any:
        """Infer the native femoral-head center from fitted-center and derived LCE constructions."""

        side_results = self.logic.latest_results.get("sides", {}).get(side_key, {})
        femur_head = side_results.get("femurHead", {})
        if femur_head.get("defined") and femur_head.get("center") is not None:
            return femur_head["center"]

        for base_role in ["femurHeadCenter", "lceAngleRadialArm", "lceAngleVisual"]:
            point = self._first_side_point(base_role, side_key)
            if point is not None:
                return point
        return None

    def _seed_acetabular_angle_line(self, base_role: str, side_key: Any) -> bool:
        """Seed a Sharp/Tonnis-style measured arm from teardrop and lateral sourcil landmarks."""

        teardrop = self._acetabular_angle_base_point(base_role, side_key)
        lateral_sourcil = self._lateral_sourcil_point(side_key)
        if teardrop is None or lateral_sourcil is None:
            return False
        if vector_length(as_array(lateral_sourcil) - as_array(teardrop)) <= EPSILON:
            return False
        return self._seed_side_role_if_empty(base_role, side_key, [teardrop, lateral_sourcil])

    def _seed_lce_point(self, side_key: Any) -> bool:
        """Seed the LCE point from an already known lateral sourcil landmark."""

        lateral_sourcil = self._lateral_sourcil_point(side_key)
        if lateral_sourcil is None:
            return False
        return self._seed_side_role_if_empty("lceAnglePoint", side_key, [lateral_sourcil])

    def _seed_acetabular_offset_lines(self, side_key: Any) -> bool:
        """Seed acetabular-offset lines from teardrop and femoral-head center landmarks."""

        direction = self._reference_superior_direction()
        if direction is None:
            return False
        seeded = False
        teardrop = self._sharp_teardrop_point(side_key)
        if teardrop is not None:
            seeded = self._seed_side_role_if_empty(
                "acetabularOffsetLineA",
                side_key,
                self._line_points_through(teardrop, direction),
            ) or seeded
        femur_center = self._femur_center_point(side_key)
        if femur_center is not None:
            seeded = self._seed_side_role_if_empty(
                "acetabularOffsetLineB",
                side_key,
                self._line_points_through(femur_center, direction),
            ) or seeded
        return seeded

    def _seed_femoral_offset_line(self, side_key: Any) -> bool:
        """Seed the femoral-offset line through the fitted femoral-head center."""

        side_results = self.logic.latest_results.get("sides", {}).get(side_key, {})
        shaft_axis = side_results.get("femoralShaftAxis", {})
        direction = shaft_axis.get("direction")
        femur_center = self._femur_center_point(side_key)
        if not shaft_axis.get("defined") or direction is None or femur_center is None:
            return False
        return self._seed_side_role_if_empty(
            "femoralOffsetLine",
            side_key,
            self._line_points_through(femur_center, direction),
        )

    def _seed_extrusion_index_lines(self, side_key: Any) -> bool:
        """Seed FEI lines from the femoral-head circle and lateral sourcil when available."""

        offset_direction = self._reference_superior_direction()
        lateral_direction = self._reference_lateral_direction(side_key)
        if offset_direction is None:
            return False

        seeded = False
        femur_center = self._femur_center_point(side_key)
        femur_radius = self._femur_head_radius(side_key)
        if femur_center is not None and femur_radius is not None and lateral_direction is not None:
            center = as_array(femur_center)
            medial_anchor = center - lateral_direction * femur_radius
            lateral_anchor = center + lateral_direction * femur_radius
            seeded = self._seed_side_role_if_empty(
                "extrusionIndexMedialLine",
                side_key,
                self._line_points_through(medial_anchor, offset_direction),
            ) or seeded
            seeded = self._seed_side_role_if_empty(
                "extrusionIndexLateralLine",
                side_key,
                self._line_points_through(lateral_anchor, offset_direction),
            ) or seeded

        lateral_sourcil = self._lateral_sourcil_point(side_key)
        if lateral_sourcil is not None:
            seeded = self._seed_side_role_if_empty(
                "extrusionIndexMiddleLine",
                side_key,
                self._line_points_through(lateral_sourcil, offset_direction),
            ) or seeded
        return seeded

    def _clear_workflow_if_removed_roles(self, roles: Any) -> None:
        """Abort the active workflow if its required scene nodes were removed. This protects the widget
        from continuing a placement sequence against stale MRML references.
        """

        if not roles:
            return
        if any(step.get("role") in roles for step in self.active_placement_queue):
            self.active_placement_queue = []
            self.active_placement_name = None
            self.active_placement_measurement_key = None
            self.active_placement_side_key = None
            self.logic.stop_placement_mode()
            self.instructions_label.setText(
                "Removed the last custom measurement. You can place a new one at any time."
        )

    def _add_other_point(self, start_placement: Any=True) -> Any:
        """Create and optionally start placement for one additional labelled custom point."""

        if not self._custom_measurement_can_add(MeasurementKey.OTHER_POINT):
            self.instructions_label.setText(
                "Finish placing the current custom point before adding another one."
            )
            self.refresh_ui()
            return False

        index, role = self.logic.create_other_point()
        self._set_case_dirty(True)
        self._observe_scene_and_nodes()
        instruction = f"Place point {index}. Its numbered label stays visible beside the point."
        if start_placement:
            self._start_workflow(
                f"Point {index}",
                [
                    {
                        "role": role,
                        "persistent": False,
                        "instruction": instruction,
                    }
                ],
                instruction,
                measurement_key=MeasurementKey.OTHER_POINT,
            )
        else:
            self.logic.update_all_derived_measurements(self.current_image_node())
            self.refresh_ui()
        return True

    def _add_other_line(self, start_placement: Any=True) -> Any:
        """Create and optionally start placement for one additional ad hoc line. Repeated tools are
        added explicitly so users can build arbitrary supplementary measurements without overwriting
        prior ones.
        """

        if not self._custom_measurement_can_add(MeasurementKey.OTHER_LINE):
            self.instructions_label.setText(
                "Finish placing the current custom line before adding another one."
            )
            self.refresh_ui()
            return False
        lock_mode = self._selected_reference_lock_mode(
            self.other_line_parallel_check,
            self.other_line_perpendicular_check,
        )
        if lock_mode != OtherAngleLockMode.NONE and not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before creating a line with a reference-locked orientation.")
            return False

        index, role = self.logic.create_other_line(lock_mode)
        self._set_case_dirty(True)
        self._observe_scene_and_nodes()
        if lock_mode == OtherAngleLockMode.PARALLEL:
            instruction = (
                f"Draw line {index}. Its orientation stays parallel to the reference line while its "
                "length and position remain editable."
            )
        elif lock_mode == OtherAngleLockMode.PERPENDICULAR:
            instruction = (
                f"Draw line {index}. Its orientation stays perpendicular to the reference line while "
                "its length and position remain editable."
            )
        else:
            instruction = f"Draw line {index}. Its length updates automatically."
        if start_placement:
            self._start_workflow(
                f"Line {index}",
                [
                    {
                        "role": role,
                        "persistent": False,
                        "instruction": instruction,
                    }
                ],
                instruction,
                measurement_key=MeasurementKey.OTHER_LINE,
            )
        else:
            self.logic.update_all_derived_measurements(self.current_image_node())
            self.refresh_ui()
        return True

    def _add_other_angle(self, start_placement: Any=True) -> Any:
        """Create and optionally start placement for one additional ad hoc angle. Lock mode is captured
        at creation time so each custom angle remembers the intended construction rule.
        """

        if not self._custom_measurement_can_add(MeasurementKey.OTHER_ANGLE):
            self.instructions_label.setText(
                "Finish placing the current custom angle before adding another one."
            )
            self.refresh_ui()
            return False
        lock_mode = self._selected_reference_lock_mode(
            self.other_angle_parallel_check,
            self.other_angle_perpendicular_check,
        )
        if lock_mode != OtherAngleLockMode.NONE and not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before creating an angle with a reference-locked arm.")
            return False

        index, points_role, _reference_role, _free_arm_role = self.logic.create_other_angle(lock_mode)
        self._set_case_dirty(True)
        self._observe_scene_and_nodes()
        if lock_mode == OtherAngleLockMode.PARALLEL:
            instruction = (
                f"Place angle {index}: first the reference-parallel arm point, "
                "then the vertex, then the free arm point."
            )
        elif lock_mode == OtherAngleLockMode.PERPENDICULAR:
            instruction = (
                f"Place angle {index}: first the reference-perpendicular arm "
                "point, then the vertex, then the free arm point."
            )
        else:
            instruction = (
                f"Place angle {index}: first arm point, then the vertex, then the second arm point."
            )
        if start_placement:
            self._start_workflow(
                f"Angle {index}",
                [
                    {
                        "role": points_role,
                        "persistent": True,
                        "instruction": instruction,
                    }
                ],
                instruction,
                measurement_key=MeasurementKey.OTHER_ANGLE,
            )
        else:
            self.logic.update_all_derived_measurements(self.current_image_node())
            self.refresh_ui()
        return True

    def _toggle_edge_contour_placement(
        self,
        measurement_key: Any,
        base_role: str,
        contour_name: str,
    ) -> None:
        """Start, restart, or pause one named edge-attracted anatomy contour."""

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        role = self.logic.side_role(base_role, side_key)
        side_contour_name = f"{side_label} {contour_name}"
        if (
            self.active_placement_measurement_key == measurement_key
            and self.active_placement_side_key == side_key
            and self.active_placement_name == side_contour_name
            and not self.active_placement_queue
        ):
            self.active_placement_name = None
            self.active_placement_measurement_key = None
            self.active_placement_side_key = None
            self.active_femoral_shaft_contour_step_index = None
            self.logic.stop_placement_mode()
            self.instructions_label.setText(
                f"{side_contour_name} placement paused. Click the button again to redraw the contour."
            )
            self.logic.update_all_derived_measurements(self.current_image_node())
            self.refresh_ui()
            return

        self.logic.reset_roles([role], self.current_image_node())
        node = self.logic.get_node(role, create_if_missing=True)
        node.SetDisplayVisibility(True)
        self._set_case_dirty(True)
        self.logic.set_measurement_visible(measurement_key, True, side_key)
        self.active_placement_name = side_contour_name
        self.active_placement_measurement_key = measurement_key
        self.active_placement_side_key = side_key
        self.active_femoral_shaft_contour_step_index = None
        self.active_placement_queue = []
        self.instructions_label.setText(
            f"Place points along the {side_contour_name.lower()}. Points snap locally toward strong image edges; "
            "click the button again when finished."
        )
        self.logic.activate_placement(node, persistent=True)
        self.logic.update_all_derived_measurements(self.current_image_node())
        node.SetDisplayVisibility(True)
        self.refresh_ui()

    def _femoral_shaft_contour_role(self, side_key: Any, step_index: int) -> Any:
        """Return the side-specific role for one femoral-shaft contour placement step."""

        return self.logic.side_role(FEMORAL_SHAFT_CONTOUR_BASE_ROLES[int(step_index)], side_key)

    def _femoral_shaft_contour_instruction(self, side_label: str, step_index: int) -> str:
        """Return the user instruction for one femoral-shaft contour placement step."""

        contour_number = int(step_index) + 1
        return (
            f"Place {side_label.lower()} femoral shaft contour {contour_number} of 4 with many "
            "points along the cortex. Right-click when this contour is finished; the tool will "
            "advance to the next contour automatically. Use any order for medial/lateral and "
            "inner/outer cortices."
        )

    def _femoral_shaft_contour_step_has_curve(self, side_key: Any, step_index: int) -> bool:
        """Return whether the current femoral-shaft contour has enough points to advance."""

        role = self._femoral_shaft_contour_role(side_key, step_index)
        node = self.logic.get_node(role, create_if_missing=False)
        return bool(node is not None and node.GetNumberOfDefinedControlPoints() >= 2)

    def _activate_femoral_shaft_contour_step(self, side_key: Any, step_index: int) -> None:
        """Activate placement for one of the four femoral-shaft contour curves."""

        side_label = SIDE_LABELS[side_key]
        role = self._femoral_shaft_contour_role(side_key, step_index)
        node = self.logic.get_node(role, create_if_missing=True)
        node.SetDisplayVisibility(True)
        self.active_placement_name = f"{side_label} Femoral Shaft Contour {step_index + 1}"
        self.active_placement_measurement_key = MeasurementKey.FEMORAL_SHAFT_CONTOUR
        self.active_placement_side_key = side_key
        self.active_femoral_shaft_contour_step_index = int(step_index)
        self.active_placement_queue = []
        self.instructions_label.setText(
            self._femoral_shaft_contour_instruction(side_label, step_index)
        )
        self.logic.activate_placement(node, persistent=True)
        self.logic.update_all_derived_measurements(self.current_image_node())
        node.SetDisplayVisibility(True)
        self.refresh_ui()

    def _advance_or_finish_femoral_shaft_contour(self, side_key: Any) -> None:
        """Advance the femoral-shaft contour stepper or finish and classify the four contours."""

        step_index = self.active_femoral_shaft_contour_step_index
        if step_index is None:
            return
        if not self._femoral_shaft_contour_step_has_curve(side_key, step_index):
            role = self._femoral_shaft_contour_role(side_key, step_index)
            node = self.logic.get_node(role, create_if_missing=True)
            self.logic.activate_placement(node, persistent=True)
            self.instructions_label.setText(
                "Place at least two points, preferably several along the cortex, then right-click "
                "to finish this femoral shaft contour."
            )
            self.refresh_ui()
            return

        next_step_index = int(step_index) + 1
        if next_step_index < len(FEMORAL_SHAFT_CONTOUR_BASE_ROLES):
            self._activate_femoral_shaft_contour_step(side_key, next_step_index)
            return

        self.active_placement_name = None
        self.active_placement_measurement_key = None
        self.active_placement_side_key = None
        self.active_femoral_shaft_contour_step_index = None
        self.logic.stop_placement_mode()
        results = self.logic.update_all_derived_measurements(self.current_image_node())
        side_results = results["sides"][side_key]
        if side_results["femoralShaftContours"]["defined"]:
            self.instructions_label.setText(
                "Femoral Shaft contours complete. The four curves were classified as medial/lateral "
                "and inner/outer from their coordinates."
            )
        else:
            self.instructions_label.setText(
                "Femoral Shaft contour placement stopped. Add at least two points to each of the four "
                "contours to classify them."
            )
        self.refresh_ui()

    def on_femoral_shaft_contour_clicked(self, _checked: Any=False) -> None:
        """Start or advance the four-curve femoral shaft contour workflow for the selected side."""

        side_key = self.current_side_key()
        if (
            self.active_placement_measurement_key == MeasurementKey.FEMORAL_SHAFT_CONTOUR
            and self.active_placement_side_key == side_key
            and self.active_femoral_shaft_contour_step_index is not None
        ):
            self._advance_or_finish_femoral_shaft_contour(side_key)
            return

        contour_roles = [
            self.logic.side_role(base_role, side_key)
            for base_role in FEMORAL_SHAFT_CONTOUR_BASE_ROLES
        ]
        self.logic.reset_roles(contour_roles, self.current_image_node())
        self._set_case_dirty(True)
        self.logic.set_measurement_visible(MeasurementKey.FEMORAL_SHAFT_CONTOUR, True, side_key)
        self._activate_femoral_shaft_contour_step(side_key, 0)

    def on_other_line_parallel_toggled(self, checked: Any) -> None:
        """Handle changes to Other Line Parallel."""

        self._sync_reference_lock_checkboxes(
            self.other_line_parallel_check,
            self.other_line_perpendicular_check,
            checked,
        )

    def on_other_line_perpendicular_toggled(self, checked: Any) -> None:
        """Handle changes to Other Line Perpendicular."""

        self._sync_reference_lock_checkboxes(
            self.other_line_perpendicular_check,
            self.other_line_parallel_check,
            checked,
        )

    def on_other_angle_parallel_toggled(self, checked: Any) -> None:
        """Handle changes to Other Angle Parallel. Small UI event handlers stay intentionally thin so
        the actual measurement rules remain centralized in the logic layer.
        """

        self._sync_reference_lock_checkboxes(
            self.other_angle_parallel_check,
            self.other_angle_perpendicular_check,
            checked,
        )

    def on_other_angle_perpendicular_toggled(self, checked: Any) -> None:
        """Handle changes to Other Angle Perpendicular. Small UI event handlers stay intentionally thin
        so the actual measurement rules remain centralized in the logic layer.
        """

        self._sync_reference_lock_checkboxes(
            self.other_angle_perpendicular_check,
            self.other_angle_parallel_check,
            checked,
        )

    def _remove_last_other_line(self) -> None:
        """Remove the most recently added ad hoc line. Last-in removal keeps the numbered custom-
        measurement workflow simple and predictable.
        """

        removed_roles = self.logic.remove_last_other_line()
        if not removed_roles:
            return
        self._set_case_dirty(True)
        self._clear_workflow_if_removed_roles(removed_roles)
        self._observe_scene_and_nodes()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def _remove_last_other_point(self) -> None:
        """Remove the most recently added labelled custom point."""

        removed_roles = self.logic.remove_last_other_point()
        if not removed_roles:
            return
        self._set_case_dirty(True)
        self._clear_workflow_if_removed_roles(removed_roles)
        self._observe_scene_and_nodes()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def _remove_last_other_angle(self) -> None:
        """Remove the most recently added ad hoc angle and its derived arms. Removing the full bundle
        together prevents orphaned helper geometry.
        """

        removed_roles = self.logic.remove_last_other_angle()
        if not removed_roles:
            return
        self._set_case_dirty(True)
        self._clear_workflow_if_removed_roles(removed_roles)
        self._observe_scene_and_nodes()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_other_line_count_changed(self, value: Any) -> None:
        """Handle changes to Other Line Count. Small UI event handlers stay intentionally thin so the
        actual measurement rules remain centralized in the logic layer.
        """

        current_count = self.logic.other_line_count()
        target_count = int(value)
        if target_count == current_count:
            return
        allowed_target = current_count + (1 if self._custom_measurement_can_add(MeasurementKey.OTHER_LINE) else 0)
        if target_count > allowed_target:
            self.refresh_ui()
            return
        if target_count > current_count:
            additions = target_count - current_count
            for addition_index in range(additions):
                created = self._add_other_line(start_placement=addition_index == additions - 1)
                if not created:
                    self.refresh_ui()
                    return
        else:
            for _ in range(current_count - target_count):
                self._remove_last_other_line()

    def on_other_point_count_changed(self, value: Any) -> None:
        """Handle changes to the custom Point count."""

        current_count = self.logic.other_point_count()
        target_count = int(value)
        if target_count == current_count:
            return
        allowed_target = current_count + (1 if self._custom_measurement_can_add(MeasurementKey.OTHER_POINT) else 0)
        if target_count > allowed_target:
            self.refresh_ui()
            return
        if target_count > current_count:
            additions = target_count - current_count
            for addition_index in range(additions):
                created = self._add_other_point(start_placement=addition_index == additions - 1)
                if not created:
                    self.refresh_ui()
                    return
        else:
            for _ in range(current_count - target_count):
                self._remove_last_other_point()

    def on_other_angle_count_changed(self, value: Any) -> None:
        """Handle changes to Other Angle Count. Small UI event handlers stay intentionally thin so the
        actual measurement rules remain centralized in the logic layer.
        """

        current_count = self.logic.other_angle_count()
        target_count = int(value)
        if target_count == current_count:
            return
        allowed_target = current_count + (1 if self._custom_measurement_can_add(MeasurementKey.OTHER_ANGLE) else 0)
        if target_count > allowed_target:
            self.refresh_ui()
            return
        if target_count > current_count:
            additions = target_count - current_count
            for addition_index in range(additions):
                created = self._add_other_angle(start_placement=addition_index == additions - 1)
                if not created:
                    self.refresh_ui()
                    return
        else:
            for _ in range(current_count - target_count):
                self._remove_last_other_angle()

    def on_measurement_visibility_toggled(self, measurement_key: Any, checked: Any) -> None:
        """Store a hide-or-show preference for one measurement family. Visibility is tracked
        independently from the numeric result so users can declutter the image without deleting
        work.
        """

        self.logic.set_measurement_visible(
            measurement_key,
            not bool(checked),
            self._measurement_side_key(measurement_key),
        )
        self.refresh_ui()

    def _warn(self, message: Any) -> None:
        """Show a short warning message to the user. Warnings are kept lightweight so the UI stays
        informative without interrupting the workflow.
        """

        self.instructions_label.setText(message)
        slicer.util.warningDisplay(message, windowTitle="Pelvic Xray Measurements")

    def on_calibration_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Calibration workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        self.logic.reset_roles(["calibrationPoints", "calibrationCircle"], self.current_image_node())
        self._start_workflow(
            "Calibration Ball",
            [
                {
                    "role": "calibrationPoints",
                    "persistent": True,
                    "instruction": (
                        "Place 3 points on the edge of the "
                        f"{self.logic.calibration_ball_diameter_mm:.1f} mm "
                        "calibration ball."
                    ),
                }
            ],
            (
                "Place 3 points on the edge of the "
                f"{self.logic.calibration_ball_diameter_mm:.1f} mm calibration ball."
            ),
            measurement_key=MeasurementKey.CALIBRATION,
        )

    def on_reference_line_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Reference Line workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        self.logic.reset_roles(["referenceLine"], self.current_image_node())
        self._start_workflow(
            "Reference Line",
            [
                {
                    "role": "referenceLine",
                    "persistent": False,
                    "instruction": (
                        "Draw the pelvic reference line at the level of the teardrops whenever feasible. "
                        "This also improves automatic point suggestions."
                    ),
                }
            ],
            ("Draw the pelvic reference line at the level of the teardrops whenever feasible. "
             "An ischial-tuberosity-level line may make automatic point placement inaccurate."),
            measurement_key=MeasurementKey.REFERENCE_LINE,
        )

    def on_tonnis_angle_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Acetabular Index (Tönnis) workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the Acetabular Index (Tönnis) measurement.")
            return

        had_measurement_points = self._side_roles_have_defined_points(["tonnisAngleLine"], side_key)
        self.logic.reset_roles(
            self.logic.side_roles(
                ["tonnisAngleLine", "tonnisAngleReferenceArm"],
                side_key,
            ),
            self.current_image_node(),
        )
        auto_lateral_endpoint = False
        if not had_measurement_points:
            if not self._seed_acetabular_angle_line("tonnisAngleLine", side_key):
                auto_lateral_endpoint = self._queue_acetabular_angle_lateral_endpoint(
                    "tonnisAngleLine",
                    side_key,
                )
        if auto_lateral_endpoint:
            instruction = (
                f"Place the {side_label.lower()} Acetabular Index (Tönnis) medial sourcil/base point. "
                "The lateral sourcil is already available and will be added automatically."
            )
        else:
            instruction = (
                f"Place the {side_label.lower()} Acetabular Index (Tönnis) "
                "medial/base point first, then the lateral point. "
                "The reference arm stays parallel to the reference "
                "line, and the angle is positive above the reference "
                "arm and negative below it."
            )
        self._start_workflow(
            f"{side_label} Acetabular Index (Tönnis)",
            [
                {
                    "role": self.logic.side_role("tonnisAngleLine", side_key),
                    "persistent": False,
                    "instruction": instruction,
                }
            ],
            instruction,
            measurement_key=MeasurementKey.TONNIS_ANGLE,
            side_key=side_key,
        )

    def on_sharp_angle_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Sharp Angle workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the Sharp angle measurement.")
            return

        had_measurement_points = self._side_roles_have_defined_points(["sharpAngleLine"], side_key)
        self.logic.reset_roles(
            self.logic.side_roles(
                ["sharpAngleLine", "sharpAngleReferenceArm"],
                side_key,
            ),
            self.current_image_node(),
        )
        auto_lateral_endpoint = False
        if not had_measurement_points:
            if not self._seed_acetabular_angle_line("sharpAngleLine", side_key):
                auto_lateral_endpoint = self._queue_acetabular_angle_lateral_endpoint(
                    "sharpAngleLine",
                    side_key,
                )
        if auto_lateral_endpoint:
            instruction = (
                f"Place the {side_label.lower()} Sharp angle teardrop/base point. "
                "The lateral sourcil is already available and will be added automatically."
            )
        else:
            instruction = (
                f"Place the {side_label.lower()} Sharp angle "
                "teardrop/base point first, then the lateral "
                "acetabular point. The reference arm stays parallel to "
                "the reference line, with positive values above it and "
                "negative values below it."
            )
        self._start_workflow(
            f"{side_label} Sharp Angle",
            [
                {
                    "role": self.logic.side_role("sharpAngleLine", side_key),
                    "persistent": False,
                    "instruction": instruction,
                }
            ],
            instruction,
            measurement_key=MeasurementKey.SHARP_ANGLE,
            side_key=side_key,
        )

    def on_lce_angle_clicked(self, _checked: Any=False) -> None:
        """Start or restart the LCE Angle workflow. Each button acts as both an entry point and a reset
        shortcut so users can replace a measurement without hunting for separate delete commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the LCE angle measurement.")
            return
        if not side_results["femurHead"]["defined"]:
            self._warn("Define the femur head first so the LCE angle can use its center point.")
            return

        had_measurement_points = self._side_roles_have_defined_points(["lceAnglePoint"], side_key)
        self.logic.reset_roles(
            self.logic.side_roles(
                ["lceAnglePoint", "lceAngleVisual", "lceAngleRadialArm"],
                side_key,
            ),
            self.current_image_node(),
        )
        if not had_measurement_points:
            self._seed_lce_point(side_key)
        self._start_workflow(
            f"{side_label} LCE Angle",
            [
                {
                    "role": self.logic.side_role("lceAnglePoint", side_key),
                    "persistent": True,
                    "instruction": (
                        f"Place the {side_label.lower()} LCE angle point. "
                        "The angle uses the femur head center, a superior line "
                        "perpendicular to the reference line, and becomes "
                        "negative if the point lies medial to that line."
                    ),
                }
            ],
            f"Place the {side_label.lower()} LCE angle point.",
            measurement_key=MeasurementKey.LCE_ANGLE,
            side_key=side_key,
        )

    def on_femur_head_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Femur Head workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        self.logic.reset_roles(
            self.logic.side_roles(
                ["femurHeadPoints", "femurHeadCenter", "femurHeadCircle"],
                side_key,
            ),
            self.current_image_node(),
        )
        self._start_workflow(
            f"{side_label} Femur Head",
            [
                {
                    "role": self.logic.side_role("femurHeadPoints", side_key),
                    "persistent": True,
                    "instruction": (
                        f"Place 3 boundary points on the {side_label.lower()} femur head. "
                        "The fitted circle and center update automatically."
                    ),
                }
            ],
            f"Place 3 boundary points on the {side_label.lower()} femur head.",
            measurement_key=MeasurementKey.FEMUR_HEAD,
            side_key=side_key,
        )

    def on_shaft_axis_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Shaft Axis workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        self.logic.reset_roles(
            self.logic.side_roles(
                ["shaftGuideProximal", "shaftGuideDistal", "shaftAxis"],
                side_key,
            ),
            self.current_image_node(),
        )
        self._start_workflow(
            f"{side_label} Femoral Shaft Axis",
            [
                {
                    "role": self.logic.side_role("shaftGuideProximal", side_key),
                    "persistent": False,
                    "instruction": f"Draw the first {side_label.lower()} femoral shaft guide line.",
                },
                {
                    "role": self.logic.side_role("shaftGuideDistal", side_key),
                    "persistent": False,
                    "instruction": f"Draw the second {side_label.lower()} femoral shaft guide line.",
                },
            ],
            f"Draw the first {side_label.lower()} femoral shaft guide line.",
            measurement_key=MeasurementKey.SHAFT_AXIS,
            side_key=side_key,
        )

    def _axis_workflow_definition(
        self,
        measurement_key: Any,
        side_key: Any,
        side_label: Any,
    ) -> Any:
        """Build the current guided-placement definition for one neck-axis tool."""

        if measurement_key == MeasurementKey.IMPLANT_NECK_AXIS:
            return self._implant_neck_axis_workflow_definition(side_key, side_label)
        return self._femoral_neck_axis_workflow_definition(side_key, side_label)

    def _femoral_neck_axis_workflow_definition(self, side_key: Any, side_label: Any) -> Any:
        """Build the workflow steps for the femoral neck-axis tool."""

        lock_to_center = self.logic.axis_lock_to_center_enabled(
            MeasurementKey.NECK_AXIS,
            side_key,
        )
        use_single_guide = self.logic.axis_use_single_guide_enabled(
            MeasurementKey.NECK_AXIS,
            side_key,
        )
        proximal_instruction = f"Draw the first {side_label.lower()} femoral neck guide line."
        if use_single_guide and lock_to_center:
            proximal_instruction += (
                " The axis is derived from this single guide and stays locked to the femur head center."
            )
        elif use_single_guide:
            proximal_instruction += " The axis is derived from this single guide line."
        elif lock_to_center:
            proximal_instruction += (
                " The derived axis passes through the femur head center once both guides are defined."
            )
        else:
            proximal_instruction += " CCD angle updates automatically once both axes are defined."

        steps = [
            {
                "role": self.logic.side_role("neckGuideProximal", side_key),
                "persistent": False,
                "instruction": proximal_instruction,
            }
        ]
        if not use_single_guide:
            distal_instruction = f"Draw the second {side_label.lower()} femoral neck guide line."
            if lock_to_center:
                distal_instruction += (
                    " The derived axis passes through the femur head center and CCD angle updates automatically."
                )
            else:
                distal_instruction += " CCD angle updates automatically once both axes are defined."
            steps.append(
                {
                    "role": self.logic.side_role("neckGuideDistal", side_key),
                    "persistent": False,
                    "instruction": distal_instruction,
                }
            )
        return f"{side_label} Femoral Neck Axis", steps, proximal_instruction

    def _implant_neck_axis_workflow_definition(self, side_key: Any, side_label: Any) -> Any:
        """Build the workflow steps for the implant neck-axis tool."""

        lock_to_center = self.logic.axis_lock_to_center_enabled(
            MeasurementKey.IMPLANT_NECK_AXIS,
            side_key,
        )
        use_single_guide = self.logic.axis_use_single_guide_enabled(
            MeasurementKey.IMPLANT_NECK_AXIS,
            side_key,
        )
        proximal_instruction = f"Draw the {side_label.lower()} proximal implant neck guide line."
        if use_single_guide and lock_to_center:
            proximal_instruction += (
                " The axis is derived from this single guide and stays locked to the implant head center."
            )
        elif use_single_guide:
            proximal_instruction += " The axis is derived from this single guide line."
        elif lock_to_center:
            proximal_instruction += (
                " The derived axis passes through the implant head center once both guides are defined."
            )
        else:
            proximal_instruction += " The implant neck axis is derived from both guide lines."

        steps = [
            {
                "role": self.logic.side_role("implantNeckGuideProximal", side_key),
                "persistent": False,
                "instruction": proximal_instruction,
            }
        ]
        if not use_single_guide:
            distal_instruction = f"Draw the {side_label.lower()} distal implant neck guide line."
            if lock_to_center:
                distal_instruction += (
                    " The implant neck axis passes through the implant head "
                    "center and the implant-femoral CCD angle updates "
                    "automatically."
                )
            else:
                distal_instruction += (
                    " The implant neck axis and implant-femoral CCD angle update automatically."
                )
            steps.append(
                {
                    "role": self.logic.side_role("implantNeckGuideDistal", side_key),
                    "persistent": False,
                    "instruction": distal_instruction,
                }
            )
        return f"{side_label} Implant Neck Axis", steps, proximal_instruction

    def _sync_active_axis_workflow_if_editable(self, measurement_key: Any) -> None:
        """Refresh an active neck-axis workflow when its pre-placement mode changes."""

        side_key = self.current_side_key()
        if (
            self.active_placement_measurement_key != measurement_key
            or self.active_placement_side_key != side_key
            or not self.active_placement_queue
        ):
            return

        workflow_name, steps, _initial_message = self._axis_workflow_definition(
            measurement_key,
            side_key,
            self.current_side_label(),
        )
        first_role = steps[0]["role"]
        if self.active_placement_queue[0]["role"] != first_role:
            return

        guide_node = self.logic.get_node(first_role)
        if self._defined_point_count(guide_node) > 0:
            return

        self.active_placement_name = workflow_name
        self.active_placement_queue = list(steps)
        self._activate_current_step()

    def on_neck_axis_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Neck Axis workflow. Each button acts as both an entry point and a reset
        shortcut so users can replace a measurement without hunting for separate delete commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        lock_to_center = self.logic.axis_lock_to_center_enabled(MeasurementKey.NECK_AXIS, side_key)
        if lock_to_center and not side_results["femurHead"]["defined"]:
            self._warn(
                "Define the femur head first so the locked femoral neck axis can pass through its center."
            )
            return
        self.logic.reset_roles(
            self.logic.side_roles(
                ["neckGuideProximal", "neckGuideDistal", "neckAxis"], side_key
            ),
            self.current_image_node(),
        )
        workflow_name, steps, proximal_instruction = self._axis_workflow_definition(
            MeasurementKey.NECK_AXIS,
            side_key,
            side_label,
        )
        self._start_workflow(
            workflow_name,
            steps,
            proximal_instruction,
            measurement_key=MeasurementKey.NECK_AXIS,
            side_key=side_key,
        )

    def on_acetabular_offset_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Acetabular Offset workflow. Each button acts as both an entry point and
        a reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the acetabular offset.")
            return

        had_measurement_points = self._side_roles_have_defined_points(
            ["acetabularOffsetLineA", "acetabularOffsetLineB"],
            side_key,
        )
        self.logic.reset_roles(
            self.logic.side_roles(
                ["acetabularOffsetLineA", "acetabularOffsetLineB"],
                side_key,
            ),
            self.current_image_node(),
        )
        if not had_measurement_points:
            self._seed_acetabular_offset_lines(side_key)
        self._start_workflow(
            f"{side_label} Acetabular Offset",
            [
                {
                    "role": self.logic.side_role("acetabularOffsetLineA", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the first {side_label.lower()} acetabular offset line. "
                        "Its angle is locked perpendicular to the reference line."
                    ),
                },
                {
                    "role": self.logic.side_role("acetabularOffsetLineB", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the second {side_label.lower()} acetabular offset line. "
                        "Its angle is locked perpendicular to the reference line."
                    ),
                },
            ],
            f"Draw the first {side_label.lower()} acetabular offset line.",
            measurement_key=MeasurementKey.ACETABULAR_OFFSET,
            side_key=side_key,
        )

    def on_femoral_offset_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Femoral Offset workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        if not side_results["femoralShaftAxis"]["defined"]:
            self._warn("Define the femoral shaft axis before starting the femoral offset.")
            return

        had_measurement_points = self._side_roles_have_defined_points(["femoralOffsetLine"], side_key)
        self.logic.reset_roles(self.logic.side_roles(["femoralOffsetLine"], side_key), self.current_image_node())
        if not had_measurement_points:
            self._seed_femoral_offset_line(side_key)
        self._start_workflow(
            f"{side_label} Femoral Offset",
            [
                {
                    "role": self.logic.side_role("femoralOffsetLine", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the {side_label.lower()} femoral offset line. "
                        "It stays parallel to the femoral shaft axis."
                    ),
                }
            ],
            f"Draw the {side_label.lower()} femoral offset line.",
            measurement_key=MeasurementKey.FEMORAL_OFFSET,
            side_key=side_key,
        )

    def on_extrusion_index_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Extrusion Index workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the femoral head extrusion index.")
            return

        had_measurement_points = self._side_roles_have_defined_points(
            [
                "extrusionIndexMedialLine",
                "extrusionIndexMiddleLine",
                "extrusionIndexLateralLine",
            ],
            side_key,
        )
        self.logic.reset_roles(
            self.logic.side_roles(
                [
                    "extrusionIndexMedialLine",
                    "extrusionIndexMiddleLine",
                    "extrusionIndexLateralLine",
                ],
                side_key,
            ),
            self.current_image_node()
        )
        if not had_measurement_points:
            self._seed_extrusion_index_lines(side_key)
        self._start_workflow(
            f"{side_label} Femoral Head Extrusion Index",
            [
                {
                    "role": self.logic.side_role("extrusionIndexMedialLine", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the first {side_label.lower()} extrusion-index line at the most medial position. "
                        "It stays perpendicular to the reference line."
                    ),
                },
                {
                    "role": self.logic.side_role("extrusionIndexMiddleLine", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the second {side_label.lower()} extrusion-index line crossing the lateral sourcil. "
                        "It stays perpendicular to the reference line."
                    ),
                },
                {
                    "role": self.logic.side_role("extrusionIndexLateralLine", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the final {side_label.lower()} extrusion-index line tangent to "
                        "the lateral side of the femoral head. "
                        "It stays perpendicular to the reference line."
                    ),
                },
            ],
            f"Draw the first {side_label.lower()} extrusion-index line at the most medial position.",
            measurement_key=MeasurementKey.EXTRUSION_INDEX,
            side_key=side_key,
        )

    def on_femur_shaft_morphology_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Femur Shaft Morphology setup workflow. The geometry is calibrated and
        axis-based because its station distances are defined in centimetres from the lesser
        trochanter reference level.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        if not side_results["femoralShaftAxis"]["defined"]:
            self._warn("Define the femoral shaft axis before starting femur shaft morphology.")
            return
        if not self.logic.latest_results["calibration"]["defined"]:
            self._warn("Measure the calibration ball before starting femur shaft morphology.")
            return

        self.logic.reset_roles(
            self.logic.side_roles(
                [
                    "shaftMorphologyLTPoints",
                    "shaftMorphologyMidline",
                    "shaftMorphologyPoints",
                    "shaftMorphologyGuideLineA",
                    "shaftMorphologyGuideLineB",
                ],
                side_key,
            ),
            self.current_image_node()
        )
        self._start_workflow(
            f"{side_label} Femur Shaft Morphology",
            [
                {
                    "role": self.logic.side_role("shaftMorphologyLTPoints", side_key),
                    "persistent": True,
                    "instruction": (
                        f"Place two {side_label.lower()} points bracketing "
                        "the lesser trochanter, one above and one below it. "
                        "The calibrated shaft morphology guide points "
                        "will be generated automatically."
                    ),
                }
            ],
            (
                f"Place two {side_label.lower()} points bracketing the lesser "
                "trochanter, "
                "one above and one below it."
            ),
            measurement_key=MeasurementKey.FEMUR_SHAFT_MORPHOLOGY,
            side_key=side_key,
        )

    def on_lld_clicked(self, _checked: Any=False) -> None:
        """Start or restart the LLD workflow. Each button acts as both an entry point and a reset
        shortcut so users can replace a measurement without hunting for separate delete commands.
        """

        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the leg length discrepancy measurement.")
            return

        self.logic.reset_roles(
            [
                "lldPoints",
                "lldLeftProjection",
                "lldRightProjection",
                "lldLeftParallel",
                "lldRightParallel",
                "lldHeightDifference",
            ],
            self.current_image_node()
        )
        self._start_workflow(
            "Leg Length Discrepancy",
            [
                {
                    "role": "lldPoints",
                    "persistent": True,
                    "instruction": (
                        "Place the two minor trochanter points in any order. "
                        "Left and right are assigned automatically, and the "
                        "height difference is measured perpendicular to the "
                        "reference line."
                    ),
                }
            ],
            "Place the two minor trochanter points in any order.",
            measurement_key=MeasurementKey.LLD,
        )

    def on_implant_head_center_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Implant Head Center workflow. Each button acts as both an entry point
        and a reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        self.logic.reset_roles(
            self.logic.side_roles(
                ["implantHeadPoints", "implantHeadCenter", "implantHeadCircle"],
                side_key,
            ),
            self.current_image_node(),
        )
        self._start_workflow(
            f"{side_label} Implant Head Center",
            [
                {
                    "role": self.logic.side_role("implantHeadPoints", side_key),
                    "persistent": True,
                    "instruction": (
                        f"Place 3 boundary points on the {side_label.lower()} "
                        "implant head. "
                        "The fitted circle and center update automatically."
                    ),
                }
            ],
            (
                f"Place 3 boundary points on the {side_label.lower()} implant "
                "head."
            ),
            measurement_key=MeasurementKey.IMPLANT_HEAD,
            side_key=side_key,
        )

    def on_inclination_angle_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Inclination Angle workflow. Each button acts as both an entry point and
        a reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn(
                "Define the reference line before starting the acetabular inclination angle measurement."
            )
            return

        self.logic.reset_roles(
            self.logic.side_roles(["acetabularInclinationLine"], side_key),
            self.current_image_node(),
        )
        self._start_workflow(
            f"{side_label} Acetabular Inclination Angle (Free Hand)",
            [
                {
                    "role": self.logic.side_role("acetabularInclinationLine", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the {side_label.lower()} acetabular inclination line. "
                        "The angle to the reference line updates automatically."
                    ),
                }
            ],
            f"Draw the {side_label.lower()} acetabular inclination line.",
            measurement_key=MeasurementKey.INCLINATION_ANGLE,
            side_key=side_key,
        )

    def on_cup_opening_ellipse_fit_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Cup Opening Ellipse Fit workflow. Each button acts as both an entry
        point and a reset shortcut so users can replace a measurement without hunting for separate
        delete commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the cup opening ellipse fit.")
            return

        self.logic.reset_roles(
            self.logic.side_roles(
                [
                    "cupOpeningEllipsePoints",
                    "cupOpeningEllipse",
                    "cupOpeningEllipseMajorDiameter",
                    "cupOpeningEllipseMinorDiameter",
                ],
                side_key,
            ),
            self.current_image_node(),
        )
        self.logic.set_cup_opening_ellipse_control_source(side_key, "points")
        self._start_workflow(
            f"{side_label} Cup Opening Ellipse Fit",
            [
                {
                    "role": self.logic.side_role("cupOpeningEllipsePoints", side_key),
                    "persistent": True,
                    "instruction": (
                        f"Place 6 points along the {side_label.lower()} cup "
                        "opening ellipse. The fitted ellipse, major/minor "
                        "diameters, and ellipse-based angles update "
                        "automatically."
                    ),
                }
            ],
            f"Place 6 points along the {side_label.lower()} cup opening ellipse.",
            measurement_key=MeasurementKey.CUP_OPENING_ELLIPSE_FIT,
            side_key=side_key,
        )

    def on_implant_neck_axis_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Implant Neck Axis workflow. The tool mirrors the femoral neck axis
        workflow and supports the same side-specific single-guide and center-lock options.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        lock_to_center = self.logic.axis_lock_to_center_enabled(
            MeasurementKey.IMPLANT_NECK_AXIS,
            side_key,
        )
        if lock_to_center and not side_results["implantHead"]["defined"]:
            self._warn(
                "Define the implant head first so the locked implant neck axis can pass through its center."
            )
            return
        self.logic.reset_roles(
            self.logic.side_roles(
                [
                    "implantNeckGuideProximal",
                    "implantNeckGuideDistal",
                    "implantNeckAxis",
                ],
                side_key,
            ),
            self.current_image_node(),
        )
        workflow_name, steps, proximal_instruction = self._axis_workflow_definition(
            MeasurementKey.IMPLANT_NECK_AXIS,
            side_key,
            side_label,
        )
        self._start_workflow(
            workflow_name,
            steps,
            proximal_instruction,
            measurement_key=MeasurementKey.IMPLANT_NECK_AXIS,
            side_key=side_key,
        )

    def on_postop_acetabular_offset_clicked(self, _checked: Any=False) -> None:
        """Start or restart the post-op Acetabular Offset workflow. Each button acts as both an entry
        point and a reset shortcut so users can replace a measurement without hunting for separate
        delete commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        if not self.logic.latest_results["referenceLine"]["defined"]:
            self._warn("Define the reference line before starting the post-operative acetabular offset.")
            return

        self.logic.reset_roles(
            self.logic.side_roles(
                ["postOpAcetabularOffsetLineA", "postOpAcetabularOffsetLineB"],
                side_key,
            ),
            self.current_image_node(),
        )
        self._start_workflow(
            f"{side_label} Post-Op Acetabular Offset",
            [
                {
                    "role": self.logic.side_role("postOpAcetabularOffsetLineA", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the first {side_label.lower()} post-operative acetabular offset line. "
                        "Its angle is locked perpendicular to the reference line."
                    ),
                },
                {
                    "role": self.logic.side_role("postOpAcetabularOffsetLineB", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the second {side_label.lower()} post-operative acetabular offset line. "
                        "Its angle is locked perpendicular to the reference line."
                    ),
                },
            ],
            f"Draw the first {side_label.lower()} post-operative acetabular offset line.",
            measurement_key=MeasurementKey.POSTOP_ACETABULAR_OFFSET,
            side_key=side_key,
        )

    def on_postop_femoral_offset_clicked(self, _checked: Any=False) -> None:
        """Start or restart the post-op Femoral Offset workflow. Each button acts as both an entry
        point and a reset shortcut so users can replace a measurement without hunting for separate
        delete commands.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        if not side_results["femoralShaftAxis"]["defined"]:
            self._warn("Define the femoral shaft axis before starting the post-operative femoral offset.")
            return

        self.logic.reset_roles(self.logic.side_roles(["postOpFemoralOffsetLine"], side_key), self.current_image_node())
        self._start_workflow(
            f"{side_label} Post-Op Femoral Offset",
            [
                {
                    "role": self.logic.side_role("postOpFemoralOffsetLine", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the {side_label.lower()} post-operative femoral offset line. "
                        "It stays parallel to the femoral shaft axis."
                    ),
                }
            ],
            f"Draw the {side_label.lower()} post-operative femoral offset line.",
            measurement_key=MeasurementKey.POSTOP_FEMORAL_OFFSET,
            side_key=side_key,
        )

    def on_implant_alignment_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Stem Alignment workflow. The tool mirrors the shaft-axis workflow so
        the post-operative stem axis is derived from two guide lines instead of a single freehand
        line.
        """

        side_key = self.current_side_key()
        side_label = self.current_side_label()
        side_results = self.logic.latest_results["sides"][side_key]
        if not side_results["femoralShaftAxis"]["defined"]:
            self._warn("Define the femoral shaft axis before starting the stem alignment measurement.")
            return

        self.logic.reset_roles(
            self.logic.side_roles(
                ["implantAlignmentGuideProximal", "implantAlignmentGuideDistal", "implantAlignmentLine"],
                side_key,
            ),
            self.current_image_node(),
        )
        self._start_workflow(
            f"{side_label} Stem Alignment",
            [
                {
                    "role": self.logic.side_role("implantAlignmentGuideProximal", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the {side_label.lower()} proximal stem alignment guide line. "
                        "The stem axis is derived from both guide lines."
                    ),
                },
                {
                    "role": self.logic.side_role("implantAlignmentGuideDistal", side_key),
                    "persistent": False,
                    "instruction": (
                        f"Draw the {side_label.lower()} distal stem alignment guide line. "
                        "The stem alignment angle to the femoral shaft axis updates automatically."
                    ),
                }
            ],
            f"Draw the {side_label.lower()} proximal stem alignment guide line.",
            measurement_key=MeasurementKey.IMPLANT_ALIGNMENT,
            side_key=side_key,
        )

    def on_other_point_clicked(self, _checked: Any=False) -> None:
        """Start placement for a new labelled custom point."""

        self._add_other_point(start_placement=True)

    def on_other_line_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Other Line workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        self._add_other_line(start_placement=True)

    def on_other_angle_clicked(self, _checked: Any=False) -> None:
        """Start or restart the Other Angle workflow. Each button acts as both an entry point and a
        reset shortcut so users can replace a measurement without hunting for separate delete
        commands.
        """

        self._add_other_angle(start_placement=True)

    def on_iliopectineal_line_clicked(self, _checked: Any=False) -> None:
        """Start, restart, or pause the Iliopectineal Line contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.ILIOPECTINEAL_LINE,
            "iliopectinealLine",
            "Iliopectineal Line",
        )

    def on_ilioischial_line_clicked(self, _checked: Any=False) -> None:
        """Start, restart, or pause the Ilioischial Line contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.ILIOISCHIAL_LINE,
            "ilioischialLine",
            "Ilioischial Line",
        )

    def on_shenton_line_clicked(self, _checked: Any=False) -> None:
        """Start, restart, or pause the Shenton Line contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.SHENTON_LINE,
            "shentonLine",
            "Shenton Line",
        )

    def on_acetabular_roof_sourcil_clicked(self, _checked: Any=False) -> None:
        """Start, restart, or pause the Acetabular Roof (Sourcil) contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.ACETABULAR_ROOF_SOURCIL,
            "acetabularRoofSourcil",
            "Acetabular Roof (Sourcil)",
        )

    def on_anterior_acetabular_wall_clicked(self, _checked: Any=False) -> None:
        """Place or finish the active-side anterior wall using the shared contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.ANTERIOR_ACETABULAR_WALL,
            "anteriorAcetabularWall",
            "Anterior Acetabular Wall",
        )

    def on_posterior_acetabular_wall_clicked(self, _checked: Any=False) -> None:
        """Place or finish the active-side posterior wall using the shared contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.POSTERIOR_ACETABULAR_WALL,
            "posteriorAcetabularWall",
            "Posterior Acetabular Wall",
        )

    def on_linea_terminalis_clicked(self, _checked: Any=False) -> None:
        """Start, restart, or pause the Linea Terminalis contour workflow."""

        self._toggle_edge_contour_placement(
            MeasurementKey.LINEA_TERMINALIS,
            "lineaTerminalis",
            "Linea Terminalis",
        )

    def on_save_all_clicked(self, _checked: Any=False) -> None:
        """Handle the Export All button by producing MRB, CSV, and annotated-image outputs together."""

        self._save_all_exports()

    def on_save_all_and_load_next_clicked(self, _checked: Any=False) -> None:
        """Handle Export All / Load Next Image in one action for folder-driven review workflows."""

        export_info = self._save_all_exports()
        if export_info is not None:
            self._load_adjacent_folder_image(1)

    def on_save_scene_clicked(self, _checked: Any=False) -> None:
        """Handle the Export Scene button. Export actions are kept thin here so they all flow through
        the same conflict-handling, status, and error-reporting path.
        """

        export_info = self._run_export_action(
            "Export Scene",
            lambda parent_directory, image_node: [
                self.logic.default_scene_path(parent_directory, image_node)
            ],
            self.logic.save_scene,
            lambda export_info: f"Exported scene to {export_info['scenePath']}.",
        )
        if export_info is not None:
            self._mark_case_saved()

    def on_export_csv_clicked(self, _checked: Any=False) -> None:
        """Handle the Export CSV button. Export actions are kept thin here so they all flow through the
        same conflict-handling, status, and error-reporting path.
        """

        self._run_export_action(
            "Export CSV",
            self._csv_export_paths,
            self._export_csv_case,
            self._csv_export_success_message,
        )

    def on_export_image_clicked(self, _checked: Any=False) -> None:
        """Handle the Export Image button. Export actions are kept thin here so they all flow through
        the same conflict-handling, status, and error-reporting path.
        """

        self._run_export_action(
            "Export Image",
            lambda parent_directory, image_node: [
                self.logic.default_image_path(parent_directory, image_node)
            ],
            self._export_annotation_image,
            lambda export_info: f"Exported annotated image to {export_info['imagePath']}.",
        )
