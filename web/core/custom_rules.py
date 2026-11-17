"""Fork-owned copies of desktop custom line and angle constraint calculations."""

from typing import Any
from enum import StrEnum
import numpy as np
from .geometry import vector_length, unit_vector, superior_reference_direction, unsigned_angle_between_directions

EPSILON = 1e-6
DEFAULT_CONSTRUCTION_LINE_LENGTH_SU = 40.0
OTHER_LINE_LOCK_ATTRIBUTE = "PelvicXrayMeasurements.OtherLineLockToReference"
OTHER_ANGLE_LOCK_ATTRIBUTE = "PelvicXrayMeasurements.OtherAngleLockToReference"


class OtherAngleLockMode(StrEnum):
    """Saved-scene-compatible custom reference constraints."""

    NONE = "none"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"


class CustomGeometryRules:
    def _other_line_lock_mode(self, line_node: Any) -> Any:
        """Return the stored lock mode for one custom line node."""
        if line_node is None:
            return OtherAngleLockMode.NONE
        try:
            return OtherAngleLockMode(str(line_node.GetAttribute(OTHER_LINE_LOCK_ATTRIBUTE) or OtherAngleLockMode.NONE))
        except ValueError:
            return OtherAngleLockMode.NONE

    def _locked_other_line_direction(self, lock_mode: Any, reference: Any, plane_normal: Any, image_node: Any) -> Any:
        """Return the constrained direction for one custom line lock mode."""
        if lock_mode == OtherAngleLockMode.PARALLEL:
            return unit_vector(reference["direction"])
        if lock_mode == OtherAngleLockMode.PERPENDICULAR:
            return superior_reference_direction(reference["direction"], plane_normal, image_node)
        return None

    def _apply_other_line_locked_reference(
        self, line_node: Any, lock_mode: Any, reference: Any, plane_normal: Any, image_node: Any
    ) -> Any:
        """Constrain a custom line to its locked reference orientation while preserving midpoint."""
        points = self._defined_points(line_node)
        if len(points) < 2 or lock_mode == OtherAngleLockMode.NONE or (not reference["defined"]):
            return points
        locked_direction = self._locked_other_line_direction(lock_mode, reference, plane_normal, image_node)
        if locked_direction is None:
            return points
        current_vector = points[1] - points[0]
        line_length = vector_length(current_vector)
        if line_length < EPSILON:
            line_length = DEFAULT_CONSTRUCTION_LINE_LENGTH_SU
        if vector_length(current_vector) >= EPSILON and float(np.dot(current_vector, locked_direction)) < 0.0:
            locked_direction = -locked_direction
        midpoint = (points[0] + points[1]) / 2.0
        half_vector = locked_direction * (line_length / 2.0)
        self._set_control_point_position(line_node, 0, midpoint - half_vector)
        self._set_control_point_position(line_node, 1, midpoint + half_vector)
        return self._defined_points(line_node)

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

    def _locked_other_angle_direction(self, lock_mode: Any, reference: Any, plane_normal: Any, image_node: Any) -> Any:
        """Return the locked first-arm direction for a custom angle."""
        if lock_mode == OtherAngleLockMode.PARALLEL:
            return unit_vector(reference["direction"])
        return superior_reference_direction(reference["direction"], plane_normal, image_node)

    def _apply_other_angle_locked_reference(
        self, points_node: Any, points: Any, lock_mode: Any, reference: Any, plane_normal: Any, image_node: Any
    ) -> Any:
        """Adjust the first arm of a locked custom angle to its constrained direction."""
        if len(points) < 2 or lock_mode == OtherAngleLockMode.NONE or (not reference["defined"]):
            return points
        vertex = points[1]
        locked_vector = points[0] - vertex
        locked_length = vector_length(locked_vector)
        if locked_length < EPSILON:
            locked_length = DEFAULT_CONSTRUCTION_LINE_LENGTH_SU
        locked_direction = self._locked_other_angle_direction(lock_mode, reference, plane_normal, image_node)
        if locked_direction is None:
            return points
        if vector_length(locked_vector) >= EPSILON and float(np.dot(locked_vector, locked_direction)) < 0.0:
            locked_direction = -locked_direction
        locked_endpoint = vertex + locked_direction * locked_length
        self._set_control_point_position(points_node, 0, locked_endpoint)
        return self._defined_points(points_node)

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
