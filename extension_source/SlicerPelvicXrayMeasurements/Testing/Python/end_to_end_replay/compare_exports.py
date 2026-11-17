"""Ordered CSV comparison with a machine-roundoff allowance for the Pelvic X-ray Measurements automation bundle."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import struct
from pathlib import Path
from typing import TypedDict

from common import display_path, sha256_of_file


class RowComparison(TypedDict):
    row_number: int
    status: str
    section: str
    name: str
    index: str
    label: str
    differing_fields: str
    roundoff_fields: str
    expected_json: str
    actual_json: str


class ComparisonReport(TypedDict):
    expected_csv: str
    actual_csv: str
    expected_row_count: int
    actual_row_count: int
    raw_byte_match: bool
    schema_match: bool
    schema_errors: list[str]
    passed: bool
    max_numeric_ulps: int
    roundoff_count: int
    roundoff_field_count: int
    expected_sha256: str
    actual_sha256: str
    match_count: int
    mismatch_count: int
    missing_count: int
    unexpected_count: int
    row_results: list[RowComparison]


# Count representable binary64 steps rather than accepting a relative tolerance.
MAX_NUMERIC_ULPS = 8
NUMERIC_FIELDS = {
    "measurement": {"raw_value", "corrected_value_mm"},
    "point": {"x_ras", "y_ras", "z_ras"},
    "derived_point": {"x_ras", "y_ras", "z_ras"},
}


def _read_export(path: Path) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Read ordered rows, rejecting duplicate headers and malformed row widths."""
    errors, rows = [], []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        if not header or any(not name for name in header) or len(set(header)) != len(header):
            errors.append("The header is empty or contains empty or duplicate names.")
        for line, values in enumerate(reader, start=2):
            if not values:
                continue
            if len(values) != len(header):
                errors.append(f"Row {line} has {len(values)} cells; expected {len(header)}.")
            rows.append({name: values[i] if i < len(values) else "" for i, name in enumerate(header)})
    return header, rows, errors


def _ordered_bits(value: float) -> int:
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    return (~bits & ((1 << 64) - 1)) if bits >> 63 else bits | (1 << 63)


def _cell_status(section: str, field: str, expected: str, actual: str) -> str:
    if field not in NUMERIC_FIELDS.get(section, set()):
        return "match" if expected == actual else "mismatch"
    if not expected or not actual:
        return "match" if expected == actual else "mismatch"
    try:
        a, b = float(expected), float(actual)
    except ValueError:
        return "mismatch"
    if not (math.isfinite(a) and math.isfinite(b)):
        return "mismatch"
    if expected == actual:
        return "match"
    if a == b or abs(_ordered_bits(a) - _ordered_bits(b)) <= MAX_NUMERIC_ULPS:
        return "roundoff"
    return "mismatch"


def compare_csv_files(expected_csv: Path, actual_csv: Path) -> ComparisonReport:
    """Require exact schema and text, retaining a separate raw-byte comparison."""
    expected_header, expected_rows, expected_errors = _read_export(expected_csv)
    actual_header, actual_rows, actual_errors = _read_export(actual_csv)
    errors = ["Expected: " + error for error in expected_errors]
    errors += ["Actual: " + error for error in actual_errors]
    if expected_header != actual_header:
        errors.append("The ordered column names differ.")
    rows: list[RowComparison] = []
    for i in range(max(len(expected_rows), len(actual_rows))):
        expected = expected_rows[i] if i < len(expected_rows) else None
        actual = actual_rows[i] if i < len(actual_rows) else None
        identity = expected if expected is not None else actual
        differing, roundoff = [], []
        if expected is None:
            status, differing = "unexpected", ["*"]
        elif actual is None:
            status, differing = "missing", ["*"]
        else:
            for field in dict.fromkeys([*expected, *actual]):
                cell = _cell_status(expected.get("section", ""), field, expected.get(field, ""), actual.get(field, ""))
                if cell == "mismatch":
                    differing.append(field)
                elif cell == "roundoff":
                    roundoff.append(field)
            status = "mismatch" if differing else "roundoff" if roundoff else "match"
        rows.append(
            {
                "row_number": i + 2,
                "status": status,
                **{key: identity.get(key, "") for key in ("section", "name", "index", "label")},
                "differing_fields": ", ".join(differing),
                "roundoff_fields": ", ".join(roundoff),
                "expected_json": json.dumps(expected, sort_keys=True)
                if expected is not None and status != "match"
                else "",
                "actual_json": json.dumps(actual, sort_keys=True) if actual is not None and status != "match" else "",
            }
        )
    counts = {
        status + "_count": sum(row["status"] == status for row in rows)
        for status in ("match", "roundoff", "mismatch", "missing", "unexpected")
    }
    return {
        "expected_csv": display_path(expected_csv),
        "actual_csv": display_path(actual_csv),
        "expected_row_count": len(expected_rows),
        "actual_row_count": len(actual_rows),
        "raw_byte_match": expected_csv.read_bytes() == actual_csv.read_bytes(),
        "schema_match": not errors,
        "schema_errors": errors,
        "passed": not errors and not any(counts[s + "_count"] for s in ("mismatch", "missing", "unexpected")),
        "max_numeric_ulps": MAX_NUMERIC_ULPS,
        "expected_sha256": sha256_of_file(expected_csv),
        "actual_sha256": sha256_of_file(actual_csv),
        **counts,
        "roundoff_field_count": sum(len(row["roundoff_fields"].split(", ")) for row in rows if row["roundoff_fields"]),
        "row_results": rows,
    }


def _outcome(report: ComparisonReport) -> str:
    if not report["passed"]:
        return "The replay export does not match the reference under the comparison rules."
    if report["raw_byte_match"]:
        return "The replay export matches the reference CSV byte for byte."
    if report["roundoff_count"]:
        return f"The replay export matches the reference within {report['max_numeric_ulps']} floating-point steps per numeric value. Raw file bytes differ."
    return "All parsed fields match exactly. Raw file bytes differ."


def write_csv_report(report: ComparisonReport, destination: Path) -> None:
    """Write the row-by-row comparison report as CSV."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_number",
        "status",
        "section",
        "name",
        "index",
        "label",
        "differing_fields",
        "roundoff_fields",
        "expected_json",
        "actual_json",
    ]
    with destination.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report["row_results"])


def write_markdown_report(report: ComparisonReport, destination: Path) -> None:
    """Write a concise Markdown summary plus the first comparison discrepancies."""

    mismatches = [row for row in report["row_results"] if row["status"] != "match"]
    lines = [
        "# Pelvic X-ray Measurements CSV Replay Report",
        "",
        f"- Expected CSV: `{report['expected_csv']}`",
        f"- Actual CSV: `{report['actual_csv']}`",
        f"- Comparison: `{'PASS' if report['passed'] else 'FAIL'}`",
        f"- Schema match: `{report['schema_match']}`",
        f"- Schema errors: `{report['schema_errors']}`",
        f"- Raw byte match: `{report['raw_byte_match']}`",
        f"- Numeric rounding limit (binary64 steps): `{report['max_numeric_ulps']}`",
        f"- Rows with accepted numeric rounding: `{report['roundoff_count']}`",
        f"- Fields with accepted numeric rounding: `{report['roundoff_field_count']}`",
        f"- Expected rows: `{report['expected_row_count']}`",
        f"- Actual rows: `{report['actual_row_count']}`",
        f"- Exact rows: `{report['match_count']}`",
        f"- Mismatched rows: `{report['mismatch_count']}`",
        f"- Missing rows: `{report['missing_count']}`",
        f"- Unexpected rows: `{report['unexpected_count']}`",
        f"- Expected SHA-256: `{report['expected_sha256']}`",
        f"- Actual SHA-256: `{report['actual_sha256']}`",
        "",
    ]
    if not mismatches and report["passed"]:
        lines.extend(
            [
                "## Outcome",
                "",
                _outcome(report),
            ]
        )
    else:
        lines.extend(
            [
                "## Outcome",
                "",
                _outcome(report),
                "",
                "## First differences (including accepted rounding)",
                "",
                "| Row | Status | Section | Name | Index | Label | Changed fields | Rounded fields |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for mismatch in mismatches[:50]:
            lines.append(
                "| {row_number} | {status} | {section} | {name} | {index} | {label} | {differing_fields} | {roundoff_fields} |".format(
                    **mismatch
                )
            )
    destination.write_text("\n".join(lines) + "\n")


def write_html_report(report: ComparisonReport, destination: Path) -> None:
    """Write an HTML visualization of the comparison summary and first differences."""

    mismatches = [row for row in report["row_results"] if row["status"] != "match"]
    summary_items = [
        ("Expected CSV", report["expected_csv"]),
        ("Actual CSV", report["actual_csv"]),
        ("Comparison", "PASS" if report["passed"] else "FAIL"),
        ("Schema match", "Yes" if report["schema_match"] else "No"),
        ("Schema errors", "; ".join(report["schema_errors"]) or "None"),
        ("Raw byte match", "Yes" if report["raw_byte_match"] else "No"),
        ("Numeric rounding limit (binary64 steps)", str(report["max_numeric_ulps"])),
        ("Rows with accepted numeric rounding", str(report["roundoff_count"])),
        ("Fields with accepted numeric rounding", str(report["roundoff_field_count"])),
        ("Expected rows", str(report["expected_row_count"])),
        ("Actual rows", str(report["actual_row_count"])),
        ("Exact rows", str(report["match_count"])),
        ("Mismatched rows", str(report["mismatch_count"])),
        ("Missing rows", str(report["missing_count"])),
        ("Unexpected rows", str(report["unexpected_count"])),
        ("Expected SHA-256", report["expected_sha256"]),
        ("Actual SHA-256", report["actual_sha256"]),
    ]

    rows_html = ""
    for mismatch in mismatches[:100]:
        rows_html += (
            "<tr>"
            f"<td>{html.escape(str(mismatch['row_number']))}</td>"
            f"<td>{html.escape(mismatch['status'])}</td>"
            f"<td>{html.escape(mismatch['section'])}</td>"
            f"<td>{html.escape(mismatch['name'])}</td>"
            f"<td>{html.escape(mismatch['index'])}</td>"
            f"<td>{html.escape(mismatch['label'])}</td>"
            f"<td>{html.escape(mismatch['differing_fields'])}</td>"
            f"<td>{html.escape(mismatch['roundoff_fields'])}</td>"
            "</tr>\n"
        )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Pelvic X-ray Measurements CSV Replay Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; }}
    h1, h2 {{ margin-bottom: 0.4rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .pass {{ color: #116329; font-weight: 700; }}
    .fail {{ color: #b42318; font-weight: 700; }}
    code {{ background: #f6f8fa; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Pelvic X-ray Measurements CSV Replay Report</h1>
  <table>
    <tbody>
      {"".join(f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in summary_items)}
    </tbody>
  </table>
  <h2>Outcome</h2>
  <p class="{"pass" if report["passed"] else "fail"}">
    {html.escape(_outcome(report))}
  </p>
  <p>The rounding allowance applies only to finite measurement values and point coordinates.
  Column names, row order, labels, units, metadata and blank values must match exactly.</p>
  <h2>First differences (including accepted rounding)</h2>
  <table>
    <thead>
      <tr>
        <th>Row</th>
        <th>Status</th>
        <th>Section</th>
        <th>Name</th>
        <th>Index</th>
        <th>Label</th>
        <th>Changed fields</th>
        <th>Rounded fields</th>
      </tr>
    </thead>
    <tbody>
      {rows_html if rows_html else '<tr><td colspan="8">No differences.</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""
    destination.write_text(html_text)


def main() -> None:
    """CLI entry point for ordered CSV comparison."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-csv", required=True, type=Path)
    parser.add_argument("--actual-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    report = compare_csv_files(args.expected_csv, args.actual_csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_report(report, args.output_dir / "comparison_details.csv")
    write_markdown_report(report, args.output_dir / "comparison_report.md")
    write_html_report(report, args.output_dir / "comparison_report.html")

    (args.output_dir / "comparison_summary.json").write_text(
        json.dumps({key: value for key, value in report.items() if key != "row_results"}, indent=2) + "\n"
    )
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
