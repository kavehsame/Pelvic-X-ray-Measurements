"""Exercise the auto-place dialog and MRML writes in a synthetic Slicer scene.

Run with Slicer --testing --python-script <this file> and the module path installed.
"""
from __future__ import annotations

import sys

import numpy as np
import qt
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy


def main():
    image = vtk.vtkImageData()
    image.SetDimensions(600, 600, 1)
    image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
    y_grid, x_grid = np.mgrid[:600, :600]
    pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(600, 600)
    left_shaft = np.exp(-((x_grid - (155 + 0.06 * (y_grid - 300))) / 30) ** 4)
    right_shaft = np.exp(-((x_grid - (445 - 0.06 * (y_grid - 300))) / 30) ** 4)
    pixels[:] = np.asarray(30 + 170 * np.maximum(left_shaft, right_shaft), dtype=np.uint8)
    image.Modified()
    volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "Synthetic radiograph")
    volume.SetAndObserveImageData(image)
    volume.SetOrigin(-300, -300, 0)
    volume.SetSpacing(1, 1, 1)
    widget = slicer.modules.pelvicxraymeasurements.widgetRepresentation().self()
    from PelvicXrayMeasurementsAutoPlacement import (
        enforce_morphology_side_constraints,
        make_frame,
        predict_feature,
        read_model,
    )
    from PelvicXrayMeasurementsConstants import MeasurementKey

    widget._warn = lambda message: print(f"WARN: {message}")
    widget._sync_current_image_node(volume)
    widget.side_selector.setCurrentIndex(0)
    panel = widget.auto_place_button.parentWidget()
    smart_labels = [label for label in panel.findChildren(qt.QLabel) if label.text == "Smart Point Placement"]
    assert smart_labels, "Smart Point Placement section heading is missing"
    setup_labels = [label for label in panel.findChildren(qt.QLabel) if label.text == "1: Setup"]
    assert setup_labels, "Setup heading is missing"
    panel_layout = panel.layout()
    auto_index = panel_layout.indexOf(widget.auto_place_button)
    smart_index = panel_layout.indexOf(smart_labels[0])
    assert smart_index < auto_index, "Smart Point Placement heading must appear above the Auto-place button"
    setup_index = panel_layout.indexOf(setup_labels[0])
    assert auto_index < setup_index, "Auto-place button must appear above the 1: Setup heading"

    def set_points(role, coordinates):
        node = widget.logic.get_node(role, create_if_missing=True)
        labels = widget.logic._node_spec_for_role(role).get("labels", [])
        widget.logic._set_named_points(node, [np.array(point, dtype=float) for point in coordinates], labels)

    def assert_shaft_guide_spans(proximal, distal):
        for node in (proximal, distal):
            span = np.linalg.norm(widget.logic._markup_control_point_position(node, 1)
                                  - widget.logic._markup_control_point_position(node, 0))
            assert 15 < span < 50, f"{node.GetName()} guide span collapsed or exceeded anatomical range: {span:.1f}"

    def assert_line_span(role, minimum):
        node = widget.logic.get_node(role, create_if_missing=False)
        assert node and node.GetNumberOfDefinedControlPoints() == 2, f"{role} was not placed"
        span = np.linalg.norm(widget.logic._markup_control_point_position(node, 1)
                              - widget.logic._markup_control_point_position(node, 0))
        assert span > minimum, f"{role} line collapsed to {span:.1f}"

    def assert_morphology_sides(side):
        shaft_axis = widget.logic.latest_results["sides"][side]["femoralShaftAxis"]
        assert shaft_axis["defined"], f"{side} shaft axis was not derived from its two guides"
        axis_node = widget.logic.get_node(f"{side}_shaftAxis", create_if_missing=False)
        assert axis_node.GetNumberOfDefinedControlPoints() == 2 and axis_node.GetDisplayVisibility(), f"{side} shaft axis line was not drawn"
        head = widget.logic.latest_results["sides"][side]["femurHead"]
        reference = widget.logic.latest_results["referenceLine"]
        frame = make_frame(side, reference["points"][:2], head["center"], head["rawValue"])
        direction = np.asarray(shaft_axis["direction"], dtype=float)
        direction /= np.linalg.norm(direction)
        lateral = np.r_[frame[2][0], 0.0]
        lateral -= direction * np.dot(lateral, direction)
        lateral /= np.linalg.norm(lateral)
        origin = np.asarray(shaft_axis["origin"], dtype=float)
        cortex = widget.logic.get_node(f"{side}_shaftMorphologyPoints", create_if_missing=False)
        assert cortex.GetNumberOfDefinedControlPoints() == 10, f"{side} cortex points were not placed"
        offsets = [np.dot(widget.logic._markup_control_point_position(cortex, index) - origin, lateral)
                   for index in range(10)]
        lateral_indices = (1, 3, 6, 7, 9) if side == "left" else (0, 2, 4, 5, 8)
        assert all(offsets[index] > 0 for index in lateral_indices), f"{side} inferred lateral points crossed the shaft axis: {offsets}"
        assert all(offsets[index] < 0 for index in range(10) if index not in lateral_indices), f"{side} inferred medial points crossed the shaft axis: {offsets}"
        model = read_model(widget._auto_point_model_path())
        inferred = predict_feature(model, "pre", "shaft_morphology", frame)["shaftMorphologyPoints"]
        constrained = enforce_morphology_side_constraints(
            inferred, shaft_axis["origin"], shaft_axis["direction"], frame, side
        )
        expected_offsets = [np.dot(point - origin, lateral) for point in constrained]
        np.testing.assert_allclose(offsets, expected_offsets, atol=1e-3,
                                   err_msg=f"{side} morphology used default widths instead of the learned offsets")

    set_points("calibrationPoints", [[150, 150, 0], [162.5, 162.5, 0], [175, 150, 0]])
    set_points("referenceLine", [[-60, -20, 0], [-140, -20, 0]])
    set_points("left_femurHeadPoints", [[-120, 0, 0], [-100, 20, 0], [-80, 0, 0]])
    widget.logic.update_all_derived_measurements(volume)
    widget.refresh_ui()
    assert widget.auto_place_button.isEnabled(), "Prerequisites should enable auto placement"

    dialog_checks = []

    def accept_dialog(attempt=0):
        matches = [item for item in qt.QApplication.topLevelWidgets() if item.isVisible() and item.windowTitle.startswith("Auto-place")]
        if matches:
            dialog = matches[0]
            confirm = next((button for button in dialog.findChildren(qt.QPushButton)
                            if button.objectName == "autoPlaceConfirmButton"), None)
            morphology = [checkbox for checkbox in dialog.findChildren(qt.QCheckBox)
                          if "Femur shaft morphology" in checkbox.text]
            shaft_axis = [checkbox for checkbox in dialog.findChildren(qt.QCheckBox)
                          if "Femoral shaft axis" in checkbox.text]
            implant_neck = [checkbox for checkbox in dialog.findChildren(qt.QCheckBox)
                            if "Implant neck axis" in checkbox.text]
            dialog_checks.append((bool(confirm and confirm.isVisible()),
                                  bool(morphology and morphology[0].isChecked()),
                                  bool(shaft_axis and shaft_axis[0].isChecked()),
                                  bool(implant_neck and implant_neck[0].isChecked())))
            if confirm and confirm.isVisible():
                confirm.click()
            else:
                dialog.reject()
            return
        warnings = [item for item in qt.QApplication.topLevelWidgets() if isinstance(item, qt.QMessageBox) and item.isVisible()]
        for warning in warnings:
            print(f"WARN: {warning.text}")
            warning.accept()
        if not warnings and attempt < 50:
            qt.QTimer.singleShot(100, lambda: accept_dialog(attempt + 1))

    qt.QTimer.singleShot(100, accept_dialog)
    widget.on_auto_place_clicked()
    assert dialog_checks[-1] == (True, True, True, False), "Confirm, morphology, and shaft axis must be visible and selected"
    sharp = widget.logic.get_node("left_sharpAngleLine", create_if_missing=False)
    assert sharp.GetNumberOfDefinedControlPoints() == 2, "Sharp suggestion was not placed"
    assert not bool(sharp.GetLocked()), "Suggested points must remain editable"
    morphology = widget.logic.get_node("left_shaftMorphologyLTPoints", create_if_missing=False)
    assert morphology.GetNumberOfDefinedControlPoints() == 2, "Morphology LT suggestion was not placed"
    proximal = widget.logic.get_node("left_shaftGuideProximal", create_if_missing=False)
    distal = widget.logic.get_node("left_shaftGuideDistal", create_if_missing=False)
    assert proximal.GetNumberOfDefinedControlPoints() == 2 and distal.GetNumberOfDefinedControlPoints() == 2, "Shaft axis guides were not placed"
    assert_shaft_guide_spans(proximal, distal)
    for role in ("left_acetabularOffsetLineA", "left_acetabularOffsetLineB", "left_femoralOffsetLine",
                 "left_extrusionIndexMedialLine", "left_extrusionIndexMiddleLine", "left_extrusionIndexLateralLine"):
        assert_line_span(role, 20)
    derived = widget.logic.get_node("left_shaftMorphologyPoints", create_if_missing=False)
    assert derived.GetNumberOfDefinedControlPoints() == 10, "Remaining morphology points were not constructed"
    assert widget.logic.latest_results["sides"]["left"]["femurShaftMorphology"]["defined"], "Left morphology measurements were not constructed"
    assert_morphology_sides("left")
    third_station_width = np.linalg.norm(widget.logic._markup_control_point_position(derived, 2) - widget.logic._markup_control_point_position(derived, 3))
    assert third_station_width > 0, "Morphology 3 cm point pair collapsed"

    widget.logic.get_node("left_femurHeadPoints").RemoveAllControlPoints()
    proximal.RemoveAllControlPoints()
    distal.RemoveAllControlPoints()
    set_points("left_implantHeadPoints", [[-120, 0, 0], [-100, 20, 0], [-80, 0, 0]])
    widget.logic.update_all_derived_measurements(volume)
    widget.refresh_ui()
    print("Post-op prerequisites:", widget.logic.latest_results["sides"]["left"]["femurHead"]["defined"], widget.logic.latest_results["sides"]["left"]["implantHead"]["defined"])
    assert widget.auto_place_button.isEnabled(), "Implant head should select post-op mode"
    qt.QTimer.singleShot(100, accept_dialog)
    widget.on_auto_place_clicked()
    assert dialog_checks[-1] == (True, False, True, True), "Post-op shaft axis and implant neck should be selected"
    implant_neck = widget.logic.get_node("left_implantNeckGuideProximal", create_if_missing=False)
    assert implant_neck.GetNumberOfDefinedControlPoints() == 2, "Implant neck suggestion was not placed"
    assert not bool(implant_neck.GetLocked()), "Post-op points must remain editable"
    assert widget.logic.axis_use_single_guide_enabled(MeasurementKey.IMPLANT_NECK_AXIS, "left"), "Auto-place must enable single-guide implant neck mode"
    assert widget.logic.axis_lock_to_center_enabled(MeasurementKey.IMPLANT_NECK_AXIS, "left"), "Auto-place must enable through-center implant neck mode"
    implant_neck_axis = widget.logic.get_node("left_implantNeckAxis", create_if_missing=False)
    assert implant_neck_axis.GetNumberOfDefinedControlPoints() == 2, "Derived implant neck axis was not drawn"
    assert bool(implant_neck_axis.GetDisplayVisibility()), "Derived implant neck axis is not visible"
    assert proximal.GetNumberOfDefinedControlPoints() == 2 and distal.GetNumberOfDefinedControlPoints() == 2, "Post-op shaft axis guides were not placed"
    assert_shaft_guide_spans(proximal, distal)
    for role in ("left_acetabularInclinationLine", "left_postOpAcetabularOffsetLineA",
                 "left_postOpAcetabularOffsetLineB", "left_postOpFemoralOffsetLine"):
        assert_line_span(role, 20)

    widget.side_selector.setCurrentIndex(1)
    set_points("referenceLine", [[60, -20, 0], [140, -20, 0]])
    set_points("right_femurHeadPoints", [[80, 0, 0], [100, 20, 0], [120, 0, 0]])
    widget.logic.update_all_derived_measurements(volume)
    widget.refresh_ui()
    assert widget.current_side_key() == "right" and widget.auto_place_button.isEnabled()
    qt.QTimer.singleShot(100, accept_dialog)
    widget.on_auto_place_clicked()
    assert dialog_checks[-1] == (True, True, True, False), "Right pre-op shaft axis and morphology should be selected"
    right_sharp = widget.logic.get_node("right_sharpAngleLine", create_if_missing=False)
    assert right_sharp.GetNumberOfDefinedControlPoints() == 2, "Right-side suggestion was not placed"
    right_proximal = widget.logic.get_node("right_shaftGuideProximal", create_if_missing=False)
    right_distal = widget.logic.get_node("right_shaftGuideDistal", create_if_missing=False)
    right_derived = widget.logic.get_node("right_shaftMorphologyPoints", create_if_missing=False)
    assert right_proximal.GetNumberOfDefinedControlPoints() == 2 and right_distal.GetNumberOfDefinedControlPoints() == 2, "Right shaft axis guides were not placed"
    assert_shaft_guide_spans(right_proximal, right_distal)
    assert right_derived.GetNumberOfDefinedControlPoints() == 10, "Right morphology points were not constructed"
    assert_morphology_sides("right")

    widget.logic.get_node("right_femurHeadPoints").RemoveAllControlPoints()
    right_proximal.RemoveAllControlPoints()
    right_distal.RemoveAllControlPoints()
    set_points("right_implantHeadPoints", [[80, 0, 0], [100, 20, 0], [120, 0, 0]])
    widget.logic.update_all_derived_measurements(volume)
    widget.refresh_ui()
    qt.QTimer.singleShot(100, accept_dialog)
    widget.on_auto_place_clicked()
    assert dialog_checks[-1] == (True, False, True, True), "Right post-op shaft axis and implant neck should be selected"
    right_implant_neck = widget.logic.get_node("right_implantNeckGuideProximal", create_if_missing=False)
    assert right_implant_neck.GetNumberOfDefinedControlPoints() == 2, "Right implant neck suggestion was not placed"
    assert widget.logic.axis_use_single_guide_enabled(MeasurementKey.IMPLANT_NECK_AXIS, "right"), "Right auto-place must enable single-guide implant neck mode"
    assert widget.logic.axis_lock_to_center_enabled(MeasurementKey.IMPLANT_NECK_AXIS, "right"), "Right auto-place must enable through-center implant neck mode"
    right_implant_neck_axis = widget.logic.get_node("right_implantNeckAxis", create_if_missing=False)
    assert right_implant_neck_axis.GetNumberOfDefinedControlPoints() == 2, "Right derived implant neck axis was not drawn"
    assert bool(right_implant_neck_axis.GetDisplayVisibility()), "Right derived implant neck axis is not visible"
    assert right_proximal.GetNumberOfDefinedControlPoints() == 2 and right_distal.GetNumberOfDefinedControlPoints() == 2, "Right post-op shaft axis guides were not placed"
    assert_shaft_guide_spans(right_proximal, right_distal)
    qt.QApplication.processEvents()
    widget.cleanup()
    print("PASS: left/right pre/post dialogs, shaft guides, and pre-op derived morphology points")


try:
    main()
except Exception as error:
    print(f"FAIL: {error}", file=sys.stderr)
    slicer.app.exit(1)
else:
    slicer.app.exit(0)
