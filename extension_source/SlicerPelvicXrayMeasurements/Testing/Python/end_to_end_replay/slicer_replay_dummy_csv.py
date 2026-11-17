"""Replay a dummy export CSV into the extension and export a fresh actual CSV for comparison."""
# ruff: noqa: I001

from __future__ import annotations

import traceback

from scenario_definition import REPLAY_EDITABLE_ROLE_STAGES, SYNTHETIC_VOLUME
from slicer_harness import (
    apply_neck_axis_options,
    bootstrap_extension,
    create_dynamic_roles,
    create_synthetic_volume,
    export_csv,
    load_csv_rows,
    load_config_from_env,
    parse_replay_metadata,
    populate_roles_in_stages,
    reset_scene,
    role_points_from_csv_rows,
    update_measurements,
)


def main() -> None:
    """Recreate the synthetic case purely from the dummy CSV and export a fresh comparison CSV."""

    try:
        config = load_config_from_env()

        _module, _node_specs = bootstrap_extension(config["extensionDir"])
        from PelvicXrayMeasurements import PelvicXrayMeasurementsLogic  # pylint: disable=import-error

        dummy_rows = load_csv_rows(config["dummyCsvPath"])
        replay_metadata = parse_replay_metadata(dummy_rows)
        replay_points = role_points_from_csv_rows(dummy_rows)

        reset_scene()
        logic = PelvicXrayMeasurementsLogic()
        logic.set_calibration_ball_present(replay_metadata["calibrationBallPresent"])
        logic.set_calibration_ball_diameter_mm(replay_metadata["calibrationBallDiameterMm"])
        logic.set_annotator_name(replay_metadata["annotatorName"])
        logic.set_case_export_timestamp(replay_metadata["exportTimestamp"])
        logic.set_case_comments(replay_metadata["comments"])
        logic.ensure_nodes()
        apply_neck_axis_options(logic, replay_metadata["neckAxisOptions"])

        image_node = create_synthetic_volume(
            replay_metadata["imageNodeName"] or SYNTHETIC_VOLUME["caseName"],
            SYNTHETIC_VOLUME["dimensions"],
            SYNTHETIC_VOLUME["spacing"],
            SYNTHETIC_VOLUME["origin"],
        )

        create_dynamic_roles(
            logic,
            replay_points,
            replay_metadata["lineLockModes"],
            replay_metadata["angleLockModes"],
        )
        update_measurements(logic, image_node)
        populate_roles_in_stages(logic, image_node, replay_points, REPLAY_EDITABLE_ROLE_STAGES)
        update_measurements(logic, image_node)

        export_csv(
            logic,
            image_node,
            config["outputParent"],
            export_curve_points_txt=True,
        )
    except Exception as error:  # pragma: no cover - exercised inside Slicer
        traceback.print_exc()
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
