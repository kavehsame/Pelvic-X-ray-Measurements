"""Bilateral AP research overlays, in nominal millimetres, shared by both editions."""

from collections import deque
from functools import lru_cache
from math import cos, degrees, isfinite, radians, sin
from zipfile import ZipFile
from pathlib import Path
import json
from typing import NamedTuple

import numpy as np

TEMPLATE_ATTRIBUTE = "PelvicXrayMeasurements.PlanningTemplate"
COMPONENTS = ("cup", "stem")
ROTATION_ROLES = {
    "cup": "planningCupAnchor",
    "stem": "planningStemAnchor",
    "fragment": "fragmentTarget",
}
FRAGMENT_CUT = "PelvicXrayMeasurements.FragmentCut"
VIEW_AXES = "PelvicXrayMeasurements.PlanningViewAxes"
FRAGMENT_ANGLE = "PelvicXrayMeasurements.FragmentAngle"
CUT_ROLES = {"straight": "resectionStraight", "stepped": "resectionStepped"}


# Both editions also accept independent, session-only vector overlay packs.
def read_catalog():
    for path in (
        Path(__file__).with_name("planning_templates.json"),
        Path(__file__).resolve().parents[1] / "Resources" / "planning_templates.json",
    ):
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["format"] not in ("pxm-ap-png-1", "pxm-ap-outlines-1"):
                raise ValueError("Unsupported planning template library.")
            return {record["id"]: record for record in payload["items"]}
    return {}


ITEMS = read_catalog()
ARTWORK = frozenset(item["image"] for item in ITEMS.values() if "image" in item)


@lru_cache(maxsize=1)
def artwork_archive():
    for folder in (Path(__file__).parent, Path(__file__).resolve().parents[1] / "Resources"):
        path = folder / "planning_artwork.zip"
        if path.is_file():
            return ZipFile(path)
    raise ValueError("The local implant drawings are missing from this installation.")


def artwork_bytes(digest):
    if digest not in ARTWORK:
        raise ValueError("Unknown implant drawing.")
    return artwork_archive().read(digest + ".png")


def template_scale(ball_factor, metric):
    """World coordinates already include horizontal and vertical image pitch."""
    if ball_factor is not None and isfinite(ball_factor) and ball_factor > 0:
        return ball_factor
    return 1.0 if metric else None


def dicom_spacing(patient, detector):
    """Read DICOM row/column spacing; a detector pitch alone needs a ball for sizing."""
    for pair, patient_space in ((patient, True), (detector, False)):
        try:
            row, col = map(float, pair.split("\\") if isinstance(pair, str) else pair)
            if all(isfinite(v) and v > 0 for v in (row, col)):
                return (col, row), patient_space
        except (TypeError, ValueError):
            continue
    return (1., 1.), False


METRIC_ATTRIBUTE = "PelvicXrayMeasurements.PlanningMetric"
AP_AXES_ATTRIBUTE = "PelvicXrayMeasurements.PlanningAPAxes"
STANDARD_AP = ((1., 0.), (0., -1.))


def dicom_ap_axes(cosines, orientation=None):
    """Patient left and superior in the physical column/row basis of a frontal film."""
    try:
        i, j = np.asarray(cosines, float).reshape(2, 3)
        normal = np.cross(i, j)
        if abs(normal[1]) > .8 and np.isfinite(normal).all():
            left = np.array([i[0], j[0]])
            left /= np.linalg.norm(left)
            up = np.array([-left[1], left[0]])
            if np.dot(up, [i[2], j[2]]) < 0:
                up = -up
            return [left.tolist(), up.tolist()]
    except (TypeError, ValueError):
        pass
    if orientation and len(orientation) == 2:
        dirs = {"L": (1, 0), "R": (-1, 0), "H": (0, 1), "F": (0, -1)}
        values = [dirs.get(str(label)[:1].upper(), (0, 0)) for label in orientation]
        if abs(np.linalg.det(values)) == 1:
            return np.transpose(values).tolist()
    return STANDARD_AP


def raster_frame(item):
    """Top-left, top-right, bottom-right and bottom-left PNG edges in a left-hip frame."""
    w, h = item["pixels"]
    xy = (np.array([[0, 0], [w, 0], [w, h], [0, h]]) - item["pivot"]) * item["pitch"]
    xy[:, 1] *= -1
    if item["drawn"] == "right":
        xy[:, 0] *= -1
    return xy

CATALOG = {}
for _id, _item in ITEMS.items():
    CATALOG.setdefault(_item["family"], []).append(_id)
# label, source role, number of landmarks, colour, placement instruction
TOOLS = {
    "straight_resection": (
        "Straight Neck Resection",
        "resectionStraight",
        2,
        (0.99, 0.62, 0.18),
        "Mark the medial and lateral ends of the planned femoral neck cut.",
    ),
    "stepped_resection": (
        "Stepped Neck Resection",
        "resectionStepped",
        3,
        (0.96, 0.42, 0.74),
        "Mark the medial end, the corner of the step and the lateral end.",
    ),
    "bone_fragment": (
        "Retained Bone Fragment Placement",
        "fragmentBoundary",
        0,
        (0.94, 0.84, 0.38),
        "Select the retained femur from the neck cut. Drag the fragment or its point to move it. Drag the round handle to rotate. Click the button again to reset.",
    ),
    "fragment_pose": (
        "Position Bone Fragment",
        "fragmentTarget",
        1,
        (0.99, 0.43, 0.31),
        "Drag the fragment point to translate the retained bone.",
    ),
    "cup_center": (
        "Cup Center",
        "cupShellPoints",
        3,
        (0.23, 0.88, 0.81),
        "Place three separated points on the spherical outer cup shell. Avoid the opening ellipse.",
    ),
}
for component, colour in zip(
    COMPONENTS, ((0.28, 0.84, 1.0), (1.0, 0.72, 0.31)), strict=True
):
    TOOLS["template_" + component] = (
        f"Place {component.title()} Template",
        f"planning{component.title()}Anchor",
        1,
        colour,
        "Drag the implant to move it. Drag the round handle to rotate about its pivot, or enter an angle.",
    )
# Result key, stable CSV suffix and descriptive label.
LENGTH_FIELDS = (
    ("straight_resection", "Planning_StraightResection_Length", "Straight cut"),
    ("step_medial", "Planning_SteppedResection_MedialLength", "Stepped cut · medial"),
    (
        "step_lateral",
        "Planning_SteppedResection_LateralLength",
        "Stepped cut · lateral",
    ),
    (
        "stepped_resection",
        "Planning_SteppedResection_TotalLength",
        "Stepped cut · total",
    ),
    ("inlay_wear", "PostOp_ProjectedHeadPenetration", "Inlay wear estimate"),
)
WEAR_HELP = "Projected distance between implant head and shell centres on this film. Serial films are needed to measure change."


def extra_roles(key):
    role = TOOLS[key][1]
    if key == "cup_center":
        return ["cupShellCenter", "cupShellCircle", "inlayWearLine"]
    if key == "bone_fragment":
        return ["fragmentSourceOutline"]
    if key == "stepped_resection" or key.startswith("template_"):
        return [role + "Outline"]
    return []


def node_specs(side):
    specs = {}

    def add(role, label, kind, color, labels=(), **properties):
        specs[f"{side}_{role}"] = dict(
            className="vtkMRML" + kind + "Node",
            name=f"Hip Measurements - {side.title()} {label}",
            color=color,
            labels=list(labels),
            **properties,
        )

    for key, (title, role, count, color, _help) in TOOLS.items():
        labels = [f"{role}_{side.title()}_P{i + 1}" for i in range(count)]
        kind = "MarkupsLine" if key == "straight_resection" else "MarkupsFiducial"
        if key == "bone_fragment":
            # Older scenes may identify this markup by its original display name.
            add(role, "Retained Bone", "MarkupsCurve", color)
        else:
            add(role, title, kind, color, labels, completionCount=count)
        for derived in extra_roles(key):
            kind = {
                "cupShellCenter": "MarkupsFiducial",
                "inlayWearLine": "MarkupsLine",
            }.get(derived, "Model")
            add(
                derived,
                derived,
                kind,
                color,
                locked=True,
                projectToSlice=derived.endswith("Outline"),
            )
    return specs


def cut_lengths(straight, stepped):
    values = {}
    if len(straight) == 2:
        values["straight_resection"] = float(np.linalg.norm(np.subtract(*straight)))
    if len(stepped) == 3:
        lengths = np.linalg.norm(np.diff(stepped, axis=0), axis=1)
        values.update(
            step_medial=float(lengths[0]),
            step_lateral=float(lengths[1]),
            stepped_resection=float(sum(lengths)),
        )
    return values


def default_template(component, side="left"):
    for item in ITEMS.values():
        if item["component"] == component and item["side"] in ("both", str(side)):
            return template_choice(component, {"id": item["id"], "angle": 0.0}, side)
    return None


def template_choice(component, raw, side, *, allow_missing=False):
    choice = json.loads(raw) if isinstance(raw, str) and raw else raw
    if not choice:
        return default_template(component, side)
    if (
        not isinstance(choice, dict)
        or not isinstance(choice.get("id"), str)
        or not choice["id"]
    ):
        raise ValueError("The saved implant reference is invalid.")
    item = ITEMS.get(choice["id"])
    if item is None and not allow_missing:
        raise ValueError(
            "The saved implant reference is unavailable in the local library."
        )
    if item and (
        item["component"] != component or item["side"] not in ("both", str(side))
    ):
        raise ValueError("The implant reference does not match this component or side.")
    angle = float(choice["angle"])
    if not np.isfinite(angle) or abs(angle) > 180:
        raise ValueError("Template rotation must be between −180° and 180°.")
    result = {"id": choice["id"], "angle": angle}
    # Store the catalogue wording with the pose so a session-only pack can be identified later.
    for field in ("family", "size"):
        value = (item if item is not None else choice).get(field)
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 512 or any(ord(c) < 32 for c in value):
                raise ValueError(f"Invalid saved implant {field}.")
            result[field] = value
    if item and "image" in item:
        if isinstance(raw, str) and "frame" not in choice:
            # Old CSVs measured cup rotation from a level opening. Keep their pose
            # when switching to the original manufacturer's AP drawing as zero.
            delta = degrees(item["sourceAngle"]) * (-1 if item["drawn"] == "right" else 1)
            result["angle"] = (angle + delta + 180) % 360 - 180
        result["frame"] = "sheet"
    elif choice.get("frame") == "sheet":
        result["frame"] = "sheet"
    return result


def node_template_choice(node, component, side):
    """Read the selected pose and retain the identity on a placed anchor, including older cases."""
    raw = node.GetAttribute(TEMPLATE_ATTRIBUTE) if node is not None else None
    choice = template_choice(component, raw, side, allow_missing=True)
    if choice and node is not None and node.GetNumberOfDefinedControlPoints():
        saved = json.loads(raw) if raw else {}
        if any(saved.get(key) != value for key, value in choice.items()):
            node.SetAttribute(TEMPLATE_ATTRIBUTE, json.dumps({**saved, **choice}))
    return choice


def implant_report(side, component, choice):
    """Describe a placed implant using the exact family and size labels shown in Planning."""
    family, size = choice.get("family", ""), choice.get("size", "")
    prefix = f"{side.title()}_Planning_{component.title()}_"
    fields = {"Component": component, "Family": family, "Size": size, "ID": choice["id"]}
    size_text = f"Size {size}" if size else "Size unavailable"
    return {
        "caption": f"{side.title()} {component} · {family or choice['id']} · {size_text}",
        "metadata": {prefix + key: value for key, value in fields.items()},
    }


def artwork_hit_grid(alpha):
    """Fill enclosed areas for dragging; the original alpha remains the display texture."""
    h, w = alpha.shape
    stride = max(1, (max(h, w) + 255) // 256)
    padded = np.pad(alpha, ((0, -h % stride), (0, -w % stride)))
    solid = padded.reshape(padded.shape[0]//stride, stride, -1, stride).max(axis=(1, 3)) > 12
    # A margin around the ink ensures all exterior pockets connect to the seed.
    blocked = np.pad(solid, 1)
    queue = deque([(0, 0)])
    outside = np.zeros_like(blocked)
    outside[0, 0] = True
    height, width = blocked.shape
    while queue:
        y, x = queue.popleft()
        for j, i in ((y-1,x), (y+1,x), (y,x-1), (y,x+1)):
            if 0 <= j < height and 0 <= i < width and not blocked[j,i] and not outside[j,i]:
                outside[j,i] = True
                queue.append((j,i))
    return ~outside[1:-1,1:-1]


def plan_axes(node, right, up):
    """Remember the view in which a plan was placed so rotated or mirrored CSVs reopen faithfully."""
    raw = node.GetAttribute(VIEW_AXES)
    if raw:
        return np.asarray(json.loads(raw), dtype=float)
    axes = np.asarray([right, up], dtype=float)
    node.SetAttribute(VIEW_AXES, json.dumps(axes.tolist()))
    return axes


def transformed_attributes(attrs, matrix):
    if VIEW_AXES not in attrs:
        return attrs
    axes = np.asarray(json.loads(attrs[VIEW_AXES]), dtype=float)
    if axes.shape != (2, 3) or not np.isfinite(axes).all():
        raise ValueError("The saved planning orientation is invalid.")
    axes = axes @ np.asarray(matrix)[:3, :3].T
    lengths = np.linalg.norm(axes, axis=1)
    if min(lengths) < 1e-8 or np.linalg.norm(np.cross(*axes)) < 1e-6 * np.prod(lengths):
        raise ValueError("The saved planning orientation is degenerate.")
    return {**attrs, VIEW_AXES: json.dumps((axes / lengths[:, None]).tolist())}


def fragment_rotation(node, angle, right, up):
    original = plan_axes(node, right, up)
    return -angle if np.dot(np.cross(*original), np.cross(right, up)) < 0 else angle


def validate_attributes(role, attrs):
    if not isinstance(attrs, dict):
        raise ValueError(f"Invalid saved options for {role}.")
    side, _, base = role.partition("_")
    if side not in ("left", "right"):
        return
    if (
        base in ("planningCupAnchor", "planningStemAnchor")
        and TEMPLATE_ATTRIBUTE in attrs
    ):
        kind = "cup" if base == "planningCupAnchor" else "stem"
        template_choice(kind, attrs[TEMPLATE_ATTRIBUTE], side, allow_missing=True)
    if (
        base == "fragmentBoundary"
        and attrs.get(FRAGMENT_CUT, "straight") not in CUT_ROLES
    ):
        raise ValueError("Invalid saved cut for the bone fragment.")
    if base == "fragmentTarget":
        angle = float(attrs.get(FRAGMENT_ANGLE, 0))
        if not np.isfinite(angle) or abs(angle) > 180:
            raise ValueError("Fragment rotation must be between −180° and 180°.")


def catalog_menu():
    return [
        {k: item[k] for k in ("id", "family", "component", "size", "side")}
        for item in ITEMS.values()
    ]


def outline(choice, anchor, side, right, up, scale):
    """Map a PNG frame or imported vector vertices to the radiograph at its physical size."""
    if (
        not choice
        or choice["id"] not in ITEMS
        or not scale
        or right is None
        or up is None
    ):
        return []
    item = ITEMS[choice["id"]]
    angle = radians(choice["angle"])
    lateral = np.asarray(right) * (1 if str(side) == "left" else -1)
    up = np.asarray(up)
    x_axis = cos(angle) * lateral - sin(angle) * up
    y_axis = sin(angle) * lateral + cos(angle) * up
    return [
        np.asarray(anchor) + (x * x_axis + y * y_axis) / scale
        for x, y in (raster_frame(item) if "image" in item else item["outline"])
    ]


OVERLAY_FORMAT = "pxm-overlay-pack-1"
PACK_LIMIT = 12 * 1024 * 1024


def simple_outline(xy):
    """Check non-adjacent edges for a crossing or touch after bounding-box rejection."""
    a, b = xy[:-1], xy[1:]
    n = len(a)
    if len(np.unique(a, axis=0)) != n:
        return False
    low, high = np.minimum(a, b), np.maximum(a, b)

    def cross(u, v):
        return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]

    for i in range(n - 2):
        stop = n - 1 if i == 0 else n
        indices = np.arange(i + 2, stop)
        candidates = (high[indices] >= low[i]).all(1) & (low[indices] <= high[i]).all(1)
        if candidates.any():
            c, d = a[indices[candidates]], b[indices[candidates]]
            u, v = a[i], b[i]
            if (
                (cross(v - u, c - u) * cross(v - u, d - u) <= 0)
                & (cross(d - c, u - c) * cross(d - c, v - c) <= 0)
            ).any():
                return False
    return True


def import_overlays(content):
    """Validate a data-only session library before changing any selectable template."""
    if len(content) > PACK_LIMIT:
        raise ValueError("An overlay pack must be 12 MiB or smaller.")
    try:
        pack = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Choose a PXM overlay pack in JSON format.") from exc
    if not isinstance(pack, dict) or (
        pack.get("format"),
        pack.get("units"),
        pack.get("view"),
        pack.get("axes"),
    ) != (OVERLAY_FORMAT, "mm", "AP", "x-lateral-y-superior"):
        raise ValueError("Expected a version 1 PXM AP overlay pack in millimetres.")
    items = pack.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 1500:
        raise ValueError("An overlay pack must contain between 1 and 1,500 items.")
    pending = {}
    for index, row in enumerate(items, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Item {index} must be an object.")
        values = {}
        for key in (
            "id",
            "family",
            "size",
            "manufacturer",
            "reference",
            "source",
            "scale_method",
        ):
            val = row.get(key)
            if (
                not isinstance(val, str)
                or not val.strip()
                or len(val) > 512
                or any(ord(ch) < 32 for ch in val)
            ):
                raise ValueError(f"Item {index} needs a valid {key}.")
            values[key] = val.strip()
        ident = values["id"]
        if ident in pending:
            raise ValueError(f"Duplicate reference within pack: {ident}.")
        if row.get("component") not in COMPONENTS or row.get("side") not in (
            "both",
            "left",
            "right",
        ):
            raise ValueError(f"{ident}: choose cup or stem and a valid side.")
        points, pivot = row.get("outline"), row.get("pivot")
        if not isinstance(points, list) or not 4 <= len(points) <= 4096:
            raise ValueError(
                f"{ident}: supply a closed outline with 4 to 4,096 coordinate pairs."
            )

        def pair(v):
            return (
                isinstance(v, list)
                and len(v) == 2
                and all(type(x) in (float, int) and abs(x) <= 2000 for x in v)
            )

        if (
            not pair(pivot)
            or not all(pair(pt) for pt in points)
            or points[0] != points[-1]
        ):
            raise ValueError(
                f"{ident}: use finite millimetre pairs and repeat the first vertex at the end."
            )
        xy = np.asarray(points, dtype=float) - np.asarray(pivot)
        area = abs(np.dot(xy[:-1, 0], xy[1:, 1]) - np.dot(xy[:-1, 1], xy[1:, 0])) / 2
        if area < 1 or np.max(np.abs(xy)) > 2000:
            raise ValueError(
                f"{ident}: the outline is degenerate or outside its coordinate range."
            )
        if not simple_outline(xy):
            raise ValueError(
                f"{ident}: the perimeter crosses itself or repeats a vertex."
            )
        item = {
            **values,
            "component": row["component"],
            "side": row["side"],
            "outline": xy.tolist(),
        }
        existing = ITEMS.get(ident)
        if existing and any(
            existing.get(k) != item[k]
            for k in ("family", "size", "component", "side", "outline")
        ):
            raise ValueError(f"{ident} already identifies a different template.")
        pending[ident] = item
    for ident, item in pending.items():
        if ident not in ITEMS:
            ITEMS[ident] = item
            CATALOG.setdefault(item["family"], []).append(ident)
    return len(pending)


def available_cuts(get_points):
    return [
        name
        for name, role in CUT_ROLES.items()
        if len(get_points(role)) == (2 if name == "straight" else 3)
    ]


def retained_boundary(
    cut, dimensions, spacing, *, side, lesser=(), shaft=(), head=(), cortex=()
):
    """Return the open lateral-to-medial portion in image indices. Closure follows all cut vertices."""
    p = np.asarray(cut, dtype=float)[:, :2]
    wh, sp = np.asarray(dimensions[:2], float), np.asarray(spacing[:2], float)
    if (
        len(p) not in (2, 3)
        or np.any(wh < 2)
        or np.any(sp <= 0)
        or not np.isfinite(p).all()
    ):
        raise ValueError(
            "A complete straight or stepped cut and a planar radiograph are required."
        )
    med, lat = p[[0, -1]] * sp
    mid = (lat + med) / 2
    width = np.linalg.norm(lat - med)
    if width < min(sp):
        raise ValueError("Separate the medial and lateral cut ends.")

    # Work along the image axes. Landmarks, when present, identify the distal edge even after a quarter turn.
    def physical(points):
        return np.asarray(points, float).reshape(-1, 2) * sp

    sh, lt, heads, cort = map(physical, (shaft, lesser, head, cortex))
    # The head is often farther medial than superior. Its offset alone cannot identify
    # a quarter turn. Prefer a distal shaft landmark or a sufficiently long cortical trace.
    distal_hint = sh.mean(0) - mid if len(sh) else None
    if distal_hint is None and len(cort):
        offsets = cort - mid
        lengths = np.linalg.norm(offsets, axis=1)
        if lengths.max() >= 1.5 * width:
            distal_hint = offsets[lengths >= 0.85 * lengths.max()].mean(0)
    d, direction = 1, 1
    if distal_hint is not None and np.linalg.norm(distal_hint) > 0.35 * width:
        d = int(np.argmax(abs(distal_hint)))
        direction = np.sign(distal_hint[d])
    else:
        for hint in (
            mid - heads[0] if len(heads) else None,
            lt.mean(0) - mid if len(lt) else None,
        ):
            if hint is not None and abs(hint[d]) > 0.2 * width:
                direction = np.sign(hint[d])
                break
    l = 1 - d
    down = np.eye(2)[d] * direction
    outward = lat[l] - med[l]
    latdir = np.eye(2)[l] * (
        np.sign(outward) if abs(outward) > 1e-7 else (1 if side == "left" else -1)
    )
    axes = np.array([latdir, down])
    m, a = (np.array([med, lat]) - mid) @ axes.T
    corners = np.array([[-1, -1], wh, [-1, wh[1]], [wh[0], -1]]) * sp
    frame = (corners - mid) @ axes.T
    inner, top = frame.min(0)
    outer, bottom = frame.max(0)
    length = min(width, 0.35 * min((wh * sp)))
    shoulder = a + [0.55 * length, -0.85 * length]
    lt_corner = m + [-0.38 * length, 0.65 * length]
    if len(heads):
        shoulder[1] = min(shoulder[1], ((heads[0] - mid) @ axes.T)[1] - 0.12 * length)
    if len(lt):
        refs = (lt - mid) @ axes.T
        lt_corner[0] = min(lt_corner[0], refs[:, 0].min() - 0.22 * length)
        lt_corner[1] = max(lt_corner[1], refs[:, 1].max() + 0.16 * length)
    if len(cort):
        measured = (cort - mid) @ axes.T
        proximal = measured[
            (measured[:, 0] >= a[0]) & (measured[:, 1] < a[1] + length * 0.3)
        ]
        if len(proximal):
            # Clear the highest marked lateral cortex before continuing to the outer image margin.
            top_point = proximal[np.argmin(proximal[:, 1])]
            shoulder[1] = min(shoulder[1], top_point[1] - 0.18 * length)
            shoulder[0] = min(
                shoulder[0], max(a[0] + 0.04 * length, top_point[0] - 0.10 * length)
            )
    shoulder = [min(outer, shoulder[0]), max(top, shoulder[1])]
    u, v = np.clip(lt_corner, [inner, m[1]], [m[0], bottom])
    slope = 0.12
    if len(cort) or len(sh):
        envelope = (np.vstack([cort, sh]) - mid) @ axes.T
        distal = envelope[envelope[:, 1] > v + 0.25 * length]
        if len(distal):
            slope = max(
                slope,
                float(np.max((u - distal[:, 0] + 0.16 * length) / (distal[:, 1] - v))),
            )
    end = u - slope * (bottom - v)
    path = [shoulder, [outer, shoulder[1]], [outer, bottom], [max(inner, end), bottom]]
    if end < inner:
        path.append([inner, min(bottom, v + (u - inner) / slope)])
    path.append([u, v])
    return ((np.asarray(path) @ axes + mid) / sp).tolist()


def template_axes(node, side, right, up):
    right, up = plan_axes(node, right, up)
    return right * (1 if side == "left" else -1), up


def rotation_from_pointer(delta, lateral, superior, previous):
    x, y = np.dot(delta, lateral), -np.dot(delta, superior)
    return float(np.degrees(np.arctan2(y, x))) if np.hypot(x, y) > 1e-6 else previous


def rotation_ray(angle, lateral, superior):
    return cos(radians(angle)) * lateral - sin(radians(angle)) * superior


class RotationControl(NamedTuple):
    angle: float
    axes: tuple[np.ndarray, np.ndarray]
    template: dict | None = None

    def ray(self):
        return rotation_ray(self.angle, *self.axes)

    def drag(self, node, offset):
        angle = rotation_from_pointer(offset, *self.axes, self.angle)
        if self.template is None:
            node.SetAttribute(FRAGMENT_ANGLE, str(angle))
        else:
            node.SetAttribute(
                TEMPLATE_ATTRIBUTE, json.dumps({**self.template, "angle": angle})
            )


def rotation_control(node, kind, side, right, up):
    if kind == "fragment":
        # Fragment CSV angles are relative to the original image, independent of hip side.
        return RotationControl(
            float(node.GetAttribute(FRAGMENT_ANGLE) or 0),
            tuple(plan_axes(node, right, up)),
        )
    choice = template_choice(
        kind, node.GetAttribute(TEMPLATE_ATTRIBUTE), side, allow_missing=True
    )
    if not choice or choice["id"] not in ITEMS:
        return None
    return RotationControl(
        choice["angle"], template_axes(node, side, right, up), choice
    )


def automatic_trace(get_points, kind, dimensions, spacing, to_pixel, from_pixel, side):
    def pixels(role):
        return [to_pixel(point)[:2] for point in get_points(role)]

    cut = get_points(CUT_ROLES[kind])
    cortex = [p for i in range(1, 5) for p in pixels(f"femoralShaftContour{i}")]
    limits = retained_boundary(
        [to_pixel(p) for p in cut],
        dimensions,
        spacing,
        side=side,
        lesser=pixels("shaftMorphologyLTPoints"),
        shaft=pixels("shaftGuideDistal"),
        head=pixels("femurHeadCenter") or pixels("implantHeadCenter"),
        cortex=cortex,
    )
    return [from_pixel(point) for point in limits]


def fragment_projection(cut, boundary, target, angle, to_pixel, spacing, *, rows_down):
    """Return a closed source polygon and its rigid transform in image indices."""
    if len(cut) not in (2, 3) or len(boundary) < 2 or len(target) != 1:
        return None
    polygon = np.array([to_pixel(p)[:2] for p in [*cut, *boundary]], dtype=float)
    if (
        abs(
            np.dot(polygon[:, 0], np.roll(polygon[:, 1], 1))
            - np.dot(polygon[:, 1], np.roll(polygon[:, 0], 1))
        )
        < 1e-4
    ):
        return None
    origin = (polygon[0] + polygon[len(cut) - 1]) * 0.5
    dest = np.asarray(to_pixel(target[0])[:2])
    theta = radians(float(angle)) * (1 if rows_down else -1)
    sx, sy = spacing[:2]
    rotation = np.array(
        [[cos(theta), -sin(theta) * sy / sx], [sin(theta) * sx / sy, cos(theta)]]
    )
    transform = np.column_stack((rotation, dest - rotation @ origin))
    return {"polygon": polygon.tolist(), "matrix": transform.tolist()}


def _scan_polygon(poly, shape):
    """Yield filled scanline runs, clipping indices to the image."""
    poly = np.asarray(poly)
    q = np.roll(poly, -1, axis=0)
    for y in range(
        max(0, int(np.ceil(poly[:, 1].min()))),
        min(shape[0], int(np.ceil(poly[:, 1].max()))),
    ):
        crosses = (poly[:, 1] > y) != (q[:, 1] > y)
        p1, p2 = poly[crosses], q[crosses]
        xs = sorted(
            p1[:, 0] + (y - p1[:, 1]) * (p2[:, 0] - p1[:, 0]) / (p2[:, 1] - p1[:, 1])
        )
        for left, right in zip(xs[::2], xs[1::2], strict=True):
            start, end = max(0, int(np.ceil(left))), min(shape[1], int(np.ceil(right)))
            if start < end:
                yield y, start, end


def compose_fragments(source, plans):
    """Render moved image tissue from immutable source pixels, in one independent preview."""
    if not plans:
        return source
    if all(
        np.allclose(p["matrix"], [[1, 0, 0], [0, 1, 0]], atol=1e-9, rtol=0)
        for p in plans
    ):
        return source
    output = source.copy()
    background = source.min()
    for plan in plans:
        for y, start, end in _scan_polygon(plan["polygon"], source.shape):
            output[y, start:end] = background
    for plan in plans:
        matrix = np.asarray(plan["matrix"])
        inverse = np.linalg.inv(matrix[:, :2])
        moved = np.asarray(plan["polygon"]) @ matrix[:, :2].T + matrix[:, 2]
        for y, start, end in _scan_polygon(moved, source.shape):
            x_coord = np.arange(start, end)
            xx, yy = inverse @ (
                np.array([x_coord, np.full(len(x_coord), y)]) - matrix[:, 2, None]
            )
            valid = (
                (xx >= 0)
                & (xx <= source.shape[1] - 1)
                & (yy >= 0)
                & (yy <= source.shape[0] - 1)
            )
            xx, yy = xx[valid], yy[valid]
            ix, iy = xx.astype(int), yy.astype(int)
            jx, jy = (
                np.minimum(ix + 1, source.shape[1] - 1),
                np.minimum(iy + 1, source.shape[0] - 1),
            )
            dx, dy = xx - ix, yy - iy
            vals = (
                (1 - dx) * (1 - dy) * source[iy, ix]
                + dx * (1 - dy) * source[iy, jx]
                + (1 - dx) * dy * source[jy, ix]
                + dx * dy * source[jy, jx]
            )
            output[y, x_coord[valid]] = vals
    return output
