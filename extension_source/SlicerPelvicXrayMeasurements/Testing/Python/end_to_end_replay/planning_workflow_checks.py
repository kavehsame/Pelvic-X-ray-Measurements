"""Check surgical planning and CSV restore with real Slicer controls on a synthetic image."""

import csv
import json
import random
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import slicer


def check_planning(widget, volume, points, events):
    import vtk
    import PelvicXrayMeasurementsPlanning as plan
    from PelvicXrayMeasurementsCSVImport import prepare_csv, apply_csv

    logic = widget.logic
    widget.side_selector.setCurrentIndex(0)
    events()
    side = lambda: logic.latest_results["sides"]["left"]
    volume.CreateDefaultDisplayNodes()
    image = slicer.util.arrayFromVolume(volume)
    image[0, 323:342, 322:340] = 210
    slicer.util.arrayFromVolumeModified(volume)
    original = image.copy()

    def draw(key, coordinates):
        if key == "bone_fragment":
            widget._retain_bone("manual", "stepped")
        else:
            widget.planning_buttons[key].click()
        events()
        assert widget.active_placement_measurement_key == key, key
        points("left_" + plan.TOOLS[key][1], [(*p, 0.0) for p in coordinates])
        if key == "bone_fragment":
            widget._plan_view[0].InvokeEvent("RightButtonPressEvent")
            widget._plan_view[0].InvokeEvent("RightButtonReleaseEvent")
            events()
        assert not widget.active_placement_queue, key

    assert "fragment_pose" not in widget.planning_buttons
    assert widget.planning_buttons["bone_fragment"].text == "Retained Bone Fragment Placement"
    angle = widget.planning_fields["bone_fragment"]["angle"]
    assert not angle.enabled and angle.parentWidget() == widget.fragment_manual_button.parentWidget()
    import_row = widget.import_overlay_button.parentWidget()
    assert widget.overlay_guide_button.parentWidget() == import_row
    assert import_row.layout().indexOf(widget.overlay_guide_button) == import_row.layout().indexOf(widget.import_overlay_button) + 1
    assert widget.overlay_guide_button.text == "How It Works" and widget.overlay_guide_button.enabled
    from PelvicXrayMeasurements import MODULE_DIR
    guide = Path(MODULE_DIR) / "Resources" / "implant-overlays.html"
    assert "How implant overlays work" in guide.read_text(encoding="utf-8")
    with patch("webbrowser.open_new_tab", return_value=True) as launch:
        widget.overlay_guide_button.click()
        launch.assert_called_once_with(guide.resolve().as_uri())
    assert widget.current_image_node() == volume
    layout = import_row.parentWidget().layout()
    cup_row = widget.planning_buttons["template_cup"].parentWidget()
    assert layout.indexOf(cup_row) == layout.indexOf(import_row) + 1
    assert widget.import_overlay_button.minimumHeight == widget.planning_buttons["template_cup"].minimumHeight == 32
    assert not widget.planning_buttons["bone_fragment"].enabled
    draw("straight_resection", [(20, 20), (40, 20)])
    np.testing.assert_allclose(side()["straight_resection"]["correctedValue"], 20)
    widget.planning_buttons["bone_fragment"].click()
    events()
    auto_boundary = logic.get_node("left_fragmentBoundary")
    assert auto_boundary.GetNumberOfDefinedControlPoints() >= 5
    assert not auto_boundary.GetDisplayVisibility()
    assert side()["fragment_pose"]["defined"]
    # Exercise normal slice-view dragging inside the selected patch, away from the position landmark.
    widget._sync_plan_view()
    plan_poly = np.array(logic._fragment_hit_plans["left"]["polygon"])
    iren = widget._plan_view[0]
    matrix = vtk.vtkMatrix4x4()
    volume.GetIJKToRASMatrix(matrix)
    target = logic.get_node("left_fragmentTarget")
    pivot = logic._defined_points(target)[0].copy()
    assert widget._selected_plan_kind == "fragment" and angle.enabled and widget._plan_view[2].GetVisibility()
    info = widget._plan_screen("fragment")
    xy = np.rint(info.handle).astype(int)
    offset = xy - info.center
    goal = np.rint(info.center + [-offset[1], offset[0]]).astype(int)
    iren.SetEventPosition(*map(int, xy))
    iren.InvokeEvent("LeftButtonPressEvent")
    assert widget._plan_drag[:2] == ("rotate", "fragment")
    iren.SetEventPosition(*map(int, goal))
    iren.InvokeEvent("MouseMoveEvent")
    assert abs(abs(angle.value) - 90) < 2 and abs(logic._fragment_hit_plans["left"]["matrix"][0][0]) < 0.04
    np.testing.assert_allclose(logic._defined_points(target)[0], pivot)
    iren.InvokeEvent("LeftButtonReleaseEvent")
    angle.setValue(0)
    hit = None
    for a in np.linspace(.2,.8,5):
        xy = (1-a)*plan_poly[2] + a*plan_poly[-1]
        screen = np.rint(widget._screen(matrix.MultiplyPoint([*xy,0,1])[:3])).astype(int)
        if widget._hit_plan(screen) and widget._hit_plan(screen)[:2] == ("move", "fragment"):
            hit = screen
            break
    assert hit is not None
    iren.SetEventPosition(*map(int,hit)); iren.InvokeEvent("LeftButtonPressEvent")
    iren.SetEventPosition(*map(int,hit+[13,8])); iren.InvokeEvent("MouseMoveEvent"); iren.InvokeEvent("LeftButtonReleaseEvent")
    assert np.linalg.norm(logic._defined_points(target)[0]-pivot)>0.1
    widget.planning_buttons["bone_fragment"].click()
    events()
    assert not side()["fragment_pose"]["defined"] and auto_boundary.GetNumberOfDefinedControlPoints() == 0
    assert side()["straight_resection"]["defined"]
    draw("stepped_resection", [(20, 20), (23, 24), (40, 24)])
    np.testing.assert_allclose(side()["stepped_resection"]["correctedValue"], 22)
    draw("bone_fragment", [(40, 42), (20, 42)])
    assert widget._selected_plan_kind == "fragment" and widget._plan_view[2].GetVisibility()
    start = np.rint(widget._screen(logic._defined_points(target)[0])).astype(int)
    end = np.rint(widget._screen([80,32,0])).astype(int)
    iren.SetEventPosition(*map(int, start))
    iren.InvokeEvent("LeftButtonPressEvent")
    assert widget._plan_drag[:2] == ("move", "fragment")
    iren.SetEventPosition(*map(int, end))
    iren.InvokeEvent("MouseMoveEvent")
    iren.InvokeEvent("LeftButtonReleaseEvent")
    events()
    preview = logic._fragment_preview
    assert preview and preview.GetAttribute("PXM.FragmentSource") == volume.GetID()
    moved = slicer.util.arrayFromVolume(preview)
    assert original[0, 330, 330] == 210 and moved[0, 330, 330] != 210 and moved[0, 340, 380] == 210
    np.testing.assert_array_equal(slicer.util.arrayFromVolume(volume), original)
    widget.on_measurement_visibility_toggled("bone_fragment", True)
    assert logic._fragment_preview is None and not target.GetDisplayVisibility() and not widget._plan_view[2].GetVisibility()
    widget.on_measurement_visibility_toggled("bone_fragment", False)
    assert logic._fragment_preview is not None
    angle.setValue(25)
    assert logic.get_node("left_fragmentTarget").GetAttribute(plan.FRAGMENT_ANGLE) == "25.0"

    widget.implant_head_center_button.click()
    events()
    points("left_implantHeadPoints", [(40, 40, 0), (50, 50, 0), (60, 40, 0)])
    draw("cup_center", [(35, 44), (53, 62), (71, 44)])
    np.testing.assert_allclose(side()["inlay_wear"]["correctedValue"], 5.0, atol=1e-8)
    assert logic.get_node("left_inlayWearLine").GetNumberOfDefinedControlPoints() == 2
    assert not logic.latest_results["sides"]["right"]["inlay_wear"]["defined"]
    for kind in ("cup", "stem"):
        if not plan.default_template(kind):
            continue
        key = "template_" + kind
        controls = widget.planning_fields[key]
        controls["family"].setCurrentIndex(controls["family"].count - 1)
        controls["size"].setCurrentIndex(controls["size"].count - 1)
        controls["angle"].setValue(-15.0)
        draw(key, [(50, 40)])
        role = "left_" + plan.TOOLS[key][1]
        choice = json.loads(logic.get_node(role).GetAttribute(plan.TEMPLATE_ATTRIBUTE))
        assert choice["id"] == controls["size"].itemData(controls["size"].currentIndex)
        assert choice["angle"] == -15.0
        model = logic.get_node(role + "Outline")
        frame = model.GetPolyData()
        item = plan.ITEMS[choice["id"]]
        if "image" in item:
            assert model.GetAttribute("PXM.TemplateArtwork") == item["image"]
            assert frame.GetNumberOfPoints() == 4 and frame.GetNumberOfLines() == 0
        else:
            assert frame.GetNumberOfPoints() == len(item["outline"])
        widget._sync_plan_view()
        info = widget._plan_screen(kind)
        iren = widget._plan_view[0]
        xy = np.rint(info.handle).astype(int)
        pivot = info.center
        goal = np.rint(pivot + np.array([-(xy-pivot)[1], (xy-pivot)[0]])).astype(int)
        iren.SetEventPosition(*map(int, xy)); iren.InvokeEvent("LeftButtonPressEvent")
        assert widget._plan_drag and widget._plan_drag[0] == "rotate", (kind, xy)
        iren.SetEventPosition(*map(int, goal)); iren.InvokeEvent("MouseMoveEvent"); iren.InvokeEvent("LeftButtonReleaseEvent")
        assert abs(controls["angle"].value+15)>60 and widget._plan_drag is None
        controls["angle"].setValue(-15.0)
    widget._load_overlay_path(Path(__file__).resolve().parents[3]/"overlay-example.json")
    assert "example/asymmetric-stem/1" in plan.ITEMS
    fields=widget.planning_fields["template_stem"]
    assert fields["family"].findData("Synthetic demonstration")>=0
    logic.set_case_comments("Planning, bilateral\nmasked case")
    with tempfile.TemporaryDirectory(prefix="pxm_planning_") as folder:
        source = Path(logic.export_csv(folder, volume)["csvPath"])
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns, rows = list(reversed(reader.fieldnames)), list(reader)
        results = {row["name"]: row for row in rows if row["section"] == "measurement"}
        for _, suffix, _ in plan.LENGTH_FIELDS:
            assert "Left_" + suffix in results, suffix
        assert float(results["Left_PostOp_ProjectedHeadPenetration"]["corrected_value_mm"]) == 5.0
        rows.append({"section": "point", "name": "Future tool", "details": "right_futureRole"})
        random.Random(49).shuffle(rows)
        shuffled = Path(folder) / "shuffled.csv"
        with shuffled.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["future_column", *columns])
            writer.writeheader()
            writer.writerows(rows)
        saved = prepare_csv(logic, shuffled, volume)
        for key in plan.TOOLS:
            if key.startswith("template_") and not plan.default_template(key.removeprefix("template_")):
                continue
            assert "left_" + plan.TOOLS[key][1] in saved[1], key
        apply_csv(logic, saved, volume)
        widget.refresh_ui()
        np.testing.assert_allclose(side()["inlay_wear"]["correctedValue"], 5.0, atol=1e-8)
        np.testing.assert_allclose(side()["stepped_resection"]["correctedValue"], 22)
        assert logic.case_comments() == "Planning, bilateral\nmasked case"
        assert logic._fragment_preview.GetAttribute("PXM.FragmentSource") == volume.GetID()
        assert logic.get_node("left_fragmentBoundary").GetAttribute(plan.FRAGMENT_CUT) == "stepped"
        assert np.count_nonzero(slicer.util.arrayFromVolume(logic._fragment_preview) != original)
        assert widget._capture_annotation_image(volume).width() >= 2048
        # Load the previous release's original full export after shuffling both axes of the table.
        historical = Path(__file__).with_name("dummy_expected_full_export.csv")
        with historical.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns, rows = list(reversed(reader.fieldnames)), list(reader)
        random.Random(171).shuffle(rows)
        with shuffled.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        apply_csv(logic, prepare_csv(logic, shuffled, volume), volume)
        np.testing.assert_allclose(side()["femurHead"]["correctedValue"], 56.0)
        np.testing.assert_allclose(side()["implantHead"]["correctedValue"], 38.0)
        np.testing.assert_allclose(logic.latest_results["referenceLine"]["correctedLength"], 500.0)
        assert logic.case_comments() == "Automated replay reference case."
        assert not side()["inlay_wear"]["defined"]
        assert logic._fragment_preview is None
        assert logic.get_node("left_planningStemAnchor").GetAttribute(plan.TEMPLATE_ATTRIBUTE) is None
    print(
        "PASS: shell fit, projected wear, resection lengths, moving real image pixels, local implants and reordered CSV restore",
        flush=True,
    )
