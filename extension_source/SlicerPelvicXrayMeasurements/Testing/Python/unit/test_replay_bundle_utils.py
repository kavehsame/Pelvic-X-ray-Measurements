"""Unit tests for replay-bundle utilities that do not require Slicer."""
# ruff: noqa: I001
from __future__ import annotations

import csv
from pathlib import Path

from PelvicXrayMeasurementsConstants import OtherAngleLockMode
from common import (
    discover_extension_dir,
    display_path,
    expected_csv_path,
    load_csv_rows,
    normalize_slicer_input_path,
    resolve_slicer_runtime,
)
from compare_exports import (
    compare_csv_files,
    write_csv_report,
    write_html_report,
    write_markdown_report,
)
from slicer_harness import parse_replay_metadata, role_points_from_csv_rows
from run_end_to_end_test import serialize_config_for_log


def write_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    """Write a small deterministic CSV for comparison tests."""

    fieldnames = ["section", "name", "index", "label", "details", "raw_value"]
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_common_path_helpers(tmp_path: Path) -> None:
    """Replay path helpers should resolve bundle paths without leaking absolute roots."""

    root = discover_extension_dir()
    assert (root / 'PelvicXrayMeasurements').is_dir() or (root / 'PelvicXrayMeasurements.py').is_file()
    assert expected_csv_path().name == "dummy_expected_full_export.csv"
    assert display_path(tmp_path / "example.txt", preferred_base=tmp_path) == "example.txt"

    mac_bundle = tmp_path / "Slicer.app"
    (mac_bundle / "Contents" / "MacOS").mkdir(parents=True)
    (mac_bundle / "Contents" / "bin").mkdir(parents=True)
    (mac_bundle / "Contents" / "MacOS" / "Slicer").write_text("")
    (mac_bundle / "Contents" / "bin" / "PythonSlicer").write_text("")
    (mac_bundle / "Contents" / "bin" / "python-real").write_text("")

    normalized = normalize_slicer_input_path(mac_bundle)
    assert normalized.name == "Slicer"
    launcher, python_real = resolve_slicer_runtime(normalized)
    assert launcher.name == "PythonSlicer"
    assert python_real.name == "python-real"

    linux_install = tmp_path / "Slicer-linux"
    (linux_install / "bin").mkdir(parents=True)
    for name in ("Slicer", "bin/PythonSlicer", "bin/python-real"):
        (linux_install / name).write_text("")
    normalized = normalize_slicer_input_path(linux_install)
    assert normalized == linux_install / "Slicer"
    launcher, python_real = resolve_slicer_runtime(normalized)
    assert launcher == linux_install / "bin/PythonSlicer"
    assert python_real == linux_install / "bin/python-real"


def test_serialize_config_for_log(tmp_path: Path) -> None:
    """Config serialization should convert Path values into relative JSON-safe strings."""

    config = {
        "extensionDir": tmp_path / "extension",
        "randomSeed": 123,
    }
    serialized = serialize_config_for_log(config, tmp_path)
    assert serialized == {
        "extensionDir": "extension",
        "randomSeed": 123,
    }


def test_compare_exports_and_report_writers(tmp_path: Path) -> None:
    """CSV comparison and report generation should stay deterministic."""

    expected_csv = tmp_path / "expected.csv"
    actual_csv = tmp_path / "actual.csv"
    write_rows(
        expected_csv,
        [
            {"section": "metadata", "name": "CaseName", "index": "", "label": "", "details": "A", "raw_value": ""},
            {"section": "measurement", "name": "Value", "index": "1", "label": "", "details": "", "raw_value": "5"},
        ],
    )
    write_rows(
        actual_csv,
        [
            {"section": "metadata", "name": "CaseName", "index": "", "label": "", "details": "A", "raw_value": ""},
            {"section": "measurement", "name": "Value", "index": "1", "label": "", "details": "", "raw_value": "6"},
            {"section": "measurement", "name": "Extra", "index": "2", "label": "", "details": "", "raw_value": "7"},
        ],
    )

    report = compare_csv_files(expected_csv, actual_csv)
    assert report["raw_byte_match"] is False
    assert report["match_count"] == 1
    assert report["mismatch_count"] == 1
    assert report["unexpected_count"] == 1

    csv_report = tmp_path / "report.csv"
    md_report = tmp_path / "report.md"
    html_report = tmp_path / "report.html"
    write_csv_report(report, csv_report)
    write_markdown_report(report, md_report)
    write_html_report(report, html_report)

    assert csv_report.exists()
    assert "does not exactly match" in md_report.read_text()
    assert "<table>" in html_report.read_text()


def test_load_csv_rows_handles_utf8_bom(tmp_path: Path) -> None:
    """Replay CSV readers should accept UTF-8 BOM files written for spreadsheet compatibility."""

    csv_path = tmp_path / "bom.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["section", "name"])
        writer.writeheader()
        writer.writerow({"section": "metadata", "name": "CaseName"})

    rows = load_csv_rows(csv_path)
    assert rows == [{"section": "metadata", "name": "CaseName"}]


def test_parse_replay_metadata_restores_line_and_angle_lock_modes() -> None:
    """Replay metadata parsing should recover custom line and angle lock modes from CSV details."""

    rows = [
        {"section": "metadata", "name": "ImageNode", "details": "Example.dcm"},
        {"section": "metadata", "name": "Annotator", "details": "Automated Test"},
        {"section": "metadata", "name": "Timestamp", "details": "2026-06-10 14:05:00"},
        {"section": "metadata", "name": "Comments", "details": "Replay metadata"},
        {
            "section": "measurement",
            "name": "Line_1_Length",
            "details": (
                "Custom line measurement created from two placed points. "
                "Orientation locked parallel to the reference line."
            ),
        },
        {
            "section": "measurement",
            "name": "Line_2_Length",
            "details": (
                "Custom line measurement created from two placed points. "
                "Orientation locked perpendicular to the reference line."
            ),
        },
        {
            "section": "measurement",
            "name": "Angle_1",
            "details": "Custom three-point angle measurement. First arm locked parallel to the reference line.",
        },
        {
            "section": "measurement",
            "name": "Angle_2",
            "details": "Custom three-point angle measurement. First arm locked perpendicular to the reference line.",
        },
    ]

    metadata = parse_replay_metadata(rows)
    assert metadata["exportTimestamp"] == "2026-06-10 14:05:00"
    assert metadata["lineLockModes"] == {
        1: OtherAngleLockMode.PARALLEL,
        2: OtherAngleLockMode.PERPENDICULAR,
    }
    assert metadata["angleLockModes"] == {
        1: OtherAngleLockMode.PARALLEL,
        2: OtherAngleLockMode.PERPENDICULAR,
    }


def test_role_points_from_csv_rows_strips_point_detail_metadata() -> None:
    """Replay grouping should use the role prefix when point details include extra metadata."""

    rows = [
        {
            "section": "point",
            "index": "0",
            "label": "FemoralShaft_MedialOuterCortex_1",
            "x_ras": "1.0",
            "y_ras": "2.0",
            "z_ras": "0.0",
            "details": (
                "left_femoralShaftContour1; "
                "femoral_shaft_contour_class=medialOuter (Medial Outer Cortex)"
            ),
        }
    ]

    grouped = role_points_from_csv_rows(rows)

    assert list(grouped) == ["left_femoralShaftContour1"]
    assert grouped["left_femoralShaftContour1"][0]["label"] == "FemoralShaft_MedialOuterCortex_1"
