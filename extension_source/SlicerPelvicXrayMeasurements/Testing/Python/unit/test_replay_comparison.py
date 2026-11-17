"""Regression tests for cross-platform CSV replay acceptance and strict metadata."""

import csv
import math

import pytest

from compare_exports import compare_csv_files, write_html_report, write_markdown_report


def write_export(path, rows, fields=None):
    fields = fields or ["section", "name", "index", "label", "raw_value", "x_ras", "units"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def adjacent(value, steps):
    for _ in range(steps):
        value = math.nextafter(value, math.inf)
    return repr(value)


@pytest.mark.parametrize(
    "section,field",
    [
        ("measurement", "raw_value"),
        ("measurement", "corrected_value_mm"),
        ("point", "x_ras"),
        ("point", "y_ras"),
        ("point", "z_ras"),
        ("derived_point", "x_ras"),
        ("derived_point", "y_ras"),
        ("derived_point", "z_ras"),
    ],
)
def test_roundoff_limit_for_measurements_and_coordinates(tmp_path, section, field):
    fields = ["section", "name", field]
    # Include negative coordinates and a power-of-two boundary where ULP size changes.
    for value in (32.0, -32.0):
        expected = {"section": section, "name": "Test", field: repr(value)}
        source = write_export(tmp_path / "expected.csv", [expected], fields)
        actual = write_export(tmp_path / "actual.csv", [{**expected, field: adjacent(value, 8)}], fields)
        report = compare_csv_files(source, actual)
        assert report["passed"] and not report["raw_byte_match"]
        assert report["match_count"] == 0 and report["roundoff_count"] == 1
        assert report["roundoff_field_count"] == 1
        assert report["row_results"][0]["roundoff_fields"] == field
        write_export(actual, [{**expected, field: adjacent(value, 9)}], fields)
        assert not compare_csv_files(source, actual)["passed"]


@pytest.mark.parametrize(
    "section,field",
    [
        ("metadata", "raw_value"),
        ("metadata", "x_ras"),
        ("measurement", "name"),
        ("measurement", "index"),
        ("point", "label"),
        ("measurement", "units"),
    ],
)
def test_numeric_looking_metadata_stays_exact(tmp_path, section, field):
    expected = {"section": section, field: "32.0"}
    source = write_export(tmp_path / "expected.csv", [expected])
    actual = write_export(tmp_path / "actual.csv", [{**expected, field: adjacent(32.0, 1)}])
    report = compare_csv_files(source, actual)
    assert not report["passed"] and report["mismatch_count"] == 1
    assert report["roundoff_field_count"] == 0


@pytest.mark.parametrize(
    "expected,actual",
    [
        ("nan", "nan"),
        ("inf", "inf"),
        ("-inf", "-inf"),
        ("32.0", "nan"),
        ("", "0"),
        ("0", ""),
        ("32.0", "32.00000001"),
    ],
)
def test_invalid_values_missing_values_and_real_changes_fail(tmp_path, expected, actual):
    source = write_export(tmp_path / "expected.csv", [{"section": "measurement", "raw_value": expected}])
    observed = write_export(tmp_path / "actual.csv", [{"section": "measurement", "raw_value": actual}])
    assert not compare_csv_files(source, observed)["passed"]


@pytest.mark.parametrize(
    "contents",
    [
        "section,name,raw_value,extra\nmeasurement,Value,32,\n",
        "section,name\nmeasurement,Value\n",
        "name,section,raw_value\nValue,measurement,32\n",
        "section,name,raw_value,raw_value\nmeasurement,Value,32,32\n",
        "section,name,raw_value\nmeasurement,Value,32,extra\n",
        "section,name,raw_value\nmeasurement,Value\n",
    ],
)
def test_schema_changes_and_malformed_rows_fail(tmp_path, contents):
    source = tmp_path / "expected.csv"
    source.write_text("section,name,raw_value\nmeasurement,Value,32\n")
    observed = tmp_path / "actual.csv"
    observed.write_text(contents)
    report = compare_csv_files(source, observed)
    assert not report["passed"] and not report["schema_match"]
    assert report["schema_errors"]


def test_missing_unexpected_and_reordered_rows_fail(tmp_path):
    rows = [{"section": "measurement", "name": name, "raw_value": "32"} for name in ("A", "B")]
    source = write_export(tmp_path / "expected.csv", rows)
    for observed in (rows[:1], rows + rows[:1], rows[::-1]):
        actual = write_export(tmp_path / "actual.csv", observed)
        assert not compare_csv_files(source, actual)["passed"]


def test_reports_distinguish_exact_bytes_roundoff_and_failure(tmp_path):
    row = {"section": "measurement", "name": "Angle", "raw_value": "32.23095263550207"}
    source = write_export(tmp_path / "expected.csv", [row])
    for value, passed, outcome in (
        (row["raw_value"], True, "byte for byte"),
        ("32.23095263550209", True, "floating-point steps"),
        ("33", False, "does not match"),
    ):
        actual = write_export(tmp_path / "actual.csv", [{**row, "raw_value": value}])
        report = compare_csv_files(source, actual)
        assert report["passed"] is passed
        for suffix, writer in (("html", write_html_report), ("md", write_markdown_report)):
            target = tmp_path / ("report." + suffix)
            writer(report, target)
            assert outcome in target.read_text()
