"""Unit tests for presentation-only formatting helpers."""
from __future__ import annotations

from PelvicXrayMeasurementsFormatting import (
    build_measurement_overlay_entries,
    build_measurement_overlay_text,
    format_calibration_summary,
    format_compact_angle,
    format_compact_length,
    format_compact_percent,
    format_compact_ratio,
    format_lld_summary,
    format_overlay_angle_text,
    format_overlay_length_text,
    format_overlay_percent_text,
    format_overlay_ratio_text,
    format_reference_summary,
    format_shaft_axis_summary,
)
from PelvicXrayMeasurementsResults import MeasurementResultsMixin


class DummyResultsOwner(MeasurementResultsMixin):
    """Minimal object that supplies the result-mixin runtime attributes."""

    calibration_ball_present = True
    calibration_ball_diameter_mm = 25.0


def make_results() -> dict[str, object]:
    """Create a fresh result structure for formatting tests."""

    return DummyResultsOwner()._empty_results()


def test_overlay_scalar_formatters() -> None:
    """Overlay-specific scalar formatters should emit the expected unit strings."""

    measurement = {"defined": True, "rawValue": 12.345, "correctedValue": 6.789}
    assert format_overlay_length_text(measurement) == "6.79 mm"
    assert format_overlay_angle_text({"defined": True, "rawValue": 22.2}) == "22.20 deg"
    assert format_overlay_percent_text({"defined": True, "rawValue": 41.23}) == "41.2 %"
    assert format_overlay_ratio_text({"defined": True, "rawValue": 1.234}) == "1.23"


def test_summary_formatters() -> None:
    """Results-panel summaries should preserve their current wording and units."""

    results = make_results()
    assert format_calibration_summary(results, 25.0) == "Place 3 pts on the 25.0 mm ball."

    results["calibration"]["ballPresent"] = False
    assert format_calibration_summary(results, 25.0) == "Not present | su only"

    results["calibration"]["ballPresent"] = True
    results["calibration"]["defined"] = True
    results["calibration"]["rawDiameter"] = 44.0
    results["calibration"]["scaleFactor"] = 0.56818
    assert format_calibration_summary(results, 25.0) == "44.00 su | 0.5682 mm/su"

    assert format_reference_summary(results) == "-"
    results["referenceLine"]["defined"] = True
    results["referenceLine"]["rawLength"] = 123.456
    results["referenceLine"]["correctedLength"] = 70.0
    assert format_reference_summary(results) == "123.46 su | 70.00 mm"

    assert format_lld_summary(results) == "Need ref + 2 pts."
    results["lld"]["defined"] = True
    results["lld"]["rawValue"] = 8.0
    results["lld"]["correctedValue"] = 4.5
    results["lld"]["signedCorrectedValue"] = -4.5
    assert format_lld_summary(results) == "8.00 su | 4.50 mm | L-R -4.50 mm"


def test_compact_measurement_formatters() -> None:
    """Compact grid formatters should stay concise and unit-aware."""

    length_measurement = {"defined": True, "rawValue": 10.0, "correctedValue": 5.0}
    assert format_compact_length(length_measurement, calibration_ball_present=True) == "10.00 su | 5.00 mm"
    assert format_compact_length(
        {"defined": True, "rawValue": 10.0, "correctedValue": None},
        calibration_ball_present=True,
    ) == "10.00 su | no cal"
    assert format_compact_angle({"defined": True, "rawValue": 33.3}) == "33.30 deg"
    assert format_compact_percent({"defined": True, "rawValue": 47.89}) == "47.9 %"
    assert format_compact_ratio({"defined": True, "rawValue": 1.234}) == "1.23"


def test_shaft_axis_summary() -> None:
    """The diagnostic shaft-axis summary should reflect definition and deviation state."""

    assert format_shaft_axis_summary({"defined": False}) == "Define both femoral shaft guide lines."
    summary = format_shaft_axis_summary(
        {
            "defined": True,
            "deviationGuideA": 2.5,
            "deviationGuideB": 1.5,
        }
    )
    assert summary == "Ready | deviation from perpendicular: 2.50 deg / 1.50 deg"


def test_overlay_text_builder_includes_annotator_and_measurements() -> None:
    """Overlay text assembly should keep annotator metadata first and preserve measurement ordering."""

    results = make_results()
    results["calibration"]["defined"] = True
    results["calibration"]["rawDiameter"] = 40.0
    results["calibration"]["knownDiameterMm"] = 25.0
    results["referenceLine"]["defined"] = True
    results["referenceLine"]["rawLength"] = 100.0
    results["referenceLine"]["correctedLength"] = 50.0
    results["sides"]["left"]["tonnisAngle"]["defined"] = True
    results["sides"]["left"]["tonnisAngle"]["rawValue"] = 12.0
    results["otherLines"].append({"index": 1, "defined": True, "rawValue": 7.0, "correctedValue": None})
    results["otherAngles"].append({"index": 1, "defined": True, "rawValue": 42.0})

    entries = build_measurement_overlay_entries(results)
    assert any(entry.startswith("Cal 25.00 mm") for entry in entries)
    assert any(entry.startswith("L Acetabular Index (Tönnis) 12.00 deg") for entry in entries)
    assert any(entry == "Line 1 7.00 su" for entry in entries)
    assert any(entry == "Angle 1 42.00 deg" for entry in entries)

    overlay_text = build_measurement_overlay_text(
        results=results,
        annotator_text="Annotator: Automated Test",
        entries_per_line=2,
        include_measurements=True,
    )
    lines = overlay_text.splitlines()
    assert lines[0] == "Annotator: Automated Test"
    assert any("Cal 25.00 mm" in line for line in lines[1:])


def test_overlay_text_builder_can_emit_annotator_only() -> None:
    """Measurement suppression should still keep the annotator line."""

    overlay_text = build_measurement_overlay_text(
        results=make_results(),
        annotator_text="Annotator: Example",
        include_measurements=False,
    )
    assert overlay_text == "Annotator: Example"


def test_placed_implant_caption_is_independent_of_cut_lengths_and_numeric_overlay():
    from PelvicXrayMeasurementsPlanning import implant_report

    results = make_results()
    choice = {"id": "test/42", "family": "Synthetic shell", "size": "42 mm"}
    results["sides"]["right"]["template_cup"]["implant"] = implant_report("right", "cup", choice)
    results["sides"]["left"]["straight_resection"].update(defined=True, rawValue=17, correctedValue=17)
    for values in (True, False):
        text = build_measurement_overlay_text(results, annotator_text="Annotator: Test", include_measurements=values)
        assert text.splitlines()[:2] == ["Annotator: Test", "Right cup · Synthetic shell · Size 42 mm"]
        assert "Straight cut" not in text and "Left cup" not in text


def test_pretty_value_and_sanitize_filename() -> None:
    import PelvicXrayMeasurementsGeometry as geometry
    """Display formatting and filename cleanup should remain stable."""

    assert geometry.pretty_value(None) == "Not defined"
    assert geometry.pretty_value(12.3456, 2) == "12.35"
    assert geometry.sanitize_filename("A/B  C?.dcm") == "A_B_C_.dcm"
