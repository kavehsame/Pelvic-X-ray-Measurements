"""Read and write local annotation files without resolving any external references."""

import csv
import gzip
import io
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

import numpy as np

from .custom import custom_spec
from .imaging import MAX_FILE, check_matrix, decode
from .schema import NODE_SPECS, ROLE_ATTRIBUTE
from .workflow import WORKFLOWS

STATE_ATTRIBUTE = "PelvicXrayMeasurements.BrowserState"
NAME_ATTRIBUTE = "PelvicXrayMeasurements.AnnotatorName"
INPUT_ROLES = {
    role
    for w in WORKFLOWS.values()
    for s in w.steps
    for role in ((f"left_{s.base_role}", f"right_{s.base_role}") if s.bilateral else (s.base_role,))
} | {f"{side}_shaftMorphologyPoints" for side in ("left", "right")}


def supported_role(role):
    spec = custom_spec(role)
    return role in INPUT_ROLES or bool(spec and not spec["locked"] and len(role) < 30)


def valid_tracks(groups):
    points = {}
    for role, value in groups.items():
        if not supported_role(role):
            continue
        spec = NODE_SPECS.get(role) or custom_spec(role)
        bound = spec.get("completionCount", 2 if spec["className"].endswith("LineNode") else 5000)
        track = np.asarray(value, dtype=float)
        if track.size == 0:
            continue
        if track.ndim != 2 or track.shape[1] != 3 or not np.isfinite(track).all() or len(track) > bound:
            raise ValueError(f"Invalid saved points for {role}.")
        points[role] = track
    return points


def curve_type(value):
    """Accept Slicer's exported names and the browser's numeric curve types."""
    names = {"linear": 0, "spline": 1, "cardinalspline": 1, "kochanekspline": 2}
    text = str(value).strip().lower()
    result = names.get(text)
    if result is None:
        result = int(text)
    if result not in (0, 1, 2):
        raise ValueError("The saved curve interpolation is not supported.")
    return result


def read_csv(raw):
    lines = io.StringIO(raw.decode("utf-8-sig"), newline="")
    reader = csv.DictReader(lines)
    if not {"section", "name"}.issubset(reader.fieldnames or ()):
        raise ValueError("Choose a Pelvic X-ray Measurements coordinate CSV.")
    by_name = {spec["name"]: role for role, spec in NODE_SPECS.items()}
    metadata, groups, curves, segments = {}, {}, {}, {}
    for row in reader:
        if row.get("section") == "metadata":
            # Flags exported by Slicer carry explanatory prose in details.
            metadata[row["name"]] = (
                row.get("raw_value") if row.get("units") == "flag" else row.get("details") or row.get("raw_value")
            ) or ""
            continue
        if row.get("section") == "measurement" and row["name"] == "CalibrationBall_KnownDiameter":
            metadata.setdefault(row["name"], row.get("corrected_value_mm") or row.get("raw_value"))
            continue
        if row.get("section") == "measurement":
            match = re.fullmatch(r"(Line|Angle)_(\d+)(?:_Length)?", row["name"])
            if match:
                kind, index = match.groups()
                role = f"otherLine_{index}" if kind == "Line" else f"otherAngle_{index}_points"
                details = row.get("details", "")
                mode = next((value for value in ("parallel", "perpendicular") if f"locked {value}" in details), "none")
                metadata.setdefault(role + "_lock", mode)
            continue
        if row.get("section") not in {"point", "derived_point"}:
            continue
        role = row.get("role") or row.get("details", "").split(";", 1)[0] or by_name.get(row["name"], "")
        if not supported_role(role):
            continue
        if row.get("point_index"):
            index = int(row["point_index"]) - 1
            point = [float(row[key]) for key in ("r", "a", "s")]
        else:
            index = int(row["index"])
            point = [float(row[key]) for key in ("x_ras", "y_ras", "z_ras")]
        track = groups.setdefault(role, {})
        if index < 0 or index in track:
            raise ValueError(f"Invalid or duplicate point index for {role}.")
        track[index] = point
        if row.get("curve_type"):
            curves[role] = curve_type(row["curve_type"])
        if row.get("curve_points_per_segment"):
            size = int(row["curve_points_per_segment"])
            if not 1 <= size <= 1000:
                raise ValueError("Invalid saved curve sampling count.")
            segments[role] = size
    for role, track in groups.items():
        if sorted(track) != list(range(len(track))):
            raise ValueError(f"Saved point indices are incomplete for {role}.")
    settings = json.loads(metadata.get("WebSceneState") or "{}")
    if not isinstance(settings, dict):
        raise ValueError("The saved scene settings must be an object.")
    settings.setdefault("comments", metadata.get("Comments", ""))
    settings.setdefault("annotator", metadata.get("Annotator", ""))
    settings.setdefault("active_side", metadata.get("ActiveSide", "left"))
    settings.setdefault("ball_diameter", metadata.get("CalibrationBall_KnownDiameter") or 25)
    options = {}
    for side in ("left", "right"):
        for kind in ("neck", "implant_neck"):
            key = f"{side}_{kind}_options"
            if key in metadata:
                option = json.loads(metadata[key])
                options[f"{side}_{kind}"] = [option["lockToCenter"], option["useSingleGuide"]]
            else:
                family = "FemoralNeckAxis" if kind == "neck" else "ImplantNeckAxis"
                flag = f"{family}_{side.title()}_UseSingleGuide"
                if flag in metadata:
                    options[f"{side}_{kind}"] = [
                        metadata.get(f"{family}_{side.title()}_LockToCenter") in {"true", "True", "1"},
                        metadata[flag] in {"true", "True", "1"},
                    ]
    settings.setdefault("axis_options", options)
    attributes = {role: json.loads(metadata.get(f"{role}_attributes", "{}")) for role in groups}
    for role in groups:
        attribute = (
            "PelvicXrayMeasurements.OtherLineLockToReference"
            if role.startswith("otherLine_")
            else "PelvicXrayMeasurements.OtherAngleLockToReference"
        )
        if role + "_lock" in metadata:
            attributes[role][attribute] = metadata[role + "_lock"]
    matrix = check_matrix(json.loads(metadata["ImageIJKToRAS"])) if metadata.get("ImageIJKToRAS") else None
    return {
        "points": valid_tracks({role: [track[i] for i in range(len(track))] for role, track in groups.items()}),
        "attributes": attributes,
        "curve_types": curves,
        "curve_segments": segments,
        "settings": settings,
        "matrix": matrix,
        "case_name": metadata.get("CaseName") or metadata.get("ImageNode", ""),
    }


def read_member(archive, name, limit):
    if ".." in PurePosixPath(name).parts or PurePosixPath(name).is_absolute():
        raise ValueError("The scene contains an unsafe archive path.")
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError("A file in the scene exceeds the browser size limit.")
    with archive.open(info) as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("A file in the scene exceeds the browser size limit.")
    return content


def attributes(element):
    raw = element.get("attributes", "")
    return dict(piece.split(":", 1) for piece in re.split(r";(?=[a-zA-Z0-9_.]+:|$)", raw) if ":" in piece)


def storage_path(element, storages, folder):
    refs = dict(re.findall(r"([a-zA-Z]+):([^; ]+)", element.get("references", "")))
    storage_id = refs.get("storage", element.get("storageNodeRef"))
    storage = storages.get(storage_id)
    if storage is None:
        return None
    name = PurePosixPath(unquote(storage.get("fileName", "")).replace("\\", "/"))
    return (folder / name).as_posix() if not name.is_absolute() and ".." not in name.parts else None


def read_mrb(raw):
    if len(raw) > MAX_FILE:
        raise ValueError("Choose a scene archive smaller than 200 MB.")
    with ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) > 18000 or len(names) != len(set(names)):
            raise ValueError("The scene contains too many files or duplicate paths.")
        scene_members = [n for n in names if n.lower().endswith(".mrml")]
        if len(scene_members) != 1:
            raise ValueError("The MRB must contain one MRML scene.")
        scene_name = scene_members[0]
        xml = read_member(archive, scene_name, 12_000_000)
        if b"<!ENTITY" in xml.upper():
            raise ValueError("This scene uses unsupported XML entities.")
        root = ET.fromstring(xml)
        storages = {e.get("id"): e for e in root if "Storage" in e.tag and e.get("fileName")}
        folder = PurePosixPath(scene_name).parent
        volumes = [
            (e, storage_path(e, storages, folder))
            for e in root
            if e.tag in {"Volume", "ScalarVolume", "ScalarVolumeNode"}
        ]
        volumes = [(e, path) for e, path in volumes if path]
        if len(volumes) != 1:
            raise ValueError("Open an MRB containing one stored radiograph.")
        element, path = volumes[0]
        if "transform:" in element.get("references", "") or element.get("transformNodeRef"):
            raise ValueError("Harden the volume transform in Slicer before opening this scene in Chrome.")
        image = decode(path, read_member(archive, path, MAX_FILE))
        if image.source_affine is None:
            raise ValueError("The saved radiograph does not contain a coordinate frame.")
        settings = {}
        for node in root.findall("ScriptedModule"):
            attrs = attributes(node)
            if STATE_ATTRIBUTE in attrs:
                settings.update(json.loads(attrs[STATE_ATTRIBUTE]))
            if NAME_ATTRIBUTE in attrs:
                settings["annotator"] = attrs[NAME_ATTRIBUTE]
        groups, meta, curves = {}, {}, {}
        for node in root:
            if node.tag not in {"MarkupsFiducial", "MarkupsLine", "MarkupsCurve", "MarkupsAngle"}:
                continue
            attrs = attributes(node)
            role = attrs.get(ROLE_ATTRIBUTE, "")
            if not supported_role(role):
                continue
            file_name = storage_path(node, storages, folder)
            if file_name is None or not file_name.lower().endswith(".json"):
                raise ValueError("This MRB uses an older markup format. Import its coordinate CSV instead.")
            if "transform:" in node.get("references", "") or node.get("transformNodeRef"):
                raise ValueError("Harden markup transforms in Slicer before opening this scene in Chrome.")
            record = json.loads(read_member(archive, file_name, 2_000_000))["markups"][0]
            coords = [p["position"] for p in record["controlPoints"] if p.get("positionStatus", "defined") == "defined"]
            if record.get("coordinateSystem", "LPS").upper() == "LPS":
                coords = [[-x, -y, z] for x, y, z in coords]
            if role in groups:
                raise ValueError(f"Duplicate markup role in the scene: {role}.")
            groups[role] = coords
            meta[role] = attrs
            if record.get("curveType") == "linear":
                curves[role] = 0
        return image, {
            "points": valid_tracks(groups),
            "attributes": meta,
            "curve_types": curves,
            "settings": settings,
            "matrix": image.source_affine,
            "case_name": element.get("name", ""),
        }


def append_csv_metadata(path, settings, image):
    from .csv_export import FIELDS

    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writerow(
            {
                "section": "metadata",
                "name": "WebSceneState",
                "details": json.dumps(settings),
                "annotator": settings["annotator"],
            }
        )
        if image.source_affine is not None:
            writer.writerow(
                {
                    "section": "metadata",
                    "name": "SourceImageIJKToRAS",
                    "details": json.dumps(image.source_affine.tolist()),
                    "annotator": settings["annotator"],
                }
            )


def nrrd_bytes(image, matrix):
    dtype = image.pixels.dtype
    if dtype.kind in "iu" and dtype.itemsize <= 2:
        typ = {("u", 1): "unsigned char", ("u", 2): "unsigned short", ("i", 1): "signed char", ("i", 2): "short"}[
            (dtype.kind, dtype.itemsize)
        ]
    elif dtype.kind == "f" and dtype.itemsize <= 4:
        dtype, typ = np.dtype("<f4"), "float"
    else:
        dtype, typ = np.dtype("<f8"), "double"
    h, w = image.shape
    vec = lambda values: "(" + ",".join(f"{float(x):.17g}" for x in values) + ")"
    directions = " ".join(vec(matrix[:3, c]) for c in range(3))
    header = (
        f"NRRD0004\ntype: {typ}\ndimension: 3\nsizes: {w} {h} 1\n"
        f"space: right-anterior-superior\nspace directions: {directions}\n"
        f"kinds: domain domain domain\nendian: little\nencoding: gzip\nspace origin: {vec(matrix[:3, 3])}\n\n"
    )
    pixels = image.pixels.astype(dtype.newbyteorder("<"), copy=False)
    return header.encode("ascii") + gzip.compress(pixels.tobytes(), compresslevel=3, mtime=0)


def write_mrb(image, controller, case_name, settings):
    """Write a compact MRML scene with a scalar NRRD and Slicer markups JSON."""
    root = ET.Element("MRML", {"version": "Slicer 5.8.0 0", "userTags": ""})
    add = lambda tag, **attrs: ET.SubElement(root, tag, attrs)
    add(
        "Selection",
        id="vtkMRMLSelectionNodeSingleton",
        singletonTag="Singleton",
        activeVolumeID="vtkMRMLScalarVolumeNode1",
        references="activeVolume:vtkMRMLScalarVolumeNode1;",
    )
    add(
        "Volume",
        id="vtkMRMLScalarVolumeNode1",
        name=case_name,
        labelMap="0",
        references="display:vtkMRMLScalarVolumeDisplayNode1;storage:vtkMRMLVolumeArchetypeStorageNode1;",
    )
    low, high = settings["window"]
    add(
        "VolumeDisplay",
        id="vtkMRMLScalarVolumeDisplayNode1",
        name="VolumeDisplay",
        autoWindowLevel="false",
        window=str(high - low),
        level=str((high + low) / 2),
        references=(
            "color:vtkMRMLColorTableNodeInvertedGrey;" if settings["invert"] else "color:vtkMRMLColorTableNodeGrey;"
        ),
    )
    add(
        "VolumeArchetypeStorage",
        id="vtkMRMLVolumeArchetypeStorageNode1",
        name="VolumeArchetypeStorage",
        fileName="Data/radiograph.nrrd",
        useCompression="1",
        centerImage="0",
        UseOrientationFromFile="1",
    )
    for lab in ("Red", "Green", "Yellow"):
        add(
            "SliceComposite",
            id=f"vtkMRMLSliceCompositeNode{lab}",
            singletonTag=lab,
            layoutName=lab,
            backgroundVolumeRef="vtkMRMLScalarVolumeNode1",
            references="backgroundVolume:vtkMRMLScalarVolumeNode1;",
        )
    note = json.dumps(settings, ensure_ascii=True).replace(";", r"\u003b")
    annotator = str(settings["annotator"]).replace(";", ",")
    add(
        "ScriptedModule",
        id="vtkMRMLScriptedModuleNode1",
        name="Pelvic Browser Export Metadata",
        attributes=f"{NAME_ATTRIBUTE}:{annotator};{STATE_ATTRIBUTE}:{note}",
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
        archive.writestr("Scene/Data/radiograph.nrrd", nrrd_bytes(image, controller.current_image_node().affine))
        for index, node in enumerate(controller.scene.GetNodesByClass("vtkMRMLMarkupsNode"), 1):
            role = node.GetAttribute(ROLE_ATTRIBUTE)
            if not role or role == "activeSideBadge" or not node.points:
                continue
            kind = node.classname.removeprefix("vtkMRMLMarkups").removesuffix("Node")
            filename = f"Data/markup_{index:04d}.mrk.json"
            display_id, storage_id = f"vtkMRMLMarkupsDisplayNode{index}", f"vtkMRMLMarkupsJsonStorageNode{index}"
            add(
                f"Markups{kind}",
                id=f"vtkMRMLMarkups{kind}Node{index}",
                name=node.name,
                locked="true" if node.locked else "false",
                references=f"display:{display_id};storage:{storage_id};",
                attributes=";".join(f"{k}:{v}" for k, v in sorted(node.attributes.items()) if ";" not in v),
            )
            add(
                "MarkupsDisplay",
                id=display_id,
                name=f"Display {index}",
                visibility="true" if node.visible else "false",
                color=" ".join(map(str, node.display.color)),
                selectedColor=" ".join(map(str, node.display.color)),
                pointLabelsVisibility="false",
                propertiesLabelVisibility="false",
            )
            add("MarkupsJsonStorage", id=storage_id, name=f"Storage {index}", fileName=filename, coordinateSystem="RAS")
            points = [
                {
                    "id": str(i + 1),
                    "label": node.labels[i],
                    "position": point.tolist(),
                    "orientation": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                    "positionStatus": "defined",
                    "selected": True,
                    "locked": node.locked,
                    "visibility": True,
                }
                for i, point in enumerate(node.points)
            ]
            doc = {
                "@schema": "https://raw.githubusercontent.com/slicer/slicer/main/Modules/Loadable/Markups/Resources/Schema/markups-schema-v1.0.3.json#",
                "markups": [
                    {
                        "type": kind,
                        "coordinateSystem": "RAS",
                        "coordinateUnits": "mm",
                        "locked": node.locked,
                        "controlPoints": points,
                        **(
                            {"curveType": "linear" if node.curve_type == 0 else "cardinalSpline"}
                            if kind == "Curve"
                            else {}
                        ),
                    }
                ],
            }
            archive.writestr("Scene/" + filename, json.dumps(doc, separators=(",", ":")))
        archive.writestr("Scene/Scene.mrml", ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return buffer.getvalue()
