"""Strict CSV comparison and report generation for the Pelvic X-ray Measurements automation bundle."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import TypedDict

from common import display_path, load_csv_rows, sha256_of_file


class RowComparison(TypedDict):
    row_number: int
    status: str
    section: str
    name: str
    index: str
    label: str
    differing_fields: str
    expected_json: str
    actual_json: str


class ComparisonReport(TypedDict):
    expected_csv: str
    actual_csv: str
    expected_row_count: int
    actual_row_count: int
    raw_byte_match: bool
    expected_sha256: str
    actual_sha256: str
    match_count: int
    mismatch_count: int
    missing_count: int
    unexpected_count: int
    row_results: list[RowComparison]


def compare_csv_files(expected_csv: Path, actual_csv: Path) -> ComparisonReport:
    """Compare two CSV exports both as raw bytes and as ordered row dictionaries."""

    expected_bytes = expected_csv.read_bytes()
    actual_bytes = actual_csv.read_bytes()
    expected_rows = load_csv_rows(expected_csv)
    actual_rows = load_csv_rows(actual_csv)

    max_rows = max(len(expected_rows), len(actual_rows))
    row_results: list[RowComparison] = []
    match_count = 0
    mismatch_count = 0
    missing_count = 0
    unexpected_count = 0

    for row_index in range(max_rows):
        expected_row = expected_rows[row_index] if row_index < len(expected_rows) else None
        actual_row = actual_rows[row_index] if row_index < len(actual_rows) else None

        if expected_row is None:
            unexpected_count += 1
            row_results.append(
                {
                    "row_number": row_index + 2,
                    "status": "unexpected",
                    "section": actual_row.get("section", ""),
                    "name": actual_row.get("name", ""),
                    "index": actual_row.get("index", ""),
                    "label": actual_row.get("label", ""),
                    "differing_fields": "*",
                    "expected_json": "",
                    "actual_json": json.dumps(actual_row, sort_keys=True),
                }
            )
            continue

        if actual_row is None:
            missing_count += 1
            row_results.append(
                {
                    "row_number": row_index + 2,
                    "status": "missing",
                    "section": expected_row.get("section", ""),
                    "name": expected_row.get("name", ""),
                    "index": expected_row.get("index", ""),
                    "label": expected_row.get("label", ""),
                    "differing_fields": "*",
                    "expected_json": json.dumps(expected_row, sort_keys=True),
                    "actual_json": "",
                }
            )
            continue

        differing_fields = [
            field_name
            for field_name in expected_row.keys()
            if expected_row.get(field_name, "") != actual_row.get(field_name, "")
        ]
        if differing_fields:
            mismatch_count += 1
            row_results.append(
                {
                    "row_number": row_index + 2,
                    "status": "mismatch",
                    "section": expected_row.get("section", ""),
                    "name": expected_row.get("name", ""),
                    "index": expected_row.get("index", ""),
                    "label": expected_row.get("label", ""),
                    "differing_fields": ", ".join(differing_fields),
                    "expected_json": json.dumps(expected_row, sort_keys=True),
                    "actual_json": json.dumps(actual_row, sort_keys=True),
                }
            )
        else:
            match_count += 1
            row_results.append(
                {
                    "row_number": row_index + 2,
                    "status": "match",
                    "section": expected_row.get("section", ""),
                    "name": expected_row.get("name", ""),
                    "index": expected_row.get("index", ""),
                    "label": expected_row.get("label", ""),
                    "differing_fields": "",
                    "expected_json": "",
                    "actual_json": "",
                }
            )

    return {
        "expected_csv": display_path(expected_csv),
        "actual_csv": display_path(actual_csv),
        "expected_row_count": len(expected_rows),
        "actual_row_count": len(actual_rows),
        "raw_byte_match": expected_bytes == actual_bytes,
        "expected_sha256": sha256_of_file(expected_csv),
        "actual_sha256": sha256_of_file(actual_csv),
        "match_count": match_count,
        "mismatch_count": mismatch_count,
        "missing_count": missing_count,
        "unexpected_count": unexpected_count,
        "row_results": row_results,
    }


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
        f"- Raw byte match: `{'PASS' if report['raw_byte_match'] else 'FAIL'}`",
        f"- Expected rows: `{report['expected_row_count']}`",
        f"- Actual rows: `{report['actual_row_count']}`",
        f"- Matching rows: `{report['match_count']}`",
        f"- Mismatched rows: `{report['mismatch_count']}`",
        f"- Missing rows: `{report['missing_count']}`",
        f"- Unexpected rows: `{report['unexpected_count']}`",
        f"- Expected SHA-256: `{report['expected_sha256']}`",
        f"- Actual SHA-256: `{report['actual_sha256']}`",
        "",
    ]
    if not mismatches:
        lines.extend(
            [
                "## Outcome",
                "",
                "The replay export matches the dummy expected CSV exactly.",
            ]
        )
    else:
        lines.extend(
            [
                "## Outcome",
                "",
                "The replay export does not exactly match the dummy expected CSV.",
                "",
                "## First Differences",
                "",
                "| Row | Status | Section | Name | Index | Label | Fields |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for mismatch in mismatches[:50]:
            lines.append(
                "| {row_number} | {status} | {section} | {name} | {index} | {label} | {differing_fields} |".format(
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
        ("Raw byte match", "PASS" if report["raw_byte_match"] else "FAIL"),
        ("Expected rows", str(report["expected_row_count"])),
        ("Actual rows", str(report["actual_row_count"])),
        ("Matching rows", str(report["match_count"])),
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
      {''.join(f'<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>' for label, value in summary_items)}
    </tbody>
  </table>
  <h2>Outcome</h2>
  <p class="{'pass' if not mismatches and report['raw_byte_match'] else 'fail'}">
    {'The replay export matches the dummy expected CSV exactly.' if not mismatches and report['raw_byte_match'] else 'The replay export does not exactly match the dummy expected CSV.'}
  </p>
  <h2>First Differences</h2>
  <table>
    <thead>
      <tr>
        <th>Row</th>
        <th>Status</th>
        <th>Section</th>
        <th>Name</th>
        <th>Index</th>
        <th>Label</th>
        <th>Fields</th>
      </tr>
    </thead>
    <tbody>
      {rows_html if rows_html else '<tr><td colspan="7">No differences.</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""
    destination.write_text(html_text)


def main() -> None:
    """CLI entry point for exact CSV comparison."""

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

    exit_code = 0 if report["raw_byte_match"] and report["mismatch_count"] == 0 and report["missing_count"] == 0 and report["unexpected_count"] == 0 else 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
