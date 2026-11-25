"""Local measurement session for a dedicated browser worker."""

from copy import deepcopy
import csv
import json
from pathlib import Path
from types import SimpleNamespace
from io import BytesIO
from zipfile import ZIP_STORED, BadZipFile, ZipFile
import xml.etree.ElementTree as ET

import numpy as np

from . import planning
from .planning import catalog_menu, transformed_attributes, validate_attributes
from .auto_placement import feature_specs
from .csv_export import MEASUREMENTS, write_case_csv
from .imaging import decode, default_window, display_png, reorient
from .scene import Scene, Volume, ellipse_path
from .scene_files import append_csv_metadata, read_csv, read_mrb, supported_role, valid_tracks, write_mrb
from .schema import ROLE_ATTRIBUTE
from .suggestions import SuggestionController
from .workflow import WORKFLOWS, WORKFLOW_SECTIONS, BrowserPlacementController

VERSION = "1.8.0"
CUSTOM_KINDS = ("point", "line", "angle")
CUSTOM_LOCKS = tuple(
    f"pelvic_other_{kind}_{mode}" for kind in ("line", "angle") for mode in ("parallel", "perpendicular")
)
FILE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".dcm",
    ".dicom",
    ".ima",
    ".nrrd",
    ".nhdr",
    ".nii",
    ".nii.gz",
    ".mha",
    ".mhd",
    ".mrb",
)


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class BrowserPlacement(BrowserPlacementController):
    """Use the shared placement rules with direct events from the canvas."""

    def _watch_source(self, role, node):
        pass

    def _watch_circle_source(self, role, node):
        pass

    def _sync_active_side_badge(self):
        pass  # The canvas draws this badge independently of the image coordinates.

    def _activate_step(self):
        while 0 <= self._step_index < len(self._steps):
            role, step = self._steps[self._step_index]
            spec = self._node_spec(role)
            required = int(spec.get("completionCount", self._default_completion(spec)))
            if not required or len(self.points_for_role(role)) < required:
                node = self.node_for_role(role)
                if node is None:
                    self.put_points(role, [])
                    node = self.node_for_role(role)
                if role.endswith(("_neckGuideProximal", "_implantNeckGuideProximal")):
                    self.store_axis_options()
                if role.endswith("_fragmentBoundary"):
                    node.SetCurveType(0)
                self._active_node = node
                self.server.state.pelvic_instruction = step.instruction
                return
            self._step_index += 1
        self.finish()
        self.server.state.pelvic_instruction = "Placement complete. Reused landmarks remain editable on the image."

    def _refresh_circle(self, points_role, circle_role, center_role=None):
        try:
            center, diameter = self.circle_from_three(self.points_for_role(points_role))
        except ValueError:
            self._clear_circle_model(circle_role)
            if center_role:
                self._remove_role(center_role)
            return
        if center_role:
            self.put_points(center_role, [center], derived=True)
        node = self._model_for_role(circle_role)
        node.SetAndObservePolyData(
            ellipse_path(center, np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), diameter / 2.0, diameter / 2.0)
        )
        node.SetDisplayVisibility(True)

    def _constrain_parallel_line(self, role, direction):
        """Keep the endpoint identity of reference-constrained lines while editing."""
        points = self.points_for_role(role)
        if len(points) >= 2 and direction is not None and np.dot(points[1] - points[0], direction) < 0:
            direction = -direction
        return super()._constrain_parallel_line(role, direction)

    def expire_placement(self):
        if self._active_node is None:
            return
        if self._workflow_key == "bone_fragment":
            self.finish_fragment()
            return
        if self._active_node.IsA("vtkMRMLMarkupsCurveNode"):
            self.start(self._workflow_key)
        else:
            self.finish()
        self.update_derived()

    def place(self, x, y):
        node = self._active_node
        if node is None:
            return False
        role = node.GetAttribute(ROLE_ATTRIBUTE)
        spec = self._node_spec(role)
        pixels = self.current_image_node()
        w, h, _ = pixels.GetDimensions()
        if not np.isfinite([x, y]).all() or (not role.endswith("_fragmentBoundary") and not (0 <= x <= w - 1 and 0 <= y <= h - 1)):
            return False
        required = int(spec.get("completionCount", self._default_completion(spec)))
        coords = pixels.from_image([x, y])
        if not required and len(node.points) >= 5000:
            raise ValueError("This contour already has 5,000 points. Right-click to finish it.")
        if node.points and np.linalg.norm(coords - node.points[-1]) < 1e-7:
            return False
        # Use the existing local edge calculation on this input only. Repeated
        # snapping of an entire curve can move earlier points unintentionally.
        if node.IsA("vtkMRMLMarkupsCurveNode") and self._is_anatomy_edge_contour_role(role):
            candidate = self._edge_snap_candidate_ijk(pixels.pixels[np.newaxis, ...], np.array([x, y, 0.0]))
            if candidate is not None:
                coords = pixels.from_image(candidate[:2])
        self.put_points(role, [*node.points, coords])
        if required and (len(node.points) >= required or role in self.pending_auto_line_endpoints):
            self._complete_step(node.GetID())
        self.update_derived()
        return True

    def move(self, role, index, x, y):
        if role.endswith("Rotation"):
            anchor_role = role.removesuffix("Rotation")
            side, _, base = anchor_role.partition("_")
            kind = next((k for k, value in planning.ROTATION_ROLES.items() if value == base), None)
            if kind is None or side != self.server.state.pelvic_active_side or index != 0 or not np.isfinite([x, y]).all():
                return False
            node = self.node_for_role(anchor_role)
            if node is None or not node.visible or not node.points:
                return False
            control = planning.rotation_control(node, kind, side, [-1, 0, 0], [0, 1, 0])
            if control is None:
                return False
            delta = self.current_image_node().from_image([x, y]) - node.points[0]
            control.drag(node, delta)
            self.update_derived()
            return True
        node = self.node_for_role(role)
        if node is None or node.locked or not 0 <= index < len(node.points):
            return False
        volume = self.current_image_node()
        w, h, _ = volume.GetDimensions()
        xy = [x, y] if role.endswith(("_fragmentBoundary","_fragmentTarget")) else np.clip([x, y], [0, 0], [w - 1, h - 1])
        if node.IsA("vtkMRMLMarkupsCurveNode") and self._is_anatomy_edge_contour_role(role):
            candidate = self._edge_snap_candidate_ijk(volume.pixels[np.newaxis, ...], np.array([*xy, 0.0]))
            if candidate is not None:
                xy = candidate[:2]
        node.SetNthControlPointPositionWorld(index, volume.from_image(xy))
        self.update_derived()
        return True


def index_transform(shape, turns, mirrored):
    """Return the mapping from displayed (i, j) back to the original pixels."""
    h, w = shape
    mapping = np.eye(4)
    mapping[:2] = (
        [[1, 0, 0, 0], [0, 1, 0, 0]],
        [[0, 1, 0, 0], [-1, 0, 0, h - 1]],
        [[-1, 0, 0, w - 1], [0, -1, 0, h - 1]],
        [[0, -1, 0, w - 1], [1, 0, 0, 0]],
    )[turns]
    if mirrored:
        transform = np.eye(4)
        transform[0, 0], transform[0, 3] = -1, (h if turns % 2 else w) - 1
        mapping = mapping @ transform
    return mapping


class Session:
    def __init__(self, annotator="", ball_diameter=25):
        self.scene = Scene()
        self.settings = State(
            pelvic_active_side="left",
            pelvic_ball_diameter=ball_diameter,
            pelvic_annotator_name=annotator,
            pelvic_comments="",
            pelvic_export_measurements=True,
            pelvic_active_key="",
            pelvic_active_tool="None",
            pelvic_instruction="Select an input folder or open a radiograph.",
        )
        for key in CUSTOM_LOCKS:
            self.settings[key] = False
        for key in WORKFLOWS:
            self.settings[f"pelvic_hide_{key}"] = False
        for kind in CUSTOM_KINDS:
            self.settings[f"pelvic_hide_other_{kind}"] = False
        self.server = SimpleNamespace(state=self.settings)
        self.controller = BrowserPlacement(
            self.server,
            SimpleNamespace(scene=self.scene, markups_logic=SimpleNamespace(disable_place_mode=lambda: None)),
        )
        self.auto = SuggestionController(
            self.server, self.controller, SimpleNamespace(current_volume=lambda: self.scene.volume)
        )
        self.image = None
        self.base_image = None
        self.case_name = ""
        self.turns = 0
        self.mirrored = False
        self.low = 0.0
        self.high = 1.0
        self.invert = False
        self.intensity_range = (0.0, 1.0)
        self.controller.sync_axis_options()
        self.controller.update_derived()

    def open(self, name, content, companion=None):
        self.case_name = name
        if name.lower().endswith(".mrb"):
            self.base_image, loaded = read_mrb(content)
        else:
            self.base_image, loaded = decode(name, content, companion), None
        self.orient()
        lower, upper, (self.low, self.high) = default_window(self.image)
        self.intensity_range = (lower, upper)
        self.invert = self.image.inverted
        self.settings.pelvic_instruction = "Choose a measurement tool to start placing points."
        if loaded is not None:
            self.restore(loaded, stored_pixels=True)
            self.settings.pelvic_instruction = "Saved scene opened. You can edit the annotations."
        self.controller.update_derived()

    def orient(self):
        self.image = reorient(self.base_image, self.turns, self.mirrored)
        volume = self.scene.volume = Volume(self.image.pixels, self.image.native_affine())
        volume.planning_metric = self.image.physical_spacing
        original_axes = np.asarray(self.base_image.planning_axes if self.base_image.planning_axes is not None else planning.STANDARD_AP)
        to_original = index_transform(self.base_image.shape, self.turns, self.mirrored)[:2, :2]
        directions = volume.affine[:3, :2] / self.image.spacing
        volume.planning_axes = original_axes @ to_original @ directions.T

    def has_points(self):
        return any(
            n.points and supported_role(n.GetAttribute(ROLE_ATTRIBUTE) or "")
            for n in self.scene.GetNodesByClass("vtkMRMLMarkupsNode")
        )

    def get_settings(self):
        c, s = self.controller, self.settings
        return dict(
            ball_diameter=s.pelvic_ball_diameter,
            active_side=s.pelvic_active_side,
            annotator=s.pelvic_annotator_name,
            comments=s.pelvic_comments,
            hidden_workflows=sorted(c._hidden_workflows),
            export_measurements=s.pelvic_export_measurements,
            hidden_custom=[kind for kind in CUSTOM_KINDS if s[f"pelvic_hide_other_{kind}"]],
            custom_locks={key: bool(s[key]) for key in CUSTOM_LOCKS},
            axis_options={
                f"{side}_{kind}": list(c.axis_options(side, kind))
                for side in ("left", "right")
                for kind in ("neck", "implant_neck")
            },
            window=[self.low, self.high],
            invert=self.invert,
            web_layout={"turns": self.turns, "mirrored": self.mirrored, "shape": list(self.image.shape)},
        )

    def serialize(self):
        points, attributes, curves, segments = {}, {}, {}, {}
        for node in self.scene.GetNodesByClass("vtkMRMLMarkupsNode"):
            role = node.GetAttribute(ROLE_ATTRIBUTE) or ""
            if supported_role(role) and node.points:
                points[role] = [p.tolist() for p in node.points]
                attributes[role] = node.attributes
                if node.IsA("vtkMRMLMarkupsCurveNode"):
                    curves[role] = node.curve_type
                    segments[role] = node.segment_size
        return dict(
            points=points,
            attributes=attributes,
            curve_types=curves,
            curve_segments=segments,
            settings=self.get_settings(),
            matrix=self.scene.volume.affine.tolist(),
            case_name=self.case_name,
        )

    def restore(self, saved, *, stored_pixels=False):
        tracks = valid_tracks(saved["points"])
        settings = saved["settings"]
        if not isinstance(settings, dict):
            raise ValueError("The saved scene settings must be an object.")
        for name in ("custom_locks", "axis_options"):
            if not isinstance(settings.get(name, {}), dict):
                raise ValueError(f"The saved {name.replace('_', ' ')} are invalid.")
        for options in settings.get("axis_options", {}).values():
            if not isinstance(options, (list, tuple)) or len(options) != 2 or any(type(x) is not bool for x in options):
                raise ValueError("Saved neck-axis options must contain two checkbox values.")
        for role in tracks:
            validate_attributes(role, saved.get("attributes", {}).get(role, {}))
        if saved.get("dimensions") is not None and saved["dimensions"] != list(reversed(self.base_image.shape)):
            raise ValueError("The CSV and the open image have different dimensions.")
        layout = settings.get("web_layout")
        if layout and not stored_pixels:
            full = reorient(self.base_image, layout["turns"], layout["mirrored"])
            if list(full.shape) != layout["shape"]:
                raise ValueError("The saved annotations were made on a different image size.")
        c, state = self.controller, self.settings
        diameter = float(settings.get("ball_diameter", 25.0))
        if not 0 < diameter < 1000 or not np.isfinite(diameter):
            raise ValueError("The saved calibration-ball diameter is invalid.")
        affine = saved.get("matrix")
        if affine is None and saved.get("native_csv"):
            affine = self.base_image.source_affine
        pixels_from_world = None if affine is None else np.linalg.inv(affine)
        if layout and not stored_pixels:
            self.turns, self.mirrored = int(layout["turns"]) % 4, bool(layout["mirrored"])
            self.orient()
        transform = np.eye(4)
        if pixels_from_world is not None:
            if not layout or stored_pixels:
                orientation = index_transform(self.base_image.shape, self.turns, self.mirrored)
                pixels_from_world = np.linalg.solve(orientation, pixels_from_world)
            transform = self.scene.volume.affine @ pixels_from_world
        attributes = {role: transformed_attributes(saved.get("attributes", {}).get(role, {}), transform) for role in tracks}
        c.reset_scene_state()
        self.scene.markups.clear()
        for role, track in tracks.items():
            track = (transform @ np.column_stack((track, np.ones(len(track)))).T).T[:, :3]
            c.put_points(role, track)
            node = c.node_for_role(role)
            for key, value in attributes[role].items():
                if key != ROLE_ATTRIBUTE and key.startswith("PelvicXrayMeasurements."):
                    node.SetAttribute(key, value)
            node.SetCurveType(int(saved.get("curve_types", {}).get(role, 1)))
            node.SetNumberOfPointsPerInterpolatingSegment(int(saved.get("curve_segments", {}).get(role, 30)))
        state.pelvic_ball_diameter = diameter
        state.pelvic_active_side = "right" if settings.get("active_side") == "right" else "left"
        state.pelvic_comments = str(settings.get("comments", ""))
        if not state.pelvic_annotator_name:
            state.pelvic_annotator_name = str(settings.get("annotator", ""))
        for key in CUSTOM_LOCKS:
            state[key] = bool(settings.get("custom_locks", {}).get(key, False))
        for side in ("left", "right"):
            for kind in ("neck", "implant_neck"):
                key = f"{side}_{kind}"
                c._axis_options[side, kind] = tuple(settings.get("axis_options", {}).get(key, (False, False)))
        saved_hidden = set(settings.get("hidden_workflows", ()))
        # Older web scenes used one checkbox for both implants. Expand that
        # setting on import, then allow each side to be shown independently.
        c._hidden_workflows = {
            c.visibility_key(key, side) for key in WORKFLOWS for side in ("left", "right")
            if key in saved_hidden or c.visibility_key(key, side) in saved_hidden
        }
        if "fragment_pose" in c._hidden_workflows:
            c._hidden_workflows.discard("fragment_pose")
            c._hidden_workflows.add("bone_fragment")
        for key in WORKFLOWS:
            state[f"pelvic_hide_{key}"] = c.visibility_key(key, state.pelvic_active_side) in c._hidden_workflows
        for kind in CUSTOM_KINDS:
            state[f"pelvic_hide_other_{kind}"] = kind in settings.get("hidden_custom", ())
        lo, hi = settings.get("window", (self.low, self.high))
        if np.isfinite([lo, hi]).all() and hi > lo:
            self.low, self.high, self.invert = float(lo), float(hi), bool(settings.get("invert", self.invert))
        state.pelvic_export_measurements = bool(settings.get("export_measurements", True))
        c.sync_axis_options()
        c.sync_custom_visibility()
        c.update_derived()

    def snapshot(self, controller=None):
        controller = self.controller if controller is None else controller
        state = controller.server.state
        volume = controller.scene.volume
        markups = []
        if volume is not None:
            for node in controller.scene.markups.values():
                if not node.visible:
                    continue
                role = node.GetAttribute(ROLE_ATTRIBUTE)
                if role.endswith("_fragmentBoundary") and node is not controller._active_node:
                    continue
                model = node.classname == "vtkMRMLModelNode"
                path = node.path.points if model else node.points
                if path:
                    kind = (
                        "model"
                        if model
                        else "curve"
                        if node.classname.endswith("CurveNode")
                        else "line"
                        if node.classname.endswith("LineNode")
                        else "points"
                    )
                    image = node.GetAttribute("PXM.TemplateArtwork") if model else None
                    markups.append(
                        dict(
                            **({"artwork": image} if image else {}),
                            role=role,
                            name=node.GetName(),
                            kind=kind,
                            points=[volume.to_image(p) for p in path],
                            color=[round(255 * channel) for channel in node.display.color],
                            locked=node.locked or model,
                            labels=node.labels if node.display.labels else [],
                            curve_type=node.curve_type,
                        )
                    )
        active = controller._active_node
        handles = {}
        visible = {m["role"] for m in markups}
        fragments = controller.fragment_plans()
        fragment_sides = {plan["side"] for plan in fragments}
        for side in ("left", "right"):
            for kind, base in planning.ROTATION_ROLES.items():
                role = f"{side}_{base}"
                drawn = side in fragment_sides if kind == "fragment" else role + "Outline" in visible
                if role not in visible or not drawn:
                    continue
                node = controller.node_for_role(role)
                pivot = node.points[0]
                control = planning.rotation_control(node, kind, side, [-1, 0, 0], [0, 1, 0])
                if control is not None:
                    handles[role] = [volume.to_image(pivot), volume.to_image(pivot + control.ray())]
        return dict(
            rotation_handles=handles,
            template_handles={role: ray for role, ray in handles.items() if role.endswith("Anchor")},
            state=dict(state),
            markups=markups,
            fragments=fragments,
            loaded=volume is not None,
            annotated=self.has_points(),
            active_role=active.GetAttribute(ROLE_ATTRIBUTE) if active else None,
            active_curve=bool(active and active.classname.endswith("CurveNode")),
            image=None
            if volume is None
            else dict(
                dimensions=list(volume.GetDimensions()[:2]),
                spacing=self.image.spacing,
                format=self.image.format,
                physical_spacing=self.image.physical_spacing,
                turns=self.turns,
                mirrored=self.mirrored,
                low=self.low,
                high=self.high,
                invert=self.invert,
                intensity_range=self.intensity_range,
            ),
        )


session = Session()
TRANSFER_ROOT = Path("/transfer")


def read_transfer(name):
    path = TRANSFER_ROOT / name
    try:
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def write_transfer(name, data):
    path = TRANSFER_ROOT / name
    path.write_bytes(data)
    return str(path)


def operation(action, args):
    global session
    s, result, render = session, {}, False
    c = s.controller
    state = s.settings
    if action == "template_image":
        from PIL import Image
        png = planning.artwork_bytes(args["digest"])
        with Image.open(BytesIO(png)) as drawing:
            grid = planning.artwork_hit_grid(np.asarray(drawing.convert("RGBA").getchannel("A")))
        return {"grid": list(grid.shape), "files": {"png": write_transfer("implant.png", png),
                "hit": write_transfer("implant-hit.bin", grid.astype(np.uint8).tobytes())}}
    if action == "configure":
        result.update(
            version=VERSION,
            sections=[
                {"label": label, "tools": [{"key": w.key, "label": w.label} for w in rows]}
                for label, rows in WORKFLOW_SECTIONS
            ],
            result_keys=list(MEASUREMENTS),
            planning_catalog=catalog_menu(),
            file_suffixes=FILE_SUFFIXES,
        )
    elif action == "load":
        # Self-contained scene decoding is transactional. The previous case is
        # still in memory if decoding, restoring or generating a preview fails.
        candidate = Session(args.get("annotator", state.pelvic_annotator_name), state.pelvic_ball_diameter)
        content = read_transfer("image")
        related = read_transfer("companion") if args.get("companion") else None
        candidate.open(args["filename"], content, related)
        if args.get("case_name"):
            candidate.case_name = args["case_name"]
        if args.get("saved_csv"):
            candidate.restore(read_csv(read_transfer("annotations")))
            candidate.settings.pelvic_instruction = "Saved coordinates and comments restored."
        if args.get("cached"):
            candidate.restore(args["cached"])
            candidate.settings.pelvic_instruction = "Working annotations restored."
        s = candidate
        render = True
    elif action == "close":
        s = session = Session(args.get("annotator", state.pelvic_annotator_name), state.pelvic_ball_diameter)
    elif action == "serialize":
        result["saved"] = s.serialize() if s.image is not None else None
    elif action == "restore_csv":
        if s.image is None:
            raise ValueError("Open the corresponding radiograph before importing annotations.")
        # Import into a candidate. A malformed setting must not erase existing
        # annotations before the entire import and its preview have succeeded.
        s = deepcopy(s, {id(s.image): s.image, id(s.base_image): s.base_image, id(s.scene.volume): s.scene.volume})
        s.restore(read_csv(read_transfer("annotations")))
        s.settings.pelvic_instruction = "Saved coordinates and comments restored."
        render = True
    elif action == "import_overlays":
        count = planning.import_overlays(read_transfer("overlays"))
        c.update_derived()
        result["planning_catalog"] = catalog_menu()
        state.pelvic_instruction = f"{count} overlay entries available for this session."
    elif action == "fragment":
        c.retained_bone(args.get("mode", "auto"), args.get("cut"))
    elif action == "planning_options":
        c.planning_options(args)
    elif action == "tool":
        if args["key"] == "bone_fragment":
            c.retained_bone(kind=args.get("cut"))
        else:
            c.start(args["key"])
    elif action == "place":
        result["edited"] = c.place(float(args["x"]), float(args["y"]))
    elif action in {"move", "preview_move"}:
        volume = s.scene.volume
        if volume is None:
            return {"edited": False, **s.snapshot()}
        if action == "preview_move":
            # Constrained geometry may adjust several nodes in one move. Preview
            # from the committed scene each time so the drag path cannot affect
            # saved points or the final result. The read-only volume is shared.
            preview_state = State(deepcopy(dict(state)))
            c = deepcopy(c, {id(volume): volume, id(state): preview_state})
        edited = c.move(args["role"], int(args["index"]), float(args["x"]), float(args["y"]))
        if action == "preview_move":
            return {"edited": True, **s.snapshot(c)} if edited else {"edited": False}
        result["edited"] = edited
    elif action == "finish":
        c.expire_placement()
    elif action == "hide":
        key, hidden = args["key"], bool(args["hidden"])
        if key in WORKFLOWS:
            c.set_workflow_hidden(key, hidden)
        elif key in {f"other_{kind}" for kind in CUSTOM_KINDS}:
            c.set_custom_hidden(key.removeprefix("other_"), hidden)
    elif action == "side":
        c.store_axis_options()
        c.finish(silent=True)
        state.pelvic_active_side = "right" if args["side"] == "right" else "left"
        c.sync_axis_options()
        state.pelvic_instruction = "Choose a measurement tool for the active side."
        c.update_derived()
    elif action == "ball":
        diameter = float(args["value"])
        if not 0 < diameter < 1000 or not np.isfinite(diameter):
            raise ValueError("Enter a positive calibration-ball diameter below 1,000 mm.")
        state.pelvic_ball_diameter = diameter
        c.update_derived()
    elif action == "axis":
        kind, option = args["kind"], args["option"]
        if kind not in ("neck", "implant_neck") or option not in ("use_single_guide", "lock_to_center"):
            raise ValueError("Unrecognised neck-axis setting.")
        state[f"pelvic_{kind}_{option}"] = bool(args["checked"])
        c.store_axis_options()
        c.update_derived()
    elif action == "custom":
        kind = args["kind"]
        if kind not in CUSTOM_KINDS:
            raise ValueError("Unrecognised custom tool.")
        if "count" in args:
            c.set_custom_count(kind, args["count"])
        else:
            c.add_custom(kind)
    elif action == "lock":
        key = f"pelvic_other_{args['kind']}_{args['mode']}"
        if key not in CUSTOM_LOCKS:
            raise ValueError("Unrecognised reference lock.")
        state[key] = bool(args["checked"])
        other = "parallel" if args["mode"] == "perpendicular" else "perpendicular"
        if state[key]:
            state[f"pelvic_other_{args['kind']}_{other}"] = False
        c.update_derived()
    elif action == "auto_open":
        s.auto._prepare()
        result["suggestions"] = {
            "side": s.auto.side,
            "mode": s.auto.mode,
            "features": [
                {"key": key, "label": label, "available": key in s.auto.available}
                for key, label, _ in feature_specs(s.auto.mode)
            ],
        }
    elif action == "auto_place":
        s.auto._prepare()
        for key in s.auto.available:
            state[f"pelvic_auto_{key}"] = key in args["selected"]
        s.auto.place_selected()
    elif action == "orient":
        if s.image is None or s.has_points():
            raise ValueError("Set image orientation before placing annotations.")
        if args["operation"] == "rotate":
            s.turns = (s.turns + (-1 if s.mirrored else 1)) % 4
        elif args["operation"] == "mirror":
            s.mirrored = not s.mirrored
        else:
            raise ValueError("Unrecognised image orientation operation.")
        s.orient()
        c.update_derived()
        render = True
    elif action in {"window", "preview_window"}:
        lo, hi = float(args["low"]), float(args["high"])
        if not np.isfinite([lo, hi]).all() or hi <= lo:
            raise ValueError("Window minimum must be less than its maximum.")
        if s.image is None:
            raise ValueError("Open a radiograph first.")
        if action == "preview_window":
            return {"preview": write_transfer("preview.png", display_png(s.image, lo, hi, bool(args["invert"])))}
        s.low, s.high, s.invert = lo, hi, bool(args["invert"])
        render = True
    elif action == "notes":
        state.pelvic_annotator_name = str(args["annotator"]).strip()
        state.pelvic_comments = str(args["comments"])
        state.pelvic_export_measurements = bool(args["values"])
    elif action == "export":
        if s.image is None:
            raise ValueError("Open a radiograph first.")
        annotator = (state.pelvic_annotator_name or "").strip()
        if not annotator:
            raise ValueError("Enter the annotator name before exporting.")
        results = {}
        settings = s.get_settings()
        kind = args["kind"]
        if kind in ("all", "csv"):
            path = TRANSFER_ROOT / "measurements.csv"
            path.unlink(missing_ok=True)
            write_case_csv(path, s.controller, s.case_name, annotator)
            append_csv_metadata(path, settings, s.base_image)
            results["csv"] = str(path)
        if kind in ("all", "scene"):
            results["mrb"] = write_transfer("scene.mrb", write_mrb(s.image, s.controller, s.case_name, settings))
        result["files"] = results
    elif action == "zip":
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
            for filename, key in args["entries"]:
                if "/" in filename or "\\" in filename or key not in {"csv", "mrb", "png"}:
                    raise ValueError("Invalid export filename.")
                archive.writestr(filename, read_transfer(key))
        result["files"] = {"zip": write_transfer("export.zip", buffer.getvalue())}
    else:
        raise ValueError("Unrecognised app action.")
    if render:
        result["preview"] = write_transfer("preview.png", display_png(s.image, s.low, s.high, s.invert))
    result.update(s.snapshot())
    session = s
    return result


def dispatch(action, text):
    try:
        return json.dumps(operation(action, json.loads(text)), allow_nan=False)
    except (BadZipFile, ET.ParseError, csv.Error, KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        if action == "preview_move":
            raise  # The worker records the cause locally and keeps the committed scene.
        message = str(exc) if isinstance(exc, ValueError) and str(exc) else "The file or settings could not be read."
        return json.dumps({"error": message})
