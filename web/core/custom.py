"""Numbered custom Point, Line and Angle tools with copied desktop geometry rules."""

import re
import numpy as np
from .scene import vtkVector3d
from .geometry import image_axes_from_volume, unit_vector
from .schema import ROLE_ATTRIBUTE
from .custom_rules import CustomGeometryRules, OTHER_LINE_LOCK_ATTRIBUTE, OTHER_ANGLE_LOCK_ATTRIBUTE

CUSTOM_ROLE = re.compile(r"other(Point|Line|Angle)_([1-9]\d*)(?:_(points|referenceArm|freeArm))?")


def custom_spec(role):
    """Resolve numbered roles without changing the fixed anatomical node schema."""
    match = CUSTOM_ROLE.fullmatch(role)
    if not match:
        return None
    kind, number, part = match.groups()
    index = int(number)
    if kind == "Angle" and part not in {"points", "referenceArm", "freeArm"}:
        return None
    if kind != "Angle" and part is not None:
        return None
    point = kind == "Point" or part == "points"
    color = {"Point": (0.68, 0.42, 0.88), "Line": (0.56, 0.74, 0.92), "Angle": (0.96, 0.56, 0.18)}[kind]
    labels = (
        [f"Point_{index}"]
        if kind == "Point"
        else (
            [f"Angle_{index}_ArmA", f"Angle_{index}_Vertex", f"Angle_{index}_ArmB"]
            if point
            else [
                f"{kind}_{index}"
                + ("_Reference" if part == "referenceArm" else "_FreeArm" if part == "freeArm" else "")
                + suffix
                for suffix in ("_Start", "_End")
            ]
        )
    )
    return {
        "className": "vtkMRMLMarkupsFiducialNode" if point else "vtkMRMLMarkupsLineNode",
        "name": f"Hip Measurements - {kind} {index}"
        + ({"points": " Points", "referenceArm": " Reference Arm", "freeArm": " Free Arm"}.get(part, "")),
        "color": color,
        "labels": labels,
        "completionCount": len(labels),
        "pointLabelsVisible": kind == "Point",
        "locked": part in {"referenceArm", "freeArm"},
    }


class CustomMeasurementMixin(CustomGeometryRules):
    """Adapt desktop numbering, constraints, counters and results to browser MRML."""

    def custom_indices(self, kind):
        """Discover numbered source nodes from the scene, including reloaded MRBs."""
        prefix = {"point": "otherPoint_", "line": "otherLine_", "angle": "otherAngle_"}[kind]
        suffix = "_points" if kind == "angle" else ""
        indices = []
        for node in self.scene.GetNodesByClass("vtkMRMLMarkupsNode"):
            role = node.GetAttribute(ROLE_ATTRIBUTE) or ""
            match = CUSTOM_ROLE.fullmatch(role)
            if match and role == prefix + match.group(2) + suffix:
                indices.append(int(match.group(2)))
        return sorted(set(indices))

    def custom_roles(self, kind, index):
        """Treat an angle's editable points and two helper arms as one removable bundle."""
        if kind == "angle":
            return [f"otherAngle_{index}_{part}" for part in ("points", "referenceArm", "freeArm")]
        return [f"other{kind.title()}_{index}"]

    def custom_can_add(self, kind):
        """Prevent a second unfinished measurement of the same kind, as the desktop does."""
        values = self._custom_measurements.get(kind, [])
        return not values or bool(values[-1]["defined"])

    def add_custom(self, kind):
        """Capture the selected lock mode and place a new numbered measurement."""
        from .workflow import PlacementStep

        self.update_derived()
        if self.current_image_node() is None or not self.custom_can_add(kind):
            self.server.state.pelvic_instruction = (
                f"Finish placing the current custom {kind} before adding another one."
            )
            return False
        mode = "none"
        if kind != "point":
            if self.server.state[f"pelvic_other_{kind}_parallel"]:
                mode = "parallel"
            elif self.server.state[f"pelvic_other_{kind}_perpendicular"]:
                mode = "perpendicular"
        reference = self.points_for_role("referenceLine")
        if mode != "none" and (len(reference) < 2 or np.linalg.norm(reference[1] - reference[0]) < 1e-6):
            self.server.state.pelvic_instruction = (
                "Define the reference line before creating a reference-locked measurement."
            )
            return False
        indices = self.custom_indices(kind)
        if len(indices) >= 999:
            return False
        index = max(indices, default=0) + 1
        self.finish(silent=True)
        roles = self.custom_roles(kind, index)
        for role in roles:
            self.put_points(role, [], derived=bool(custom_spec(role)["locked"]))
        node = self.node_for_role(roles[0])
        if kind != "point":
            node.SetAttribute(OTHER_LINE_LOCK_ATTRIBUTE if kind == "line" else OTHER_ANGLE_LOCK_ATTRIBUTE, mode)
        instruction = (
            f"Place point {index}."
            if kind == "point"
            else (
                f"Draw line {index}. Its length updates automatically."
                if kind == "line"
                else f"Place angle {index}: first arm point, then the vertex, then the second arm point."
            )
        )
        if mode != "none":
            instruction += f" The {'line' if kind == 'line' else 'first arm'} stays {mode} to the reference line; length and position remain editable."
        self._workflow_key = f"other_{kind}"
        self._steps = [(roles[0], PlacementStep(roles[0], instruction, bilateral=False, persistent=kind == "angle"))]
        self._step_index = 0
        self.server.state.pelvic_active_key = f"other_{kind}"
        self.server.state.pelvic_active_tool = f"{kind.title()} {index}"
        self.set_custom_hidden(kind, False)
        self._activate_step()
        self.update_derived()
        return True

    def set_custom_count(self, kind, value):
        """Increment adds one ready measurement; decrement removes latest bundles first."""
        try:
            target = int(value)
        except (TypeError, ValueError):
            self.update_derived()
            return
        self.update_derived()
        indices = self.custom_indices(kind)
        current = len(indices)
        target = max(0, min(target, 999, current + int(self.custom_can_add(kind))))
        if target > current:
            self.add_custom(kind)
        elif target < current:
            for index in reversed(indices[target:]):
                roles = self.custom_roles(kind, index)
                if self._active_node is not None and self._active_node.GetAttribute(ROLE_ATTRIBUTE) in roles:
                    self.finish()
                for role in roles:
                    self._remove_role(role)
            self.update_derived()

    def set_custom_hidden(self, kind, hidden):
        """Hide the entire numbered group without deleting inputs or numeric results."""
        self.server.state[f"pelvic_hide_other_{kind}"] = bool(hidden)
        for index in self.custom_indices(kind):
            self.node_for_role(self.custom_roles(kind, index)[0]).SetAttribute(
                "PelvicXrayMeasurements.CustomHidden", "1" if hidden else "0"
            )
        self._update_custom_visibility()

    def sync_custom_visibility(self):
        """Restore saved group visibility after case navigation or scene reload."""
        for kind in ("point", "line", "angle"):
            indices = self.custom_indices(kind)
            last = self.node_for_role(self.custom_roles(kind, indices[-1])[0]) if indices else None
            self.server.state[f"pelvic_hide_other_{kind}"] = bool(
                last is not None and last.GetAttribute("PelvicXrayMeasurements.CustomHidden") == "1"
            )

    def _defined_points(self, node):
        """Supply the copied desktop rules with defined points from a dynamic node."""
        return self.points_for_role(node.GetAttribute(ROLE_ATTRIBUTE)) if node is not None else []

    def _set_control_point_position(self, node, index, point):
        """Write desktop constraint endpoints in place, retaining editable point IDs."""
        current = [0.0] * 3
        node.GetNthControlPointPositionWorld(index, current)
        if not np.allclose(current, point, atol=1e-8, rtol=0):
            with self.scene_edit():
                node.SetNthControlPointPositionWorld(index, vtkVector3d(*map(float, point)))

    def _update_custom_measurements(self):
        """Compute copied desktop constraints, partial angle arms and calibrated results."""
        reference = self.points_for_role("referenceLine")
        ready = len(reference) >= 2 and np.linalg.norm(reference[1] - reference[0]) > 1e-6
        ref = {"defined": ready, "direction": reference[1] - reference[0] if ready else None}
        scale = self._calibration_scale()
        image = self.current_image_node()
        axis_i, axis_j = image_axes_from_volume(image)
        normal = (
            unit_vector(np.cross(axis_i, axis_j))
            if axis_i is not None and axis_j is not None
            else np.array([0.0, 0.0, 1.0])
        )
        rows = []
        self._custom_measurements = {kind: [] for kind in ("point", "line", "angle")}
        for kind in ("point", "line", "angle"):
            for index in self.custom_indices(kind):
                roles = self.custom_roles(kind, index)
                node = self.node_for_role(roles[0])
                points = self.points_for_role(roles[0])
                measurement = {"index": index, "defined": False, "rawValue": None}
                mode = "none"
                if kind == "point":
                    measurement["defined"] = bool(points)
                    value = f"({points[0][0]:.1f}, {points[0][1]:.1f}, {points[0][2]:.1f})" if points else "Not defined"
                elif kind == "line":
                    mode = self._other_line_lock_mode(node)
                    points = self._apply_other_line_locked_reference(node, mode, ref, normal, image)
                    length = np.linalg.norm(points[1] - points[0]) if len(points) >= 2 else None
                    measurement.update(defined=length is not None, rawValue=length)
                    value = (
                        "-"
                        if length is None
                        else f"{length:.2f} su"
                        + (
                            f" | {length * scale:.2f} mm"
                            if scale
                            else " | no cal"
                            if self.points_for_role("calibrationPoints")
                            else ""
                        )
                    )
                else:
                    mode = self._other_angle_lock_mode(node)
                    valid_reference = mode == "none" or ready
                    if valid_reference:
                        points = self._apply_other_angle_locked_reference(node, points, mode, ref, normal, image)
                        self._populate_other_angle_value(measurement, points)
                    for role, end in zip(roles[1:], (0, 2), strict=True):
                        self.put_points(
                            role,
                            [points[1], points[end]] if valid_reference and len(points) > max(1, end) else [],
                            derived=True,
                        )
                    value = "-" if not measurement["defined"] else f"{measurement['rawValue']:.2f} deg"
                label = f"{kind.title()} {index}" + (
                    " (Ref ||)" if mode == "parallel" else " (Ref _|_)" if mode == "perpendicular" else ""
                )
                self._custom_measurements[kind].append(measurement)
                rows.append(
                    {"id": roles[0], "kind": kind, "label": label, "value": value, "defined": measurement["defined"]}
                )
            count = len(self.custom_indices(kind))
            mode_selected = kind != "point" and (
                self.server.state[f"pelvic_other_{kind}_parallel"]
                or self.server.state[f"pelvic_other_{kind}_perpendicular"]
            )
            self.server.state[f"pelvic_other_{kind}_count"] = count
            self.server.state[f"pelvic_other_{kind}_max"] = min(999, count + int(self.custom_can_add(kind)))
            self.server.state[f"pelvic_other_{kind}_enabled"] = bool(
                self.current_image_node() is not None
                and self.custom_can_add(kind)
                and count < 999
                and (not mode_selected or ready)
            )
            self.server.state[f"pelvic_other_{kind}_applied"] = bool(count and self.custom_can_add(kind))
        self.server.state.pelvic_custom_results = rows
        self._update_custom_visibility()

    def _update_custom_visibility(self):
        """Keep partial inputs visible and hide every arm when its group is hidden."""
        for kind in ("point", "line", "angle"):
            hidden = bool(self.server.state[f"pelvic_hide_other_{kind}"])
            for index in self.custom_indices(kind):
                for role in self.custom_roles(kind, index):
                    node = self.node_for_role(role)
                    if node is not None:
                        active = self._active_node is not None and node.GetID() == self._active_node.GetID()
                        node.SetDisplayVisibility(not hidden and (active or node.GetNumberOfDefinedControlPoints() > 0))
