"""MRML scene and node-management helpers for Pelvic X-ray Measurements.

This mixin owns how measurement roles map to Slicer nodes, how dynamic custom measurements are
created, and how visibility preferences are applied. It deliberately avoids measurement math.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import slicer
import vtk

from PelvicXrayMeasurementsConstants import (
    ANATOMY_EDGE_CONTOUR_MIN_EDGE_ZSCORE,
    ANATOMY_EDGE_CONTOUR_ROLES,
    ANATOMY_EDGE_CONTOUR_SNAP_RADIUS_PX,
    ANATOMY_EDGE_CONTOUR_SNAP_SIGMA_PX,
    AXIS_LOCK_TO_CENTER_ATTRIBUTE,
    AXIS_USE_SINGLE_GUIDE_ATTRIBUTE,
    CASE_COMMENTS_ATTRIBUTE,
    CASE_EXPORT_TIMESTAMP_ATTRIBUTE,
    DEFAULT_CURVE_POINTS_PER_INTERPOLATING_SEGMENT,
    EPSILON,
    GLOBAL_MEASUREMENT_KEYS,
    LEGACY_CASE_COMMENTS_ATTRIBUTES,
    LEGACY_CASE_EXPORT_TIMESTAMP_ATTRIBUTES,
    LEGACY_ROLE_ATTRIBUTES,
    MEASUREMENT_ROLE_GROUPS,
    NECK_AXIS_MEASUREMENT_KEYS,
    OTHER_ANGLE_FREE_ARM_ROLE_PATTERN,
    OTHER_ANGLE_LOCK_ATTRIBUTE,
    OTHER_ANGLE_POINTS_ROLE_PATTERN,
    OTHER_ANGLE_REFERENCE_ARM_ROLE_PATTERN,
    OTHER_LINE_LOCK_ATTRIBUTE,
    OTHER_LINE_ROLE_PATTERN,
    OTHER_POINT_ROLE_PATTERN,
    ROLE_ATTRIBUTE,
    SIDE_KEYS,
    SIDE_MEASUREMENT_KEYS,
    MeasurementKey,
    OtherAngleLockMode,
)
from PelvicXrayMeasurementsNodeSpecs import (
    INPUT_NODE_ROLES,
    NODE_SPECS,
    other_angle_free_arm_role,
    other_angle_points_role,
    other_angle_reference_arm_role,
    other_line_role,
    other_point_role,
    side_role,
)


class SceneNodeMixin:
    """Provide scene and node-management behavior for the main logic class."""

    AXIS_OPTION_ROLE_MAP = {
        MeasurementKey.NECK_AXIS: str(MeasurementKey.NECK_AXIS),
        MeasurementKey.IMPLANT_NECK_AXIS: str(MeasurementKey.IMPLANT_NECK_AXIS),
    }

    def is_updating_measurements(self) -> Any:
        """Logic helper for is updating measurements. Encapsulating the step in its own method keeps
        the measurement pipeline readable and easier to audit.
        """

        return self._updating

    def side_role(self, base_role: Any, side_key: Any) -> Any:
        """Build the canonical MRML role name for one bilateral node. Using a deterministic side-
        prefixed role lets the logic find or recreate nodes safely across reloads and scene saves.
        """

        return side_role(side_key, base_role)

    def side_roles(self, base_roles: Any, side_key: Any) -> Any:
        """Logic helper for side roles. Encapsulating the step in its own method keeps the measurement
        pipeline readable and easier to audit.
        """

        return [self.side_role(base_role, side_key) for base_role in base_roles]

    def _axis_option_role(self, measurement_key: Any, side_key: Any) -> Any:
        """Return the persisted-axis-options role for one side-specific neck-axis measurement."""

        if side_key not in SIDE_KEYS:
            return None
        base_role = self.AXIS_OPTION_ROLE_MAP.get(measurement_key)
        if base_role is None:
            base_role = self.AXIS_OPTION_ROLE_MAP.get(str(measurement_key))
        if base_role is None:
            return None
        return self.side_role(base_role, side_key)

    def _axis_option_node(self, measurement_key: Any, side_key: Any) -> Any:
        """Return the axis node that stores persisted option attributes for one neck-axis tool."""

        role = self._axis_option_role(measurement_key, side_key)
        if role is None:
            return None
        return self.get_node(role, create_if_missing=True)

    def axis_lock_to_center_enabled(self, measurement_key: Any, side_key: Any) -> Any:
        """Return whether one neck-axis tool is configured to pass through its fitted head center."""

        node = self._axis_option_node(measurement_key, side_key)
        if node is None:
            return False
        value = node.GetAttribute(AXIS_LOCK_TO_CENTER_ATTRIBUTE)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def set_axis_lock_to_center_enabled(self, measurement_key: Any, side_key: Any, enabled: Any) -> None:
        """Persist whether one neck-axis tool should force its derived axis through the fitted center.

        The option is stored on the axis node itself so it survives MRB scene save/load cycles
        without introducing separate sidecar state.
        """

        node = self._axis_option_node(measurement_key, side_key)
        if node is None:
            return
        node.SetAttribute(AXIS_LOCK_TO_CENTER_ATTRIBUTE, "1" if enabled else "0")

    def axis_use_single_guide_enabled(self, measurement_key: Any, side_key: Any) -> Any:
        """Return whether one neck-axis tool should derive its axis from only the first guide line."""

        node = self._axis_option_node(measurement_key, side_key)
        if node is None:
            return False
        value = node.GetAttribute(AXIS_USE_SINGLE_GUIDE_ATTRIBUTE)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def set_axis_use_single_guide_enabled(self, measurement_key: Any, side_key: Any, enabled: Any) -> None:
        """Persist whether one neck-axis tool should use only a single guide line."""

        node = self._axis_option_node(measurement_key, side_key)
        if node is None:
            return
        node.SetAttribute(AXIS_USE_SINGLE_GUIDE_ATTRIBUTE, "1" if enabled else "0")

    def neck_axis_export_options(self) -> Any:
        """Return all side-specific femoral and implant neck-axis option flags for export/replay."""

        options = {}
        for measurement_key in NECK_AXIS_MEASUREMENT_KEYS:
            options[measurement_key] = {}
            for side_key in SIDE_KEYS:
                options[measurement_key][side_key] = {
                    "lockToCenter": self.axis_lock_to_center_enabled(measurement_key, side_key),
                    "useSingleGuide": self.axis_use_single_guide_enabled(measurement_key, side_key),
                }
        return options

    def set_calibration_ball_diameter_mm(self, value: Any) -> None:
        """Store the real-world calibration-ball diameter in millimetres. Calibration is handled in one
        place so every corrected measurement uses the same scale factor.
        """

        self.calibration_ball_diameter_mm = max(EPSILON, float(value))

    def set_calibration_ball_present(self, present: Any) -> None:
        """Store whether a calibration ball is present in the image. The explicit flag prevents
        accidental millimetre reporting when only scene units are valid.
        """

        self.calibration_ball_present = bool(present)

    def set_annotator_name(self, value: Any) -> None:
        """Store the current annotator name as session-scoped module state.

        The annotator is intentionally kept outside MRML scene content so closing the scene does not
        clear the field, while a full Slicer restart still resets it naturally.
        """

        self.annotator_name = str(value or "").strip()

    def case_comments(self) -> str:
        """Return the current case comments stored inside the MRML scene."""

        metadata_node = self.get_node("moduleMetadata", create_if_missing=False)
        if metadata_node is None:
            return ""
        for attribute_name in (CASE_COMMENTS_ATTRIBUTE, *LEGACY_CASE_COMMENTS_ATTRIBUTES):
            comments = str(metadata_node.GetAttribute(attribute_name) or "").strip()
            if comments:
                if attribute_name != CASE_COMMENTS_ATTRIBUTE:
                    metadata_node.SetAttribute(CASE_COMMENTS_ATTRIBUTE, comments)
                return comments
        return ""

    def set_case_comments(self, value: Any) -> None:
        """Store the current case comments inside the MRML scene.

        Comments are case-specific rather than session-scoped, so they travel with saved MRB scenes
        and reload when a previously saved case is reopened.
        """

        metadata_node = self.get_node("moduleMetadata", create_if_missing=True)
        if metadata_node is None:
            return
        metadata_node.SetAttribute(CASE_COMMENTS_ATTRIBUTE, str(value or "").strip())

    def case_export_timestamp(self) -> str:
        """Return the current case export timestamp stored inside the MRML scene."""

        metadata_node = self.get_node("moduleMetadata", create_if_missing=False)
        if metadata_node is None:
            return ""
        for attribute_name in (CASE_EXPORT_TIMESTAMP_ATTRIBUTE, *LEGACY_CASE_EXPORT_TIMESTAMP_ATTRIBUTES):
            timestamp = str(metadata_node.GetAttribute(attribute_name) or "").strip()
            if timestamp:
                if attribute_name != CASE_EXPORT_TIMESTAMP_ATTRIBUTE:
                    metadata_node.SetAttribute(CASE_EXPORT_TIMESTAMP_ATTRIBUTE, timestamp)
                return timestamp
        return ""

    def set_case_export_timestamp(self, value: Any) -> None:
        """Store the case export timestamp inside the MRML scene.

        The timestamp is treated as case-scoped export metadata so regenerated exports for the same
        saved case can preserve the originally recorded value.
        """

        metadata_node = self.get_node("moduleMetadata", create_if_missing=True)
        if metadata_node is None:
            return
        metadata_node.SetAttribute(CASE_EXPORT_TIMESTAMP_ATTRIBUTE, str(value or "").strip())

    def is_snapping_anatomy_curve_points(self) -> bool:
        """Return whether a contour snap operation is already moving markup points."""

        return bool(getattr(self, "_snapping_anatomy_curve_points", False))

    def snap_anatomy_curve_to_edges(self, role: Any, image_node: Any) -> bool:
        """Move named anatomy-contour control points toward nearby high-contrast image edges.

        Slicer markups do not expose a built-in edge-attracting curve placement mode. This method
        adds a local posterior-style snap: gradient magnitude is the edge likelihood and a Gaussian
        centered at the user's click is the spatial prior.
        """

        if not self._is_anatomy_edge_contour_role(role) or image_node is None:
            return False
        node = self.get_node(role, create_if_missing=False)
        if node is None or not node.IsA("vtkMRMLMarkupsCurveNode"):
            return False

        image_array = self._edge_snap_image_array(image_node)
        if image_array is None:
            return False

        ras_to_ijk_matrix = vtk.vtkMatrix4x4()
        image_node.GetRASToIJKMatrix(ras_to_ijk_matrix)
        ijk_to_ras_matrix = vtk.vtkMatrix4x4()
        image_node.GetIJKToRASMatrix(ijk_to_ras_matrix)

        changed = False
        self._snapping_anatomy_curve_points = True
        modify_state = node.StartModify() if hasattr(node, "StartModify") else None
        try:
            for point_index in range(node.GetNumberOfControlPoints()):
                if not self._markup_control_point_is_defined(node, point_index):
                    continue
                current_point = self._markup_control_point_position(node, point_index)
                snapped_point = self._edge_snapped_ras_point(
                    current_point,
                    image_array,
                    ras_to_ijk_matrix,
                    ijk_to_ras_matrix,
                )
                if snapped_point is None:
                    continue
                if np.linalg.norm(snapped_point - current_point) <= EPSILON:
                    continue
                self._set_markup_control_point_position(node, point_index, snapped_point)
                changed = True
        finally:
            if modify_state is not None and hasattr(node, "EndModify"):
                node.EndModify(modify_state)
            self._snapping_anatomy_curve_points = False

        return changed

    def _is_anatomy_edge_contour_role(self, role: Any) -> bool:
        """Return whether one role is a side-specific anatomy edge-contour role."""

        return any(
            role == self.side_role(base_role, side_key)
            for side_key in SIDE_KEYS
            for base_role in ANATOMY_EDGE_CONTOUR_ROLES
        )

    def _edge_snap_image_array(self, image_node: Any) -> Any:
        """Return a scalar image array in Slicer's k-j-i order for edge snapping."""

        try:
            image_array = np.asarray(slicer.util.arrayFromVolume(image_node))
        except Exception:
            return None
        if image_array.size == 0:
            return None
        if image_array.ndim == 4:
            image_array = image_array[..., 0]
        if image_array.ndim == 2:
            image_array = image_array[np.newaxis, :, :]
        if image_array.ndim != 3:
            return None
        return image_array

    def _markup_control_point_is_defined(self, node: Any, point_index: int) -> bool:
        """Return whether one markup control point has a defined image position."""

        if not hasattr(node, "GetNthControlPointPositionStatus"):
            return True
        status = node.GetNthControlPointPositionStatus(point_index)
        defined_status = (
            slicer.vtkMRMLMarkupsNode.PositionDefined
            if hasattr(slicer, "vtkMRMLMarkupsNode")
            else status
        )
        return status == defined_status

    def _markup_control_point_position(self, node: Any, point_index: int) -> Any:
        """Return one markup control point as a NumPy RAS vector."""

        point = [0.0, 0.0, 0.0]
        if hasattr(node, "GetNthControlPointPositionWorld"):
            node.GetNthControlPointPositionWorld(point_index, point)
        else:
            node.GetNthControlPointPosition(point_index, point)
        return np.asarray(point, dtype=float)

    def _set_markup_control_point_position(self, node: Any, point_index: int, point: Any) -> None:
        """Set one markup control point in RAS coordinates."""

        if hasattr(node, "SetNthControlPointPositionWorld"):
            node.SetNthControlPointPositionWorld(
                point_index,
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )
        else:
            node.SetNthControlPointPosition(
                point_index,
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )

    def _matrix_multiply_point(self, matrix: Any, point: Any) -> Any:
        """Multiply a homogeneous 3D point by a VTK matrix and return xyz coordinates."""

        output_point = [0.0, 0.0, 0.0, 0.0]
        matrix.MultiplyPoint(
            [float(point[0]), float(point[1]), float(point[2]), 1.0],
            output_point,
        )
        weight = output_point[3] if abs(output_point[3]) > EPSILON else 1.0
        return np.asarray(output_point[:3], dtype=float) / weight

    def _edge_snapped_ras_point(
        self,
        ras_point: Any,
        image_array: Any,
        ras_to_ijk_matrix: Any,
        ijk_to_ras_matrix: Any,
    ) -> Any:
        """Return the best nearby edge point in RAS coordinates for one clicked point."""

        ijk_point = self._matrix_multiply_point(ras_to_ijk_matrix, ras_point)
        candidate = self._edge_snap_candidate_ijk(image_array, ijk_point)
        if candidate is None:
            return None
        return self._matrix_multiply_point(ijk_to_ras_matrix, candidate)

    def _edge_snap_candidate_ijk(self, image_array: Any, ijk_point: Any) -> Any:
        """Find the maximum local edge-posterior point around one continuous IJK coordinate."""

        depth, height, width = image_array.shape
        k_index = int(round(float(ijk_point[2])))
        if not (0 <= k_index < depth):
            return None

        radius = int(ANATOMY_EDGE_CONTOUR_SNAP_RADIUS_PX)
        center_i = int(round(float(ijk_point[0])))
        center_j = int(round(float(ijk_point[1])))
        i_min = max(1, center_i - radius)
        i_max = min(width - 2, center_i + radius)
        j_min = max(1, center_j - radius)
        j_max = min(height - 2, center_j + radius)
        if i_min > i_max or j_min > j_max:
            return None

        gradients = []
        candidates = []
        image_slice = image_array[k_index]
        for j_index in range(j_min, j_max + 1):
            for i_index in range(i_min, i_max + 1):
                gradient = self._edge_gradient_magnitude(image_slice, i_index, j_index)
                gradients.append(gradient)
                candidates.append((i_index, j_index, gradient))
        if not gradients:
            return None

        gradient_values = np.asarray(gradients, dtype=float)
        gradient_median = float(np.median(gradient_values))
        gradient_mad = float(np.median(np.abs(gradient_values - gradient_median)))
        gradient_scale = max(1.4826 * gradient_mad, EPSILON)
        minimum_edge = gradient_median + ANATOMY_EDGE_CONTOUR_MIN_EDGE_ZSCORE * gradient_scale
        sigma = max(float(ANATOMY_EDGE_CONTOUR_SNAP_SIGMA_PX), EPSILON)

        best_score = None
        best_candidate = None
        best_gradient = None
        for i_index, j_index, gradient in candidates:
            distance_squared = (float(i_index) - ijk_point[0]) ** 2 + (float(j_index) - ijk_point[1]) ** 2
            edge_zscore = (float(gradient) - gradient_median) / gradient_scale
            score = edge_zscore - distance_squared / (2.0 * sigma * sigma)
            if best_score is None or score > best_score:
                best_score = score
                best_candidate = (i_index, j_index)
                best_gradient = gradient

        if best_candidate is None or best_gradient is None or best_gradient < minimum_edge:
            return None

        return np.asarray(
            [float(best_candidate[0]), float(best_candidate[1]), float(ijk_point[2])],
            dtype=float,
        )

    def _edge_gradient_magnitude(self, image_slice: Any, i_index: int, j_index: int) -> float:
        """Return centered finite-difference gradient magnitude for one 2D pixel."""

        gx = float(image_slice[j_index, i_index + 1]) - float(image_slice[j_index, i_index - 1])
        gy = float(image_slice[j_index + 1, i_index]) - float(image_slice[j_index - 1, i_index])
        return float(np.hypot(gx, gy))

    def set_cup_opening_ellipse_control_source(self, side_key: Any, source: Any) -> None:
        """Remember which interaction source most recently controlled the cup ellipse. The state exists
        to keep future ellipse-edit logic explicit rather than inferred from side effects.
        """

        if side_key in SIDE_KEYS:
            self._cup_opening_ellipse_control_source[side_key] = str(source or "points")

    def note_cup_opening_ellipse_control_role(self, role: Any) -> None:
        """Update the remembered cup-ellipse control source from a modified node role. This converts
        raw MRML events into a semantic editing source the logic can reason about.
        """

        if not role:
            return
        for side_key in SIDE_KEYS:
            if role == self.side_role("cupOpeningEllipsePoints", side_key):
                self.set_cup_opening_ellipse_control_source(side_key, "points")
                return
            if role in (
                self.side_role("cupOpeningEllipseMajorDiameter", side_key),
                self.side_role("cupOpeningEllipseMinorDiameter", side_key),
            ):
                self.set_cup_opening_ellipse_control_source(side_key, "handles")
                return

    def _dynamic_node_specs(self) -> Any:
        """Return the per-logic registry for runtime-only custom-measurement specs.

        Repeatable ad hoc lines and angles need mutable specifications, but that state belongs to the
        current logic instance rather than the imported module-level base schema.
        """

        dynamic_specs = getattr(self, "_dynamic_node_spec_registry", None)
        if dynamic_specs is None:
            dynamic_specs = {}
            self._dynamic_node_spec_registry = dynamic_specs
        return dynamic_specs

    def _dynamic_other_roles_are_scene_synced(self) -> Any:
        """Return whether dynamic `Others` roles have been recovered from the current scene.

        Saved scenes may already contain numbered custom line and angle nodes before this logic
        instance creates any of its own cache entries. A one-time sync restores those roles without
        rescanning the full scene on every measurement update.
        """

        return bool(getattr(self, "_dynamic_other_roles_scene_synced", False))

    def _set_dynamic_other_roles_scene_synced(self, synced: Any) -> None:
        """Store whether the dynamic-role registry is synchronized with the current scene."""

        self._dynamic_other_roles_scene_synced = bool(synced)

    def _is_dynamic_other_role(self, role: Any) -> Any:
        """Return whether a role belongs to one of the repeatable custom `Others` tools."""

        if role is None:
            return False
        return bool(
            OTHER_LINE_ROLE_PATTERN.match(role)
            or OTHER_POINT_ROLE_PATTERN.match(role)
            or OTHER_ANGLE_POINTS_ROLE_PATTERN.match(role)
            or OTHER_ANGLE_REFERENCE_ARM_ROLE_PATTERN.match(role)
            or OTHER_ANGLE_FREE_ARM_ROLE_PATTERN.match(role)
        )

    def _ensure_dynamic_other_roles_loaded_from_scene(self) -> Any:
        """Recover dynamic `Others` roles from the MRML scene once per scene lifetime.

        The recovery scan is still needed so reopening a saved scene restores previously created
        numbered lines and angles, but it should not run during every recomputation cycle.
        """

        if self._dynamic_other_roles_are_scene_synced():
            return list(self._dynamic_node_specs().keys())

        roles = []
        for node_index in range(slicer.mrmlScene.GetNumberOfNodes()):
            node = slicer.mrmlScene.GetNthNode(node_index)
            if node is None:
                continue
            role = node.GetAttribute(ROLE_ATTRIBUTE)
            if not self._is_dynamic_other_role(role):
                continue
            self._ensure_dynamic_other_spec(role)
            roles.append(role)

        self._set_dynamic_other_roles_scene_synced(True)
        return sorted(set(roles))

    def _all_node_roles(self) -> Any:
        """Return every static and dynamic node role in the same effective order as before.

        Static declarative roles come first from the module schema, followed by runtime-discovered
        dynamic roles in their discovery or creation order.
        """

        self._ensure_dynamic_other_roles_loaded_from_scene()
        roles = list(NODE_SPECS.keys())
        roles.extend(self._dynamic_node_specs().keys())
        return roles

    def _node_spec_for_role(self, role: Any) -> Any:
        """Return the specification for one role from the static or runtime registry.

        Dynamic repeatable tools are resolved through a per-logic registry so callers can treat them
        exactly like built-in roles without mutating the imported module constant.
        """

        self._ensure_dynamic_other_spec(role)
        dynamic_spec = self._dynamic_node_specs().get(role)
        if dynamic_spec is not None:
            return dynamic_spec
        static_spec = NODE_SPECS.get(role)
        if static_spec is not None:
            return static_spec
        raise LookupError(f"Unknown measurement role: {role}")

    def _dynamic_other_spec_for_role(self, role: Any) -> Any:
        """Create a node specification for a numbered custom measurement role. Dynamic specs let the
        repeatable tools plug into the same node-management machinery as built-in tools.
        """

        line_match = OTHER_LINE_ROLE_PATTERN.match(role)
        if line_match:
            index = int(line_match.group(1))
            return {
                "className": "vtkMRMLMarkupsLineNode",
                "name": f"Hip Measurements - Line {index}",
                "color": (0.56, 0.74, 0.92),
                "labels": [f"Line_{index}_Start", f"Line_{index}_End"],
            }

        point_match = OTHER_POINT_ROLE_PATTERN.match(role)
        if point_match:
            index = int(point_match.group(1))
            return {
                "className": "vtkMRMLMarkupsFiducialNode",
                "name": f"Hip Measurements - Point {index}",
                "color": (0.68, 0.42, 0.88),
                "completionCount": 1,
                "labels": [f"Point_{index}"],
                "pointLabelsVisible": True,
            }

        angle_points_match = OTHER_ANGLE_POINTS_ROLE_PATTERN.match(role)
        if angle_points_match:
            index = int(angle_points_match.group(1))
            return {
                "className": "vtkMRMLMarkupsFiducialNode",
                "name": f"Hip Measurements - Angle {index} Points",
                "color": (0.96, 0.56, 0.18),
                "completionCount": 3,
                "labels": [f"Angle_{index}_ArmA", f"Angle_{index}_Vertex", f"Angle_{index}_ArmB"],
            }

        angle_reference_match = OTHER_ANGLE_REFERENCE_ARM_ROLE_PATTERN.match(role)
        if angle_reference_match:
            index = int(angle_reference_match.group(1))
            return {
                "className": "vtkMRMLMarkupsLineNode",
                "name": f"Hip Measurements - Angle {index} Reference Arm",
                "color": (0.96, 0.56, 0.18),
                "labels": [f"Angle_{index}_Reference_Start", f"Angle_{index}_Reference_End"],
                "locked": True,
            }

        angle_free_arm_match = OTHER_ANGLE_FREE_ARM_ROLE_PATTERN.match(role)
        if angle_free_arm_match:
            index = int(angle_free_arm_match.group(1))
            return {
                "className": "vtkMRMLMarkupsLineNode",
                "name": f"Hip Measurements - Angle {index} Free Arm",
                "color": (0.96, 0.56, 0.18),
                "labels": [f"Angle_{index}_FreeArm_Start", f"Angle_{index}_FreeArm_End"],
                "locked": True,
            }

        return None

    def _ensure_dynamic_other_spec(self, role: Any) -> Any:
        """Ensure that a dynamic node role has a specification entry. The logic can then treat dynamic
        and static roles uniformly.
        """

        if role in NODE_SPECS or role in self._dynamic_node_specs():
            return True
        dynamic_spec = self._dynamic_other_spec_for_role(role)
        if dynamic_spec is None:
            return False
        self._dynamic_node_specs()[role] = dynamic_spec
        return True

    def _dynamic_other_roles_from_scene(self) -> Any:
        """Discover repeatable line and angle roles already present in the scene. Scene scanning lets
        the module reopen saved cases without maintaining a separate registry file.
        """

        return self._ensure_dynamic_other_roles_loaded_from_scene()

    def other_line_indices(self) -> Any:
        """Return the sorted indices of all saved ad hoc lines. Index-based discovery keeps numbering
        stable across scene reloads.
        """

        indices = []
        for role in self._dynamic_other_roles_from_scene():
            match = OTHER_LINE_ROLE_PATTERN.match(role)
            if match:
                indices.append(int(match.group(1)))
        return sorted(set(indices))

    def other_point_indices(self) -> Any:
        """Return the sorted indices of all saved labelled custom points."""

        indices = []
        for role in self._dynamic_other_roles_from_scene():
            match = OTHER_POINT_ROLE_PATTERN.match(role)
            if match:
                indices.append(int(match.group(1)))
        return sorted(set(indices))

    def other_angle_indices(self) -> Any:
        """Return the sorted indices of all saved ad hoc angles. The indices drive both UI counters and
        export labelling.
        """

        indices = []
        for role in self._dynamic_other_roles_from_scene():
            match = OTHER_ANGLE_POINTS_ROLE_PATTERN.match(role)
            if match:
                indices.append(int(match.group(1)))
        return sorted(set(indices))

    def other_line_count(self) -> Any:
        """Return how many ad hoc lines currently exist. The count is derived from scene content so the
        UI cannot drift from reality.
        """

        return len(self.other_line_indices())

    def other_point_count(self) -> Any:
        """Return how many labelled custom points currently exist."""

        return len(self.other_point_indices())

    def other_angle_count(self) -> Any:
        """Return how many ad hoc angles currently exist. Like the line count, the value is derived
        from MRML state instead of stored separately.
        """

        return len(self.other_angle_indices())

    def other_line_roles(self) -> Any:
        """Return every role belonging to ad hoc line measurements. Role grouping keeps visibility and
        reset logic consistent with built-in tools.
        """

        return [other_line_role(index) for index in self.other_line_indices()]

    def other_point_roles(self) -> Any:
        """Return every role belonging to labelled custom point measurements."""

        return [other_point_role(index) for index in self.other_point_indices()]

    def other_angle_roles(self) -> Any:
        """Return every role belonging to ad hoc angle measurements. Grouped roles make cleanup and
        export code much simpler.
        """

        roles = []
        for index in self.other_angle_indices():
            roles.append(other_angle_points_role(index))
            roles.append(other_angle_reference_arm_role(index))
            roles.append(other_angle_free_arm_role(index))
        return roles

    def create_other_line(self, lock_mode: Any=OtherAngleLockMode.NONE) -> Any:
        """Create the next numbered ad hoc line node and make it visible. Numbering is monotonic so
        exported results and in-scene labels stay understandable.
        """

        next_index = max(self.other_line_indices(), default=0) + 1
        role = other_line_role(next_index)
        self._ensure_dynamic_other_spec(role)
        node = self.get_node(role, create_if_missing=True)
        node.SetAttribute(
            OTHER_LINE_LOCK_ATTRIBUTE,
            str(lock_mode or OtherAngleLockMode.NONE),
        )
        node.SetDisplayVisibility(True)
        return next_index, role

    def create_other_point(self) -> Any:
        """Create the next numbered labelled point node and make it visible."""

        next_index = max(self.other_point_indices(), default=0) + 1
        role = other_point_role(next_index)
        self._ensure_dynamic_other_spec(role)
        node = self.get_node(role, create_if_missing=True)
        node.SetDisplayVisibility(True)
        return next_index, role

    def create_other_angle(self, lock_mode: Any=OtherAngleLockMode.NONE) -> Any:
        """Create the next numbered ad hoc angle nodes and initialize their lock mode. The points and
        derived arms are created together so the angle behaves like one logical tool.
        """

        next_index = max(self.other_angle_indices(), default=0) + 1
        points_role = other_angle_points_role(next_index)
        reference_role = other_angle_reference_arm_role(next_index)
        free_arm_role = other_angle_free_arm_role(next_index)
        self._ensure_dynamic_other_spec(points_role)
        self._ensure_dynamic_other_spec(reference_role)
        self._ensure_dynamic_other_spec(free_arm_role)
        points_node = self.get_node(points_role, create_if_missing=True)
        points_node.SetAttribute(
            OTHER_ANGLE_LOCK_ATTRIBUTE,
            str(lock_mode or OtherAngleLockMode.NONE),
        )
        points_node.SetDisplayVisibility(True)
        reference_node = self.get_node(reference_role, create_if_missing=True)
        reference_node.SetDisplayVisibility(False)
        free_arm_node = self.get_node(free_arm_role, create_if_missing=True)
        free_arm_node.SetDisplayVisibility(False)
        return next_index, points_role, reference_role, free_arm_role

    def _remove_dynamic_role(self, role: Any) -> None:
        """Remove one dynamically created custom-measurement role from both scene and caches. Cleanup
        is centralized so dynamic tools do not leave stale bookkeeping behind.
        """

        self._ensure_dynamic_other_spec(role)
        node = self.get_node(role, create_if_missing=False)
        if node is not None:
            slicer.mrmlScene.RemoveNode(node)
        self._node_cache.pop(role, None)
        self._dynamic_node_specs().pop(role, None)

    def remove_last_other_line(self) -> Any:
        """Remove the highest-numbered ad hoc line. This matches the decrementing counter workflow
        exposed in the UI.
        """

        indices = self.other_line_indices()
        if not indices:
            return []
        role = other_line_role(indices[-1])
        self._remove_dynamic_role(role)
        return [role]

    def remove_last_other_point(self) -> Any:
        """Remove the highest-numbered labelled custom point."""

        indices = self.other_point_indices()
        if not indices:
            return []
        role = other_point_role(indices[-1])
        self._remove_dynamic_role(role)
        return [role]

    def remove_last_other_angle(self) -> Any:
        """Remove the highest-numbered ad hoc angle and both of its helper arms. The grouped removal
        preserves numbering semantics and avoids partial state.
        """

        indices = self.other_angle_indices()
        if not indices:
            return []
        last_index = indices[-1]
        roles = [
            other_angle_points_role(last_index),
            other_angle_reference_arm_role(last_index),
            other_angle_free_arm_role(last_index),
        ]
        for role in roles:
            self._remove_dynamic_role(role)
        return roles

    def clear_dynamic_other_specs(self) -> None:
        """Drop cached specifications for dynamically created custom tools. This is mainly used during
        scene transitions so the next scene can be reconstructed cleanly.
        """

        for role in self._dynamic_node_specs():
            self._node_cache.pop(role, None)
        self._dynamic_node_specs().clear()
        self._set_dynamic_other_roles_scene_synced(False)

    def clear_node_cache(self) -> None:
        """Forget cached node IDs so the next lookup adopts nodes from the current MRML scene.

        Manual MRB loads can replace the entire scene while the module panel is already open. Clearing
        the cache before the post-load adoption pass prevents stale or prematurely created placeholder
        nodes from hiding the saved annotations.
        """

        self._node_cache.clear()
        self._set_dynamic_other_roles_scene_synced(False)

    def _measurement_visibility_key(self, measurement_key: Any, side_key: Any=None) -> Any:
        """Build the dictionary key used for measurement visibility preferences. Side-aware keys are
        kept explicit so left and right visibility can differ safely.
        """

        if side_key is None or measurement_key in GLOBAL_MEASUREMENT_KEYS:
            return measurement_key
        return f"{measurement_key}:{side_key}"

    def measurement_visible(self, measurement_key: Any, side_key: Any=None) -> Any:
        """Return whether a measurement family should currently be shown. Visibility preferences are
        stored independently from node display state so they can be re-applied after updates.
        """

        visibility_key = self._measurement_visibility_key(measurement_key, side_key)
        return bool(self._measurement_visibility.get(visibility_key, True))

    def set_measurement_visible(self, measurement_key: Any, visible: Any, side_key: Any=None) -> None:
        """Store and immediately apply a measurement visibility preference. The setter applies the
        preference at once so the image responds without needing a full manual refresh.
        """

        visibility_key = self._measurement_visibility_key(measurement_key, side_key)
        self._measurement_visibility[visibility_key] = bool(visible)
        self.apply_measurement_visibility_preferences()

    def _measurement_roles(self, measurement_key: Any, side_key: Any=None) -> Any:
        """Return the MRML roles belonging to one logical measurement. Centralizing this mapping keeps
        visibility, reset, and export code aligned.
        """

        if measurement_key == MeasurementKey.OTHER_LINE:
            return self.other_line_roles()
        if measurement_key == MeasurementKey.OTHER_POINT:
            return self.other_point_roles()
        if measurement_key == MeasurementKey.OTHER_ANGLE:
            return self.other_angle_roles()
        base_roles = MEASUREMENT_ROLE_GROUPS.get(measurement_key, [])
        if measurement_key in GLOBAL_MEASUREMENT_KEYS:
            return list(base_roles)
        if side_key is None:
            return []
        return self.side_roles(base_roles, side_key)

    def _node_has_visible_content(self, node: Any) -> Any:
        """Check whether a node contains enough geometry to be worth displaying. This prevents empty
        placeholder nodes from cluttering the scene.
        """

        if node is None:
            return False
        if node.IsA("vtkMRMLMarkupsNode"):
            return node.GetNumberOfDefinedControlPoints() > 0
        if node.IsA("vtkMRMLModelNode"):
            poly_data = node.GetPolyData()
            return poly_data is not None and poly_data.GetNumberOfPoints() > 0
        return False

    def apply_measurement_visibility_preferences(self) -> None:
        """Apply stored visibility preferences to every measurement node. Visibility is recalculated
        after updates because derived helper nodes may appear or disappear as geometry changes.
        """

        self._apply_visibility_for_measurement_keys(GLOBAL_MEASUREMENT_KEYS)
        for side_key in SIDE_KEYS:
            self._apply_visibility_for_measurement_keys(SIDE_MEASUREMENT_KEYS, side_key)

    def _apply_visibility_for_measurement_keys(
        self,
        measurement_keys: Any,
        side_key: Any=None,
    ) -> None:
        """Apply stored visibility preferences to one set of global or side-specific measurements."""

        for measurement_key in measurement_keys:
            visible = self.measurement_visible(measurement_key, side_key)
            for role in self._measurement_roles(measurement_key, side_key):
                node = self.get_node(role, create_if_missing=True)
                node.SetDisplayVisibility(bool(visible and self._node_has_visible_content(node)))

    def ensure_nodes(self) -> None:
        """Ensure that all required MRML nodes for the module exist. Node creation is centralized so
        every workflow can assume its inputs and outputs are present.
        """

        for role in self._all_node_roles():
            self.get_node(role, create_if_missing=True)

    def observed_input_nodes(self) -> Any:
        """Return the input nodes whose edits should trigger live recomputation. The observer list
        intentionally excludes many derived nodes to keep updates responsive.
        """

        self.ensure_nodes()
        roles = list(INPUT_NODE_ROLES)
        roles.extend(self.other_line_roles())
        roles.extend(self.other_point_roles())
        roles.extend(other_angle_points_role(index) for index in self.other_angle_indices())
        return [self.get_node(role) for role in roles]

    def guess_default_image_node(self) -> Any:
        """Return the first available scalar volume as a default radiograph. This reduces setup
        friction in the common case of working with a single loaded image.
        """

        image_nodes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        for node in image_nodes:
            return node
        return None

    def _node_role_matches(self, node: Any, role: Any) -> bool:
        """Return whether one node carries the current or legacy module role attribute."""

        if node is None:
            return False
        if node.GetAttribute(ROLE_ATTRIBUTE) == role:
            return True
        for attribute_name in LEGACY_ROLE_ATTRIBUTES:
            if node.GetAttribute(attribute_name) == role:
                return True
        return False

    def _node_has_case_metadata(self, node: Any) -> bool:
        """Return whether one metadata node carries saved case-level text or export metadata."""

        if node is None:
            return False
        attribute_names = (
            CASE_COMMENTS_ATTRIBUTE,
            CASE_EXPORT_TIMESTAMP_ATTRIBUTE,
            *LEGACY_CASE_COMMENTS_ATTRIBUTES,
            *LEGACY_CASE_EXPORT_TIMESTAMP_ATTRIBUTES,
        )
        for attribute_name in attribute_names:
            if str(node.GetAttribute(attribute_name) or "").strip():
                return True
        return False

    def _preferred_node_for_role(self, nodes: Any, role: Any=None) -> Any:
        """Choose the best candidate when a scene contains duplicate nodes for one role."""

        if role == "moduleMetadata":
            for node in nodes:
                if self._node_has_case_metadata(node):
                    return node
        for node in nodes:
            if self._node_has_visible_content(node):
                return node
        return nodes[0] if nodes else None

    def get_node(self, role: Any, create_if_missing: Any=False) -> Any:
        """Return the MRML node for a logical role, optionally creating it. The role-based lookup
        decouples the measurement logic from scene-specific node IDs.
        """

        spec = self._node_spec_for_role(role)
        cached_node_id = self._node_cache.get(role)
        if cached_node_id:
            cached_node = slicer.mrmlScene.GetNodeByID(cached_node_id)
            if (
                cached_node is not None
                and self._node_role_matches(cached_node, role)
                and cached_node.GetClassName() == spec["className"]
            ):
                return cached_node
            self._node_cache.pop(role, None)

        matching_nodes = []
        mismatched_nodes = []
        for node_index in range(slicer.mrmlScene.GetNumberOfNodes()):
            node = slicer.mrmlScene.GetNthNode(node_index)
            if node and self._node_role_matches(node, role):
                if node.GetClassName() != spec["className"]:
                    mismatched_nodes.append(node)
                    continue
                matching_nodes.append(node)

        preferred_node = self._preferred_node_for_role(matching_nodes, role)
        if preferred_node is not None:
            self._configure_node(preferred_node, role)
            self._node_cache[role] = preferred_node.GetID()
            return preferred_node

        for node in mismatched_nodes:
            slicer.mrmlScene.RemoveNode(node)

        if not create_if_missing:
            return None

        node = slicer.mrmlScene.AddNewNodeByClass(spec["className"], spec["name"])
        node.SetAttribute(ROLE_ATTRIBUTE, role)
        self._configure_node(node, role)
        self._node_cache[role] = node.GetID()
        return node

    def _configure_node(self, node: Any, role: Any) -> None:
        """Apply naming, display, and label conventions to a node for a given role. Centralizing
        configuration keeps recreated or reloaded nodes consistent with freshly created ones.
        """

        spec = self._node_spec_for_role(role)
        node.SetName(spec["name"])
        if node.GetAttribute(ROLE_ATTRIBUTE) != role:
            node.SetAttribute(ROLE_ATTRIBUTE, role)
        if hasattr(node, "SetHideFromEditors"):
            node.SetHideFromEditors(bool(spec.get("hideFromEditors", False)))

        if node.IsA("vtkMRMLMarkupsNode"):
            self._configure_markup_node(node, spec)

        elif node.IsA("vtkMRMLModelNode"):
            self._configure_model_node(node, spec)

    def _apply_fixed_markup_point_count(self, node: Any, spec: Any) -> None:
        """Apply fixed control-point-count constraints to a markup node when requested."""

        if "fixedPointCount" not in spec:
            return
        fixed_point_count = int(spec["fixedPointCount"])
        if hasattr(node, "SetFixedNumberOfControlPoints"):
            node.SetFixedNumberOfControlPoints(True)
        if hasattr(node, "SetMaximumNumberOfControlPoints"):
            node.SetMaximumNumberOfControlPoints(fixed_point_count)
        if hasattr(node, "SetRequiredNumberOfControlPoints"):
            node.SetRequiredNumberOfControlPoints(fixed_point_count)

    def _configure_markup_node(self, node: Any, spec: Any) -> None:
        """Apply module-standard display and point-count settings to a markup node."""

        node.CreateDefaultDisplayNodes()
        self._apply_fixed_markup_point_count(node, spec)
        if node.IsA("vtkMRMLMarkupsCurveNode") and hasattr(
            node, "SetNumberOfPointsPerInterpolatingSegment"
        ):
            points_per_segment = int(
                spec.get(
                    "pointsPerInterpolatingSegment",
                    DEFAULT_CURVE_POINTS_PER_INTERPOLATING_SEGMENT,
                )
            )
            node.SetNumberOfPointsPerInterpolatingSegment(
                points_per_segment
            )
        node.SetLocked(bool(spec.get("locked", False)))
        self._configure_markup_display(
            node.GetDisplayNode(),
            spec["color"],
            point_labels_visible=bool(spec.get("pointLabelsVisible", False)),
        )
        display_node = node.GetDisplayNode()
        if display_node is not None and "glyphScale" in spec and hasattr(display_node, "SetGlyphScale"):
            display_node.SetGlyphScale(float(spec["glyphScale"]))
        if display_node is not None and "textScale" in spec and hasattr(display_node, "SetTextScale"):
            display_node.SetTextScale(float(spec["textScale"]))

    def _configure_model_node(self, node: Any, spec: Any) -> None:
        """Apply module-standard display settings to a model node."""

        node.CreateDefaultDisplayNodes()
        if hasattr(node, "SaveWithSceneOff"):
            # Every model node in this extension is derived from persisted markups and is recreated
            # during scene refresh, so skipping MRB serialization avoids fragile auxiliary VTK files
            # without changing what the user sees after reload.
            node.SaveWithSceneOff()
        self._configure_model_display(node.GetDisplayNode(), spec["color"])

    def _configure_markup_display(
        self,
        display_node: Any,
        color: Any,
        point_labels_visible: Any=False,
    ) -> None:
        """Apply the standard 2D markup display settings for this module. Interaction handles are
        intentionally suppressed where possible to keep radiograph views uncluttered.
        """

        if display_node is None:
            return
        display_node.SetColor(*color)
        if hasattr(display_node, "SetSelectedColor"):
            display_node.SetSelectedColor(*color)
        if hasattr(display_node, "SetVisibility2D"):
            display_node.SetVisibility2D(True)
        if hasattr(display_node, "SetVisibility3D"):
            display_node.SetVisibility3D(False)
        if hasattr(display_node, "SetPointLabelsVisibility"):
            display_node.SetPointLabelsVisibility(bool(point_labels_visible))
        if hasattr(display_node, "SetPropertiesLabelVisibility"):
            display_node.SetPropertiesLabelVisibility(False)
        if hasattr(display_node, "SetGlyphScale"):
            display_node.SetGlyphScale(1.4)
        if hasattr(display_node, "SetLineThickness"):
            display_node.SetLineThickness(0.25)
        if hasattr(display_node, "SetTextScale"):
            display_node.SetTextScale(1.0 if point_labels_visible else 0.0)
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

    def _configure_model_display(self, display_node: Any, color: Any) -> None:
        """Apply the standard model display settings for helper geometry. Slice-intersection display is
        used so 3D surfaces such as circles and ellipses can appear as 2D constructions in the x-ray
        views. The configuration prefers the current 2D visibility API so the module stays compatible
        with recent Slicer releases without changing how those helper models are shown.
        """

        if display_node is None:
            return
        display_node.SetColor(*color)
        if hasattr(display_node, "SetSelectedColor"):
            display_node.SetSelectedColor(*color)
        if hasattr(display_node, "SetSliceDisplayMode") and hasattr(
            slicer, "vtkMRMLModelDisplayNode"
        ):
            display_node.SetSliceDisplayMode(
                slicer.vtkMRMLModelDisplayNode.SliceDisplayIntersection
            )
        if hasattr(display_node, "SetVisibility2D"):
            display_node.SetVisibility2D(True)
        elif hasattr(display_node, "SetSliceIntersectionVisibility"):
            display_node.SetSliceIntersectionVisibility(True)
        if hasattr(display_node, "SetSliceIntersectionThickness"):
            display_node.SetSliceIntersectionThickness(2)
        if hasattr(display_node, "SetSliceIntersectionOpacity"):
            display_node.SetSliceIntersectionOpacity(1.0)
        if hasattr(display_node, "SetVisibility3D"):
            display_node.SetVisibility3D(False)

    def reset_roles(self, roles: Any, image_node: Any=None) -> None:
        """Clear a group of roles and recompute derived measurements afterward. Grouped resets let each
        button act as a restart action for its own workflow.
        """

        for role in roles:
            node = self.get_node(role, create_if_missing=True)
            if node.IsA("vtkMRMLMarkupsNode"):
                node.RemoveAllControlPoints()
                node.SetDisplayVisibility(True)
                self._apply_labels(node, role)
            elif node.IsA("vtkMRMLModelNode"):
                self._clear_model(node)
        self.update_all_derived_measurements(image_node)

    def node_is_complete(self, role: Any) -> Any:
        """Return whether a node has collected enough user input to satisfy its workflow step.
        Completion is determined from node content so editing and replay stay robust.
        """

        node = self.get_node(role)
        if node is None or not node.IsA("vtkMRMLMarkupsNode"):
            return False

        spec = self._node_spec_for_role(role)
        expected_count = spec.get("completionCount", 2 if node.IsA("vtkMRMLMarkupsLineNode") else 0)
        return node.GetNumberOfDefinedControlPoints() >= expected_count

    def activate_placement(self, node: Any, persistent: Any=False) -> None:
        """Put Slicer into place mode for the given markup node. Placement is wrapped here so the
        widget can request consistent persistent or one-shot behavior.
        """

        if node is None:
            return

        application_logic = slicer.app.applicationLogic()
        if application_logic is None:
            return
        selection_node = application_logic.GetSelectionNode()
        interaction_node = application_logic.GetInteractionNode()
        if selection_node is None or interaction_node is None:
            return
        selection_node.SetReferenceActivePlaceNodeClassName(node.GetClassName())
        if hasattr(selection_node, "SetActivePlaceNodeID"):
            selection_node.SetActivePlaceNodeID(node.GetID())
        interaction_node.SetPlaceModePersistence(1 if persistent else 0)
        interaction_node.SetCurrentInteractionMode(interaction_node.Place)

    def stop_placement_mode(self) -> None:
        """Leave Slicer place mode. Explicitly stopping placement avoids accidental extra points when
        workflows finish or are cancelled.
        """

        interaction_node = slicer.app.applicationLogic().GetInteractionNode()
        interaction_node.SetCurrentInteractionMode(interaction_node.ViewTransform)
