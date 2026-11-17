"""Adapt the copied desktop rules to the browser's scene and placement queue."""

import numpy as np
from .scene import vtk_to_numpy
from .interaction_rules import DesktopInteractionRules
from .schema import NODE_SPECS, ROLE_ATTRIBUTE, side_role


class LandmarkReuseMixin(DesktopInteractionRules):
    @staticmethod
    def side_role(base, side):
        return side_role(side, base)

    def current_image_node(self):
        return self.slicer_app.scene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")

    def get_node(self, role, create_if_missing=False):
        node = self.node_for_role(role)
        if node is None and create_if_missing:
            self.put_points(role, [])
            node = self.node_for_role(role)
        return node

    def _defined_points(self, node):
        return self.points_for_role(node.GetAttribute(ROLE_ATTRIBUTE))

    def _node_spec_for_role(self, role):
        return NODE_SPECS[role]

    def _set_named_points(self, node, points, _labels):
        self.put_points(node.GetAttribute(ROLE_ATTRIBUTE), points)

    @staticmethod
    def volume_array(volume):
        data = volume.GetImageData()
        width, height, depth = data.GetDimensions()
        scalars = data.GetPointData().GetScalars()
        components = scalars.GetNumberOfComponents()
        shape = (depth, height, width) if components == 1 else (depth, height, width, components)
        return vtk_to_numpy(scalars).reshape(shape)

    def _seed_display_span(self, volume, fallback_points):
        if volume is not None:
            bounds = [0.0] * 6
            volume.GetRASBounds(bounds)
            extent = max(abs(bounds[i + 1] - bounds[i]) for i in (0, 2, 4))
            if extent > 1e-6:
                return extent * 0.75
        if fallback_points:
            extent = float(np.max(np.ptp(np.vstack(fallback_points), axis=0)))
            if extent > 1e-6:
                return extent * 1.5
        return 150.0

    @property
    def latest_results(self):
        reference = self.points_for_role("referenceLine")
        results = {
            "referenceLine": {
                "defined": len(reference) >= 2,
                "points": reference,
                "direction": reference[1] - reference[0] if len(reference) >= 2 else None,
            },
            "sides": {},
        }
        for side in ("left", "right"):
            shaft = self.points_for_role(side_role(side, "shaftAxis"))
            head = {"defined": False}
            try:
                center, diameter = self.circle_from_three(self.points_for_role(side_role(side, "femurHeadPoints")))
                head = {"defined": True, "center": center, "rawValue": diameter}
            except ValueError:
                pass
            results["sides"][side] = {
                "femurHead": head,
                "femoralShaftAxis": {
                    "defined": len(shaft) >= 2,
                    "direction": shaft[1] - shaft[0] if len(shaft) >= 2 else None,
                },
            }
        return results

    def seed_shared_landmarks(self, key, side):
        """Reuse landmarks on shared turns; manual turns never call this adapter."""
        if key in ("tonnis", "sharp"):
            base = "tonnisAngleLine" if key == "tonnis" else "sharpAngleLine"
            if not self._seed_acetabular_angle_line(base, side):
                if self._queue_acetabular_angle_lateral_endpoint(base, side):
                    return (
                        "Place the medial sourcil/base point." if key == "tonnis" else "Place the teardrop/base point."
                    )
        elif key == "lce":
            self._seed_lce_point(side)
        elif key == "acetabular_offset":
            self._seed_acetabular_offset_lines(side)
        elif key == "femoral_offset":
            self._seed_femoral_offset_line(side)
        elif key == "extrusion":
            self._seed_extrusion_index_lines(side)
        return None
