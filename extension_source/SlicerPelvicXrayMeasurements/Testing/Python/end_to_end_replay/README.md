# Pelvic X-ray Measurements End-to-End Replay Test

This folder contains the full-case CSV replay and interaction checks for the extension. They import the live extension source and drive it from the outside, keeping automation separate from the extension runtime.

## What is inside

- [common.py]: shared paths, CSV helpers, and Slicer executable discovery.
- [scenario_definition.py]: a randomized synthetic full-case scenario that exercises every built-in tool, both sides for bilateral tools, all named contour tools, femoral-shaft contours, labelled custom points, three custom line measurements and three custom angle measurements covering `none`, `parallel`, and `perpendicular` lock modes, and non-default neck-axis mode combinations inside the same canonical replay case.
- [slicer_harness.py]: Slicer-side automation helpers for loading the extension, creating a synthetic image, populating markups, and exporting CSV.
- [slicer_generate_dummy_expected_csv.py]: uses the real extension logic to generate the golden dummy CSV.
- [slicer_replay_dummy_csv.py]: reads the dummy CSV, recreates the case by placing the editable points back into the extension, and exports a fresh actual CSV.
- [compare_exports.py]: ordered CSV comparison plus `csv`, `md`, and `html` reports.
- [run_end_to_end_test.py]: the main runner.
- **slicer_auto_place_smoke.py**: checks the Smart Point Placement dialog and derived geometry on both sides, for native and implant heads.
- **slicer_workflow_smoke.py**: checks multi-guide advancement, morphology, bilateral leg-length lines, circle visibility and advancement through four shaft contours in a live Slicer widget.

## Expected CSV

The golden dummy export is:

- [dummy_expected_full_export.csv]

It is intended to contain:

- All exported measurement rows produced by a comprehensive case where every built-in measurement family is used.
- All exported metadata rows needed for that case, including the `Annotator`, `Timestamp`, and `Comments` rows.
- All exported point rows that appear in that case, including editable inputs and extension-generated helper markups.
- Curve reconstruction metadata for contour control points, including curve type and points per interpolation segment.
- All derived-point rows emitted by the extension export.

### Where `run_end_to_end_test.py` looks for it

By default, `run_end_to_end_test.py` reads the golden CSV from the same folder as the runner itself:

- `Testing/Python/end_to_end_replay/dummy_expected_full_export.csv`

Missing reference files cause an error. `--regenerate-expected` creates a new reference inside the new run directory; the shipped reference is never overwritten.

Use **--expected-csv** to select a different reference.

## How the replay works

1. A synthetic blank image volume is created in Slicer with a fixed orientation and case name.
2. The extension logic is instantiated directly from the source.
3. The dummy CSV is parsed.
4. The exported metadata is restored into the live extension state, including the exported side-specific neck-axis option data.
5. Only the roles that are truly user-editable are placed back into the extension. Derived helper nodes are not written directly; they are allowed to be recomputed by the extension.
6. The extension exports a fresh CSV.
7. The fresh export is compared against the dummy expected CSV.

This means the test checks both:

- That the editable-input replay path reconstructs the same measurement state.
- That the extension re-derives the same helper geometry, point labels, measurement values, annotator metadata, comments metadata, line-lock metadata, neck-axis mode metadata, curve metadata, contour classifications, and export rows.

The replay also requests the optional sampled curve-points TXT export during both golden CSV generation and replay. The TXT file is checked for curve content and the expected points-per-segment metadata.

The shared scenario includes non-default neck-axis modes and all tool families, not every possible image or interaction. A coverage gate requires 58 named measurement rows and 114 coordinate roles, including four femoral-shaft contours on each side.

## Run

Invoke **run_end_to_end_test.py** with **--slicer** selecting an installed Slicer
executable, application bundle or installation directory. Use **--help** for the
full argument list. **--output-dir** selects a new evidence folder. The default
creates a new timestamped run.

**--regenerate-expected** generates a new reference inside that run; it never
overwrites the shipped reference. **--seed** makes explicit regeneration repeatable.
Review changed expectations independently of the code producing them.

## Outputs

The runner writes:

- `logs/slicer_generate_dummy_expected_csv.config.json` and `logs/slicer_replay_dummy_csv.config.json`
- `logs/generate_expected.stdout.txt` and `logs/generate_expected.stderr.txt` when regenerating the golden CSV
- `logs/replay.stdout.txt` and `logs/replay.stderr.txt`
- `logs/compare.stdout.txt` and `logs/compare.stderr.txt`
- `comparison/comparison_summary.json`
- `comparison/comparison_details.csv`
- `comparison/comparison_report.md`
- `comparison/comparison_report.html`

## Notes

- The bundle currently uses a synthetic volume named `SyntheticFullCase.dcm`, so the extension exports into a case folder named `SyntheticFullCase`.
- The comparison requires identical column names, row order, labels, units, metadata and blank values. Finite measurement values and point coordinates may differ by at most eight representable binary64 floating-point steps. The reports identify accepted rounding separately from mismatches and retain the raw-byte comparison and both checksums. This accommodates machine rounding; it is not a clinical accuracy threshold.
- The golden CSV is produced by the extension itself, which keeps the oracle aligned with the current export schema and row order.

The four-stage **Testing/Python/verify.py** runner performs unit tests, the full
CSV replay, Smart Point Placement checks and interactive workflow checks. It
requires **--slicer** and a new **--output** folder. This is software verification;
a self-generated reference is not an independent clinical comparator.
