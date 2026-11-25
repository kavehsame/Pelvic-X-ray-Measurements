"""Folder-driven case workflow helpers for Pelvic X-ray Measurements.

These helpers are intentionally pure and Slicer-independent so folder navigation and saved-scene
lookup can be tested outside the Slicer runtime.
"""
from __future__ import annotations

import csv
import math
import os
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import TypedDict
from urllib.parse import quote, unquote

from PelvicXrayMeasurementsConstants import CALIBRATION_BALL_DIAMETER_MM, MeasurementKey, SideKey
from PelvicXrayMeasurementsGeometry import sanitize_filename

SUPPORTED_INPUT_IMAGE_SUFFIXES = (
    ".bmp",
    ".dcm",
    ".dicom",
    ".ima",
    ".jpeg",
    ".jpg",
    ".mha",
    ".mhd",
    ".nrrd",
    ".nii",
    ".nii.gz",
    ".png",
    ".tif",
    ".tiff",
)

CSV_EXPORT_ENCODING = "utf-8-sig"
BUNDLE_PATH_SAFE_QUOTE_CHARACTERS = "/"
COMPACT_BUNDLE_ROOT = "S"
COMPACT_BUNDLE_DATA_DIR = f"{COMPACT_BUNDLE_ROOT}/Data"
EMPTY_POLYDATA_VTK_LEGACY = (
    "# vtk DataFile Version 3.0\n"
    "Empty PolyData\n"
    "ASCII\n"
    "DATASET POLYDATA\n"
    "POINTS 0 float\n"
    "VERTICES 0 0\n"
    "LINES 0 0\n"
    "POLYGONS 0 0\n"
    "TRIANGLE_STRIPS 0 0\n"
)
MRML_FILENAME_ATTRIBUTE_RE = re.compile(r'(fileName=)(["\'])(.*?)(\2)')


class SavedCaseMetadata(TypedDict):
    """Persisted case-level settings recovered from one exported CSV."""

    imageNodeName: str | None
    annotatorName: str
    exportTimestamp: str
    comments: str
    calibrationBallPresent: bool
    calibrationBallDiameterMm: float
    neckAxisOptions: dict[MeasurementKey, dict[SideKey, dict[str, bool]]]


def _has_supported_image_suffix(path: Path) -> bool:
    """Return whether the file name looks like a directly loadable image."""

    lower_name = path.name.lower()
    return any(lower_name.endswith(suffix) for suffix in SUPPORTED_INPUT_IMAGE_SUFFIXES)


def is_supported_input_image(path: str | Path) -> bool:
    """Return whether a file should participate in folder-driven image navigation."""

    candidate = Path(path)
    if not candidate.is_file() or candidate.name.startswith("."):
        return False
    return _has_supported_image_suffix(candidate) or candidate.suffix == ""


def list_input_images(input_directory: str | Path) -> list[Path]:
    """Return the sorted image files available in one input folder."""

    directory = Path(input_directory).expanduser()
    if not path_is_dir(directory):
        return []
    return sorted(
        (path.resolve() for path in directory.iterdir() if is_supported_input_image(path)),
        key=lambda path: path.name.lower(),
    )


def case_name_from_image_filename(image_filename: str) -> str:
    """Return the exported case-file base name for one image file name."""

    return sanitize_filename(image_filename)


def case_folder_name_from_image_filename(image_filename: str) -> str:
    """Return the exported case-folder name for one image file name."""

    stem_name = Path(image_filename).stem or image_filename
    return sanitize_filename(stem_name)


def default_scene_path_for_image_filename(output_directory: str | Path, image_filename: str) -> Path:
    """Return the default MRB path that the extension uses for one image file name."""

    output_root = Path(output_directory).expanduser()
    return (
        output_root
        / case_folder_name_from_image_filename(image_filename)
        / f"{case_name_from_image_filename(image_filename)}.mrb"
    )


def default_csv_path_for_image_filename(output_directory: str | Path, image_filename: str) -> Path:
    """Return the default CSV export path that the extension uses for one image file name."""

    output_root = Path(output_directory).expanduser()
    return (
        output_root
        / case_folder_name_from_image_filename(image_filename)
        / f"{case_name_from_image_filename(image_filename)}_measurements.csv"
    )


def filesystem_path(path: str | Path) -> str:
    """Return a Windows-safe filesystem path without changing behavior on other platforms."""

    path_text = os.fspath(path)
    if os.name != "nt":
        return path_text
    if path_text.startswith("\\\\?\\") or path_text.startswith("\\\\.\\"):
        return path_text
    normalized_path = os.path.abspath(os.path.normpath(path_text))
    if normalized_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + normalized_path.lstrip("\\")
    return "\\\\?\\" + normalized_path


def path_exists(path: str | Path) -> bool:
    """Return whether a path exists, tolerating Windows long-path prefixes when needed."""

    try:
        return os.path.exists(filesystem_path(path))
    except OSError:
        return os.path.exists(path)


def path_is_dir(path: str | Path) -> bool:
    """Return whether a path is a directory, tolerating Windows long-path prefixes when needed."""

    try:
        return os.path.isdir(filesystem_path(path))
    except OSError:
        return os.path.isdir(path)


def path_mtime(path: str | Path) -> float:
    """Return the modification time for one path using Windows-safe filesystem access."""

    return os.stat(filesystem_path(path)).st_mtime


def directory_children(directory: str | Path, suffix: str) -> list[Path]:
    """Return direct child files with one suffix using Windows-safe directory scanning."""

    directory_path = Path(directory)
    try:
        with os.scandir(filesystem_path(directory_path)) as entries:
            return sorted(
                (
                    directory_path / entry.name
                    for entry in entries
                    if entry.is_file() and entry.name.lower().endswith(suffix)
                ),
                key=lambda path: path.name,
            )
    except OSError:
        return []


def _ascii_safe_bundle_component(component: str) -> str:
    """Return an ASCII-safe ZIP member component for scene-bundle data files."""

    normalized_component = str(component or "")
    if "%ff" in normalized_component.lower():
        normalized_component = re.sub(r"(?i)%ff([0-9a-f]{2})", r"%\1", normalized_component)
        normalized_component = re.sub(r"(?i)%ff", "", normalized_component)
    if "%" in normalized_component:
        normalized_component = unquote(normalized_component, encoding="utf-8", errors="ignore")
    normalized_component = unicodedata.normalize("NFKD", normalized_component)
    ascii_component = normalized_component.encode("ascii", "ignore").decode("ascii")
    ascii_component = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_component).strip("._")
    return ascii_component or "item"


def _ascii_safe_bundle_path(relative_path: str) -> str:
    """Return an ASCII-safe relative path for one MRB member."""

    trailing_separator = "/" if relative_path.endswith("/") else ""
    raw_parts = [part for part in str(relative_path or "").split("/") if part not in ("", ".")]
    safe_parts = [_ascii_safe_bundle_component(part) for part in raw_parts]
    safe_path = "/".join(safe_parts)
    if trailing_separator:
        safe_path += trailing_separator
    return safe_path or "item"


def _bundle_member_suffix(member_path: str) -> str:
    """Return the full suffix chain for one bundle member path."""

    return "".join(PurePosixPath(member_path).suffixes)


def _bundle_member_category(member_path: str) -> str:
    """Return the short category prefix used for compact MRB member names."""

    lower_member_path = member_path.lower()
    if lower_member_path.endswith(".mrk.json"):
        return "m"
    if lower_member_path.endswith(".vtk"):
        return "d"
    if (
        lower_member_path.endswith(".nrrd")
        or lower_member_path.endswith(".nii")
        or lower_member_path.endswith(".nii.gz")
    ):
        return "v"
    return "f"


def _compact_bundle_member_path(
    source_info: zipfile.ZipInfo,
    category_counts: dict[str, int],
    directory_counts: dict[str, int],
) -> str:
    """Return the compact target path for one rewritten MRB member."""

    if source_info.is_dir():
        normalized_directory = source_info.filename.rstrip("/")
        lower_directory = normalized_directory.lower()
        if lower_directory.endswith("/data") or normalized_directory == COMPACT_BUNDLE_DATA_DIR:
            return f"{COMPACT_BUNDLE_DATA_DIR}/"
        if not normalized_directory or "/" not in normalized_directory:
            return f"{COMPACT_BUNDLE_ROOT}/"
        directory_counts["dir"] += 1
        return f"{COMPACT_BUNDLE_ROOT}/Dir{directory_counts['dir']:02d}/"

    if source_info.filename.lower().endswith(".mrml"):
        category_counts["scene"] += 1
        if category_counts["scene"] == 1:
            return f"{COMPACT_BUNDLE_ROOT}/scene.mrml"
        return f"{COMPACT_BUNDLE_ROOT}/scene_{category_counts['scene']:02d}.mrml"

    category = _bundle_member_category(source_info.filename)
    category_counts[category] += 1
    suffix = _bundle_member_suffix(source_info.filename)
    return f"{COMPACT_BUNDLE_DATA_DIR}/{category}_{category_counts[category]:03d}{suffix}"


def _unique_bundle_path(candidate_path: str, is_directory: bool, used_paths: set[str]) -> str:
    """Return a bundle member path that stays unique after ASCII normalization."""

    normalized_candidate = candidate_path[:-1] if is_directory and candidate_path.endswith("/") else candidate_path
    if normalized_candidate not in used_paths:
        used_paths.add(normalized_candidate)
        return candidate_path

    path_object = PurePosixPath(normalized_candidate)
    parent_path = "" if str(path_object.parent) == "." else str(path_object.parent)
    file_name = path_object.name or "item"
    suffixes = "" if is_directory else "".join(path_object.suffixes)
    base_name = file_name[:-len(suffixes)] if suffixes else file_name
    index = 2
    while True:
        candidate_name = f"{base_name}_{index}{suffixes}"
        unique_candidate = f"{parent_path}/{candidate_name}" if parent_path else candidate_name
        if unique_candidate not in used_paths:
            used_paths.add(unique_candidate)
            return f"{unique_candidate}/" if is_directory else unique_candidate
        index += 1


def _copy_zip_info(source_info: zipfile.ZipInfo, filename: str) -> zipfile.ZipInfo:
    """Clone ZIP metadata while replacing the member filename."""

    copied_info = zipfile.ZipInfo(filename=filename, date_time=source_info.date_time)
    copied_info.comment = source_info.comment
    copied_info.compress_type = source_info.compress_type
    copied_info.create_system = source_info.create_system
    copied_info.create_version = source_info.create_version
    copied_info.extract_version = source_info.extract_version
    copied_info.extra = source_info.extra
    copied_info.flag_bits = source_info.flag_bits
    copied_info.internal_attr = source_info.internal_attr
    copied_info.external_attr = source_info.external_attr
    copied_info.volume = source_info.volume
    return copied_info


def _mrml_reference_path_pairs(
    original_mrml_member_path: str,
    rewritten_mrml_member_path: str,
    original_bundle_path: str,
    rewritten_bundle_path: str,
) -> list[tuple[str, str]]:
    """Return bundle-path pairs that may appear inside one MRML file.

    Slicer stores most scene-bundle references relative to the MRML file directory, not as full ZIP
    member paths. The repair step therefore updates both the full member names and their MRML-local
    relative forms.
    """

    path_pairs = [(original_bundle_path, rewritten_bundle_path)]
    original_mrml_parent = PurePosixPath(original_mrml_member_path).parent
    rewritten_mrml_parent = PurePosixPath(rewritten_mrml_member_path).parent
    try:
        original_relative_path = PurePosixPath(original_bundle_path).relative_to(original_mrml_parent).as_posix()
        rewritten_relative_path = PurePosixPath(rewritten_bundle_path).relative_to(rewritten_mrml_parent).as_posix()
    except ValueError:
        return path_pairs
    path_pairs.append((original_relative_path, rewritten_relative_path))
    return path_pairs


def _quoted_bundle_reference_variants(path: str) -> tuple[str, ...]:
    """Return the URL-quoted path variants observed in Slicer MRML scene bundles."""

    return (
        quote(path, safe=BUNDLE_PATH_SAFE_QUOTE_CHARACTERS),
        quote(path, safe=f"{BUNDLE_PATH_SAFE_QUOTE_CHARACTERS}()"),
    )


def _bundle_reference_replacement_values(source_path: str, target_path: str) -> dict[str, str]:
    """Return raw and URL-quoted forms for one exact fileName attribute replacement."""

    replacement_values = {source_path: target_path}
    for quoted_source_path, quoted_target_path in zip(
        _quoted_bundle_reference_variants(source_path),
        _quoted_bundle_reference_variants(target_path),
    ):
        replacement_values[quoted_source_path] = quoted_target_path
    return replacement_values


def _replace_mrml_filename_attribute_values(
    mrml_text: str,
    replacement_values: dict[str, str],
) -> str:
    """Rewrite only exact MRML fileName attribute values, preserving their quote style."""

    def replace_attribute(match: re.Match[str]) -> str:
        prefix, quote_character, reference_value, _closing_quote = match.groups()
        repaired_reference_value = replacement_values.get(reference_value, reference_value)
        return f"{prefix}{quote_character}{repaired_reference_value}{quote_character}"

    return MRML_FILENAME_ATTRIBUTE_RE.sub(replace_attribute, mrml_text)


def _mrml_filename_attribute_values(mrml_text: str) -> list[str]:
    """Return the raw fileName attribute values in one MRML document."""

    return [match.group(3) for match in MRML_FILENAME_ATTRIBUTE_RE.finditer(mrml_text)]


def _rewrite_mrml_bundle_references(
    mrml_text: str,
    original_mrml_member_path: str,
    rewritten_mrml_member_path: str,
    renamed_paths: dict[str, str],
) -> str:
    """Rewrite raw and URL-quoted scene-bundle file references inside one MRML document."""

    replacement_values: dict[str, str] = {}
    for original_bundle_path, rewritten_bundle_path in renamed_paths.items():
        for source_path, target_path in _mrml_reference_path_pairs(
            original_mrml_member_path,
            rewritten_mrml_member_path,
            original_bundle_path,
            rewritten_bundle_path,
        ):
            replacement_values.update(_bundle_reference_replacement_values(source_path, target_path))

    return _replace_mrml_filename_attribute_values(mrml_text, replacement_values)


def _mrml_referenced_bundle_paths(mrml_text: str, mrml_member_path: str) -> set[str]:
    """Return the ZIP member paths referenced by one MRML document."""

    mrml_parent = PurePosixPath(mrml_member_path).parent
    referenced_paths: set[str] = set()
    for quoted_reference in _mrml_filename_attribute_values(mrml_text):
        decoded_reference = unquote(quoted_reference, encoding="utf-8", errors="ignore")
        referenced_paths.add((mrml_parent / decoded_reference).as_posix())
    return referenced_paths


def _replace_mrml_reference_variants(mrml_text: str, source_path: str, target_path: str) -> str:
    """Replace one MRML storage reference in both raw and URL-quoted forms."""

    return _replace_mrml_filename_attribute_values(
        mrml_text,
        _bundle_reference_replacement_values(source_path, target_path),
    )


def rewrite_scene_bundle_with_ascii_paths(
    source_mrb_path: str | Path,
    target_mrb_path: str | Path,
) -> bool:
    """Copy one MRB while normalizing bundle member names to ASCII-safe paths.

    Returns whether any member name required normalization.
    """

    renamed_paths: dict[str, str] = {}
    used_paths: set[str] = set()
    source_infos: list[zipfile.ZipInfo] = []
    category_counts = {
        "scene": 0,
        "v": 0,
        "m": 0,
        "d": 0,
        "f": 0,
    }
    directory_counts = {"dir": 0}

    with zipfile.ZipFile(filesystem_path(source_mrb_path), "r") as source_archive:
        source_infos = source_archive.infolist()
        for source_info in source_infos:
            safe_path = _compact_bundle_member_path(source_info, category_counts, directory_counts)
            safe_path = _unique_bundle_path(safe_path, source_info.is_dir(), used_paths)
            renamed_paths[source_info.filename] = safe_path

        changed_paths = {
            original_path: rewritten_path
            for original_path, rewritten_path in renamed_paths.items()
            if original_path != rewritten_path
        }
        target_member_paths = set(renamed_paths.values())
        placeholder_model_paths: set[str] = set()

        with zipfile.ZipFile(
            filesystem_path(target_mrb_path),
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as target_archive:
            for source_info in source_infos:
                target_info = _copy_zip_info(source_info, renamed_paths[source_info.filename])
                if source_info.is_dir():
                    target_archive.writestr(target_info, b"")
                    continue

                member_bytes = source_archive.read(source_info.filename)
                if source_info.filename.lower().endswith(".mrml") and changed_paths:
                    member_text = member_bytes.decode("utf-8", errors="replace")
                    member_bytes = _rewrite_mrml_bundle_references(
                        member_text,
                        source_info.filename,
                        renamed_paths[source_info.filename],
                        changed_paths,
                    ).encode("utf-8")
                if source_info.filename.lower().endswith(".mrml"):
                    repaired_mrml_text = member_bytes.decode("utf-8", errors="replace")
                    rewritten_mrml_path = renamed_paths[source_info.filename]
                    rewritten_mrml_parent = PurePosixPath(rewritten_mrml_path).parent
                    for quoted_reference in _mrml_filename_attribute_values(repaired_mrml_text):
                        decoded_reference = unquote(quoted_reference, encoding="utf-8", errors="ignore")
                        referenced_path = (rewritten_mrml_parent / decoded_reference).as_posix()
                        if not referenced_path.endswith(".vtk") or referenced_path in target_member_paths:
                            continue
                        category_counts["d"] += 1
                        placeholder_path = _unique_bundle_path(
                            f"{COMPACT_BUNDLE_DATA_DIR}/d_{category_counts['d']:03d}.vtk",
                            False,
                            used_paths,
                        )
                        target_member_paths.add(placeholder_path)
                        placeholder_model_paths.add(placeholder_path)
                        placeholder_relative_path = PurePosixPath(placeholder_path).relative_to(
                            rewritten_mrml_parent
                        ).as_posix()
                        repaired_mrml_text = _replace_mrml_reference_variants(
                            repaired_mrml_text,
                            decoded_reference,
                            placeholder_relative_path,
                        )
                    for referenced_path in _mrml_referenced_bundle_paths(
                        repaired_mrml_text,
                        renamed_paths[source_info.filename],
                    ):
                        if referenced_path.endswith(".vtk") and referenced_path not in target_member_paths:
                            placeholder_model_paths.add(referenced_path)
                            target_member_paths.add(referenced_path)
                    member_bytes = repaired_mrml_text.encode("utf-8")
                target_archive.writestr(target_info, member_bytes)

            for placeholder_path in sorted(placeholder_model_paths):
                target_archive.writestr(placeholder_path, EMPTY_POLYDATA_VTK_LEGACY.encode("utf-8"))

    return bool(placeholder_model_paths) or any(
        original_path != rewritten_path for original_path, rewritten_path in renamed_paths.items()
    )


def repair_scene_bundle_in_place(scene_path: str | Path) -> bool:
    """Rewrite one MRB in place with ASCII-safe member paths when needed."""

    scene_path_object = Path(scene_path)
    scene_directory = scene_path_object.parent
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=filesystem_path(scene_directory),
            prefix=f".{scene_path_object.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_stream:
            temporary_path = Path(temporary_stream.name)

        rewritten = rewrite_scene_bundle_with_ascii_paths(scene_path_object, temporary_path)
        if rewritten:
            os.replace(filesystem_path(temporary_path), filesystem_path(scene_path_object))
        elif temporary_path is not None and path_exists(temporary_path):
            os.unlink(filesystem_path(temporary_path))
        return rewritten
    except Exception:
        if temporary_path is not None and path_exists(temporary_path):
            os.unlink(filesystem_path(temporary_path))
        raise


def latest_saved_scene_path_for_image_filename(
    output_directory: str | Path, image_filename: str
) -> Path | None:
    """Return the most recently modified saved MRB for one image, if present."""

    default_scene = default_scene_path_for_image_filename(output_directory, image_filename)
    case_folder = default_scene.parent
    if not path_is_dir(case_folder):
        return None

    case_name = case_name_from_image_filename(image_filename)
    stem_case_name = sanitize_filename(Path(image_filename).stem or image_filename)
    all_candidates = sorted(
        directory_children(case_folder, ".mrb"),
        key=lambda path: (path_mtime(path), path.name),
        reverse=True,
    )
    if not all_candidates:
        return None

    preferred_candidates = [
        path
        for path in all_candidates
        if path.name == f"{case_name}.mrb"
        or path.name.startswith(f"{case_name}_")
        or path.name == f"{stem_case_name}.mrb"
        or path.name.startswith(f"{stem_case_name}_")
    ]
    if preferred_candidates:
        return preferred_candidates[0]
    return all_candidates[0]


def _csv_name_bases_for_image_filename(image_filename: str) -> tuple[str, ...]:
    """Return the accepted exported CSV base names for one input image name."""

    case_name = case_name_from_image_filename(image_filename)
    stem_case_name = sanitize_filename(Path(image_filename).stem or image_filename)
    if stem_case_name == case_name:
        return (case_name,)
    return (case_name, stem_case_name)


def _scene_version_suffix(scene_path: Path, image_filename: str) -> str | None:
    """Return the version suffix shared by one saved MRB and its sibling CSV, if detectable."""

    scene_name = scene_path.name
    for base_name in _csv_name_bases_for_image_filename(image_filename):
        default_scene_name = f"{base_name}.mrb"
        versioned_scene_prefix = f"{base_name}_"
        if scene_name == default_scene_name:
            return ""
        if scene_name.startswith(versioned_scene_prefix) and scene_path.suffix == ".mrb":
            return scene_path.stem[len(base_name):]
    return None


def latest_saved_csv_path_for_image_filename(
    output_directory: str | Path,
    image_filename: str,
    saved_scene_path: str | Path | None=None,
) -> Path | None:
    """Return the CSV exported alongside one image, preferring the version that matches a saved MRB."""

    default_csv = default_csv_path_for_image_filename(output_directory, image_filename)
    case_folder = default_csv.parent
    if not path_is_dir(case_folder):
        return None

    if saved_scene_path is not None:
        scene_path = Path(saved_scene_path)
        version_suffix = _scene_version_suffix(scene_path, image_filename)
        if version_suffix is not None:
            for base_name in _csv_name_bases_for_image_filename(image_filename):
                candidate = case_folder / f"{base_name}_measurements{version_suffix}.csv"
                if path_exists(candidate):
                    return candidate

    all_candidates = sorted(
        directory_children(case_folder, ".csv"),
        key=lambda path: (path_mtime(path), path.name),
        reverse=True,
    )
    preferred_candidates = [
        path
        for path in all_candidates
        if any(
            path.name == f"{base_name}_measurements.csv"
            or path.name.startswith(f"{base_name}_measurements_")
            for base_name in _csv_name_bases_for_image_filename(image_filename)
        )
    ]
    if preferred_candidates:
        return preferred_candidates[0]
    return None


def load_export_csv_rows(csv_path: str | Path) -> list[dict[str, str]]:
    """Load one exported measurement CSV with the same UTF-8 BOM handling used by the extension."""

    with open(filesystem_path(csv_path), newline="", encoding=CSV_EXPORT_ENCODING) as stream:
        reader = csv.DictReader(stream)
        if not {"section", "name"}.issubset(reader.fieldnames or ()):
            raise ValueError("Choose a Pelvic X-ray Measurements coordinate CSV.")
        return list(reader)


def _default_neck_axis_options() -> dict[MeasurementKey, dict[SideKey, dict[str, bool]]]:
    """Return the default neck-axis option state used when CSV metadata is absent."""

    return {
        MeasurementKey.NECK_AXIS: {
            SideKey.LEFT: {"lockToCenter": False, "useSingleGuide": False},
            SideKey.RIGHT: {"lockToCenter": False, "useSingleGuide": False},
        },
        MeasurementKey.IMPLANT_NECK_AXIS: {
            SideKey.LEFT: {"lockToCenter": False, "useSingleGuide": False},
            SideKey.RIGHT: {"lockToCenter": False, "useSingleGuide": False},
        },
    }


def parse_saved_case_metadata(csv_rows: list[dict[str, str]]) -> SavedCaseMetadata:
    """Extract case-level settings from one exported CSV."""

    metadata: SavedCaseMetadata = {
        "imageNodeName": None,
        "annotatorName": "",
        "exportTimestamp": "",
        "comments": "",
        "calibrationBallPresent": True,
        "calibrationBallDiameterMm": float(CALIBRATION_BALL_DIAMETER_MM),
        "neckAxisOptions": _default_neck_axis_options(),
    }
    option_names = {
        "FemoralNeckAxis_Left_LockToCenter": (MeasurementKey.NECK_AXIS, SideKey.LEFT, "lockToCenter"),
        "FemoralNeckAxis_Left_UseSingleGuide": (MeasurementKey.NECK_AXIS, SideKey.LEFT, "useSingleGuide"),
        "FemoralNeckAxis_Right_LockToCenter": (MeasurementKey.NECK_AXIS, SideKey.RIGHT, "lockToCenter"),
        "FemoralNeckAxis_Right_UseSingleGuide": (MeasurementKey.NECK_AXIS, SideKey.RIGHT, "useSingleGuide"),
        "ImplantNeckAxis_Left_LockToCenter": (MeasurementKey.IMPLANT_NECK_AXIS, SideKey.LEFT, "lockToCenter"),
        "ImplantNeckAxis_Left_UseSingleGuide": (MeasurementKey.IMPLANT_NECK_AXIS, SideKey.LEFT, "useSingleGuide"),
        "ImplantNeckAxis_Right_LockToCenter": (MeasurementKey.IMPLANT_NECK_AXIS, SideKey.RIGHT, "lockToCenter"),
        "ImplantNeckAxis_Right_UseSingleGuide": (MeasurementKey.IMPLANT_NECK_AXIS, SideKey.RIGHT, "useSingleGuide"),
    }

    diameters = {}
    for row in csv_rows:
        section = str(row.get("section", "")).strip()
        name = str(row.get("name", "")).strip()
        if section == "metadata" and name == "ImageNode":
            metadata["imageNodeName"] = row.get("details") or None
        elif section == "metadata" and name == "Annotator":
            metadata["annotatorName"] = str(row.get("details", "")).strip()
        elif section == "metadata" and name == "Timestamp":
            metadata["exportTimestamp"] = str(row.get("details", "")).strip()
        elif section == "metadata" and name == "Comments":
            metadata["comments"] = str(row.get("details", "")).strip()
        elif section == "metadata" and name == "CalibrationBall_NotPresent":
            metadata["calibrationBallPresent"] = str(row.get("raw_value", "0")).strip() != "1"
        elif section == "metadata" and name in option_names:
            measurement_key, side_key, option_key = option_names[name]
            metadata["neckAxisOptions"][measurement_key][side_key][option_key] = (
                str(row.get("raw_value", "0")).strip() == "1"
            )
        elif section in {"metadata", "measurement"} and name == "CalibrationBall_KnownDiameter":
            value_text = row.get("corrected_value_mm") or row.get("raw_value") or row.get("details")
            value_text = str(value_text or "").strip()
            if value_text:
                diameter = float(value_text)
                if not math.isfinite(diameter) or diameter <= 0:
                    raise ValueError("The saved calibration-ball diameter must be finite and positive.")
                diameters[section] = diameter

    if diameters:
        metadata["calibrationBallDiameterMm"] = diameters.get("metadata", diameters.get("measurement"))
    return metadata
