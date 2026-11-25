"""Round-trip a rotated, mirrored planning case between browser Python and installed Slicer."""

import argparse
from collections import Counter
import csv
import io
import json
import os
from pathlib import Path
import random
import subprocess

import numpy as np

from check_core import QA, ROOT
from core import planning
from core.csv_export import write_case_csv
from core.engine import Session, index_transform
from core.imaging import Radiograph
from core.scene_files import append_csv_metadata, nrrd_bytes, read_csv


def shuffled_table(source, destination):
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        names, rows = list(reversed(reader.fieldnames)), list(reader)
    random.Random(49).shuffle(rows)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def check_implant_rows(csv_path, placements):
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        fields = {row["name"]: row["details"] for row in csv.DictReader(stream)
                  if row["section"] == "metadata" and any(t in row["name"] for t in ("_Planning_Cup_", "_Planning_Stem_"))}
    expected = {}
    for (side, kind), item in placements.items():
        prefix = f"{side.title()}_Planning_{kind.title()}_"
        for field, value in (("Component", kind), ("Family", item["family"]), ("Size", item["size"]), ("ID", item["id"])):
            expected[prefix + field] = value
    assert fields == expected, (csv_path.name, fields, expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slicer", type=Path, required=True)
    args = parser.parse_args()
    folder = QA / "planning_interchange"
    folder.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[:96, :128]
    image = Radiograph((9 * xx + 5 * yy).astype(np.int16), (0.8, 0.8), None, "NRRD")
    angle = 0.33
    frame = np.array(
        [
            [0.8 * np.cos(angle), 0, -np.sin(angle), 42],
            [0, 0.8, 0, -65],
            [0.8 * np.sin(angle), 0, np.cos(angle), 15],
            [0, 0, 0, 1],
        ]
    )
    data = nrrd_bytes(image, frame)
    (folder / "Oblique.nrrd").write_bytes(data)
    s = Session("Synthetic reader")
    s.open("Oblique.nrrd", data)
    s.turns, s.mirrored = 1, True
    s.orient()
    c = s.controller
    s.settings.pelvic_comments = "Oblique, mirrored"

    def place(key, points):
        c.start(key)
        for point in points:
            assert c.place(*point), key
        if key == "bone_fragment":
            c.expire_placement()

    place("calibration", [(10, 20), (20, 10), (30, 20)])
    place("implant_head", [(40, 40), (50, 30), (60, 40)])
    place("cup_center", [(35, 44), (53, 26), (71, 44)])
    place("straight_resection", [(20, 50), (40, 50)])
    place("stepped_resection", [(20, 55), (23, 59), (40, 59)])
    place("bone_fragment", [(40, 70), (20, 70)])
    place("fragment_pose", [(64, 75)])
    c.planning_options({"key": "fragment_pose", "angle": 30})
    placed = {}
    for kind in ("cup", "stem"):
        choice = planning.default_template(kind)
        if choice:
            choice["angle"] = 17
            c.planning_options({"key": "template_" + kind, "choice": choice})
            place("template_" + kind, [(55, 62)])
            placed["left", kind] = planning.ITEMS[choice["id"]]
    s.settings.pelvic_active_side = "right"
    c.update_derived()
    right_cup = next(i for i in reversed(planning.ITEMS.values()) if i["component"] == "cup" and i["side"] in ("both", "right"))
    c.planning_options({"key": "template_cup", "choice": {"id": right_cup["id"], "angle": -12}})
    place("template_cup", [(72, 44)])
    placed["right", "cup"] = right_cup
    snap = s.snapshot()
    roles = [
        "left_cupShellPoints",
        "left_cupShellCenter",
        "left_fragmentBoundary",
        "left_fragmentTarget",
        "left_resectionStraight",
        "left_resectionStepped",
        "left_planningCupAnchorOutline",
        "left_planningStemAnchorOutline",
    ]
    transform = index_transform(s.base_image.shape, s.turns, s.mirrored)
    coords = {}
    def recorded(snapshot, controller):
        volume = controller.current_image_node()
        boundary = controller.points_for_role("left_fragmentBoundary")
        return [*snapshot["markups"], {"role":"left_fragmentBoundary", "points":[volume.to_image(p) for p in boundary]}]
    for markup in recorded(snap, c):
        if markup["role"] in roles:
            arr = np.asarray(markup["points"])
            coords[markup["role"]] = (
                np.column_stack((arr, np.zeros(len(arr)), np.ones(len(arr)))) @ transform.T
            )[:, :2].tolist()
    moved = planning.compose_fragments(s.image.pixels, snap["fragments"])
    pixels = []
    for y, x in [(60, 29), (74, 62), (80, 65), (83, 61), (90, 70)]:
        j, k = (transform @ [x, y, 0, 1])[:2].astype(int)
        pixels.append([int(k), int(j), float(moved[y, x])])
    wear = c._numeric_results["pelvic_result_left_inlay_wear"][0]
    np.testing.assert_allclose(wear, 6.25)
    captions = [f"{side.title()} {kind} · {item['family']} · Size {item['size']}" for (side, kind), item in placed.items()]
    (folder / "expected.json").write_text(json.dumps(dict(coords=coords, wear=wear, pixels=pixels, captions=captions)))
    out = folder / "web.csv"
    write_case_csv(out, c, s.case_name, "Synthetic reader")
    append_csv_metadata(out, s.get_settings(), s.base_image)
    check_implant_rows(out, placed)
    shuffled_table(out, out)
    # These are actual 1.8.0 exports of this synthetic case, before labels were saved.
    historical = {("left", "cup"): planning.ITEMS["Mathys/52.34.1006"], ("left", "stem"): planning.ITEMS["Mathys/52.34.0201"]}
    for edition in ("slicer", "web"):
        legacy = folder / f"legacy_{edition}.csv"
        shuffled_table(ROOT / f"web/tests/fixtures/planning_1_8_0_{edition}.csv", legacy)
        resumed = Session()
        resumed.open("Oblique.nrrd", data)
        resumed.restore(read_csv(legacy.read_bytes()))
        migrated = folder / f"web_from_{edition}_180.csv"
        write_case_csv(migrated, resumed.controller, resumed.case_name, "Synthetic reader")
        check_implant_rows(migrated, historical)
        np.testing.assert_allclose(resumed.controller._numeric_results["pelvic_result_left_inlay_wear"][0], wear)
    executable = args.slicer.resolve()
    if executable.is_dir():
        executable = executable / "Contents/MacOS/Slicer"
    package = ROOT / "extension_source/SlicerPelvicXrayMeasurements"
    args = [
        str(executable),
        "--no-splash",
        "--disable-settings",
        "--ignore-slicerrc",
        "--testing",
        "--additional-module-paths",
        str(package / "PelvicXrayMeasurements"),
        "--python-script",
        str(package / "Testing/Python/end_to_end_replay/slicer_planning_interop.py"),
    ]
    with (folder / "slicer.log").open("w") as log:
        result = subprocess.run(
            args,
            cwd=ROOT,
            env={**os.environ, "PXM_INTEROP_DIR": str(folder)},
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
    assert result.returncode == 0 and "PXM_PLANNING_INTEROP_OK" in (folder / "slicer.log").read_text(), (
        folder / "slicer.log"
    )
    reverse = Session()
    reverse.open("Oblique.nrrd", data)
    native = (folder / "slicer.csv").read_bytes()
    check_implant_rows(folder / "slicer.csv", placed)
    for edition in ("slicer", "web"):
        check_implant_rows(folder / f"slicer_from_{edition}_180.csv", historical)
    reverse.restore(read_csv(native))
    again = reverse.snapshot()
    for item in recorded(again, reverse.controller):
        if item["role"] in coords:
            np.testing.assert_allclose(item["points"], coords[item["role"]], atol=0.021)
    assert set(coords) <= {m["role"] for m in recorded(again, reverse.controller)}
    np.testing.assert_allclose(reverse.controller._numeric_results["pelvic_result_left_inlay_wear"][0], wear)
    output = planning.compose_fragments(reverse.image.pixels, again["fragments"])
    for row, col, value in pixels:
        assert abs(float(output[row, col]) - value) <= 1
    sections = Counter(row["section"] for row in csv.DictReader(io.StringIO(native.decode("utf-8-sig"))))
    (folder / "result.json").write_text(
        json.dumps(
            dict(
                status="passed",
                calibrated_wear_mm=wear,
                coordinate_groups=list(coords),
                sampled_pixels=len(pixels),
                native_csv_rows=dict(sections),
                placed_implants=len(placed),
                historical_planning_exports=["1.8.0 web", "1.8.0 Slicer"],
                native_png_captions_with_and_without_measurements=True,
            ),
            indent=2,
        )
        + "\n"
    )
    print("PASS: web to Slicer to web on a rotated and mirrored oblique image")


if __name__ == "__main__":
    main()
