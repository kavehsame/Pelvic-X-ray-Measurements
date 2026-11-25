"""Direct manipulation of local AP templates and retained radiographic fragments in Slicer's red view."""

from pathlib import Path
from typing import NamedTuple

import numpy as np
import qt
import slicer
import vtk

import PelvicXrayMeasurementsPlanning as planning
import PelvicXrayMeasurementsTemplateDisplay as template_display
from PelvicXrayMeasurementsGeometry import image_right_direction, image_up_direction


class _ScreenPlan(NamedTuple):
    node: object
    rotation: planning.RotationControl
    pivot: np.ndarray
    center: np.ndarray
    handle: np.ndarray
    outline: object


class PlanInteractionMixin:
    def _plan_node(self, base):
        return self.logic.get_node(self.logic.side_role(base, self.current_side_key()))

    def _choose_fragment_cut(self, options):
        if len(options) == 1:
            return options[0]
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Choose the neck cut")
        box.setText("Both cuts are present on this side. Which cut defines the retained bone?")
        buttons = {box.addButton(k.title(), qt.QMessageBox.ActionRole): k for k in options}
        box.addButton(qt.QMessageBox.Cancel)
        box.exec()
        return buttons.get(box.clickedButton())

    def _finish_plan_placement(self):
        self.active_placement_queue = []
        self.active_placement_measurement_key = self.active_placement_name = self.active_placement_side_key = None
        self.logic._tracing_fragment_side = None
        self.logic.stop_placement_mode()

    def _set_plan_points(self, node, points):
        change = node.StartModify()
        try:
            self.logic._set_named_points(node, points, [])
        finally:
            node.EndModify(change)

    def _retain_bone(self, mode="auto", kind=None):
        volume = self.current_image_node()
        if volume is None:
            return
        side = self.current_side_key()
        get = lambda base: self.logic._defined_points(self._plan_node(base))
        boundary, target = self._plan_node("fragmentBoundary"), self._plan_node("fragmentTarget")
        options = planning.available_cuts(get)
        reset = mode == "auto" and boundary.GetNumberOfDefinedControlPoints() > 0
        if not reset:
            if not options:
                return
            kind = kind or self._choose_fragment_cut(options)
            if kind not in options:
                return
        cut = get(planning.CUT_ROLES[kind]) if not reset else []
        if not reset and mode == "auto":
            ijk, ras = vtk.vtkMatrix4x4(), vtk.vtkMatrix4x4()
            volume.GetRASToIJKMatrix(ijk)
            volume.GetIJKToRASMatrix(ras)
            z = ijk.MultiplyPoint([*cut[0], 1])[2]
            try:
                points = planning.automatic_trace(
                    get,
                    kind,
                    volume.GetImageData().GetDimensions(),
                    volume.GetSpacing(),
                    lambda p: ijk.MultiplyPoint([*p, 1]),
                    lambda p: ras.MultiplyPoint([*p, z, 1])[:3],
                    side,
                )
            except ValueError as exc:
                self._warn(str(exc))
                return
        self._finish_plan_placement()
        self._selected_plan_kind = None
        self._set_plan_points(target, [])
        target.SetAttribute(planning.FRAGMENT_ANGLE, None)
        target.SetAttribute(planning.VIEW_AXES, None)
        self._set_plan_points(boundary, [])
        if reset:
            message = "Fragment reset. Click Retained Bone Fragment Placement to select it again."
        else:
            self.logic.set_measurement_visible("bone_fragment", True, side)
            boundary.SetAttribute(planning.FRAGMENT_CUT, kind)
            boundary.SetCurveTypeToLinear()
            if mode == "manual":
                self.logic._tracing_fragment_side = side
                self.active_placement_measurement_key = "bone_fragment"
                self.active_placement_side_key = side
                self.active_placement_name = f"{side.title()} {planning.TOOLS['bone_fragment'][0]}"
                self.logic.activate_placement(boundary, persistent=True)
                message = "Trace from the lateral cut end, including the image margin. Right-click to close at the medial end."
            else:
                self._set_plan_points(boundary, points)
                self._set_plan_points(target, [(cut[0] + cut[-1]) / 2])
                self._selected_plan_kind = "fragment"
                message = "Drag the fragment to move it or drag its round handle to rotate."
        self._set_case_dirty(True)
        self.logic.update_all_derived_measurements(volume)
        self.refresh_ui()
        self.instructions_label.setText(message)

    def _complete_manual_fragment(self):
        boundary = self._plan_node("fragmentBoundary")
        if boundary.GetNumberOfDefinedControlPoints() < 2:
            self.instructions_label.setText("Place at least two trace points before finishing.")
            return
        cut = self.logic._defined_points(
            self._plan_node(planning.CUT_ROLES[boundary.GetAttribute(planning.FRAGMENT_CUT)])
        )
        self._finish_plan_placement()
        self._set_plan_points(self._plan_node("fragmentTarget"), [(cut[0] + cut[-1]) / 2])
        self._selected_plan_kind = "fragment"
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()
        self.instructions_label.setText("Drag the fragment to move it or drag its round handle to rotate.")

    def _import_overlay_file(self, _checked=False):
        filename = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(), "Import session overlay pack", "", "PXM overlay packs (*.json)"
        )
        if filename:
            self._load_overlay_path(filename)

    def _load_overlay_path(self, filename):
        try:
            path = Path(filename)
            if path.stat().st_size > planning.PACK_LIMIT:
                raise ValueError("Choose a pack of 12 MiB or less.")
            count = planning.import_overlays(path.read_bytes())
        except (OSError, ValueError) as exc:
            self._warn(str(exc))
            return
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()
        self.instructions_label.setText(f"{count} overlay entries available for this session.")

    def _detach_plan_view(self):
        self._plan_drag = None
        if getattr(self, "_plan_view", None):
            interactor, renderer, actor, tags, node, tag = self._plan_view
            for t in tags.values():
                interactor.RemoveObserver(t)
            node.RemoveObserver(tag)
            renderer.RemoveActor2D(actor)
            for _, overlay in self._plan_artwork.values():
                renderer.RemoveActor2D(overlay)
            self._plan_artwork.clear()
            self._plan_view = None

    def _sync_plan_view(self):
        if not getattr(self, "_plan_view_enabled", True) or not self.logic:
            return
        sw = self._red_slice_widget()
        if sw is None or self.current_image_node() is None:
            self._detach_plan_view()
            return
        view = sw.sliceView()
        iren = view.renderWindow().GetInteractor()
        if iren is None:
            return
        if not getattr(self, "_plan_view", None) or self._plan_view[0] != iren:
            self._detach_plan_view()
            ren = view.renderWindow().GetRenderers().GetFirstRenderer()
            actor = vtk.vtkActor2D()
            actor.SetMapper(vtk.vtkPolyDataMapper2D())
            actor.GetProperty().SetColor(0.25, 0.85, 1.0)
            actor.GetProperty().SetLineWidth(2.5)
            actor.PickableOff()
            ren.AddActor2D(actor)
            tags = {
                event: iren.AddObserver(event, self._plan_mouse, 1.5)
                for event in (
                    "LeftButtonPressEvent",
                    "LeftButtonReleaseEvent",
                    "MouseMoveEvent",
                    "RightButtonPressEvent",
                    "RightButtonReleaseEvent",
                    "LeaveEvent",
                )
            }
            node = sw.mrmlSliceNode()
            self._plan_artwork = {}
            tag = node.AddObserver("ModifiedEvent", lambda *_: self._refresh_plan_display())
            self._plan_view = (iren, ren, actor, tags, node, tag)
        self._refresh_plan_display()

    def _refresh_plan_display(self):
        if self._plan_view:
            _, renderer, _, _, node, _ = self._plan_view
            template_display.sync_artwork(self.logic, renderer, node, self._plan_artwork)
            self._draw_rotation_handle()

    def _plan_screen(self, kind):
        volume = self.current_image_node()
        side = self.current_side_key()
        base = planning.ROTATION_ROLES[kind]
        node = self._plan_node(base)
        if not node.GetNumberOfDefinedControlPoints() or not node.GetDisplayVisibility():
            return None
        outline = None
        if kind == "fragment":
            if side not in getattr(self.logic, "_fragment_hit_plans", {}):
                return None
        else:
            outline = self._plan_node(base + "Outline").GetPolyData()
            if (
                not self.logic.measurement_visible("template_" + kind, side)
                or not outline
                or not outline.GetNumberOfPoints()
            ):
                return None
        control = planning.rotation_control(node, kind, side, image_right_direction(volume), image_up_direction(volume))
        if control is None:
            return None
        pivot = self.logic._defined_points(node)[0]
        center = self._screen(pivot)
        direction = self._screen(pivot + control.ray()) - center
        length = np.linalg.norm(direction)
        if length < 1e-8:
            return None
        return _ScreenPlan(node, control, pivot, center, center + direction * (48 / length), outline)

    def _screen(self, ras):
        m = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Invert(self._plan_view[4].GetXYToRAS(), m)
        return np.asarray(m.MultiplyPoint([*ras, 1.0])[:2])

    def _world(self, xy):
        return np.asarray(self._plan_view[4].GetXYToRAS().MultiplyPoint([*xy, 0.0, 1.0])[:3])

    def _draw_rotation_handle(self):
        if not getattr(self, "_plan_view", None):
            return
        actor = self._plan_view[2]
        kind = getattr(self, "_selected_plan_kind", None)
        info = (
            self._plan_screen(kind)
            if self.logic and self.current_image_node() and kind and not self.active_placement_measurement_key
            else None
        )
        actor.SetVisibility(bool(info))
        if not info:
            return
        pivot, handle = info.center, info.handle
        signature = (*pivot, *handle)
        if getattr(self, "_handle_actor", None) == actor and getattr(self, "_handle_position", None) == signature:
            return
        self._handle_actor, self._handle_position = actor, signature
        pts, lines = vtk.vtkPoints(), vtk.vtkCellArray()
        for path in (
            [pivot, handle],
            [handle + 6 * np.array([np.cos(t), np.sin(t)]) for t in np.linspace(0, 2 * np.pi, 33)],
        ):
            lines.InsertNextCell(len(path))
            for x, y in path:
                lines.InsertCellPoint(pts.InsertNextPoint(x, y, 0))
        poly = vtk.vtkPolyData()
        poly.SetPoints(pts)
        poly.SetLines(lines)
        actor.GetMapper().SetInputData(poly)

    @staticmethod
    def _inside(point, polygon):
        if len(polygon) < 3:
            return False
        a = np.asarray(polygon)
        b = np.roll(a, -1, axis=0)
        x, y = point
        cross = (a[:, 1] > y) != (b[:, 1] > y)
        return bool(
            np.count_nonzero(
                x < (a[cross, 0] + (y - a[cross, 1]) * (b[cross, 0] - a[cross, 0]) / (b[cross, 1] - a[cross, 1]))
            )
            % 2
        )

    def _hit_plan(self, at):
        side = self.current_side_key()
        selected = getattr(self, "_selected_plan_kind", None)
        if not getattr(self.logic, "_fragment_hit_plans", {}).get(side) and not any(
            self._plan_node("planning" + k.title() + "Anchor").GetNumberOfDefinedControlPoints()
            for k in planning.COMPONENTS
        ):
            return None
        if selected:
            info = self._plan_screen(selected)
            if info and np.linalg.norm(info.handle - at) <= 10:
                return ("rotate", selected, self._world(info.handle) - self._world(at))
        # Preserve the normal markup editor when another visible control point is under the cursor.
        for node_id in tuple(self.logic._node_cache.values()):
            node = slicer.mrmlScene.GetNodeByID(node_id)
            if not node or not node.IsA("vtkMRMLMarkupsNode") or node.GetLocked() or not node.GetDisplayVisibility():
                continue
            for p in self.logic._defined_points(node):
                if np.linalg.norm(self._screen(p) - at) < 7:
                    for kind, base in planning.ROTATION_ROLES.items():
                        if node == self._plan_node(base):
                            return ("move", kind, p - self._world(at))
                    return None
        for kind in dict.fromkeys((selected, *planning.COMPONENTS)):
            if kind not in planning.COMPONENTS:
                continue
            info = self._plan_screen(kind)
            if info:
                corners = [self._screen(info.outline.GetPoint(i)) for i in range(info.outline.GetNumberOfPoints())]
                item = planning.ITEMS[info.rotation.template["id"]]
                hit = template_display.hits_artwork(item["image"], at, corners) if "image" in item else self._inside(at, corners)
                if hit:
                    return ("move", kind, info.pivot - self._world(at))
        plan = getattr(self.logic, "_fragment_hit_plans", {}).get(side)
        if plan:
            volume = self.current_image_node()
            m = vtk.vtkMatrix4x4()
            volume.GetRASToIJKMatrix(m)
            xy = m.MultiplyPoint([*self._world(at), 1])[:2]
            a = np.asarray(plan["matrix"])
            polygon = np.asarray(plan["polygon"]) @ a[:, :2].T + a[:, 2]
            if self._inside(xy, polygon):
                target = self.logic._defined_points(self._plan_node("fragmentTarget"))[0]
                return ("move", "fragment", target - self._world(at))
        return None

    def _plan_mouse(self, caller, event):
        if not getattr(self, "_plan_view", None) or not self.logic or self.current_image_node() is None:
            return
        at = np.asarray(caller.GetEventPosition(), float)

        def consume():
            caller.GetCommand(self._plan_view[3][event]).SetAbortFlag(1)

        if (
            getattr(self.logic, "_tracing_fragment_side", None) == self.current_side_key()
            and self.active_placement_measurement_key == "bone_fragment"
        ):
            if caller.GetShiftKey() or caller.GetControlKey() or caller.GetAltKey():
                return
            if event == "LeftButtonPressEvent":
                consume()
                node = self._plan_node("fragmentBoundary")
                points = self.logic._defined_points(node)
                position = self._world(at)
                if not points or np.linalg.norm(points[-1] - position) > 1e-6:
                    self._set_plan_points(node, [*points, position])
                self._set_case_dirty(True)
                return
            if event == "LeftButtonReleaseEvent":
                consume()
                return
            if event == "RightButtonPressEvent":
                consume()
                self._plan_right_release = True
                self._complete_manual_fragment()
            return
        if event == "RightButtonReleaseEvent" and getattr(self, "_plan_right_release", False):
            self._plan_right_release = False
            consume()
            return
        if event == "LeaveEvent":
            self._plan_drag = None
            return
        if (
            self.active_placement_measurement_key
            or caller.GetShiftKey()
            or caller.GetControlKey()
            or caller.GetAltKey()
        ):
            self._plan_drag = None
            return
        if event == "LeftButtonPressEvent":
            self._plan_drag = self._hit_plan(at)
            if self._plan_drag:
                self._selected_plan_kind = self._plan_drag[1]
                consume()
                self._draw_rotation_handle()
                caller.Render()
            return
        drag = getattr(self, "_plan_drag", None)
        if not drag or event not in ("MouseMoveEvent", "LeftButtonReleaseEvent"):
            return
        consume()
        mode, kind, offset = drag
        if event == "LeftButtonReleaseEvent":
            self._plan_drag = None
        world = self._world(at) + offset
        if mode == "rotate":
            info = self._plan_screen(kind)
            if not info:
                return
            info.rotation.drag(info.node, world - info.pivot)
        else:
            node = self._plan_node(planning.ROTATION_ROLES[kind])
            self._set_plan_points(node, [world])
        self._set_case_dirty(True)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()
        caller.Render()
