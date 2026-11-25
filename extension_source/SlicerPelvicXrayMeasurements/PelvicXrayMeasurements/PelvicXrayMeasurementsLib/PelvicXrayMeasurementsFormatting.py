"""Formatting helpers for Pelvic X-ray Measurements.

These functions keep presentation-only string building out of the Slicer entry module. They do not
touch MRML nodes or widget state, so they can be reused by the UI and export paths without changing
runtime behavior.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PelvicXrayMeasurementsConstants import (
    IMAGE_OVERLAY_ENTRIES_PER_LINE,
    IMAGE_OVERLAY_MEASUREMENT_ORDER,
    IMAGE_OVERLAY_SIDE_ORDER,
    SIDE_LABELS,
)
from PelvicXrayMeasurementsGeometry import pretty_value

MeasurementMap = Mapping[str, Any]
ResultsMap = Mapping[str, Any]


def format_overlay_length_text(measurement: MeasurementMap) -> str | None:
    """Format one length measurement for the exported-image overlay.

    Args:
        measurement: Result entry containing `defined`, `rawValue`, and optional
            `correctedValue` fields.

    Returns:
        A length string in millimetres or scene units, or `None` when the
        measurement is undefined.
    """

    if not measurement.get("defined"):
        return None
    if measurement.get("correctedValue") is not None:
        return f"{pretty_value(measurement['correctedValue'])} mm"
    if measurement.get("rawValue") is not None:
        return f"{pretty_value(measurement['rawValue'])} su"
    return None


def format_overlay_angle_text(measurement: MeasurementMap) -> str | None:
    """Format one angle measurement for the exported-image overlay.

    Args:
        measurement: Result entry containing `defined` and `rawValue` fields.

    Returns:
        A degree string, or `None` when the measurement is undefined.
    """

    if not measurement.get("defined"):
        return None
    return f"{pretty_value(measurement['rawValue'])} deg"


def format_overlay_percent_text(measurement: MeasurementMap) -> str | None:
    """Format one percentage measurement for the exported-image overlay.

    Args:
        measurement: Result entry containing `defined` and `rawValue` fields.

    Returns:
        A percentage string, or `None` when the measurement is undefined.
    """

    if not measurement.get("defined"):
        return None
    return f"{float(measurement['rawValue']):.1f} %"


def format_overlay_ratio_text(measurement: MeasurementMap) -> str | None:
    """Format one ratio measurement for the exported-image overlay.

    Args:
        measurement: Result entry containing `defined` and `rawValue` fields.

    Returns:
        A plain ratio string, or `None` when the measurement is undefined.
    """

    if not measurement.get("defined"):
        return None
    return f"{float(measurement['rawValue']):.2f}"


def build_overlay_global_length_entry(
    results: ResultsMap,
    result_key: str,
    label: str,
) -> str | None:
    """Build one overlay entry for a global length-like measurement.

    Args:
        results: Full nested result structure for the current case.
        result_key: Name of the global result block to read.
        label: Human-facing label prefix for the overlay entry.

    Returns:
        A formatted overlay entry string, or `None` when that measurement should
        not appear.
    """

    if result_key == "calibration":
        calibration = results["calibration"]
        if not calibration["defined"]:
            return None
        if calibration["ballPresent"]:
            value_text = f"{pretty_value(calibration['knownDiameterMm'])} mm"
        elif calibration["rawDiameter"] is not None:
            value_text = f"{pretty_value(calibration['rawDiameter'])} su"
        else:
            return None
        return f"{label} {value_text}"

    if result_key == "referenceLine":
        measurement = {
            "defined": results["referenceLine"]["defined"],
            "rawValue": results["referenceLine"]["rawLength"],
            "correctedValue": results["referenceLine"]["correctedLength"],
        }
        value_text = format_overlay_length_text(measurement)
        return f"{label} {value_text}" if value_text else None

    if result_key == "lld":
        measurement = {
            "defined": results["lld"]["defined"],
            "rawValue": results["lld"]["rawValue"],
            "correctedValue": results["lld"]["correctedValue"],
        }
        value_text = format_overlay_length_text(measurement)
        return f"{label} {value_text}" if value_text else None

    return None


def _overlay_formatter_by_kind() -> dict[str, Any]:
    """Return the formatter used for each overlay entry type."""

    return {
        "sideLength": format_overlay_length_text,
        "sideAngle": format_overlay_angle_text,
        "sidePercent": format_overlay_percent_text,
        "sideRatio": format_overlay_ratio_text,
    }


def _side_overlay_entries(results: ResultsMap, formatter_by_kind: Mapping[str, Any]) -> list[str]:
    """Build ordered side-specific overlay entries from the results map."""

    entries: list[str] = []
    for entry_kind, result_key, label in IMAGE_OVERLAY_MEASUREMENT_ORDER:
        if entry_kind == "globalLength":
            entry = build_overlay_global_length_entry(results, result_key, label)
            if entry:
                entries.append(entry)
            continue

        formatter = formatter_by_kind.get(entry_kind)
        if formatter is None:
            continue

        for side_key in IMAGE_OVERLAY_SIDE_ORDER:
            measurement = results["sides"][side_key].get(result_key, {})
            value_text = formatter(measurement)
            if value_text:
                entries.append(f"{SIDE_LABELS[side_key][0]} {label} {value_text}")
    return entries


def _custom_overlay_entries(results: ResultsMap) -> list[str]:
    """Build overlay entries for user-created custom line and angle tools."""

    entries: list[str] = []
    for measurement in results["otherLines"]:
        value_text = format_overlay_length_text(measurement)
        if value_text:
            entries.append(f"Line {measurement['index']} {value_text}")

    for measurement in results["otherAngles"]:
        value_text = format_overlay_angle_text(measurement)
        if value_text:
            entries.append(f"Angle {measurement['index']} {value_text}")
    return entries


def build_measurement_overlay_entries(results: ResultsMap) -> list[str]:
    """Build the ordered list of measurement strings written onto exported images.

    Args:
        results: Full nested result structure for the current case.

    Returns:
        A list of already-formatted overlay entry strings in the exact
        user-facing order expected by the PNG export path.
    """

    entries = _side_overlay_entries(results, _overlay_formatter_by_kind())
    entries.extend(_custom_overlay_entries(results))
    return entries


def build_measurement_overlay_text(
    results: ResultsMap,
    annotator_text: str | None=None,
    entries_per_line: int | None=None,
    include_measurements: bool=True,
) -> str:
    """Assemble the exported-image overlay block.

    Args:
        results: Full nested result structure for the current case.
        annotator_text: Optional annotator line that should always appear first
            when provided.
        entries_per_line: Maximum number of measurement entries per rendered
            line. Defaults to the module-wide overlay layout constant.
        include_measurements: Whether to include numeric values alongside the
            annotator and labels for placed implants.

    Returns:
        The newline-delimited overlay text block used by the annotated PNG
        export.
    """

    entries = build_measurement_overlay_entries(results) if include_measurements else []
    lines: list[str] = []
    if annotator_text:
        lines.append(annotator_text)
    for side in IMAGE_OVERLAY_SIDE_ORDER:
        for component in ("cup", "stem"):
            implant = results["sides"][side].get("template_" + component, {}).get("implant")
            if implant:
                lines.append(implant["caption"])
    if not entries:
        return "\n".join(lines)

    per_line = entries_per_line or IMAGE_OVERLAY_ENTRIES_PER_LINE
    per_line = max(1, int(per_line))
    for start_index in range(0, len(entries), per_line):
        chunk = entries[start_index : start_index + per_line]
        lines.append("  |  ".join(chunk))
    return "\n".join(lines)


def format_calibration_summary(
    results: ResultsMap,
    calibration_ball_diameter_mm: float,
) -> str:
    """Format the calibration summary shown in the results panel.

    Args:
        results: Full nested result structure for the current case.
        calibration_ball_diameter_mm: Current configured real-world ball
            diameter from the widget/logic state.

    Returns:
        A concise calibration summary string for the UI.
    """

    calibration = results["calibration"]
    if not calibration["ballPresent"]:
        return "Not present | su only"
    if not calibration["defined"]:
        return f"Place 3 pts on the {calibration_ball_diameter_mm:.1f} mm ball."
    return (
        f"{pretty_value(calibration['rawDiameter'])} su | "
        f"{pretty_value(calibration['scaleFactor'], 4)} mm/su"
    )


def format_reference_summary(results: ResultsMap) -> str:
    """Format the reference-line summary shown in the results panel.

    Args:
        results: Full nested result structure for the current case.

    Returns:
        A concise reference-line status string for the UI.
    """

    reference = results["referenceLine"]
    if not reference["defined"]:
        return "-"
    text = f"{pretty_value(reference['rawLength'])} su"
    if reference["correctedLength"] is not None:
        text += f" | {pretty_value(reference['correctedLength'])} mm"
    return text


def format_compact_length(
    measurement: MeasurementMap,
    calibration_ball_present: bool,
) -> str:
    """Format one compact length result for the results grid.

    Args:
        measurement: Result entry containing length fields.
        calibration_ball_present: Whether the current case expects calibrated
            millimetre output when a value is available.

    Returns:
        A short grid-friendly length string.
    """

    if not measurement["defined"]:
        return "-"
    text = f"{pretty_value(measurement['rawValue'])} su"
    if measurement["correctedValue"] is not None:
        text += f" | {pretty_value(measurement['correctedValue'])} mm"
    elif calibration_ball_present:
        text += " | no cal"
    return text


def format_shaft_axis_summary(shaft_axis: MeasurementMap) -> str:
    """Format shaft-axis status text for diagnostic or legacy displays.

    Args:
        shaft_axis: Result entry containing axis definition and guide-deviation
            fields.

    Returns:
        A concise shaft-axis status string.
    """

    if not shaft_axis["defined"]:
        return "Define both femoral shaft guide lines."

    deviation_a = shaft_axis["deviationGuideA"]
    deviation_b = shaft_axis["deviationGuideB"]
    details = "Ready"
    if deviation_a is not None and deviation_b is not None:
        details += (
            " | deviation from perpendicular: "
            f"{pretty_value(deviation_a)} deg / {pretty_value(deviation_b)} deg"
        )
    return details


def format_lld_summary(results: ResultsMap) -> str:
    """Format the leg-length-discrepancy summary shown in the results panel.

    Args:
        results: Full nested result structure for the current case.

    Returns:
        A concise LLD summary string including signed calibrated output when
        available.
    """

    lld = results["lld"]
    if not lld["defined"]:
        return "Need ref + 2 pts."

    text = f"{pretty_value(lld['rawValue'])} su"
    if lld["correctedValue"] is not None:
        text += f" | {pretty_value(lld['correctedValue'])} mm"
    signed_corrected = lld["signedCorrectedValue"]
    if signed_corrected is not None:
        text += f" | L-R {pretty_value(signed_corrected)} mm"
    return text


def format_compact_angle(measurement: MeasurementMap) -> str:
    """Format one compact angle result for the results grid.

    Args:
        measurement: Result entry containing `defined` and `rawValue` fields.

    Returns:
        A short degree string, or `-` when undefined.
    """

    if not measurement["defined"]:
        return "-"
    return f"{pretty_value(measurement['rawValue'])} deg"


def format_compact_percent(measurement: MeasurementMap) -> str:
    """Format one compact percentage result for the results grid.

    Args:
        measurement: Result entry containing `defined` and `rawValue` fields.

    Returns:
        A short percentage string, or `-` when undefined.
    """

    if not measurement["defined"]:
        return "-"
    return f"{float(measurement['rawValue']):.1f} %"


def format_compact_ratio(measurement: MeasurementMap) -> str:
    """Format one compact dimensionless ratio for the results grid.

    Args:
        measurement: Result entry containing `defined` and `rawValue` fields.

    Returns:
        A short ratio string, or `-` when undefined.
    """

    if not measurement["defined"]:
        return "-"
    return f"{float(measurement['rawValue']):.2f}"
