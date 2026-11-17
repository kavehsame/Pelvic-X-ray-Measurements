"""Exercise manual placement queues and display visibility in a real Slicer UI."""
import json
import traceback

import qt
import slicer
import vtk


def main():
    from PelvicXrayMeasurementsConstants import MeasurementKey

    print("SLICER_RUNTIME " + json.dumps({
        "version": str(slicer.app.applicationVersion),
        "revision": str(slicer.app.repositoryRevision),
    }), flush=True)

    image = vtk.vtkImageData()
    image.SetDimensions(600, 600, 1)
    image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
    image.GetPointData().GetScalars().Fill(100)
    volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "Synthetic workflow case")
    volume.SetAndObserveImageData(image)
    volume.SetOrigin(-300, -300, 0)
    widget = slicer.modules.pelvicxraymeasurements.widgetRepresentation().self()
    widget._sync_current_image_node(volume)
    widget.side_selector.setCurrentIndex(0)

    def no_warning(message):
        raise AssertionError(message)

    widget._warn = no_warning

    def events():
        for _ in range(6):
            qt.QApplication.processEvents()

    def points(role, coordinates):
        node = widget.logic.get_node(role, create_if_missing=True)
        for point in coordinates:
            node.AddControlPointWorld(vtk.vtkVector3d(*point))
            events()
        return node

    def queued(role):
        events()
        assert widget.active_placement_queue and widget.active_placement_queue[0]["role"] == role

    widget.on_reference_line_clicked()
    queued("referenceLine")
    points("referenceLine", [(-150, 20, 0), (150, 20, 0)])
    assert not widget.active_placement_queue
    widget.on_calibration_clicked()
    points("calibrationPoints", [(150, 150, 0), (162.5, 162.5, 0), (175, 150, 0)])
    widget.on_femur_head_clicked()
    points("left_femurHeadPoints", [(-120, 0, 0), (-100, 20, 0), (-80, 0, 0)])

    widget.on_shaft_axis_clicked()
    queued("left_shaftGuideProximal")
    points("left_shaftGuideProximal", [(-120, -65, 0), (-80, -65, 0)])
    queued("left_shaftGuideDistal")
    points("left_shaftGuideDistal", [(-119, -185, 0), (-81, -185, 0)])
    assert not widget.active_placement_queue
    assert widget.logic.latest_results["sides"]["left"]["femoralShaftAxis"]["defined"]
    print("PASS: shaft guides advance independently and immediately derive the axis", flush=True)

    widget.logic.set_axis_lock_to_center_enabled(MeasurementKey.NECK_AXIS, "left", False)
    widget.logic.set_axis_use_single_guide_enabled(MeasurementKey.NECK_AXIS, "left", False)
    widget.refresh_ui()
    widget.on_neck_axis_clicked()
    queued("left_neckGuideProximal")
    points("left_neckGuideProximal", [(-90, -5, 0), (-110, 10, 0)])
    queued("left_neckGuideDistal")
    points("left_neckGuideDistal", [(-120, -40, 0), (-140, -25, 0)])
    assert not widget.active_placement_queue
    assert widget.logic.latest_results["sides"]["left"]["femoralNeckAxis"]["defined"]
    print("PASS: native two-guide neck placement", flush=True)

    widget.on_femur_shaft_morphology_clicked()
    points("left_shaftMorphologyLTPoints", [(-120, -40, 0), (-120, -60, 0)])
    assert widget.logic.get_node("left_shaftMorphologyPoints").GetNumberOfDefinedControlPoints() == 10
    assert widget.logic.latest_results["sides"]["left"]["femurShaftMorphology"]["defined"]
    widget.on_lld_clicked()
    points("lldPoints", [(-100, -50, 0), (100, -60, 0)])
    assert widget.logic.get_node("lldLeftParallel").GetNumberOfDefinedControlPoints() == 2
    assert widget.logic.get_node("lldRightParallel").GetNumberOfDefinedControlPoints() == 2
    print("PASS: ten morphology controls and bilateral LLD constructions", flush=True)

    widget.logic.set_measurement_visible(MeasurementKey.FEMUR_HEAD, False, "left")
    widget.logic.update_all_derived_measurements(volume)
    assert not widget.logic.get_node("left_femurHeadCircle").GetDisplayVisibility()
    widget.logic.set_measurement_visible(MeasurementKey.FEMUR_HEAD, True, "left")
    widget.logic.update_all_derived_measurements(volume)
    assert widget.logic.get_node("left_femurHeadCircle").GetDisplayVisibility()

    widget.on_femoral_shaft_contour_clicked()
    for index in range(4):
        assert widget.active_femoral_shaft_contour_step_index == index
        x = -124 + 16 * index
        points(f"left_femoralShaftContour{index + 1}", [(x, -80, 0), (x, -125, 0), (x, -200, 0)])
        # This is the same interaction-mode change produced by a right-click.
        widget.logic.stop_placement_mode()
        events()
    assert widget.active_femoral_shaft_contour_step_index is None
    assert widget.logic.latest_results["sides"]["left"]["femoralShaftContours"]["defined"]
    print("PASS: circle visibility and automatic advancement through all four shaft contours", flush=True)
    widget.cleanup()


try:
    main()
except Exception:
    traceback.print_exc()
    slicer.app.exit(1)
else:
    slicer.app.exit(0)
