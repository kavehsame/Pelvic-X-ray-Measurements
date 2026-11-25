"""Receive a reoriented browser plan inside an actual Slicer process and return its CSV."""

import json
import os
from pathlib import Path
import traceback
from unittest.mock import patch

import numpy as np
import slicer
import vtk


def main():
    from PelvicXrayMeasurementsCSVImport import apply_csv, prepare_csv

    folder = Path(os.environ["PXM_INTEROP_DIR"])
    volume = slicer.util.loadVolume(str(folder / "Oblique.nrrd"))
    widget = slicer.modules.pelvicxraymeasurements.widgetRepresentation().self()
    widget._sync_current_image_node(volume)
    logic = widget.logic
    expected = json.loads((folder / "expected.json").read_text())
    inv = vtk.vtkMatrix4x4()
    volume.GetRASToIJKMatrix(inv)
    for edition in ("slicer", "web"):
        apply_csv(logic, prepare_csv(logic, folder / f"legacy_{edition}.csv", volume), volume)
        for role in ("left_resectionStraight", "left_resectionStepped"):
            points = logic._defined_points(logic.get_node(role))
            ij = [inv.MultiplyPoint([*point, 1])[:2] for point in points]
            np.testing.assert_allclose(ij, expected["coords"][role], atol=3e-5)
        logic._write_csv_export(str(folder / f"slicer_from_{edition}_180.csv"), logic._build_export_rows(volume))
    apply_csv(logic, prepare_csv(logic, folder / "web.csv", volume), volume)
    for role, points in expected["coords"].items():
        node = logic.get_node(role)
        if role.endswith("Outline"):
            data = node.GetPolyData()
            world = [data.GetPoint(i) for i in range(data.GetNumberOfPoints())]
        else:
            world = logic._defined_points(node)
        actual = [inv.MultiplyPoint([*p, 1])[:2] for p in world]
        np.testing.assert_allclose(actual, points, atol=3e-5, err_msg=role)
    result = logic.latest_results["sides"]["left"]["inlay_wear"]
    np.testing.assert_allclose(result["correctedValue"], expected["wear"], atol=1e-5)
    preview = slicer.util.arrayFromVolume(logic._fragment_preview)[0]
    for row, col, value in expected["pixels"]:
        assert abs(float(preview[row, col]) - value) <= 1
    assert logic.case_comments() == "Oblique, mirrored"
    assert {key for _, key in widget.planning_values} == {"inlay_wear"}
    for show_values in (False, True):
        widget.display_measurements_on_image = show_values
        with patch.object(widget, "_draw_measurement_overlay_on_image", wraps=widget._draw_measurement_overlay_on_image) as draw:
            png = widget._capture_annotation_image(volume)
        lines = draw.call_args.args[1].splitlines()
        assert [s for s in lines if " · Size " in s] == sorted(expected["captions"], key=lambda s: not s.startswith("Right"))
        assert not any("Straight cut" in line or "Stepped cut" in line for line in lines)
        assert ("Inlay wear estimate" in "\n".join(lines)) == show_values
        assert png.save(str(folder / f"slicer_implants_{int(show_values)}.png"))
    logic._write_csv_export(str(folder / "slicer.csv"), logic._build_export_rows(volume))
    print("PXM_PLANNING_INTEROP_OK", flush=True)
    widget.cleanup()


try:
    main()
except Exception:
    traceback.print_exc()
    slicer.app.exit(1)
else:
    slicer.app.exit(0)
