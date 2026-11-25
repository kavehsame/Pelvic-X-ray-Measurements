"""Receive a reoriented browser plan inside an actual Slicer process and return its CSV."""

import json
import os
from pathlib import Path
import traceback

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
    apply_csv(logic, prepare_csv(logic, folder / "web.csv", volume), volume)
    inv = vtk.vtkMatrix4x4()
    volume.GetRASToIJKMatrix(inv)
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
