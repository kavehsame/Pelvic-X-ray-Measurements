"""Wall curves participate in editing, Hide and both supported annotation formats."""

from pathlib import Path

import numpy as np
import pytest

from core.csv_export import write_case_csv
from core.engine import Session
from core.scene_files import read_csv, read_mrb, write_mrb


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("wall", ["anterior", "posterior"])
def test_wall_edit_visibility_and_roundtrip(side, wall, tmp_path):
    session = Session("Synthetic wall check")
    session.open("SyntheticFullCase.mrb", (Path(__file__).parent / "fixtures/SyntheticFullCase.mrb").read_bytes())
    controller = session.controller
    role = f"{side}_{wall}AcetabularWall"
    node = controller.node_for_role(role)
    assert node and node.IsA("vtkMRMLMarkupsCurveNode") and len(node.points) == 4
    changed = controller.points_for_role(role)
    changed[1] = changed[1] + [2, 3, 0]
    controller.put_points(role, changed)
    controller.set_workflow_hidden(wall + "_wall", True)
    assert not node.visible
    controller.set_workflow_hidden(wall + "_wall", False)
    assert node.visible
    node.SetCurveType(0)
    node.SetNumberOfPointsPerInterpolatingSegment(30)
    csv = tmp_path / "walls.csv"
    write_case_csv(csv, controller, session.case_name, "Synthetic wall check")
    mrb = write_mrb(session.image, controller, session.case_name, session.get_settings())
    for saved in (read_csv(csv.read_bytes()), read_mrb(mrb)[1]):
        np.testing.assert_allclose(saved["points"][role], changed)
        assert saved["curve_types"][role] == 0
        assert saved.get("curve_segments", {}).get(role, 30) == 30
