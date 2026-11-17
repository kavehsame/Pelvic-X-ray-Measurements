"""Guided placement and measurement calculations for the local web scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from contextlib import contextmanager

import numpy as np
from .scene import CurvePath as vtkPolyData, vtkVector3d, ellipse_path as ellipsoid_surface_polydata

from .schema import NODE_SPECS, ROLE_ATTRIBUTE, POINT_GLYPH_FACTOR, side_role
from .custom import CustomMeasurementMixin, custom_spec
from .landmarks import LandmarkReuseMixin
from .geometry import (
    acute_angle_between_directions,
    best_common_perpendicular,
    canal_calcar_ratio,
    ellipse_from_points_in_plane,
    image_axes_from_volume,
    image_right_direction,
    image_up_direction,
    lateral_reference_direction,
    superior_reference_direction,
    signed_angle_from_base,
    version_angle,
    oriented_angle_between_directions,
    obtuse_angle_between_directions,
    unit_vector,
)


@dataclass(frozen=True)
class PlacementStep:
    """One MRML markup node that the user must define."""

    base_role: str
    instruction: str
    bilateral: bool = True
    persistent: bool = False


@dataclass(frozen=True)
class PlacementWorkflow:
    """A button-visible sequence of markup placement steps."""

    key: str
    label: str
    steps: tuple[PlacementStep, ...]


def _line(role: str, instruction: str, *, bilateral: bool = True) -> PlacementStep:
    return PlacementStep(role, instruction, bilateral=bilateral)


def _points(role: str, instruction: str, *, bilateral: bool = True) -> PlacementStep:
    return PlacementStep(role, instruction, bilateral=bilateral, persistent=True)


WORKFLOW_SECTIONS: tuple[tuple[str, tuple[PlacementWorkflow, ...]], ...] = (
    (
        "1: Setup",
        (
            PlacementWorkflow(
                "calibration",
                "Calibration Ball",
                (_points("calibrationPoints", "Place 3 points on the calibration-ball boundary.", bilateral=False),),
            ),
            PlacementWorkflow(
                "reference",
                "Reference Line",
                (
                    _line(
                        "referenceLine",
                        "Draw the pelvic reference line at the level of the two teardrops whenever feasible.",
                        bilateral=False,
                    ),
                ),
            ),
        ),
    ),
    (
        "2: Pre-Operative",
        (
            PlacementWorkflow(
                "femur_head",
                "Femur Head",
                (_points("femurHeadPoints", "Place 3 points on the femoral-head boundary."),),
            ),
            PlacementWorkflow(
                "shaft_axis",
                "Femoral Shaft Axis",
                (
                    _line("shaftGuideProximal", "Draw the proximal shaft-width guide line."),
                    _line("shaftGuideDistal", "Draw the distal shaft-width guide line."),
                ),
            ),
            PlacementWorkflow(
                "neck_axis",
                "Femoral Neck Axis",
                (
                    _line("neckGuideProximal", "Draw the first femoral-neck guide line."),
                    _line("neckGuideDistal", "Draw the second femoral-neck guide line."),
                ),
            ),
            PlacementWorkflow(
                "tonnis",
                "Acetabular Index (Tönnis)",
                (_line("tonnisAngleLine", "Draw from the medial sourcil/base point to the lateral sourcil."),),
            ),
            PlacementWorkflow(
                "sharp",
                "Sharp Angle",
                (_line("sharpAngleLine", "Draw from the teardrop/base point to the lateral acetabular point."),),
            ),
            PlacementWorkflow("lce", "LCE Angle", (_points("lceAnglePoint", "Place the lateral-center-edge point."),)),
            PlacementWorkflow(
                "acetabular_offset",
                "Acetabular Offset",
                (
                    _line("acetabularOffsetLineA", "Draw the first acetabular-offset construction line."),
                    _line("acetabularOffsetLineB", "Draw the second acetabular-offset construction line."),
                ),
            ),
            PlacementWorkflow(
                "femoral_offset", "Femoral Offset", (_line("femoralOffsetLine", "Draw the femoral-offset line."),)
            ),
            PlacementWorkflow(
                "extrusion",
                "Femoral Head Extrusion Index",
                (
                    _line("extrusionIndexMedialLine", "Draw the medial extrusion-index line."),
                    _line("extrusionIndexMiddleLine", "Draw the middle extrusion-index line."),
                    _line("extrusionIndexLateralLine", "Draw the lateral extrusion-index line."),
                ),
            ),
            PlacementWorkflow(
                "morphology",
                "Femur Shaft Morphology",
                (
                    _points(
                        "shaftMorphologyLTPoints", "Place the proximal and distal lesser-trochanter reference points."
                    ),
                ),
            ),
            PlacementWorkflow(
                "lld",
                "Leg Length Discrepancy",
                (_points("lldPoints", "Place the left and right lesser-trochanter points.", bilateral=False),),
            ),
        ),
    ),
    (
        "3: Post-Operative (THA)",
        (
            PlacementWorkflow(
                "implant_head",
                "Implant Head Center",
                (_points("implantHeadPoints", "Place 3 points on the implant-head boundary."),),
            ),
            PlacementWorkflow(
                "inclination",
                "Acetabular Inclination Angle (Free Hand)",
                (_line("acetabularInclinationLine", "Draw the cup inclination line."),),
            ),
            PlacementWorkflow(
                "cup_opening",
                "Cup Opening Ellipse Fit",
                (_points("cupOpeningEllipsePoints", "Place 6 points around the cup-opening ellipse."),),
            ),
            PlacementWorkflow(
                "implant_neck",
                "Implant Neck Axis",
                (
                    _line("implantNeckGuideProximal", "Draw the first implant-neck guide line."),
                    _line("implantNeckGuideDistal", "Draw the second implant-neck guide line."),
                ),
            ),
            PlacementWorkflow(
                "post_shaft_axis",
                "Femoral Shaft Axis",
                (
                    _line("shaftGuideProximal", "Draw the proximal shaft-width guide line."),
                    _line("shaftGuideDistal", "Draw the distal shaft-width guide line."),
                ),
            ),
            PlacementWorkflow(
                "stem_alignment",
                "Stem Alignment",
                (
                    _line("implantAlignmentGuideProximal", "Draw the proximal stem-alignment guide line."),
                    _line("implantAlignmentGuideDistal", "Draw the distal stem-alignment guide line."),
                ),
            ),
            PlacementWorkflow(
                "post_acetabular_offset",
                "Acetabular Offset",
                (
                    _line("postOpAcetabularOffsetLineA", "Draw the first postoperative acetabular-offset line."),
                    _line("postOpAcetabularOffsetLineB", "Draw the second postoperative acetabular-offset line."),
                ),
            ),
            PlacementWorkflow(
                "post_femoral_offset",
                "Femoral Offset",
                (_line("postOpFemoralOffsetLine", "Draw the postoperative femoral-offset line."),),
            ),
        ),
    ),
    (
        "5: Contours",
        tuple(
            PlacementWorkflow(
                key,
                label,
                (
                    PlacementStep(
                        role,
                        f"Place points along the {label.lower()}; press Escape or click this tool again when complete.",
                        persistent=True,
                    ),
                ),
            )
            for key, label, role in (
                ("iliopectineal", "Iliopectineal Line", "iliopectinealLine"),
                ("ilioischial", "Ilioischial Line", "ilioischialLine"),
                ("shenton", "Shenton Line", "shentonLine"),
                ("sourcil", "Acetabular Roof (Sourcil)", "acetabularRoofSourcil"),
                ("linea_terminalis", "Linea Terminalis", "lineaTerminalis"),
                ("shaft_contour", "Femoral Shaft", "femoralShaftContour1"),
            )
        ),
    ),
)


WORKFLOWS = {workflow.key: workflow for _, workflows in WORKFLOW_SECTIONS for workflow in workflows}
# Keep UI status, Hide, placement and CSV roles on the same four-curve definition.
shaft_workflow = PlacementWorkflow(
    "shaft_contour",
    "Femoral Shaft",
    tuple(
        PlacementStep(f"femoralShaftContour{i}", f"Place shaft contour {i}/4; right-click to advance.", persistent=True)
        for i in range(1, 5)
    ),
)
WORKFLOW_SECTIONS = tuple(
    (section, tuple(shaft_workflow if w.key == "shaft_contour" else w for w in workflows))
    for section, workflows in WORKFLOW_SECTIONS
)
WORKFLOWS["shaft_contour"] = shaft_workflow

SHARED_POINT_TOOLS = frozenset({"tonnis", "sharp", "lce", "acetabular_offset", "femoral_offset", "extrusion"})
NEXT_SHARED_ATTRIBUTE = "PelvicXrayMeasurements.NextUseSharedPoints"


class BrowserPlacementController(CustomMeasurementMixin, LandmarkReuseMixin):
    """Translate browser button presses into this fork's MRML markup roles."""

    def __init__(self, server, slicer_app):
        self.server = server
        self.slicer_app = slicer_app
        self.scene = slicer_app.scene
        self._steps: list[tuple[str, PlacementStep]] = []
        self._step_index = -1
        self._active_node = None
        self._observer_tags: list[int] = []
        self._transitioning = False
        self._circle_observers: dict[str, tuple[object, list[int]]] = {}
        self._source_observers: dict[str, tuple[object, list[int]]] = {}
        self._refreshing_circles: set[str] = set()
        self._updating = False
        self._hidden_workflows: set[str] = set()
        self._workflow_key: str | None = None
        self._pending_completion = None
        self._pending_refresh = None
        self._write_depth = 0
        self._morphology_free_stations = {}
        self._ellipses = {}
        self._axis_options = {}
        self._numeric_results = {}
        self.pending_auto_line_endpoints = {}
        self._pending_contours = set()
        self._custom_measurements = {kind: [] for kind in ("point", "line", "angle")}

    def axis_options(self, side, kind):
        """Read options from the side's guide, including saved MRB scenes."""
        base = "neckGuideProximal" if kind == "neck" else "implantNeckGuideProximal"
        node = self.node_for_role(side_role(side, base))
        if node is not None:
            lock = node.GetAttribute("PelvicXrayMeasurements.LockToCenter")
            single = node.GetAttribute("PelvicXrayMeasurements.UseSingleGuide")
            if lock is not None and single is not None:
                return lock == "1", single == "1"
        if (side, kind) in self._axis_options:
            return self._axis_options[side, kind]
        return (False, False) if kind == "neck" else (True, True)

    def store_axis_options(self):
        """Apply visible controls to the active side without altering the other side."""
        side = str(self.server.state.pelvic_active_side or "left")
        for kind in ("neck", "implant_neck"):
            prefix = f"pelvic_{kind}"
            values = (
                bool(self.server.state[f"{prefix}_lock_to_center"]),
                bool(self.server.state[f"{prefix}_use_single_guide"]),
            )
            self._axis_options[side, kind] = values
            base = "neckGuideProximal" if kind == "neck" else "implantNeckGuideProximal"
            node = self.node_for_role(side_role(side, base))
            if node is not None:
                node.SetAttribute("PelvicXrayMeasurements.LockToCenter", "1" if values[0] else "0")
                node.SetAttribute("PelvicXrayMeasurements.UseSingleGuide", "1" if values[1] else "0")

    def sync_axis_options(self):
        side = str(self.server.state.pelvic_active_side or "left")
        for kind in ("neck", "implant_neck"):
            lock, single = self.axis_options(side, kind)
            self.server.state[f"pelvic_{kind}_lock_to_center"] = lock
            self.server.state[f"pelvic_{kind}_use_single_guide"] = single

    def start(self, workflow_key: str) -> None:
        """Start a tool, alternating shared/manual redraws independently per side."""
        if (
            self._active_node is not None
            and self._workflow_key == workflow_key
            and self._active_node.IsA("vtkMRMLMarkupsCurveNode")
        ):
            if workflow_key == "shaft_contour" and self._active_node.GetNumberOfDefinedControlPoints() < 2:
                self.server.state.pelvic_instruction = "Place at least two contour points before advancing."
                return
            if workflow_key == "shaft_contour" and self._step_index < 3:
                for tag in self._observer_tags:
                    self._active_node.RemoveObserver(tag)
                self._observer_tags = []
                self._step_index += 1
                self._activate_step()
                return
            self.finish()
            self.update_derived()
            return
        self.store_axis_options()
        self.update_derived()
        workflow = WORKFLOWS[workflow_key]
        side = str(self.server.state.pelvic_active_side or "left")
        missing = self.missing_dependencies(workflow_key, side)
        if missing:
            self.server.state.pelvic_instruction = "Requires " + ", ".join(missing) + " before this tool can be used."
            return
        self.finish(silent=True)
        self._workflow_key = workflow_key
        steps = list(workflow.steps)
        # The extension exposes these options before placement. A single guide is
        # sufficient only when the derived axis is constrained through the head center.
        if workflow_key == "neck_axis" and bool(getattr(self.server.state, "pelvic_neck_use_single_guide", False)):
            steps = steps[:1]
        if workflow_key == "implant_neck" and bool(
            getattr(self.server.state, "pelvic_implant_neck_use_single_guide", True)
        ):
            steps = steps[:1]
        self._steps = [(side_role(side, step.base_role) if step.bilateral else step.base_role, step) for step in steps]
        previous = self.node_for_role(self._steps[0][0])
        next_shared = previous.GetAttribute(NEXT_SHARED_ATTRIBUTE) if previous is not None else None
        use_shared = (next_shared == "1") if next_shared is not None else True
        for role, _step in self._steps:
            self._remove_role(role)
            if role.endswith(("_sharpAngleLine", "_tonnisAngleLine")):
                self._remove_role(role.removesuffix("Line") + "ReferenceArm")
            if role.endswith("_lceAnglePoint"):
                for base in ("lceAngleVisual", "lceAngleRadialArm"):
                    self._remove_role(side_role(side, base))
            if role == "calibrationPoints":
                self._clear_circle_model("calibrationCircle")
            elif role == "lldPoints":
                for derived_role in ("lldLeftParallel", "lldRightParallel", "lldHeightDifference"):
                    self._remove_role(derived_role)
            elif role.endswith("_shaftMorphologyLTPoints"):
                for base_role in (
                    "shaftMorphologyMidline",
                    "shaftMorphologyPoints",
                    "shaftMorphologyGuideLineA",
                    "shaftMorphologyGuideLineB",
                ):
                    self._remove_role(side_role(side, base_role))
            elif role.endswith("_femurHeadPoints") or role.endswith("_implantHeadPoints"):
                circle_role = role.replace("Points", "Circle")
                center_role = role.replace("Points", "Center")
                self._clear_circle_model(circle_role)
                self._remove_role(center_role)
        self._step_index = 0
        instruction = self.seed_shared_landmarks(workflow_key, side) if use_shared else None
        if instruction:
            self._steps[0] = (
                self._steps[0][0],
                PlacementStep(
                    self._steps[0][1].base_role,
                    instruction + " The lateral sourcil is already available and will be added automatically.",
                    bilateral=True,
                ),
            )
        self.server.state.pelvic_active_tool = (
            f"{side.title()} {workflow.label}" if workflow.steps[0].bilateral else workflow.label
        )
        self.server.state.pelvic_active_key = workflow_key
        self._hidden_workflows.discard(workflow_key)
        self.server.state[f"pelvic_hide_{workflow_key}"] = False
        self._activate_step()
        if workflow_key in SHARED_POINT_TOOLS:
            self.node_for_role(self._steps[0][0]).SetAttribute(NEXT_SHARED_ATTRIBUTE, "0" if use_shared else "1")
        self.update_derived()

    def missing_dependencies(self, key, side=None):
        """Use one prerequisite map for disabled buttons and placement guards."""
        side = side or str(self.server.state.pelvic_active_side or "left")
        missing = []
        if self.current_image_node() is None:
            missing.append("an image")
        reference = self.points_for_role("referenceLine")
        reference_ready = len(reference) >= 2 and np.linalg.norm(reference[1] - reference[0]) > 1e-6
        if (
            key
            in {
                "tonnis",
                "sharp",
                "lce",
                "acetabular_offset",
                "extrusion",
                "lld",
                "inclination",
                "cup_opening",
                "post_acetabular_offset",
            }
            and not reference_ready
        ):
            missing.append("the Reference Line")
        shaft = self.points_for_role(side_role(side, "shaftAxis"))
        if key in {"femoral_offset", "post_femoral_offset", "stem_alignment", "morphology"} and len(shaft) < 2:
            missing.append("the active-side Femoral Shaft Axis")
        if key == "lce" and not self.latest_results["sides"][side]["femurHead"]["defined"]:
            missing.append("the active-side Femur Head")
        if key in {"neck_axis", "implant_neck"}:
            kind = "neck" if key == "neck_axis" else "implant_neck"
            center = "femurHeadCenter" if key == "neck_axis" else "implantHeadCenter"
            if self.axis_options(side, kind)[0] and not self.points_for_role(side_role(side, center)):
                missing.append("the active-side " + ("Femur Head" if key == "neck_axis" else "Implant Head"))
        if key == "morphology" and self._calibration_scale() is None:
            missing.append("a defined Calibration Ball")
        return missing

    def finish(self, silent: bool = False) -> None:
        if self._pending_completion is not None:
            self._pending_completion.cancel()
            self._pending_completion = None
        if self._active_node is not None:
            for tag in self._observer_tags:
                self._active_node.RemoveObserver(tag)
            for index in reversed(range(self._active_node.GetNumberOfControlPoints())):
                if self._active_node.GetNthControlPointPositionStatus(index) != self._active_node.PositionDefined:
                    self._active_node.RemoveNthControlPoint(index)
        self._observer_tags = []
        self._active_node = None
        self._transitioning = False
        self.slicer_app.markups_logic.disable_place_mode()
        self.pending_auto_line_endpoints.clear()
        self.server.state.pelvic_active_key = ""
        if not silent:
            self.server.state.pelvic_instruction = (
                "Placement finished. Choose another measurement or edit existing points in the view."
            )
            self.server.state.pelvic_active_tool = "None"

    def _finish_from_shortcut(self, node_id):
        if self._active_node is not None and self._active_node.GetID() == node_id:
            if self._workflow_key == "shaft_contour":
                self.start("shaft_contour")
            else:
                self.finish()
            self.update_derived()

    def reset_scene_state(self):
        """Detach callbacks and cached constraints before another case replaces the scene."""
        self.finish(silent=True)
        if self._pending_refresh is not None:
            self._pending_refresh.cancel()
            self._pending_refresh = None
        for registry in (self._source_observers, self._circle_observers):
            for node, tags in registry.values():
                for tag in tags:
                    node.RemoveObserver(tag)
            registry.clear()
        self._morphology_free_stations.clear()
        self._ellipses.clear()
        self._axis_options.clear()
        self._pending_contours.clear()
        self.pending_auto_line_endpoints.clear()

    def restore_source_observers(self):
        """Reconnect editable guides and LT points loaded from a saved scene."""
        for node in self.scene.GetNodesByClass("vtkMRMLMarkupsNode"):
            role = node.GetAttribute(ROLE_ATTRIBUTE)
            if role in NODE_SPECS or custom_spec(role or ""):
                self._configure_node(node, self._node_spec(role))
                self._watch_source(role, node)
                self._watch_circle_source(role, node)
        self.sync_custom_visibility()

    def _node_spec(self, role):
        """Resolve built-in and numbered custom roles from this fork's own schema."""
        spec = NODE_SPECS.get(role) or custom_spec(role)
        if spec is None:
            raise ValueError(f"Unknown markup role: {role}")
        return spec

    def _complete_step(self, node_id) -> None:
        self._pending_completion = None
        if self._active_node is None or self._active_node.GetID() != node_id:
            return
        caller = self._active_node
        self._transitioning = True
        try:
            role, _ = self._steps[self._step_index]
            self._complete_pending_auto_line_endpoint(role)
            spec = self._node_spec(role)
            required = int(spec.get("completionCount", self._default_completion(spec)))
            if caller.GetNumberOfDefinedControlPoints() < required:
                self._transitioning = False
                return
            for tag in self._observer_tags:
                caller.RemoveObserver(tag)
            self._observer_tags = []
            self._active_node = None
            self._step_index += 1
            if self._step_index < len(self._steps):
                self._transitioning = False
                self._activate_step()
            else:
                self.finish()
                self.update_derived()
        finally:
            if self._active_node is None:
                self._transitioning = False

    def node_for_role(self, role: str):
        """Find a named markup without depending on the desktop extension."""

        nodes = self.scene.GetNodesByClass("vtkMRMLMarkupsNode")
        nodes.InitTraversal()
        while True:
            node = nodes.GetNextItemAsObject()
            if node is None:
                return None
            if node.GetAttribute(ROLE_ATTRIBUTE) == role:
                return node

    def points_for_role(self, role: str) -> list[np.ndarray]:
        """Return defined world coordinates in markup order."""

        node = self.node_for_role(role)
        if node is None:
            return []
        points = []
        for index in range(node.GetNumberOfControlPoints()):
            if node.GetNthControlPointPositionStatus(index) != node.PositionDefined:
                continue
            point = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, point)
            points.append(np.asarray(point, dtype=float))
        return points

    def put_points(self, role: str, points, *, derived: bool = False) -> None:
        """Create or update an editable role node from explicit world coordinates."""

        spec = self._node_spec(role)
        node = self.node_for_role(role)
        if node is None:
            node = self.scene.AddNewNodeByClass(str(spec["className"]), str(spec["name"]))
            node.SetAttribute(ROLE_ATTRIBUTE, role)
            self._configure_node(node, spec)
        self._watch_circle_source(role, node)
        self._watch_source(role, node)
        points = list(points)
        # Update in place, retaining point IDs and the handle being dragged.
        # Block observer-driven recomputation until the entire node is written.
        with self.scene_edit():
            modifying = node.StartModify()
            try:
                while node.GetNumberOfControlPoints() > len(points):
                    node.RemoveNthControlPoint(node.GetNumberOfControlPoints() - 1)
                for index, point in enumerate(points):
                    value = vtkVector3d(*[float(component) for component in point])
                    if index < node.GetNumberOfControlPoints():
                        old = [0.0, 0.0, 0.0]
                        node.GetNthControlPointPositionWorld(index, old)
                        if (
                            not np.allclose(old, point, atol=1e-8, rtol=0.0)
                            or node.GetNthControlPointPositionStatus(index) != node.PositionDefined
                        ):
                            node.SetNthControlPointPositionWorld(index, value)
                    else:
                        node.AddControlPointWorld(value)
                    labels = spec.get("labels", ())
                    if index < len(labels):
                        node.SetNthControlPointLabel(index, str(labels[index]))
                node.SetLocked(bool(derived))
            finally:
                node.EndModify(modifying)

    @contextmanager
    def scene_edit(self):
        """Write one coherent construction before its source observers run."""
        self._write_depth += 1
        try:
            yield
        finally:
            self._write_depth -= 1

    @staticmethod
    def circle_from_three(points: list[np.ndarray]) -> tuple[np.ndarray, float]:
        """Fit a 2D circle to three image-plane points; reject collinearity."""

        if len(points) < 3:
            raise ValueError("Three head boundary points are required.")
        xy = np.asarray(points[:3], dtype=float)[:, :2]
        matrix = 2.0 * (xy[1:] - xy[0])
        if abs(float(np.linalg.det(matrix))) < 1e-8:
            raise ValueError("Head boundary points are nearly collinear.")
        center_xy = np.linalg.solve(matrix, np.sum(xy[1:] ** 2, axis=1) - np.sum(xy[0] ** 2))
        center = np.array([center_xy[0], center_xy[1], float(points[0][2])])
        return center, 2.0 * float(np.linalg.norm(xy[0] - center_xy))

    def update_derived(self) -> None:
        """Refresh fitted circles, axes, visible angle constructions, and result fields."""
        if self._updating or self._write_depth:
            return
        self._updating = True
        try:
            self._refresh_circle("calibrationPoints", "calibrationCircle")
            calibration_source = self.node_for_role("calibrationPoints")
            if calibration_source is not None:
                self._watch_circle_source("calibrationPoints", calibration_source)
            for side in ("left", "right"):
                for base, center_role, circle_role in (
                    ("femurHeadPoints", "femurHeadCenter", "femurHeadCircle"),
                    ("implantHeadPoints", "implantHeadCenter", "implantHeadCircle"),
                ):
                    source_role = side_role(side, base)
                    self._refresh_circle(source_role, side_role(side, circle_role), side_role(side, center_role))
                    source = self.node_for_role(source_role)
                    if source is not None:
                        self._watch_circle_source(source_role, source)
                self._update_axes_for_side(side)
                self._update_morphology_for_side(side)
                self._refresh_cup_opening_ellipse(side)
                self._update_angle_constructions(side)
                self._classify_shaft_contours(side)
            self._update_lld()
            self._sync_active_side_badge()
            self._update_result_fields()
            self._update_tool_states()
            self._update_custom_measurements()
        finally:
            self._updating = False

    def _update_tool_states(self):
        """Applied means every required input is defined on the active side."""
        side = str(self.server.state.pelvic_active_side or "left")
        for key, workflow in WORKFLOWS.items():
            missing = self.missing_dependencies(key, side)
            self.server.state[f"pelvic_enabled_{key}"] = not missing
            self.server.state[f"pelvic_dependency_{key}"] = (
                "Requires " + ", ".join(missing) + "." if missing else "Ready"
            )
            steps = list(workflow.steps)
            if key in {"neck_axis", "implant_neck"}:
                kind = "neck" if key == "neck_axis" else "implant_neck"
                if self.axis_options(side, kind)[1]:
                    steps = steps[:1]
            complete = True
            for step in steps:
                role = side_role(side, step.base_role) if step.bilateral else step.base_role
                count = len(self.points_for_role(role))
                required = int(NODE_SPECS[role].get("completionCount", self._default_completion(NODE_SPECS[role])))
                complete = complete and count >= (required if required > 0 else 2)
            model_base = {
                "calibration": "calibrationCircle",
                "femur_head": "femurHeadCircle",
                "implant_head": "implantHeadCircle",
                "cup_opening": "cupOpeningEllipse",
            }.get(key)
            if model_base:
                model_role = model_base if key == "calibration" else side_role(side, model_base)
                model = self._existing_model_for_role(model_role)
                complete = (
                    complete
                    and model is not None
                    and model.GetPolyData() is not None
                    and model.GetPolyData().GetNumberOfPoints() > 0
                )
            axis_base = {
                "shaft_axis": "shaftAxis",
                "post_shaft_axis": "shaftAxis",
                "neck_axis": "neckAxis",
                "implant_neck": "implantNeckAxis",
                "stem_alignment": "implantAlignmentLine",
            }.get(key)
            if axis_base:
                complete = complete and len(self.points_for_role(side_role(side, axis_base))) >= 2
            if key == "morphology":
                complete = complete and len(self.points_for_role(side_role(side, "shaftMorphologyPoints"))) == 10
            self.server.state[f"pelvic_applied_{key}"] = bool(complete)
        reference = self.points_for_role("referenceLine")
        native = bool(self.points_for_role(side_role(side, "femurHeadCenter")))
        implant = bool(self.points_for_role(side_role(side, "implantHeadCenter")))
        self.server.state.pelvic_auto_enabled = bool(
            self.current_image_node() is not None
            and self._calibration_scale() is not None
            and len(reference) >= 2
            and np.linalg.norm(reference[1] - reference[0]) > 1e-6
            and native != implant
        )

    def _update_axes_for_side(self, side: str) -> None:
        neck_lock, neck_single = self.axis_options(side, "neck")
        implant_lock, implant_single = self.axis_options(side, "implant_neck")
        axes = (
            ("shaftGuideProximal", "shaftGuideDistal", "shaftAxis", None, False, False),
            ("neckGuideProximal", "neckGuideDistal", "neckAxis", "femurHeadCenter", neck_lock, neck_single),
            (
                "implantAlignmentGuideProximal",
                "implantAlignmentGuideDistal",
                "implantAlignmentLine",
                None,
                False,
                False,
            ),
            (
                "implantNeckGuideProximal",
                "implantNeckGuideDistal",
                "implantNeckAxis",
                "implantHeadCenter",
                implant_lock,
                implant_single,
            ),
        )
        for guide_a, guide_b, axis_base, center_base, lock_to_center, allow_single_guide in axes:
            first = self.points_for_role(side_role(side, guide_a))
            second = self.points_for_role(side_role(side, guide_b)) if guide_b else []
            if len(first) < 2 or (guide_b and len(second) < 2 and not allow_single_guide):
                self._remove_role(side_role(side, axis_base))
                continue
            directions = [first[1] - first[0]]
            if not allow_single_guide:
                directions.append(second[1] - second[0])
            axis = best_common_perpendicular(directions, np.array([0.0, 0.0, 1.0]))
            if axis is None:
                self._remove_role(side_role(side, axis_base))
                continue
            origin = np.mean(np.asarray(first if allow_single_guide else first + second), axis=0)
            if center_base and lock_to_center:
                centers = self.points_for_role(side_role(side, center_base))
                if centers:
                    origin = centers[0]
                else:
                    self._remove_role(side_role(side, axis_base))
                    continue
            span = self._display_span(first + second) * (0.12 if center_base else 0.48)
            self.put_points(side_role(side, axis_base), [origin - axis * span, origin + axis * span], derived=True)

    @staticmethod
    def _unit_xy(vector: np.ndarray) -> np.ndarray | None:
        vector = np.asarray(vector, dtype=float)[:2]
        length = float(np.linalg.norm(vector))
        return vector / length if length > 1e-8 else None

    def _reference_directions(self, side: str) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
        reference = self.points_for_role("referenceLine")
        if len(reference) < 2:
            return None, None
        lateral = self._unit_xy(reference[1] - reference[0])
        if lateral is None:
            return None, None
        volume = self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode")
        direction = np.array([*lateral, 0.0])
        lateral = lateral_reference_direction(direction, side, volume)
        superior = superior_reference_direction(direction, np.array([0.0, 0.0, 1.0]), volume)
        return (lateral[:2], superior[:2]) if lateral is not None and superior is not None else (None, None)

    def _calibration_scale(self) -> float | None:
        """Return millimetres per scene unit from the fitted calibration ball."""
        try:
            _center, diameter = self.circle_from_three(self.points_for_role("calibrationPoints"))
            expected = float(self.server.state.pelvic_ball_diameter)
        except (TypeError, ValueError):
            return None
        return expected / diameter if expected > 0 and diameter > 1e-8 else None

    def _update_morphology_for_side(self, side: str) -> None:
        """Create the desktop-equivalent calibrated morphology construction from LT landmarks."""
        lt_points = self.points_for_role(side_role(side, "shaftMorphologyLTPoints"))
        shaft_axis = self.points_for_role(side_role(side, "shaftAxis"))
        scale = self._calibration_scale()
        derived_roles = (
            "shaftMorphologyMidline",
            "shaftMorphologyPoints",
            "shaftMorphologyGuideLineA",
            "shaftMorphologyGuideLineB",
        )
        if len(lt_points) < 2 or len(shaft_axis) < 2 or scale is None:
            for role in derived_roles:
                self._remove_role(side_role(side, role))
            self._morphology_free_stations.pop(side, None)
            for key in ("ccr", "cti", "cfi"):
                self._store_result(f"pelvic_result_{side}_{key}", None, "")
            return
        axis_origin = 0.5 * (shaft_axis[0] + shaft_axis[1])
        axis_direction = shaft_axis[1] - shaft_axis[0]
        axis_length = float(np.linalg.norm(axis_direction[:2]))
        if axis_length < 1e-8:
            return
        axis_direction /= axis_length
        up = image_up_direction(self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode"))
        if np.dot(axis_direction, up) < 0:
            axis_direction *= -1
        transverse = np.array([-axis_direction[1], axis_direction[0], 0.0])
        image_right = image_right_direction(self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode"))
        if image_right is not None and np.dot(transverse, image_right) < 0:
            transverse *= -1
        mid_lt = 0.5 * (lt_points[0] + lt_points[1])
        midpoint = axis_origin + axis_direction * float(np.dot(mid_lt - axis_origin, axis_direction))
        mm_to_scene = 1.0 / scale
        self.put_points(
            side_role(side, "shaftMorphologyMidline"),
            [
                midpoint - transverse * 32.0 * mm_to_scene,
                midpoint + transverse * 32.0 * mm_to_scene,
            ],
            derived=True,
        )
        layout = (
            (20.0, -20.0),
            (20.0, 20.0),
            (-30.0, -20.0),
            (-30.0, 20.0),
            (-100.0, -32.0),
            (-100.0, -12.0),
            (-100.0, 12.0),
            (-100.0, 32.0),
            (-110.0, -20.0),
            (-110.0, 20.0),
        )
        existing = self.points_for_role(side_role(side, "shaftMorphologyPoints"))
        # The two 11-cm points form one user-adjustable station in the desktop
        # extension. Preserve that relationship after either point is moved.
        free_indices = (8, 9)
        free_stations = [
            float(np.dot(existing[index] - midpoint, axis_direction)) for index in free_indices if index < len(existing)
        ]
        free_station = float(np.mean(free_stations)) if free_stations else -110.0 * mm_to_scene
        previous = self._morphology_free_stations.get(side)
        if previous is not None and free_stations:
            deltas = [abs(value - previous) for value in free_stations]
            free_station = free_stations[int(np.argmax(deltas))] if max(deltas) > 1e-6 else previous
        self._morphology_free_stations[side] = free_station
        points = []
        for index, (axial_mm, transverse_mm) in enumerate(layout):
            axial_offset = free_station if index in free_indices else axial_mm * mm_to_scene
            station = midpoint + axis_direction * axial_offset
            # Retain a user's transverse adjustment while keeping every point at
            # its calibrated shaft-axis station.
            offset = transverse_mm * mm_to_scene
            if index < len(existing):
                offset = float(np.dot(existing[index] - station, transverse))
            points.append(station + transverse * offset)
        self.put_points(side_role(side, "shaftMorphologyPoints"), points, derived=False)
        for role, indices in (("shaftMorphologyGuideLineA", (2, 5)), ("shaftMorphologyGuideLineB", (3, 6))):
            guide = self._extended_morphology_guide_line(
                points[indices[0]], points[indices[1]], midpoint, axis_direction
            )
            self.put_points(side_role(side, role), guide, derived=True)
            if role.endswith("GuideLineA"):
                guide_a = guide
            else:
                guide_b = guide
        inner_width = float(np.linalg.norm(points[6] - points[5]))
        outer_width = float(np.linalg.norm(points[7] - points[4]))
        proximal_width = float(np.linalg.norm(points[1] - points[0]))
        cap_width = float(np.linalg.norm(guide_b[0] - guide_a[0]))
        self._store_result(
            f"pelvic_result_{side}_ccr",
            canal_calcar_ratio(distal_canal_width=inner_width, proximal_calcar_width=cap_width),
            "",
        )
        self._store_result(
            f"pelvic_result_{side}_cti", (outer_width - inner_width) / outer_width if outer_width > 1e-8 else None, ""
        )
        self._store_result(
            f"pelvic_result_{side}_cfi", proximal_width / inner_width if inner_width > 1e-8 else None, ""
        )

    @staticmethod
    def _extended_morphology_guide_line(
        upper: np.ndarray, lower: np.ndarray, midline: np.ndarray, axis_direction: np.ndarray
    ) -> list[np.ndarray]:
        """Extend a morphology guide precisely to the mid-LT reference level."""
        direction = np.asarray(upper - lower, dtype=float)
        length = float(np.linalg.norm(direction))
        if length < 1e-8:
            return [upper, lower]
        direction /= length
        if float(np.dot(direction, axis_direction)) < 0.0:
            direction *= -1.0
        axial_component = float(np.dot(direction, axis_direction))
        if abs(axial_component) < 1e-8:
            return [upper, lower]
        distance = float(np.dot(midline - lower, axis_direction)) / axial_component
        return [lower + direction * distance, lower] if distance > 0.0 else [upper, lower]

    def _display_span(self, fallback_points: list[np.ndarray]) -> float:
        """Size helper lines from the image extent, then the available points."""
        volume = self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode")
        if volume is not None:
            bounds = [0.0] * 6
            volume.GetRASBounds(bounds)
            extent = max(abs(bounds[1] - bounds[0]), abs(bounds[3] - bounds[2]), abs(bounds[5] - bounds[4]))
            if extent > 1e-8:
                return 0.75 * float(extent)
        if fallback_points:
            extent = float(np.max(np.ptp(np.vstack(fallback_points), axis=0)))
            if extent > 1e-8:
                return 1.5 * extent
        return 150.0

    def _refresh_cup_opening_ellipse(self, side: str) -> None:
        """Fit and display the post-operative cup-opening ellipse from six rim points."""
        role = side_role(side, "cupOpeningEllipse")
        points = self.points_for_role(side_role(side, "cupOpeningEllipsePoints"))
        volume = self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode")
        axes = image_axes_from_volume(volume)
        ellipse = ellipse_from_points_in_plane(points[:6], *axes) if len(points) >= 6 else None
        self._ellipses.pop(side, None)
        self._store_result(f"pelvic_result_{side}_ellipse_inclination", None, "")
        self._store_result(f"pelvic_result_{side}_cup_version", None, "")
        if ellipse is None or len(self.points_for_role("referenceLine")) < 2:
            self._clear_circle_model(role)
            return
        node = self._model_for_role(role)
        node.SetAndObservePolyData(
            ellipsoid_surface_polydata(
                ellipse.center,
                ellipse.major_direction,
                ellipse.minor_direction,
                ellipse.major_radius,
                ellipse.minor_radius,
            )
        )
        self._ellipses[side] = ellipse
        node.SetDisplayVisibility(True)
        reference = self.points_for_role("referenceLine")
        self._store_result(
            f"pelvic_result_{side}_ellipse_inclination",
            acute_angle_between_directions(unit_vector(reference[1] - reference[0]), ellipse.major_direction),
            "°",
        )
        self._store_result(
            f"pelvic_result_{side}_cup_version", version_angle(ellipse.major_radius, ellipse.minor_radius), "°"
        )

    def _update_lld(self) -> None:
        """Draw LLD projections and the perpendicular height-difference construction."""
        points = self.points_for_role("lldPoints")
        reference = self.points_for_role("referenceLine")
        roles = ("lldLeftParallel", "lldRightParallel", "lldHeightDifference")
        if len(points) < 2 or len(reference) < 2:
            self._store_result("pelvic_result_lld", None, "")
            for role in roles:
                self._remove_role(role)
            return
        direction = self._unit_xy(reference[1] - reference[0])
        if direction is None:
            return
        # In RAS image space the patient's left landmark is the point farther
        # along the leftward reference direction; order is independent of clicks.
        left_direction, superior = self._reference_directions("left")
        if left_direction is None:
            return
        positions = [float(np.dot(point[:2] - reference[0][:2], left_direction)) for point in points[:2]]
        left_index = 0 if positions[0] >= positions[1] else 1
        right_index = 1 - left_index
        left, right = points[left_index], points[right_index]
        perpendicular = np.array([*superior, 0.0])
        projected_separation = abs(float(np.dot(right[:2] - left[:2], direction)))
        # Each medial helper covers 60% of the projected separation, so they
        # overlap across the midline as in the desktop extension.
        span = max(0.2 * self._display_span(reference + points), 0.6 * projected_separation)
        left_direction3 = np.array([left_direction[0], left_direction[1], 0.0])
        self.put_points("lldLeftParallel", [left, left - left_direction3 * span], derived=True)
        self.put_points("lldRightParallel", [right, right + left_direction3 * span], derived=True)
        midpoint_coordinate = 0.5 * (float(np.dot(left[:2], direction)) + float(np.dot(right[:2], direction)))
        left_height = left.copy()
        right_height = right.copy()
        # Shift both endpoints to a common lateral station; the final line is
        # perpendicular to the teardrop reference line.
        left_height[:2] += direction * (midpoint_coordinate - float(np.dot(left[:2], direction)))
        right_height[:2] += direction * (midpoint_coordinate - float(np.dot(right[:2], direction)))
        self.put_points("lldHeightDifference", [left_height, right_height], derived=True)
        value = abs(float(np.dot(left - right, perpendicular)))
        scale = self._calibration_scale()
        self._store_result("pelvic_result_lld", value * scale if scale else value, " mm" if scale else " su")

    def _update_angle_constructions(self, side: str) -> None:
        lateral, superior = self._reference_directions(side)
        if lateral is None:
            for base in ("tonnisAngleReferenceArm", "sharpAngleReferenceArm", "lceAngleVisual", "lceAngleRadialArm"):
                self._remove_role(side_role(side, base))
            return
        for input_base, arm_base in (
            ("tonnisAngleLine", "tonnisAngleReferenceArm"),
            ("sharpAngleLine", "sharpAngleReferenceArm"),
        ):
            points = self.points_for_role(side_role(side, input_base))
            if len(points) < 2:
                self._remove_role(side_role(side, arm_base))
                continue
            length = float(np.linalg.norm(points[1] - points[0]))
            direction = lateral
            self.put_points(
                side_role(side, arm_base),
                [points[0], points[0] + np.array([direction[0] * length, direction[1] * length, 0.0])],
                derived=True,
            )
        center = self.points_for_role(side_role(side, "femurHeadCenter"))
        target = self.points_for_role(side_role(side, "lceAnglePoint"))
        if center and target:
            length = float(np.linalg.norm(target[0] - center[0]))
            self.put_points(
                side_role(side, "lceAngleVisual"),
                [center[0], center[0] + np.array([superior[0] * length, superior[1] * length, 0.0])],
                derived=True,
            )
            self.put_points(side_role(side, "lceAngleRadialArm"), [center[0], target[0]], derived=True)
        else:
            for base in ("lceAngleVisual", "lceAngleRadialArm"):
                self._remove_role(side_role(side, base))

    def _angle_value(self, base_direction: np.ndarray, vector: np.ndarray, orientation: np.ndarray) -> float | None:
        if base_direction is None or orientation is None:
            return None
        vector = np.array([*np.asarray(vector)[:2], 0.0])
        base = np.array([*np.asarray(base_direction)[:2], 0.0])
        sign = np.array([*np.asarray(orientation)[:2], 0.0])
        return signed_angle_from_base(vector, base, sign)

    def _store_result(self, key, value, suffix):
        """Keep full precision for CSV independently of rounded display text."""
        self._numeric_results[key] = (
            (float(value), suffix) if value is not None and np.isfinite(value) else (None, suffix)
        )
        self.server.state[key] = self._format_result(value, suffix)

    def _classify_shaft_contours(self, side):
        """Use the desktop's side-aware centroid ordering for four cortex curves."""
        from .geometry import in_plane_perpendicular, plane_normal_from_volume

        roles = [f"{side}_femoralShaftContour{i}" for i in range(1, 5)]
        sets = [self.points_for_role(role) for role in roles]
        attribute = "PelvicXrayMeasurements.FemoralShaftContourClass"
        for role in roles:
            node = self.node_for_role(role)
            if node is not None:
                node.SetAttribute(attribute, "")
        if any(len(points) < 2 for points in sets):
            return
        all_points = np.vstack(sets)
        origin = np.mean(all_points, axis=0)
        shaft = self.points_for_role(f"{side}_shaftAxis")
        axis = (
            unit_vector(shaft[1] - shaft[0])
            if len(shaft) >= 2
            else unit_vector(np.linalg.svd(all_points - origin, full_matrices=False)[2][0])
        )
        volume = self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode")
        desired = image_right_direction(volume)
        if desired is None:
            desired = np.array([1.0, 0.0, 0.0])
        desired = desired if side == "left" else -desired
        lateral = unit_vector(desired - axis * np.dot(desired, axis)) if axis is not None else desired
        if lateral is None:
            lateral = in_plane_perpendicular(axis, plane_normal_from_volume(volume))
        if lateral is None:
            return
        if np.dot(lateral, desired) < 0:
            lateral = -lateral
        ordered = sorted(
            zip(roles, sets, strict=True), key=lambda item: np.dot(np.mean(item[1], axis=0) - origin, lateral)
        )
        for (role, points), classification in zip(
            ordered, ("medialOuter", "medialInner", "lateralInner", "lateralOuter"), strict=True
        ):
            node = self.node_for_role(role)
            node.SetAttribute(attribute, classification)
            label = classification[0].upper() + classification[1:]
            for index in range(len(points)):
                node.SetNthControlPointLabel(index, f"FemoralShaft_{label}_{index + 1}")

    def _format_result(self, value: float | None, suffix: str) -> str:
        if value is None or not np.isfinite(value):
            return "—"
        return f"{value:.2f}" if suffix == "" else f"{value:.1f}{suffix}"

    def _update_result_fields(self) -> None:
        calibration = self.points_for_role("calibrationPoints")
        scale = None
        try:
            _, ball_diameter = self.circle_from_three(calibration)
            expected = float(self.server.state.pelvic_ball_diameter)
            if expected > 0 and ball_diameter > 0:
                scale = expected / ball_diameter
                self.server.state.pelvic_result_calibration = f"{ball_diameter:.1f} su ({scale:.4f} mm/su)"
        except (ValueError, TypeError):
            self._store_result("pelvic_result_calibration", None, "")
        reference = self.points_for_role("referenceLine")
        reference_result = "—"
        if len(reference) >= 2:
            length = np.linalg.norm(reference[1] - reference[0])
            reference_result = f"{length:.1f} su"
            if scale is not None:
                reference_result += f" ({length * scale:.1f} mm)"
        self.server.state.pelvic_result_reference = reference_result
        for side in ("right", "left"):
            lateral, superior = self._reference_directions(side)
            head_diameter = implant_diameter = None
            try:
                _, head_diameter = self.circle_from_three(self.points_for_role(side_role(side, "femurHeadPoints")))
            except ValueError:
                pass
            try:
                _, implant_diameter = self.circle_from_three(self.points_for_role(side_role(side, "implantHeadPoints")))
            except ValueError:
                pass
            head_value = head_diameter * scale if scale is not None and head_diameter is not None else head_diameter
            implant_value = (
                implant_diameter * scale if scale is not None and implant_diameter is not None else implant_diameter
            )
            self._store_result(f"pelvic_result_{side}_head", head_value, " mm" if scale else " su")
            self._store_result(f"pelvic_result_{side}_implant_head", implant_value, " mm" if scale else " su")
            for key, role, base in (("tonnis", "tonnisAngleLine", lateral), ("sharp", "sharpAngleLine", lateral)):
                points = self.points_for_role(side_role(side, role))
                value = (
                    self._angle_value(base, points[1] - points[0], superior)
                    if len(points) >= 2 and base is not None
                    else None
                )
                self._store_result(f"pelvic_result_{side}_{key}", value, "°")
            center = self.points_for_role(side_role(side, "femurHeadCenter"))
            target = self.points_for_role(side_role(side, "lceAnglePoint"))
            value = (
                self._angle_value(superior, target[0] - center[0], lateral)
                if center and target and superior is not None
                else None
            )
            self._store_result(f"pelvic_result_{side}_lce", value, "°")
            self._update_side_other_results(side, scale)
        self._update_visibility()

    def _constrain_parallel_line(self, role, direction):
        points = self.points_for_role(role)
        length = float(np.linalg.norm(direction)) if direction is not None else 0.0
        if len(points) < 2 or length < 1e-8:
            return points
        unit = np.asarray(direction) / length
        midpoint = 0.5 * (points[0] + points[1])
        half = 0.5 * float(np.linalg.norm(points[1] - points[0]))
        constrained = [midpoint - unit * half, midpoint + unit * half]
        self.put_points(role, constrained)
        return constrained

    def _update_side_other_results(self, side, scale):
        """Calculate the complete pre/post-operative desktop result set."""
        keys = (
            "ccd",
            "inclination",
            "implant_ccd",
            "stem_alignment",
            "extrusion",
            "acetabular_offset",
            "femoral_offset",
            "global_offset",
            "post_acetabular_offset",
            "post_femoral_offset",
            "post_global_offset",
        )
        for key in keys:
            self._store_result(f"pelvic_result_{side}_{key}", None, "")
        volume = self.scene.GetFirstNodeByClass("vtkMRMLVolumeNode")
        shaft = self.points_for_role(side_role(side, "shaftAxis"))
        shaft_direction = unit_vector(shaft[1] - shaft[0]) if len(shaft) >= 2 else None
        reference = self.points_for_role("referenceLine")
        reference_direction = unit_vector(reference[1] - reference[0]) if len(reference) >= 2 else None
        lateral, superior = self._reference_directions(side)

        def store(key, value, suffix="°"):
            self._store_result(f"pelvic_result_{side}_{key}", value, suffix)

        for key, role in (
            ("ccd", "neckAxis"),
            ("implant_ccd", "implantNeckAxis"),
            ("stem_alignment", "implantAlignmentLine"),
        ):
            axis = self.points_for_role(side_role(side, role))
            if shaft_direction is None or len(axis) < 2:
                continue
            direction = unit_vector(axis[1] - axis[0])
            if key == "stem_alignment":
                value = acute_angle_between_directions(shaft_direction, direction)
            else:
                up = image_up_direction(volume)
                right = image_right_direction(volume)
                medial = -right if side == "left" else right
                oriented = oriented_angle_between_directions(shaft_direction, -up, direction, medial)
                value = (
                    oriented
                    if oriented is not None and oriented < 90.0 - 1e-6
                    else obtuse_angle_between_directions(shaft_direction, direction)
                )
            store(key, value)
        line = self.points_for_role(side_role(side, "acetabularInclinationLine"))
        if reference_direction is not None and len(line) >= 2:
            store("inclination", acute_angle_between_directions(reference_direction, unit_vector(line[1] - line[0])))
        offsets = {}
        for prefix, a, b in (
            ("", "acetabularOffsetLineA", "acetabularOffsetLineB"),
            ("post_", "postOpAcetabularOffsetLineA", "postOpAcetabularOffsetLineB"),
        ):
            if superior is not None:
                direction = np.array([*superior, 0.0])
                pa = self._constrain_parallel_line(side_role(side, a), direction)
                pb = self._constrain_parallel_line(side_role(side, b), direction)
                if len(pa) >= 2 and len(pb) >= 2:
                    offsets[prefix + "acetabular_offset"] = float(np.linalg.norm(np.cross(direction, pb[0] - pa[0])))
        if shaft_direction is not None:
            unit = shaft_direction / np.linalg.norm(shaft_direction)
            for key, role in (
                ("femoral_offset", "femoralOffsetLine"),
                ("post_femoral_offset", "postOpFemoralOffsetLine"),
            ):
                points = self._constrain_parallel_line(side_role(side, role), unit)
                if len(points) >= 2:
                    offsets[key] = float(np.linalg.norm(np.cross(unit, points[0] - shaft[0])))
        for prefix in ("", "post_"):
            if prefix + "acetabular_offset" in offsets and prefix + "femoral_offset" in offsets:
                offsets[prefix + "global_offset"] = (
                    offsets[prefix + "acetabular_offset"] + offsets[prefix + "femoral_offset"]
                )
        for key, raw in offsets.items():
            store(key, raw * scale if scale else raw, " mm" if scale else " su")
        if lateral is not None:
            projection = []
            for role in ("extrusionIndexMedialLine", "extrusionIndexMiddleLine", "extrusionIndexLateralLine"):
                points = self._constrain_parallel_line(side_role(side, role), np.array([*superior, 0.0]))
                if len(points) >= 2:
                    projection.append(float(np.dot(points[0][:2], lateral)))
            if len(projection) == 3:
                width = abs(projection[2] - projection[0])
                store("extrusion", 100.0 * (projection[2] - projection[1]) / width if width > 1e-8 else None, "%")

    def set_workflow_hidden(self, workflow_key: str, hidden: bool) -> None:
        if hidden:
            self._hidden_workflows.add(workflow_key)
        else:
            self._hidden_workflows.discard(workflow_key)
        self._update_visibility()

    def _update_visibility(self) -> None:
        hidden_roles = set()
        known_roles = set()
        for key, workflow in WORKFLOWS.items():
            hidden = key in self._hidden_workflows
            roles = [step.base_role for step in workflow.steps]
            # Include constructions derived from the tool itself.
            roles += {
                "calibration": ["calibrationCircle"],
                "femur_head": ["femurHeadCenter", "femurHeadCircle"],
                "implant_head": ["implantHeadCenter", "implantHeadCircle"],
                "cup_opening": ["cupOpeningEllipse"],
                "tonnis": ["tonnisAngleReferenceArm"],
                "sharp": ["sharpAngleReferenceArm"],
                "lce": ["lceAngleVisual", "lceAngleRadialArm"],
                "shaft_axis": ["shaftAxis"],
                "post_shaft_axis": ["shaftAxis"],
                "neck_axis": ["neckAxis"],
                "implant_neck": ["implantNeckAxis"],
                "stem_alignment": ["implantAlignmentLine"],
                "morphology": [
                    "shaftMorphologyMidline",
                    "shaftMorphologyPoints",
                    "shaftMorphologyGuideLineA",
                    "shaftMorphologyGuideLineB",
                ],
                "lld": ["lldLeftParallel", "lldRightParallel", "lldHeightDifference"],
            }.get(key, [])
            for role in roles:
                for candidate in (
                    [role]
                    if not WORKFLOWS[key].steps[0].bilateral
                    else [side_role("left", role), side_role("right", role)]
                ):
                    known_roles.add(candidate)
                    if hidden:
                        hidden_roles.add(candidate)
        for candidate in known_roles:
            visible = candidate not in hidden_roles
            node = self.node_for_role(candidate)
            if node is not None:
                active = self._active_node is not None and node.GetID() == self._active_node.GetID()
                # Keep the active list visible before its first click, including
                # Slicer's preview point. Completion governs derived geometry,
                # not whether already placed control points can be seen.
                node.SetDisplayVisibility(visible and (active or node.GetNumberOfControlPoints() > 0))
            model = self._existing_model_for_role(candidate)
            if model is not None:
                polydata = model.GetPolyData()
                model.SetDisplayVisibility(visible and polydata is not None and polydata.GetNumberOfPoints() > 0)

    def _model_for_role(self, role: str):
        """Create a fork-owned derived model with desktop-compatible display settings."""

        existing = self._existing_model_for_role(role)
        if existing is not None:
            return existing
        spec = NODE_SPECS[role]
        node = self.scene.AddNewNodeByClass("vtkMRMLModelNode", str(spec["name"]))
        node.SetAttribute(ROLE_ATTRIBUTE, role)
        node.CreateDefaultDisplayNodes()
        if hasattr(node, "SaveWithSceneOff"):
            node.SaveWithSceneOff()
        display = node.GetDisplayNode()
        color = tuple(float(value) for value in spec["color"])
        display.SetColor(*color)
        if hasattr(display, "SetSelectedColor"):
            display.SetSelectedColor(*color)
        if hasattr(display, "SetSliceDisplayMode") and hasattr(display, "SliceDisplayIntersection"):
            display.SetSliceDisplayMode(display.SliceDisplayIntersection)
        if hasattr(display, "SetVisibility2D"):
            display.SetVisibility2D(True)
        elif hasattr(display, "SetSliceIntersectionVisibility"):
            display.SetSliceIntersectionVisibility(True)
        if hasattr(display, "SetSliceIntersectionThickness"):
            display.SetSliceIntersectionThickness(2)
        if hasattr(display, "SetSliceIntersectionOpacity"):
            display.SetSliceIntersectionOpacity(1.0)
        if hasattr(display, "SetVisibility3D"):
            display.SetVisibility3D(False)
        return node

    def _existing_model_for_role(self, role: str):
        """Find an already-created derived model without changing the scene."""
        nodes = self.scene.GetNodesByClass("vtkMRMLModelNode")
        nodes.InitTraversal()
        while True:
            node = nodes.GetNextItemAsObject()
            if node is None:
                break
            if node.GetAttribute(ROLE_ATTRIBUTE) == role:
                return node
        return None

    def _clear_circle_model(self, role: str) -> None:
        """Hide a stale fitted circle while retaining its stable MRML role."""

        nodes = self.scene.GetNodesByClass("vtkMRMLModelNode")
        nodes.InitTraversal()
        while True:
            node = nodes.GetNextItemAsObject()
            if node is None:
                return
            if node.GetAttribute(ROLE_ATTRIBUTE) == role:
                node.SetAndObservePolyData(vtkPolyData())
                node.SetDisplayVisibility(False)
                return

    @staticmethod
    def _default_completion(spec: dict) -> int:
        class_name = str(spec.get("className", ""))
        if class_name.endswith("LineNode"):
            return 2
        if class_name.endswith("AngleNode"):
            return 3
        if class_name.endswith("CurveNode"):
            return 0
        return 1

    @staticmethod
    def _configure_node(node, spec: dict) -> None:
        node.CreateDefaultDisplayNodes()
        if node.IsA("vtkMRMLMarkupsCurveNode"):
            node.SetNumberOfPointsPerInterpolatingSegment(int(spec.get("pointsPerInterpolatingSegment", 30)))
        display = node.GetDisplayNode()
        if display is None:
            return
        color = tuple(float(value) for value in spec.get("color", (0.2, 0.7, 0.95)))
        display.SetColor(*color)
        display.SetSelectedColor(*color)
        # The desktop extension hides labels for ordinary annotations; only the
        # active-side badge carries explanatory text. Small glyphs keep detail visible.
        if node.GetAttribute(ROLE_ATTRIBUTE) != "activeSideBadge":
            if hasattr(display, "SetPointLabelsVisibility"):
                display.SetPointLabelsVisibility(bool(spec.get("pointLabelsVisible", False)))
            if hasattr(display, "SetTextScale"):
                display.SetTextScale(1.5 if spec.get("pointLabelsVisible", False) else 0.0)
            # Markups renderers use different label properties across Slicer
            # releases; disable every available text pathway for annotations.
            for method_name in ("SetPropertiesLabelVisibility", "SetLabelVisibility", "SetTextVisibility"):
                if hasattr(display, method_name):
                    getattr(display, method_name)(False)
        if hasattr(display, "SetGlyphScale"):
            display.SetGlyphScale(float(spec.get("glyphScale", 1.0)) * POINT_GLYPH_FACTOR)

    def _remove_role(self, role: str) -> None:
        nodes = self.scene.GetNodesByClass("vtkMRMLNode")
        nodes.InitTraversal()
        matches = []
        while True:
            node = nodes.GetNextItemAsObject()
            if node is None:
                break
            if node.GetAttribute(ROLE_ATTRIBUTE) == role:
                matches.append(node)
        for node in matches:
            self.scene.RemoveNode(node)


def button_callback(controller: BrowserPlacementController, key: str) -> Callable[[], None]:
    """Bind a workflow key without loop-variable capture errors."""

    return lambda: controller.start(key)
