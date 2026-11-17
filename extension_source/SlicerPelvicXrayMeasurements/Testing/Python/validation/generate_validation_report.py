#!/usr/bin/env python3
"""Generate a validation report for Pelvic Xray Measurements CSV output.

The extension exports a detailed CSV that contains measurements, coordinates,
derived points, and metadata. For validation we intentionally compare only the
measurement rows that are present in a separate ground-truth CSV. This mirrors
the clinical validation strategy: not every redundant left/right tool has to be
used in every synthetic test as long as each measurement family is covered.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import html
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
EXTENSION_ROOT = SCRIPT_DIR.parent.parent


@dataclass(frozen=True)
class MeasurementRow:
    """Store one measurement row from an extension-style CSV.

    Keeping parsed rows small and explicit avoids coupling the report logic to
    the CSV reader's raw dictionaries, while preserving all fields needed for
    traceability in the generated report.
    """

    name: str
    raw_value: float | None
    corrected_value_mm: float | None
    units: str
    details: str


@dataclass(frozen=True)
class Tolerances:
    """Validation cutoffs used for all numeric checks.

    The user-provided requirements define length, angle, percent, and
    morphology-ratio tolerances. Percent values are exported in percent units,
    while ratios such as CCR/CTI/CFI are exported as fractions, so both need
    explicit but differently scaled tolerances.
    """

    length_su: float
    length_mm: float
    angle_deg: float
    percent_points: float
    ratio: float
    scale_factor: float


@dataclass(frozen=True)
class CheckResult:
    """Represent one numeric comparison between ground truth and extension output.

    A single measurement may produce more than one check, such as raw scene
    units plus corrected millimetres. Splitting them keeps failures specific and
    makes calibration-related problems easy to localize.
    """

    measurement: str
    component: str
    expected: float | None
    observed: float | None
    delta: float | None
    tolerance: float | None
    status: str
    units: str
    details: str


@dataclass(frozen=True)
class FunctionalInference:
    """Summarize whether a tool-level function is validated by the numeric checks.

    These inferences do not replace raw comparisons. They explain why a passing
    representative measurement can validate a broader workflow, such as a shared
    axis construction or centralized laterality logic.
    """

    feature: str
    status: str
    evidence: str
    rationale: str


@dataclass(frozen=True)
class FunctionalRule:
    """Define how numeric evidence maps to a higher-level tool behavior.

    Each rule lists the measurement rows that must be present and passing for a
    feature-level pass. Missing evidence is reported as untested instead of
    failing the numeric validation, because validation scope is intentionally
    controlled by the ground-truth CSV.
    """

    feature: str
    evidence_names: tuple[str, ...]
    rationale: str


FUNCTIONAL_RULES = (
    FunctionalRule(
        "Calibration ball fitting and scale correction",
        ("CalibrationBall_MeasuredDiameter", "CalibrationScaleFactor", "ReferenceLine_Length"),
        "The fitted ball diameter, scale factor, and a corrected length together validate calibration and mm conversion.",
    ),
    FunctionalRule(
        "Reference Line",
        ("ReferenceLine_Length",),
        "The reference-line length validates two-point line placement and distance calculation.",
    ),
    FunctionalRule(
        "Centralized laterality handling",
        ("Left_SharpAngle", "Left_PostOp_AcetabularOffset", "Right_AcetabularIndexTonnis", "Right_PreOp_AcetabularOffset"),
        "Passing representative left and right measurements supports the shared side-selection and side-specific geometry logic.",
    ),
    FunctionalRule(
        "Femur Head",
        ("Right_FemurHead_Diameter",),
        "A correct right femur-head diameter validates the three-point circle fit, center derivation, and diameter reporting.",
    ),
    FunctionalRule(
        "Femoral Shaft Axis",
        ("Right_CCDAngle", "Right_PreOp_FemoralOffset", "Left_StemAlignment"),
        "CCD, femoral offset, and stem alignment all depend on the femoral shaft axis, so passing downstream values validate the axis workflow.",
    ),
    FunctionalRule(
        "Femoral Neck Axis and native CCD Angle",
        ("Right_CCDAngle",),
        "The native CCD angle requires both the femoral neck axis and femoral shaft axis.",
    ),
    FunctionalRule(
        "Acetabular Index (Tönnis)",
        ("Right_AcetabularIndexTonnis",),
        "A passing right Acetabular Index (Tönnis) value validates the signed Acetabular Index (Tönnis) calculation and reference-parallel arm.",
    ),
    FunctionalRule(
        "Sharp Angle",
        ("Left_SharpAngle",),
        "A passing left Sharp value validates the signed Sharp angle calculation and reference-parallel arm.",
    ),
    FunctionalRule(
        "LCE Angle",
        ("Right_LCEAngle",),
        "The LCE result validates the femur-head-center fulcrum and reference-perpendicular angle arm.",
    ),
    FunctionalRule(
        "Pre-op Acetabular Offset",
        ("Right_PreOp_AcetabularOffset",),
        "A passing right AO value validates perpendicular-to-reference offset-line spacing.",
    ),
    FunctionalRule(
        "Pre-op Femoral Offset",
        ("Right_PreOp_FemoralOffset",),
        "A passing right FO value validates shaft-parallel offset-line spacing.",
    ),
    FunctionalRule(
        "Pre-op Global Offset",
        ("Right_PreOp_GlobalOffset",),
        "The global offset validates AO + FO summation for the pre-op side.",
    ),
    FunctionalRule(
        "Femoral Head Extrusion Index",
        ("Right_FemoralHeadExtrusionIndex",),
        "The FEI percent validates the three perpendicular guide-line construction and side-aware lateral calculation.",
    ),
    FunctionalRule(
        "Leg Length Discrepancy",
        ("LLD", "LLD_Signed_LeftMinusRight"),
        "Absolute and signed LLD together validate reference-relative height difference calculation.",
    ),
    FunctionalRule(
        "Implant Head Center",
        ("Left_PostOp_ImplantHead_Diameter",),
        "The implant-head diameter validates the post-op three-point circle fit and center workflow.",
    ),
    FunctionalRule(
        "Acetabular Inclination Angle (Free Hand)",
        ("Left_AcetabularInclinationAngle_FreeHand_PostOp",),
        "A passing free-hand inclination validates the line-to-reference angle calculation.",
    ),
    FunctionalRule(
        "Cup Opening Ellipse Fit",
        ("Left_CupOpeningEllipseFit_Inclination_PostOp", "Left_CupAnteversionRetroversionAngle_PostOp"),
        "The ellipse inclination and ant/ret angle validate six-point ellipse fitting, major-axis orientation, and diameter-ratio reporting.",
    ),
    FunctionalRule(
        "Implant Neck Axis and Impl. Fem. CCD",
        ("Left_ImplantFemoralCCD_PostOp",),
        "The implant-femoral CCD result depends on the implant neck axis and native femoral shaft axis.",
    ),
    FunctionalRule(
        "Stem Alignment",
        ("Left_StemAlignment",),
        "The stem alignment angle validates the two-guide-line stem-axis workflow and comparison to the femoral shaft axis.",
    ),
    FunctionalRule(
        "Post-op Acetabular Offset",
        ("Left_PostOp_AcetabularOffset",),
        "A passing post-op AO value validates the separate THA acetabular-offset channel.",
    ),
    FunctionalRule(
        "Post-op Femoral Offset",
        ("Left_PostOp_FemoralOffset",),
        "A passing post-op FO value validates the separate THA femoral-offset channel.",
    ),
    FunctionalRule(
        "Post-op Global Offset",
        ("Left_PostOp_GlobalOffset",),
        "The post-op global offset validates THA AO + FO summation without mixing pre-op results.",
    ),
    FunctionalRule(
        "Other Line",
        ("Line_1_Length",),
        "The custom line result validates repeatable two-point distance measurement.",
    ),
    FunctionalRule(
        "Other Angle",
        ("Angle_1",),
        "The custom angle result validates repeatable three-point angle measurement.",
    ),
)

UNTESTED_NUMERIC_FEATURE_NOTES = (
    "Calibration-ball Not Present mode is not graded unless the ground-truth CSV includes CalibrationBall_NotPresent.",
    "Optional Other Angle lock-parallel and lock-perpendicular modes are not separately identifiable from the measurement CSV unless the validation file includes dedicated named angle cases.",
    "UI-only behavior such as button coloring, hide checkboxes, overwrite prompts, and image-render appearance is outside this numeric CSV validation.",
)

MORPHOLOGY_RATIO_SUFFIXES = ("CCR", "CTI", "CFI")


def parse_args() -> argparse.Namespace:
    """Parse command-line options for repeatable terminal execution.

    The two CSV inputs and one output folder are required on purpose. Validation
    runs should be explicit about which exported CSV and ground-truth CSV are
    being compared, while report filenames stay standardized inside the output
    folder.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Compare Pelvic Xray Measurements CSV output against a ground-truth CSV "
            "and generate HTML, Markdown, and machine-readable CSV reports."
        )
    )
    parser.add_argument(
        "--actual",
        type=Path,
        required=True,
        help="Extension output CSV to validate.",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        required=True,
        help="Ground-truth measurement CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output folder for validation_report.html, validation_report.md, and validation_comparison.csv.",
    )
    parser.add_argument(
        "--length-su-tolerance",
        type=float,
        default=0.2,
        help="Allowed absolute error for length raw scene-unit values.",
    )
    parser.add_argument(
        "--length-mm-tolerance",
        type=float,
        default=0.1,
        help="Allowed absolute error for corrected millimetre values.",
    )
    parser.add_argument(
        "--angle-tolerance",
        type=float,
        default=0.2,
        help="Allowed absolute error for angle values in degrees.",
    )
    parser.add_argument(
        "--percent-tolerance",
        type=float,
        default=1.0,
        help="Allowed absolute error for percentage-style values, in percentage points. Default 1.0 means +/- 1%%.",
    )
    parser.add_argument(
        "--ratio-tolerance",
        type=float,
        default=0.01,
        help="Allowed absolute error for ratio values such as CCR, CTI, and CFI. Default 0.01 means +/- 1%%.",
    )
    parser.add_argument(
        "--scale-tolerance",
        type=float,
        default=0.001,
        help="Allowed absolute error for calibration scale factor values.",
    )
    parser.add_argument(
        "--include-actual-only",
        action="store_true",
        help="Include measured rows that are not listed in the ground-truth CSV.",
    )
    return parser.parse_args()


def resolve_path(path: Path, base_dir: Path) -> Path:
    """Resolve a path relative to the current working directory and script folder.

    The script is meant to be terminal-friendly. This helper lets users run it
    either from the project root or from another working directory while still
    benefiting from the default file names.
    """

    if path.is_absolute():
        return path
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate.resolve()
    return (base_dir / path).resolve()


def resolve_output_path(path: Path) -> Path:
    """Resolve a new output path relative to the caller's working directory."""

    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (Path.cwd() / expanded).resolve()


def display_path(path: Path, preferred_base: Path) -> str:
    """Return a publish-safe path string without embedding workstation-specific roots.

    Validation reports are often shared outside the originating machine. When possible, report
    paths relative to a project root or current working directory; otherwise fall back to the file
    name instead of leaking a full absolute path.
    """

    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate

    for base in (preferred_base, Path.cwd()):
        try:
            base_resolved = base.resolve()
        except OSError:
            continue
        try:
            return str(resolved.relative_to(base_resolved))
        except ValueError:
            continue

    if not candidate.is_absolute():
        return str(candidate)
    return candidate.name


def parse_optional_float(value: str | None) -> float | None:
    """Convert a CSV numeric field into a float, preserving blanks as `None`.

    Blank fields are meaningful in the extension export: they distinguish tools
    that were not used from tools that produced a numeric value.
    """

    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_measurements(csv_path: Path) -> dict[str, MeasurementRow]:
    """Read measurement rows from a Pelvic Xray Measurements CSV.

    Rows outside the `measurement` section are intentionally ignored for numeric
    validation because point-coordinate correctness is indirectly tested by the
    measurements derived from those points.
    """

    measurements: dict[str, MeasurementRow] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            if (row.get("section") or "").strip() != "measurement":
                continue
            name = (row.get("name") or "").strip()
            if not name:
                continue
            measurements[name] = MeasurementRow(
                name=name,
                raw_value=parse_optional_float(row.get("raw_value")),
                corrected_value_mm=parse_optional_float(row.get("corrected_value_mm")),
                units=(row.get("units") or "").strip(),
                details=(row.get("details") or "").strip(),
            )
    return measurements


def measurement_kind(row: MeasurementRow) -> str:
    """Classify a measurement row so the right tolerance can be applied.

    The exported `units` text is deliberately human-readable, so classification
    uses simple semantic matching instead of brittle exact strings. A few
    validated measurement names are also recognized so older ground-truth CSVs
    with sparse unit fields still receive the right tolerance.
    """

    units = row.units.lower()
    name = row.name.lower()
    if "degree" in units:
        return "angle"
    if "percent" in units or "femoralheadextrusionindex" in name:
        return "percent"
    if "ratio" in units or any(
        name.endswith(f"_{suffix.lower()}") for suffix in MORPHOLOGY_RATIO_SUFFIXES
    ):
        return "ratio"
    if "mm per scene unit" in units:
        return "scale"
    if "flag" in units:
        return "flag"
    if "mm" in units or "su" in units:
        return "length"
    raise ValueError(
        "Could not determine a validation tolerance kind for measurement "
        f"{row.name!r} with units {row.units!r}."
    )


def compare_value(
    measurement: str,
    component: str,
    expected: float | None,
    observed: float | None,
    tolerance: float | None,
    units: str,
    details: str,
) -> CheckResult:
    """Compare one numeric value with an absolute tolerance.

    Missing observed values are treated as failures when the ground truth has a
    value, because that means the tested tool did not produce the expected
    output.
    """

    if expected is None:
        return CheckResult(
            measurement=measurement,
            component=component,
            expected=expected,
            observed=observed,
            delta=None,
            tolerance=tolerance,
            status="SKIP",
            units=units,
            details=details,
        )
    if observed is None:
        return CheckResult(
            measurement=measurement,
            component=component,
            expected=expected,
            observed=observed,
            delta=None,
            tolerance=tolerance,
            status="FAIL",
            units=units,
            details=details,
        )

    delta = observed - expected
    if tolerance is None:
        status = "PASS" if math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12) else "FAIL"
    else:
        status = "PASS" if abs(delta) <= tolerance else "FAIL"
    return CheckResult(
        measurement=measurement,
        component=component,
        expected=expected,
        observed=observed,
        delta=delta,
        tolerance=tolerance,
        status=status,
        units=units,
        details=details,
    )


def compare_measurement(
    expected: MeasurementRow,
    observed: MeasurementRow | None,
    tolerances: Tolerances,
) -> list[CheckResult]:
    """Compare one ground-truth measurement row with the extension output.

    Length rows may validate both scene units and corrected millimetres. This is
    intentional: matching corrected millimetres validates both the measurement
    geometry and the calibration scale application.
    """

    if observed is None:
        return [
            CheckResult(
                measurement=expected.name,
                component="row",
                expected=None,
                observed=None,
                delta=None,
                tolerance=None,
                status="FAIL",
                units=expected.units,
                details="Measurement row is missing from the extension output.",
            )
        ]

    kind = measurement_kind(expected)
    details = expected.details or observed.details

    if kind == "length":
        checks: list[CheckResult] = []
        if expected.raw_value is not None:
            checks.append(
                compare_value(
                    expected.name,
                    "raw_su",
                    expected.raw_value,
                    observed.raw_value,
                    tolerances.length_su,
                    "su",
                    details,
                )
            )
        if expected.corrected_value_mm is not None:
            checks.append(
                compare_value(
                    expected.name,
                    "corrected_mm",
                    expected.corrected_value_mm,
                    observed.corrected_value_mm,
                    tolerances.length_mm,
                    "mm",
                    details,
                )
            )
        return checks or [
            compare_value(
                expected.name,
                "numeric",
                expected.raw_value,
                observed.raw_value,
                tolerances.length_su,
                expected.units,
                details,
            )
        ]

    if kind == "angle":
        return [
            compare_value(
                expected.name,
                "angle_deg",
                expected.raw_value,
                observed.raw_value,
                tolerances.angle_deg,
                "degrees",
                details,
            )
        ]

    if kind == "percent":
        return [
            compare_value(
                expected.name,
                "percent_points",
                expected.raw_value,
                observed.raw_value,
                tolerances.percent_points,
                "percentage points",
                details,
            )
        ]

    if kind == "ratio":
        return [
            compare_value(
                expected.name,
                "ratio",
                expected.raw_value,
                observed.raw_value,
                tolerances.ratio,
                "ratio",
                details,
            )
        ]

    if kind == "scale":
        return [
            compare_value(
                expected.name,
                "scale_factor",
                expected.raw_value,
                observed.raw_value,
                tolerances.scale_factor,
                expected.units,
                details,
            )
        ]

    if kind == "flag":
        return [
            compare_value(
                expected.name,
                "flag",
                expected.raw_value,
                observed.raw_value,
                0.0,
                expected.units,
                details,
            )
        ]

def compare_all(
    ground_truth: dict[str, MeasurementRow],
    actual: dict[str, MeasurementRow],
    tolerances: Tolerances,
) -> list[CheckResult]:
    """Compare every ground-truth row against the corresponding actual row.

    The ground-truth file defines validation scope. This avoids failing a case
    just because intentionally unused bilateral or redundant tools are blank in
    the exported CSV.
    """

    checks: list[CheckResult] = []
    for name, expected in ground_truth.items():
        checks.extend(compare_measurement(expected, actual.get(name), tolerances))
    return checks


def nonempty_actual_only_rows(
    ground_truth: dict[str, MeasurementRow],
    actual: dict[str, MeasurementRow],
) -> list[MeasurementRow]:
    """Return actual measurement rows not covered by the ground-truth file.

    These rows are informational rather than failures. They help reviewers see
    what else the extension exported without expanding the validation scope.
    """

    extra_rows = []
    for name, row in actual.items():
        if name in ground_truth:
            continue
        if row.raw_value is None and row.corrected_value_mm is None:
            continue
        extra_rows.append(row)
    return extra_rows


def status_counts(checks: Iterable[CheckResult]) -> dict[str, int]:
    """Count PASS, FAIL, and SKIP outcomes for summary cards."""

    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return counts


def covered_measurement_counts(ground_truth: dict[str, MeasurementRow]) -> dict[str, int]:
    """Summarize validation coverage by global, left, right, and custom rows.

    The report uses this to make unilateral/bilateral coverage choices explicit
    without assuming every mirrored tool must appear in every validation image.
    """

    counts = {"global": 0, "left": 0, "right": 0, "custom": 0}
    for name in ground_truth:
        if name.startswith("Left_"):
            counts["left"] += 1
        elif name.startswith("Right_"):
            counts["right"] += 1
        elif name.startswith("Line_") or name.startswith("Angle_"):
            counts["custom"] += 1
        else:
            counts["global"] += 1
    return counts


def checks_by_measurement(checks: Iterable[CheckResult]) -> dict[str, list[CheckResult]]:
    """Group check results by measurement name for feature-level inference."""

    grouped: dict[str, list[CheckResult]] = {}
    for check in checks:
        grouped.setdefault(check.measurement, []).append(check)
    return grouped


def evidence_summary(measurement_checks: list[CheckResult]) -> str:
    """Describe the raw comparison evidence behind a functional inference.

    The wording intentionally includes expected, observed, delta, and tolerance
    values so reviewers can see the data behind a tool-level pass or fail.
    """

    parts = []
    for check in measurement_checks:
        if check.status == "SKIP":
            continue
        if check.observed is None:
            parts.append(f"{check.measurement} {check.component}: missing observed value")
            continue
        tolerance_phrase = (
            f"tolerance +/- {format_number(check.tolerance)}"
            if check.tolerance is not None
            else "exact-match tolerance"
        )
        parts.append(
            (
                f"{check.measurement} {check.component}: expected {format_number(check.expected)} "
                f"{check.units}, observed {format_number(check.observed)} {check.units}, "
                f"delta {format_number(check.delta)}, {tolerance_phrase}, {check.status}"
            )
        )
    return "; ".join(parts) if parts else "No numeric evidence available."


def infer_morphology_ratio_status(
    grouped: dict[str, list[CheckResult]],
) -> FunctionalInference:
    """Infer whether CCR, CTI, and CFI validate femur shaft morphology.

    The validation image may exercise either side. Treating left and right as
    alternative evidence sets keeps the report aligned with the module's
    centralized laterality design while still requiring the complete CCR/CTI/CFI
    trio for a full morphology pass.
    """

    side_evidence = []
    has_complete_passing_side = False
    has_failure = False
    has_any_evidence = False

    for side_label in ("Left", "Right"):
        expected_names = tuple(f"{side_label}_{suffix}" for suffix in MORPHOLOGY_RATIO_SUFFIXES)
        present_names = [name for name in expected_names if name in grouped]
        if not present_names:
            continue

        has_any_evidence = True
        missing_names = [name for name in expected_names if name not in grouped]
        present_checks = [
            check
            for name in present_names
            for check in grouped.get(name, [])
            if check.status != "SKIP"
        ]
        side_has_failure = any(check.status == "FAIL" for check in present_checks)
        has_failure = has_failure or side_has_failure
        if not missing_names and not side_has_failure and present_checks:
            has_complete_passing_side = True

        evidence = evidence_summary(present_checks)
        if missing_names:
            evidence += f"; missing evidence: {', '.join(missing_names)}"
        side_evidence.append(f"{side_label}: {evidence}")

    if not has_any_evidence:
        status = "UNTESTED"
        evidence = "No ground-truth rows found for Left/Right CCR, CTI, or CFI."
    elif has_failure:
        status = "FAIL"
        evidence = "; ".join(side_evidence)
    elif has_complete_passing_side:
        status = "PASS"
        evidence = "; ".join(side_evidence)
    else:
        status = "PARTIAL"
        evidence = "; ".join(side_evidence)

    return FunctionalInference(
        feature="Femur Shaft Morphology (CCR, CTI, CFI)",
        status=status,
        evidence=evidence,
        rationale=(
            "CCR, CTI, and CFI together validate the calibrated morphology construction, "
            "the 2/3/10/11 cm guide-point layout, and the derived ratio calculations."
        ),
    )


def infer_functional_status(checks: list[CheckResult]) -> list[FunctionalInference]:
    """Infer tool-level validation status from the raw check table.

    These summaries make the report clinically readable: a single representative
    side can validate a bilateral function when the shared laterality and
    calculation paths are otherwise exercised.
    """

    grouped = checks_by_measurement(checks)
    inferences: list[FunctionalInference] = []
    for rule in FUNCTIONAL_RULES:
        missing = [name for name in rule.evidence_names if name not in grouped]
        present_checks = [
            check
            for name in rule.evidence_names
            for check in grouped.get(name, [])
            if check.status != "SKIP"
        ]
        if not present_checks:
            status = "UNTESTED"
            evidence = f"No ground-truth row found for: {', '.join(rule.evidence_names)}"
        elif missing:
            status = "PARTIAL"
            evidence = evidence_summary(present_checks) + f"; missing evidence: {', '.join(missing)}"
        elif any(check.status == "FAIL" for check in present_checks):
            status = "FAIL"
            evidence = evidence_summary(present_checks)
        else:
            status = "PASS"
            evidence = evidence_summary(present_checks)

        inferences.append(
            FunctionalInference(
                feature=rule.feature,
                status=status,
                evidence=evidence,
                rationale=rule.rationale,
            )
        )
        if rule.feature == "Femoral Head Extrusion Index":
            inferences.append(infer_morphology_ratio_status(grouped))
    return inferences


def format_number(value: float | None, digits: int = 4) -> str:
    """Format report numbers compactly while preserving enough precision.

    Validation reports should be readable first, but the CSV output still keeps
    machine-friendly numeric values for downstream auditing.
    """

    if value is None:
        return ""
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def status_badge(status: str) -> str:
    """Return a small HTML badge for a check status."""

    label = html.escape(status)
    return f'<span class="badge badge-{label.lower()}">{label}</span>'


def file_provenance(path: Path, display_root: Path) -> dict[str, str]:
    """Collect lightweight file metadata for traceability.

    The report records only the two CSVs that actually drive validation, keeping
    the script independent of the source image format.
    """

    if not path.exists():
        return {
            "path": display_path(path, display_root),
            "exists": "no",
            "size": "",
            "modified": "",
        }
    stat = path.stat()
    modified = _dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    return {
        "path": display_path(path, display_root),
        "exists": "yes",
        "size": str(stat.st_size),
        "modified": modified,
    }


def write_checks_csv(path: Path, checks: list[CheckResult]) -> None:
    """Write the per-component comparison table as CSV.

    The HTML/Markdown reports are for humans; this file lets future validation
    dashboards or CI jobs consume the same comparisons programmatically.
    """

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "measurement",
                "component",
                "expected",
                "observed",
                "delta",
                "tolerance",
                "status",
                "units",
                "details",
            ],
        )
        writer.writeheader()
        for check in checks:
            writer.writerow(
                {
                    "measurement": check.measurement,
                    "component": check.component,
                    "expected": check.expected,
                    "observed": check.observed,
                    "delta": check.delta,
                    "tolerance": check.tolerance,
                    "status": check.status,
                    "units": check.units,
                    "details": check.details,
                }
            )


def render_markdown(
    checks: list[CheckResult],
    inferences: list[FunctionalInference],
    extra_rows: list[MeasurementRow],
    tolerances: Tolerances,
    provenance: dict[str, dict[str, str]],
    include_actual_only: bool,
) -> str:
    """Render a Markdown validation report.

    Markdown gives maintainers a reviewable text artifact that works well in
    repositories and pull requests.
    """

    counts = status_counts(checks)
    coverage = covered_measurement_counts({check.measurement: MeasurementRow(check.measurement, None, None, "", "") for check in checks})
    lines = [
        "# Pelvic Xray Measurements Validation Report",
        "",
        f"Generated: {_dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Summary",
        "",
        f"- Status: {'PASS' if counts.get('FAIL', 0) == 0 else 'FAIL'}",
        f"- Passing checks: {counts.get('PASS', 0)}",
        f"- Failing checks: {counts.get('FAIL', 0)}",
        f"- Skipped checks: {counts.get('SKIP', 0)}",
        f"- Covered measurement names: {len(set(check.measurement for check in checks))}",
        f"- Coverage by row prefix: global {coverage['global']}, left {coverage['left']}, right {coverage['right']}, custom {coverage['custom']}",
        "",
        "## Tolerances",
        "",
        f"- Length raw scene units: +/- {tolerances.length_su}",
        f"- Length corrected millimetres: +/- {tolerances.length_mm}",
        f"- Angles: +/- {tolerances.angle_deg} degrees",
        f"- Percent values: +/- {tolerances.percent_points} percentage points",
        f"- Ratio values such as CCR/CTI/CFI: +/- {tolerances.ratio}",
        f"- Calibration scale factor: +/- {tolerances.scale_factor}",
        "",
        "## Validation Strategy",
        "",
        "- Only measurement rows listed in the ground-truth CSV are graded.",
        "- Empty or unused extension rows are not failures unless the same measurement is listed in ground truth.",
        "- Length rows are checked in raw `su` and/or corrected `mm` when ground truth provides those values.",
        "- Correct corrected-mm values indirectly validate calibration scale application.",
        "- Global-offset checks indirectly validate AO + FO summation.",
        "",
        "## File Provenance",
        "",
        "| File | Exists | Size | Modified |",
        "|---|---:|---:|---|",
    ]
    for label, meta in provenance.items():
        lines.append(
            f"| {label}: `{meta['path']}` | {meta['exists']} | {meta['size']} | {meta['modified']} |"
        )

    lines.extend(
        [
            "",
            "## Detailed Checks",
            "",
            "| Status | Measurement | Component | Expected | Observed | Delta | Tolerance | Units |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for check in checks:
        lines.append(
            "| "
            + " | ".join(
                [
                    check.status,
                    f"`{check.measurement}`",
                    check.component,
                    format_number(check.expected),
                    format_number(check.observed),
                    format_number(check.delta),
                    format_number(check.tolerance),
                    check.units,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Functional Inference",
            "",
            "These statements interpret the raw checks at the tool level. They do not change the numeric pass/fail criteria.",
            "",
            "| Status | Functionality | Evidence | Why this validates the tool |",
            "|---|---|---|---|",
        ]
    )
    for inference in inferences:
        lines.append(
            "| "
            + " | ".join(
                [
                    inference.status,
                    inference.feature,
                    inference.evidence.replace("|", "\\|"),
                    inference.rationale.replace("|", "\\|"),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Functionality Without Direct Numeric Evidence",
            "",
        ]
    )
    for note in UNTESTED_NUMERIC_FEATURE_NOTES:
        lines.append(f"- {note}")

    if include_actual_only:
        lines.extend(
            [
                "",
                "## Actual-Only Measured Rows",
                "",
                "These rows were measured by the extension but were not part of the ground-truth grading scope.",
                "",
                "| Measurement | Raw | Corrected mm | Units |",
                "|---|---:|---:|---|",
            ]
        )
        for row in extra_rows:
            lines.append(
                f"| `{row.name}` | {format_number(row.raw_value)} | {format_number(row.corrected_value_mm)} | {row.units} |"
            )

    return "\n".join(lines) + "\n"


def render_html(
    checks: list[CheckResult],
    inferences: list[FunctionalInference],
    extra_rows: list[MeasurementRow],
    tolerances: Tolerances,
    provenance: dict[str, dict[str, str]],
    include_actual_only: bool,
) -> str:
    """Render a self-contained HTML validation report.

    The HTML is self-contained so it can be opened locally, attached to releases,
    or shared with collaborators without additional assets.
    """

    counts = status_counts(checks)
    overall_status = "PASS" if counts.get("FAIL", 0) == 0 else "FAIL"
    covered_measurements = len(set(check.measurement for check in checks))
    coverage = covered_measurement_counts({check.measurement: MeasurementRow(check.measurement, None, None, "", "") for check in checks})
    fail_class = "pass" if overall_status == "PASS" else "fail"

    check_rows = []
    for check in checks:
        check_rows.append(
            "<tr>"
            f"<td>{status_badge(check.status)}</td>"
            f"<td><code>{html.escape(check.measurement)}</code></td>"
            f"<td>{html.escape(check.component)}</td>"
            f"<td class=\"num\">{html.escape(format_number(check.expected))}</td>"
            f"<td class=\"num\">{html.escape(format_number(check.observed))}</td>"
            f"<td class=\"num\">{html.escape(format_number(check.delta))}</td>"
            f"<td class=\"num\">{html.escape(format_number(check.tolerance))}</td>"
            f"<td>{html.escape(check.units)}</td>"
            f"<td>{html.escape(check.details)}</td>"
            "</tr>"
        )

    inference_rows = []
    for inference in inferences:
        inference_rows.append(
            "<tr>"
            f"<td>{status_badge(inference.status)}</td>"
            f"<td><strong>{html.escape(inference.feature)}</strong></td>"
            f"<td>{html.escape(inference.evidence)}</td>"
            f"<td>{html.escape(inference.rationale)}</td>"
            "</tr>"
        )

    provenance_rows = []
    for label, meta in provenance.items():
        provenance_rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td><code>{html.escape(meta['path'])}</code></td>"
            f"<td>{html.escape(meta['exists'])}</td>"
            f"<td class=\"num\">{html.escape(meta['size'])}</td>"
            f"<td>{html.escape(meta['modified'])}</td>"
            "</tr>"
        )

    actual_only_section = ""
    if include_actual_only:
        extra_html_rows = []
        for row in extra_rows:
            extra_html_rows.append(
                "<tr>"
                f"<td><code>{html.escape(row.name)}</code></td>"
                f"<td class=\"num\">{html.escape(format_number(row.raw_value))}</td>"
                f"<td class=\"num\">{html.escape(format_number(row.corrected_value_mm))}</td>"
                f"<td>{html.escape(row.units)}</td>"
                f"<td>{html.escape(row.details)}</td>"
                "</tr>"
            )
        actual_only_section = f"""
        <section class="panel">
          <h2>Actual-Only Measured Rows</h2>
          <p>These rows were measured by the extension but were not part of the ground-truth grading scope.</p>
          <table>
            <thead>
              <tr><th>Measurement</th><th>Raw</th><th>Corrected mm</th><th>Units</th><th>Details</th></tr>
            </thead>
            <tbody>{''.join(extra_html_rows) or '<tr><td colspan="5">None</td></tr>'}</tbody>
          </table>
        </section>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pelvic Xray Measurements Validation Report</title>
  <style>
    :root {{
      --ink: #17212b;
      --muted: #64758a;
      --line: #d7e0ea;
      --paper: #f4f7fb;
      --panel: #ffffff;
      --pass: #1f8a5b;
      --fail: #b42318;
      --skip: #7a5c00;
      --accent: #24527a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: linear-gradient(135deg, #e9f0f6 0%, #f8fafc 42%, #eef4f8 100%);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{
      width: min(1180px, calc(100vw - 36px));
      margin: 32px auto;
    }}
    header {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 28px;
      background: var(--panel);
      box-shadow: 0 18px 45px rgba(30, 56, 84, 0.12);
    }}
    h1, h2 {{ margin: 0; }}
    h1 {{ font-size: clamp(28px, 4vw, 44px); letter-spacing: -0.03em; }}
    h2 {{ font-size: 20px; margin-bottom: 14px; }}
    p {{ color: var(--muted); margin: 8px 0 0; }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      padding: 8px 12px;
      border-radius: 999px;
      color: #fff;
      background: var(--{fail_class});
      font-weight: 700;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin: 18px 0;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 10px 25px rgba(30, 56, 84, 0.08);
    }}
    .card {{ padding: 16px; }}
    .card .label {{ color: var(--muted); font-size: 13px; }}
    .card .value {{ font-size: 28px; font-weight: 800; margin-top: 4px; }}
    .panel {{ padding: 22px; margin-top: 18px; overflow-x: auto; }}
    .strategy {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
      margin-top: 8px;
    }}
    .strategy div {{
      padding: 10px 12px;
      border-radius: 12px;
      background: #f6f9fc;
      color: #33475b;
      border: 1px solid #e5ecf3;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      color: #34495f;
      text-align: left;
      background: #f6f9fc;
      position: sticky;
      top: 0;
    }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    code {{
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 0.92em;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      color: #fff;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.02em;
    }}
    .badge-pass {{ background: var(--pass); }}
    .badge-fail {{ background: var(--fail); }}
    .badge-skip {{ background: var(--skip); }}
    .badge-partial {{ background: #5b6f86; }}
    .badge-untested {{ background: #6b7280; }}
    footer {{
      color: var(--muted);
      margin-top: 18px;
      text-align: center;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Pelvic Xray Measurements Validation Report</h1>
      <p>Generated {_dt.datetime.now().isoformat(timespec='seconds')}</p>
      <div class="status">Overall {overall_status}</div>
    </header>

    <section class="cards">
      <div class="card"><div class="label">Passing checks</div><div class="value">{counts.get('PASS', 0)}</div></div>
      <div class="card"><div class="label">Failing checks</div><div class="value">{counts.get('FAIL', 0)}</div></div>
      <div class="card"><div class="label">Skipped checks</div><div class="value">{counts.get('SKIP', 0)}</div></div>
      <div class="card"><div class="label">Covered measurements</div><div class="value">{covered_measurements}</div></div>
    </section>

    <section class="panel">
      <h2>Validation Strategy</h2>
      <div class="strategy">
        <div>Only rows in the ground-truth CSV are graded.</div>
        <div>Length rows validate raw <code>su</code> and corrected <code>mm</code> when available.</div>
        <div>Correct millimetres indirectly validate calibration scale application.</div>
        <div>Global offsets indirectly validate AO + FO summation.</div>
      </div>
    </section>

    <section class="panel">
      <h2>Tolerances</h2>
      <table>
        <tbody>
          <tr><th>Length raw scene units</th><td>+/- {tolerances.length_su}</td></tr>
          <tr><th>Length corrected millimetres</th><td>+/- {tolerances.length_mm}</td></tr>
          <tr><th>Angles</th><td>+/- {tolerances.angle_deg} degrees</td></tr>
          <tr><th>Percent values</th><td>+/- {tolerances.percent_points} percentage points</td></tr>
          <tr><th>Ratio values such as CCR/CTI/CFI</th><td>+/- {tolerances.ratio}</td></tr>
          <tr><th>Calibration scale factor</th><td>+/- {tolerances.scale_factor}</td></tr>
          <tr><th>Ground-truth coverage</th><td>global {coverage['global']}, left {coverage['left']}, right {coverage['right']}, custom {coverage['custom']}</td></tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2>File Provenance</h2>
      <table>
        <thead><tr><th>File</th><th>Path</th><th>Exists</th><th>Size</th><th>Modified</th></tr></thead>
        <tbody>{''.join(provenance_rows)}</tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Detailed Checks</h2>
      <table>
        <thead>
          <tr>
            <th>Status</th><th>Measurement</th><th>Component</th><th>Expected</th>
            <th>Observed</th><th>Delta</th><th>Tolerance</th><th>Units</th><th>Details</th>
          </tr>
        </thead>
        <tbody>{''.join(check_rows)}</tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Functional Inference</h2>
      <p>These statements interpret the raw checks at the tool level. They do not change the numeric pass/fail criteria.</p>
      <table>
        <thead>
          <tr><th>Status</th><th>Functionality</th><th>Evidence</th><th>Why this validates the tool</th></tr>
        </thead>
        <tbody>{''.join(inference_rows)}</tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Functionality Without Direct Numeric Evidence</h2>
      <ul>
        {''.join(f'<li>{html.escape(note)}</li>' for note in UNTESTED_NUMERIC_FEATURE_NOTES)}
      </ul>
    </section>

    {actual_only_section}

    <footer>Generated by <code>generate_validation_report.py</code></footer>
  </main>
</body>
</html>
"""


def write_report_files(
    output_dir: Path,
    checks: list[CheckResult],
    inferences: list[FunctionalInference],
    extra_rows: list[MeasurementRow],
    tolerances: Tolerances,
    provenance: dict[str, dict[str, str]],
    include_actual_only: bool,
) -> dict[str, Path]:
    """Write all report artifacts into one folder and return their paths.

    Standardized filenames make validation outputs easy to discover while the
    caller still controls where the report bundle is created.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "validation_report.html"
    markdown_path = output_dir / "validation_report.md"
    comparison_csv_path = output_dir / "validation_comparison.csv"

    markdown_path.write_text(
        render_markdown(checks, inferences, extra_rows, tolerances, provenance, include_actual_only),
        encoding="utf-8",
    )
    html_path.write_text(
        render_html(checks, inferences, extra_rows, tolerances, provenance, include_actual_only),
        encoding="utf-8",
    )
    write_checks_csv(comparison_csv_path, checks)

    return {
        "markdown": markdown_path,
        "html": html_path,
        "csv": comparison_csv_path,
    }


def main() -> int:
    """Run the validation workflow from CSV loading through report generation."""

    args = parse_args()
    actual_csv = resolve_path(args.actual, SCRIPT_DIR)
    ground_truth_csv = resolve_path(args.ground_truth, SCRIPT_DIR)
    output_dir = resolve_output_path(args.output_dir)

    if not actual_csv.exists():
        raise FileNotFoundError(f"Actual CSV not found: {actual_csv}")
    if not ground_truth_csv.exists():
        raise FileNotFoundError(f"Ground-truth CSV not found: {ground_truth_csv}")

    tolerances = Tolerances(
        length_su=args.length_su_tolerance,
        length_mm=args.length_mm_tolerance,
        angle_deg=args.angle_tolerance,
        percent_points=args.percent_tolerance,
        ratio=args.ratio_tolerance,
        scale_factor=args.scale_tolerance,
    )

    ground_truth = read_measurements(ground_truth_csv)
    actual = read_measurements(actual_csv)
    checks = compare_all(ground_truth, actual, tolerances)
    inferences = infer_functional_status(checks)
    extra_rows = nonempty_actual_only_rows(ground_truth, actual)
    provenance = {
        "Ground truth": file_provenance(ground_truth_csv, EXTENSION_ROOT),
        "Extension output": file_provenance(actual_csv, EXTENSION_ROOT),
    }

    paths = write_report_files(
        output_dir,
        checks,
        inferences,
        extra_rows,
        tolerances,
        provenance,
        args.include_actual_only,
    )

    counts = status_counts(checks)
    overall_status = "PASS" if counts.get("FAIL", 0) == 0 else "FAIL"
    print(f"Validation status: {overall_status}")
    print(f"PASS: {counts.get('PASS', 0)} | FAIL: {counts.get('FAIL', 0)} | SKIP: {counts.get('SKIP', 0)}")
    print(f"HTML report: {display_path(paths['html'], EXTENSION_ROOT)}")
    print(f"Markdown report: {display_path(paths['markdown'], EXTENSION_ROOT)}")
    print(f"Comparison CSV: {display_path(paths['csv'], EXTENSION_ROOT)}")
    return 0 if overall_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
