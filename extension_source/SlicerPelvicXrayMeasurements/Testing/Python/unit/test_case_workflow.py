"""Unit tests for folder-driven case workflow helpers."""
from __future__ import annotations

import zipfile
from pathlib import Path
from urllib.parse import quote

import pytest

from PelvicXrayMeasurementsCaseWorkflow import (
    default_csv_path_for_image_filename,
    default_scene_path_for_image_filename,
    directory_children,
    filesystem_path,
    is_supported_input_image,
    latest_saved_csv_path_for_image_filename,
    latest_saved_scene_path_for_image_filename,
    list_input_images,
    load_export_csv_rows,
    parse_saved_case_metadata,
    path_exists,
    path_is_dir,
    path_mtime,
    rewrite_scene_bundle_with_ascii_paths,
)
from PelvicXrayMeasurementsConstants import MeasurementKey, SideKey


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-25"])
def test_saved_calibration_rejects_invalid_diameter(value):
    rows = [{"section": "measurement", "name": "CalibrationBall_KnownDiameter", "corrected_value_mm": value}]
    with pytest.raises(ValueError, match="finite and positive"):
        parse_saved_case_metadata(rows)


def test_input_image_discovery_filters_supported_files(tmp_path: Path) -> None:
    """Folder image discovery should include supported image-like files only."""

    dcm_path = tmp_path / "case_a.dcm"
    png_path = tmp_path / "case_b.png"
    suffixless_path = tmp_path / "case_c"
    ignored_text_path = tmp_path / "notes.txt"
    hidden_path = tmp_path / ".hidden.dcm"

    for path in [dcm_path, png_path, suffixless_path, ignored_text_path, hidden_path]:
        path.write_text("x")

    assert is_supported_input_image(dcm_path) is True
    assert is_supported_input_image(png_path) is True
    assert is_supported_input_image(suffixless_path) is True
    assert is_supported_input_image(ignored_text_path) is False
    assert is_supported_input_image(hidden_path) is False

    discovered = list_input_images(tmp_path)
    assert [path.name for path in discovered] == ["case_a.dcm", "case_b.png", "case_c"]


def test_latest_saved_scene_lookup_prefers_newest_matching_scene(tmp_path: Path) -> None:
    """Saved-scene lookup should find the newest MRB version for one image name."""

    image_filename = "Example Case.dcm"
    default_scene_path = default_scene_path_for_image_filename(tmp_path, image_filename)
    default_scene_path.parent.mkdir(parents=True, exist_ok=True)
    default_scene_path.write_text("base")

    newer_scene_path = default_scene_path.with_name(f"{default_scene_path.stem}_2{default_scene_path.suffix}")
    newer_scene_path.write_text("newer")

    default_scene_path.touch()
    newer_scene_path.touch()

    latest_scene_path = latest_saved_scene_path_for_image_filename(tmp_path, image_filename)
    assert latest_scene_path == newer_scene_path


def test_latest_saved_scene_lookup_accepts_stem_named_scene_files(tmp_path: Path) -> None:
    """Saved-scene lookup should also accept MRBs named from the node stem only."""

    image_filename = "Example Case.dcm"
    case_folder = default_scene_path_for_image_filename(tmp_path, image_filename).parent
    case_folder.mkdir(parents=True, exist_ok=True)
    stem_named_scene_path = case_folder / "Example Case.mrb"
    stem_named_scene_path.write_text("scene")

    latest_scene_path = latest_saved_scene_path_for_image_filename(tmp_path, image_filename)
    assert latest_scene_path == stem_named_scene_path


def test_latest_saved_csv_lookup_prefers_scene_matched_version(tmp_path: Path) -> None:
    """Saved CSV lookup should favor the CSV that corresponds to the selected MRB version."""

    image_filename = "Example Case.dcm"
    default_scene_path = default_scene_path_for_image_filename(tmp_path, image_filename)
    default_csv_path = default_csv_path_for_image_filename(tmp_path, image_filename)
    default_scene_path.parent.mkdir(parents=True, exist_ok=True)
    default_scene_path.write_text("scene-1")
    default_csv_path.write_text("csv-1")

    newer_scene_path = default_scene_path.with_name(f"{default_scene_path.stem}_2{default_scene_path.suffix}")
    newer_csv_path = default_csv_path.with_name(f"{default_csv_path.stem}_2{default_csv_path.suffix}")
    newer_scene_path.write_text("scene-2")
    newer_csv_path.write_text("csv-2")

    latest_csv_path = latest_saved_csv_path_for_image_filename(
        tmp_path,
        image_filename,
        newer_scene_path,
    )
    assert latest_csv_path == newer_csv_path


def test_path_helpers_support_directory_scans_and_file_reads(tmp_path: Path) -> None:
    """Path helpers should preserve ordinary behavior while routing file access through one shim."""

    case_folder = tmp_path / "case_folder"
    case_folder.mkdir()
    csv_path = case_folder / "case_measurements.csv"
    mrb_path = case_folder / "case.mrb"
    txt_path = case_folder / "notes.txt"

    csv_path.write_text("section,name\nmetadata,CaseName\n", encoding="utf-8-sig")
    mrb_path.write_text("scene")
    txt_path.write_text("ignore")

    assert filesystem_path(csv_path) == str(csv_path)
    assert path_exists(csv_path) is True
    assert path_is_dir(case_folder) is True
    assert path_is_dir(csv_path) is False
    assert path_mtime(csv_path) > 0.0
    assert [path.name for path in directory_children(case_folder, ".csv")] == ["case_measurements.csv"]
    assert [path.name for path in directory_children(case_folder, ".mrb")] == ["case.mrb"]
    assert load_export_csv_rows(csv_path) == [{"section": "metadata", "name": "CaseName"}]


def test_rewrite_scene_bundle_with_ascii_paths_repairs_malformed_member_names(tmp_path: Path) -> None:
    """Scene-bundle repair should normalize malformed storage member names and MRML references."""

    source_bundle_path = tmp_path / "source_scene.mrb"
    repaired_bundle_path = tmp_path / "repaired_scene.mrb"
    malformed_relative_reference = (
        "Data/Hip Measurements - Left Acetabular Index (T%ffc3%ffb6nnis) Line.mrk.json"
    )
    malformed_member_path = (
        "Example_Case.dcm/Data/"
        "Hip Measurements - Left Acetabular Index (T%ffc3%ffb6nnis) Line.mrk.json"
    )
    malformed_member_reference = quote(malformed_relative_reference, safe="/")

    with zipfile.ZipFile(source_bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as source_bundle:
        source_bundle.writestr(
            "Example_Case.dcm/scene.mrml",
            (
                "<MRML>"
                f'<Storage fileName="{malformed_member_reference}" />'
                "</MRML>"
            ).encode(),
        )
        source_bundle.writestr(malformed_member_path, b"{}")

    rewritten = rewrite_scene_bundle_with_ascii_paths(source_bundle_path, repaired_bundle_path)

    assert rewritten is True

    with zipfile.ZipFile(repaired_bundle_path, "r") as repaired_bundle:
        repaired_names = repaired_bundle.namelist()
        repaired_mrml = repaired_bundle.read("S/scene.mrml").decode("utf-8")

    assert all("%ff" not in member_name.lower() for member_name in repaired_names)
    assert "S/Data/m_001.mrk.json" in repaired_names
    assert "%ff" not in repaired_mrml.lower()
    assert 'fileName="Data/m_001.mrk.json"' in repaired_mrml
    assert 'fileName="Example_Case.dcm/Data/' not in repaired_mrml


def test_rewrite_scene_bundle_with_ascii_paths_adds_missing_model_placeholders(tmp_path: Path) -> None:
    """Scene-bundle repair should add placeholder VTK files for missing derived model storage."""

    source_bundle_path = tmp_path / "source_scene_missing_model.mrb"
    repaired_bundle_path = tmp_path / "repaired_scene_missing_model.mrb"

    with zipfile.ZipFile(source_bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as source_bundle:
        source_bundle.writestr(
            "Example_Case.dcm/scene.mrml",
            b'<MRML><Storage fileName="Data/Hip%20Measurements%20-%20Left%20Femur%20Head%20Circle.vtk" /></MRML>',
        )

    rewritten = rewrite_scene_bundle_with_ascii_paths(source_bundle_path, repaired_bundle_path)

    assert rewritten is True

    with zipfile.ZipFile(repaired_bundle_path, "r") as repaired_bundle:
        repaired_names = repaired_bundle.namelist()
        placeholder_bytes = repaired_bundle.read("S/Data/d_001.vtk")

    assert "S/Data/d_001.vtk" in repaired_names
    assert b"DATASET POLYDATA" in placeholder_bytes


def test_rewrite_scene_bundle_with_ascii_paths_preserves_distinct_resaved_markup_references(
    tmp_path: Path,
) -> None:
    """Re-save repair should not chain-rename compact markup references onto each other."""

    source_bundle_path = tmp_path / "source_scene_resaved.mrb"
    repaired_bundle_path = tmp_path / "repaired_scene_resaved.mrb"

    with zipfile.ZipFile(source_bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as source_bundle:
        source_bundle.writestr(
            "Example_Case.dcm/scene.mrml",
            (
                "<MRML>"
                '<Storage id="original_m001" fileName="Data/m_001.mrk.json" />'
                '<Storage id="original_m049" fileName="Data/m_049.mrk.json" />'
                '<Storage id="original_m083" fileName="Data/m_083.mrk.json" />'
                "</MRML>"
            ).encode(),
        )
        source_bundle.writestr("Example_Case.dcm/Data/m_049.mrk.json", b'{"name": "m049"}')
        source_bundle.writestr("Example_Case.dcm/Data/m_083.mrk.json", b'{"name": "m083"}')
        source_bundle.writestr("Example_Case.dcm/Data/m_001.mrk.json", b'{"name": "m001"}')

    rewritten = rewrite_scene_bundle_with_ascii_paths(source_bundle_path, repaired_bundle_path)

    assert rewritten is True

    with zipfile.ZipFile(repaired_bundle_path, "r") as repaired_bundle:
        repaired_mrml = repaired_bundle.read("S/scene.mrml").decode("utf-8")

    assert '<Storage id="original_m001" fileName="Data/m_003.mrk.json" />' in repaired_mrml
    assert '<Storage id="original_m049" fileName="Data/m_001.mrk.json" />' in repaired_mrml
    assert '<Storage id="original_m083" fileName="Data/m_002.mrk.json" />' in repaired_mrml


def test_load_and_parse_saved_case_metadata_recovers_case_settings(tmp_path: Path) -> None:
    """Saved-case CSV parsing should recover timestamped case metadata and axis options."""

    csv_path = tmp_path / "saved_case_measurements.csv"
    csv_path.write_text(
        "\n".join(
            [
                "section,name,index,label,x_ras,y_ras,z_ras,curve_type,curve_points_per_segment,raw_value,corrected_value_mm,units,details",
                "metadata,ImageNode,,,,,,,,,,,Example Case.dcm",
                "metadata,Annotator,,,,,,,,,,,Dr Example",
                "metadata,Timestamp,,,,,,,,,,,2026-06-10 13:45:12",
                "metadata,Comments,,,,,,,,,,,Saved case note",
                "metadata,CalibrationBall_NotPresent,,,,,,,,1,,flag,",
                "metadata,FemoralNeckAxis_Left_UseSingleGuide,,,,,,,,1,,flag,",
                "measurement,CalibrationBall_KnownDiameter,,,,,,,,,32.5,mm,",
            ]
        ),
        encoding="utf-8-sig",
    )

    saved_metadata = parse_saved_case_metadata(load_export_csv_rows(csv_path))

    assert saved_metadata["imageNodeName"] == "Example Case.dcm"
    assert saved_metadata["annotatorName"] == "Dr Example"
    assert saved_metadata["exportTimestamp"] == "2026-06-10 13:45:12"
    assert saved_metadata["comments"] == "Saved case note"
    assert saved_metadata["calibrationBallPresent"] is False
    assert saved_metadata["calibrationBallDiameterMm"] == 32.5
    assert (
        saved_metadata["neckAxisOptions"][MeasurementKey.NECK_AXIS][SideKey.LEFT]["useSingleGuide"]
        is True
    )
