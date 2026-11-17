"""Generate the golden dummy export CSV by driving the real extension inside Slicer."""
# ruff: noqa: I001

from __future__ import annotations

import shutil
import traceback
from pathlib import Path

from scenario_definition import (
    build_randomized_full_scenario,
    CALIBRATION_BALL_DIAMETER_MM,
    CALIBRATION_BALL_PRESENT,
    REPLAY_EDITABLE_ROLE_STAGES,
    SYNTHETIC_VOLUME,
)
from slicer_harness import (
    apply_neck_axis_options,
    bootstrap_extension,
    create_synthetic_volume,
    export_csv,
    load_config_from_env,
    populate_roles_in_stages,
    reset_scene,
    update_measurements,
)


def main() -> None:
    """Create the synthetic case, populate all tools, and write the golden export CSV."""

    try:
        config = load_config_from_env()

        _module, _node_specs = bootstrap_extension(config["extensionDir"])
        from PelvicXrayMeasurements import PelvicXrayMeasurementsLogic  # pylint: disable=import-error

        reset_scene()
        logic = PelvicXrayMeasurementsLogic()
        logic.set_calibration_ball_present(CALIBRATION_BALL_PRESENT)
        logic.set_calibration_ball_diameter_mm(CALIBRATION_BALL_DIAMETER_MM)
        logic.set_annotator_name("Automated Test")
        logic.set_case_comments("Automated replay reference case.")
        logic.ensure_nodes()
        scenario = build_randomized_full_scenario(config.get("randomSeed"))
        apply_neck_axis_options(logic, scenario["neckAxisOptions"])
        print(
            "Generated random scenario seed="
            f"{scenario['seed']} scale={scenario['scale']:.6f} "
            f"rotationDeg={scenario['rotationDegrees']:.6f} "
            f"translationXY={scenario['translationXY']}"
        )

        image_node = create_synthetic_volume(
            SYNTHETIC_VOLUME["caseName"],
            SYNTHETIC_VOLUME["dimensions"],
            SYNTHETIC_VOLUME["spacing"],
            SYNTHETIC_VOLUME["origin"],
        )

        populate_roles_in_stages(
            logic,
            image_node,
            scenario["staticRolePoints"],
            REPLAY_EDITABLE_ROLE_STAGES,
        )

        for _index in sorted(scenario["customPoints"]):
            logic.create_other_point()
        update_measurements(logic, image_node)

        dynamic_point_points = {
            f"otherPoint_{index}": [
                {
                    "index": point_index,
                    "label": f"Point_{index}",
                    "x_ras": point_value[0],
                    "y_ras": point_value[1],
                    "z_ras": point_value[2],
                }
                for point_index, point_value in enumerate(point_data["points"])
            ]
            for index, point_data in scenario["customPoints"].items()
        }
        populate_roles_in_stages(
            logic,
            image_node,
            dynamic_point_points,
            [[role] for role in sorted(dynamic_point_points)],
        )

        for index in sorted(scenario["customLines"]):
            logic.create_other_line(scenario["customLines"][index]["lockMode"])
        update_measurements(logic, image_node)

        dynamic_line_points = {
            f"otherLine_{index}": [
                {
                    "index": point_index,
                    "label": "",
                    "x_ras": point_value[0],
                    "y_ras": point_value[1],
                    "z_ras": point_value[2],
                }
                for point_index, point_value in enumerate(line_data["points"])
            ]
            for index, line_data in scenario["customLines"].items()
        }
        populate_roles_in_stages(
            logic,
            image_node,
            dynamic_line_points,
            [[role] for role in sorted(dynamic_line_points)],
        )

        for index in sorted(scenario["customAngles"]):
            logic.create_other_angle(scenario["customAngles"][index]["lockMode"])
        update_measurements(logic, image_node)

        dynamic_angle_points = {
            f"otherAngle_{index}_points": [
                {
                    "index": point_index,
                    "label": "",
                    "x_ras": point_value[0],
                    "y_ras": point_value[1],
                    "z_ras": point_value[2],
                }
                for point_index, point_value in enumerate(angle_data["points"])
            ]
            for index, angle_data in scenario["customAngles"].items()
        }
        populate_roles_in_stages(
            logic,
            image_node,
            dynamic_angle_points,
            [[role] for role in sorted(dynamic_angle_points)],
        )

        exported_csv = export_csv(
            logic,
            image_node,
            config["outputParent"],
            export_curve_points_txt=True,
        )
        destination_csv_value = config.get("destinationCsvPath")
        if destination_csv_value is None:
            destination_csv_value = config["destinationCsv"]
        destination_csv = Path(destination_csv_value).resolve()
        destination_csv.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(exported_csv, destination_csv)
    except Exception as error:  # pragma: no cover - exercised inside Slicer
        traceback.print_exc()
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
