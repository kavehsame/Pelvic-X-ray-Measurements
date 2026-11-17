"""Slicer-side automation helpers for the Pelvic X-ray Measurements test bundle.

These helpers let the bundle drive the extension directly through its logic class while keeping all
automation code outside the extension folder itself.
"""
# ruff: noqa: E402, I001

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from re import Pattern
from typing import TypedDict

try:
    import slicer
    import vtk
except ModuleNotFoundError:  # pragma: no cover - exercised only outside Slicer
    slicer = None
    vtk = None

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "PelvicXrayMeasurements" / "PelvicXrayMeasurementsLib"
if REPO_ROOT.name == 'PelvicXrayMeasurementsVerification':
    LIB_DIR = REPO_ROOT.parent / 'PelvicXrayMeasurementsLib'
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from PelvicXrayMeasurementsConstants import OtherAngleLockMode
from PelvicXrayMeasurementsCaseWorkflow import load_export_csv_rows, parse_saved_case_metadata


CsvRow = dict[str, str]
JsonConfig = dict[str, object]


class PointRecord(TypedDict):
    index: int
    label: str
    x_ras: float
    y_ras: float
    z_ras: float


class ReplayMetadata(TypedDict):
    imageNodeName: str | None
    annotatorName: str
    exportTimestamp: str
    comments: str
    calibrationBallPresent: bool
    calibrationBallDiameterMm: float
    lineLockModes: dict[int, str]
    angleLockModes: dict[int, str]
    neckAxisOptions: dict[str, dict[str, dict[str, bool]]]


LINE_NAME_PATTERN: Pattern[str] = re.compile(r"^Line_(\d+)_Length$")
ANGLE_NAME_PATTERN: Pattern[str] = re.compile(r"^Angle_(\d+)$")
OTHER_LINE_ROLE_PATTERN: Pattern[str] = re.compile(r"^otherLine_(\d+)$")
OTHER_POINT_ROLE_PATTERN: Pattern[str] = re.compile(r"^otherPoint_(\d+)$")
OTHER_ANGLE_POINTS_ROLE_PATTERN: Pattern[str] = re.compile(r"^otherAngle_(\d+)_points$")
_HEADLESS_APP_LOGIC = None


def load_config_from_env(env_var_name: str = "HIP_TEST_CONFIG_PATH") -> JsonConfig:
    """Load a JSON configuration file whose path is passed through an environment variable."""

    config_path_text = os.environ.get(env_var_name, "")
    if not config_path_text:
        raise RuntimeError(f"Environment variable {env_var_name} is not set.")
    config_path = Path(config_path_text)
    with config_path.open("r") as stream:
        config = json.load(stream)

    for key, value in list(config.items()):
        if value is None or not isinstance(value, str):
            continue
        if key.endswith(("Dir", "Path", "Parent")):
            path_value = Path(value)
            if not path_value.is_absolute():
                config[key] = str((config_path.parent / path_value).resolve())
    return config


def ensure_minimal_runtime() -> None:
    """Bootstrap the minimum global Slicer objects needed by the extension logic.

    Headless automation uses Slicer's bundled Python runtime directly. In that mode the global MRML
    scene is not created for us, so we create it explicitly before importing or instantiating the
    extension logic. We also attach a `vtkMRMLApplicationLogic` instance to that scene because
    Markups nodes create built-in VTK measurements that expect Slicer's selection infrastructure to
    exist. Without the application logic, the replay still succeeds, but Slicer emits repeated
    "selection node not found" warnings while formatting length measurements.
    """

    global _HEADLESS_APP_LOGIC
    if not hasattr(slicer, "mrmlScene") or slicer.mrmlScene is None:
        slicer.mrmlScene = slicer.vtkMRMLScene()
    if _HEADLESS_APP_LOGIC is None:
        _HEADLESS_APP_LOGIC = slicer.vtkMRMLApplicationLogic()
    _HEADLESS_APP_LOGIC.SetMRMLScene(slicer.mrmlScene)


def bootstrap_extension(extension_dir: str) -> tuple[object, object]:
    """Import the extension module directly from its source folder."""

    ensure_minimal_runtime()
    extension_path = Path(extension_dir).resolve()
    module_dir = extension_path / "PelvicXrayMeasurements" if (extension_path / 'PelvicXrayMeasurements').is_dir() else extension_path
    lib_dir = module_dir / "PelvicXrayMeasurementsLib"
    for path in [module_dir, lib_dir]:
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)

    import PelvicXrayMeasurements  # pylint: disable=import-error
    import PelvicXrayMeasurementsNodeSpecs  # pylint: disable=import-error

    return PelvicXrayMeasurements, PelvicXrayMeasurementsNodeSpecs


def reset_scene() -> None:
    """Clear the MRML scene so each automation run starts from a known state."""

    ensure_minimal_runtime()
    slicer.mrmlScene.Clear(0)


def create_synthetic_volume(
    case_name: str, dimensions: Sequence[float], spacing: Sequence[float], origin: Sequence[float]
) -> object:
    """Create a blank single-slice scalar volume that defines a stable image coordinate system."""

    image_data = vtk.vtkImageData()
    image_data.SetDimensions(int(dimensions[0]), int(dimensions[1]), int(dimensions[2]))
    image_data.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
    scalars = image_data.GetPointData().GetScalars()
    if scalars is not None:
        scalars.Fill(0)

    volume_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", case_name)
    volume_node.SetAndObserveImageData(image_data)
    volume_node.SetSpacing(float(spacing[0]), float(spacing[1]), float(spacing[2]))
    volume_node.SetOrigin(float(origin[0]), float(origin[1]), float(origin[2]))
    volume_node.SetIJKToRASDirections(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    volume_node.CreateDefaultDisplayNodes()
    return volume_node


def set_markup_points(node: object, point_records: Iterable[PointRecord | Sequence[float] | dict[str, object]]) -> None:
    """Replace a markup node's control points with the supplied world-coordinate records."""

    if node is None:
        raise RuntimeError("Cannot populate a missing markup node.")

    normalized_records: list[PointRecord] = []
    for index, record in enumerate(point_records):
        if isinstance(record, dict):
            normalized_records.append(
                {
                    "index": int(record.get("index", index)),
                    "label": record.get("label", ""),
                    "x_ras": float(record["x_ras"]),
                    "y_ras": float(record["y_ras"]),
                    "z_ras": float(record.get("z_ras", 0.0)),
                }
            )
        else:
            normalized_records.append(
                {
                    "index": index,
                    "label": "",
                    "x_ras": float(record[0]),
                    "y_ras": float(record[1]),
                    "z_ras": float(record[2] if len(record) > 2 else 0.0),
                }
            )

    was_locked = bool(node.GetLocked()) if hasattr(node, "GetLocked") else False
    if was_locked:
        node.SetLocked(False)

    while node.GetNumberOfControlPoints() > len(normalized_records):
        node.RemoveNthControlPoint(node.GetNumberOfControlPoints() - 1)

    while node.GetNumberOfControlPoints() < len(normalized_records):
        record = normalized_records[node.GetNumberOfControlPoints()]
        node.AddControlPointWorld(
            vtk.vtkVector3d(float(record["x_ras"]), float(record["y_ras"]), float(record["z_ras"]))
        )

    for index, record in enumerate(normalized_records):
        node.SetNthControlPointPositionWorld(
            index,
            float(record["x_ras"]),
            float(record["y_ras"]),
            float(record["z_ras"]),
        )
        if record.get("label"):
            node.SetNthControlPointLabel(index, str(record["label"]))

    if was_locked:
        node.SetLocked(True)
    node.SetDisplayVisibility(bool(normalized_records))


def update_measurements(logic: object, image_node: object) -> None:
    """Recompute all derived geometry and values for the current synthetic case."""

    logic.update_all_derived_measurements(image_node)


def role_points_from_csv_rows(csv_rows: Iterable[CsvRow]) -> dict[str, list[PointRecord]]:
    """Group CSV point rows by logical role while preserving exported point order."""

    grouped: dict[str, list[PointRecord]] = {}
    for row in csv_rows:
        if row.get("section") != "point":
            continue
        role = row.get("details", "").split(";", 1)[0].strip()
        if not role:
            continue
        grouped.setdefault(role, []).append(
            {
                "index": int(row["index"]) if row.get("index") else 0,
                "label": row.get("label", ""),
                "x_ras": float(row["x_ras"]),
                "y_ras": float(row["y_ras"]),
                "z_ras": float(row["z_ras"]),
            }
        )
    for _role, records in grouped.items():
        records.sort(key=lambda record: record["index"])
    return grouped


def parse_replay_metadata(csv_rows: Iterable[CsvRow]) -> ReplayMetadata:
    """Extract non-coordinate replay settings from an exported dummy CSV."""

    rows = list(csv_rows)
    saved_metadata = parse_saved_case_metadata(rows)
    line_lock_modes = {}
    angle_lock_modes = {}

    for row in rows:
        section = row.get("section")
        name = row.get("name")
        if section == "measurement":
            line_match = LINE_NAME_PATTERN.match(name or "")
            if line_match:
                details = row.get("details", "")
                if "locked parallel" in details:
                    line_lock_modes[int(line_match.group(1))] = OtherAngleLockMode.PARALLEL
                elif "locked perpendicular" in details:
                    line_lock_modes[int(line_match.group(1))] = OtherAngleLockMode.PERPENDICULAR
                else:
                    line_lock_modes[int(line_match.group(1))] = OtherAngleLockMode.NONE
                continue
            angle_match = ANGLE_NAME_PATTERN.match(name or "")
            if not angle_match:
                continue
            details = row.get("details", "")
            if "locked parallel" in details:
                angle_lock_modes[int(angle_match.group(1))] = OtherAngleLockMode.PARALLEL
            elif "locked perpendicular" in details:
                angle_lock_modes[int(angle_match.group(1))] = OtherAngleLockMode.PERPENDICULAR
            else:
                angle_lock_modes[int(angle_match.group(1))] = OtherAngleLockMode.NONE

    return {
        "imageNodeName": saved_metadata["imageNodeName"],
        "annotatorName": saved_metadata["annotatorName"],
        "exportTimestamp": saved_metadata["exportTimestamp"],
        "comments": saved_metadata["comments"],
        "calibrationBallPresent": saved_metadata["calibrationBallPresent"],
        "calibrationBallDiameterMm": saved_metadata["calibrationBallDiameterMm"],
        "lineLockModes": line_lock_modes,
        "angleLockModes": angle_lock_modes,
        "neckAxisOptions": saved_metadata["neckAxisOptions"],
    }


def apply_neck_axis_options(logic: object, neck_axis_options: dict[str, dict[str, dict[str, bool]]]) -> None:
    """Restore exported neck-axis option flags into a fresh logic instance before replay."""

    for measurement_key, side_options in neck_axis_options.items():
        for side_key, option_values in side_options.items():
            logic.set_axis_lock_to_center_enabled(
                measurement_key, side_key, option_values.get("lockToCenter", False)
            )
            logic.set_axis_use_single_guide_enabled(
                measurement_key, side_key, option_values.get("useSingleGuide", False)
            )


def create_dynamic_roles(
    logic: object,
    point_rows_by_role: dict[str, list[PointRecord]],
    line_lock_modes: dict[int, str],
    angle_lock_modes: dict[int, str],
) -> None:
    """Create any dynamic line and angle roles required by the replay CSV."""

    line_indices = sorted(
        int(match.group(1))
        for role in point_rows_by_role
        for match in [OTHER_LINE_ROLE_PATTERN.match(role)]
        if match
    )
    point_indices = sorted(
        int(match.group(1))
        for role in point_rows_by_role
        for match in [OTHER_POINT_ROLE_PATTERN.match(role)]
        if match
    )
    angle_indices = sorted(
        int(match.group(1))
        for role in point_rows_by_role
        for match in [OTHER_ANGLE_POINTS_ROLE_PATTERN.match(role)]
        if match
    )

    for index in line_indices:
        logic.create_other_line(line_lock_modes.get(index, OtherAngleLockMode.NONE))
    for _index in point_indices:
        logic.create_other_point()
    for index in angle_indices:
        logic.create_other_angle(angle_lock_modes.get(index, OtherAngleLockMode.NONE))


def populate_roles_in_stages(
    logic: object,
    image_node: object,
    role_to_points: dict[str, list[PointRecord]],
    staged_roles: Iterable[Iterable[str]],
) -> None:
    """Populate editable nodes in a stable order, updating the extension after each stage."""

    for stage_roles in staged_roles:
        populated_this_stage = False
        for role in stage_roles:
            point_records = role_to_points.get(role)
            if not point_records:
                continue
            node = logic.get_node(role, create_if_missing=True)
            set_markup_points(node, point_records)
            populated_this_stage = True
        if populated_this_stage:
            update_measurements(logic, image_node)


def export_csv(
    logic: object,
    image_node: object,
    parent_directory: str | Path,
    export_curve_points_txt: bool=False,
) -> Path:
    """Ask the extension logic to export its measurement CSV into the supplied parent directory."""

    export_info = logic.export_csv(
        str(parent_directory),
        image_node,
        conflict_policy="replace",
        export_curve_points_txt=export_curve_points_txt,
    )
    if export_curve_points_txt:
        txt_path = Path(export_info.get("curvePointsTxtPath", "")).resolve()
        if not txt_path.exists():
            raise RuntimeError("Curve-points TXT export was requested but no TXT file was written.")
        txt_text = txt_path.read_text(encoding="utf-8")
        if "Curve:" not in txt_text or "PointsPerInterpolatingSegment: 30" not in txt_text:
            raise RuntimeError("Curve-points TXT export did not contain the expected curve metadata.")
    return Path(export_info["csvPath"]).resolve()


def load_csv_rows(csv_path: str | Path) -> list[CsvRow]:
    """Load CSV rows inside the Slicer Python runtime."""

    return load_export_csv_rows(csv_path)


def finish_with_exit_code(exit_code: int) -> None:
    """Terminate the headless runtime with the requested exit code."""

    raise SystemExit(int(exit_code))
