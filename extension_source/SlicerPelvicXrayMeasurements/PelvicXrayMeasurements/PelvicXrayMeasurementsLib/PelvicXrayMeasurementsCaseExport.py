"""Case saving and CSV export helpers for Pelvic X-ray Measurements.

Export code is isolated from calculation code so the measurement pipeline can update live while file
serialization focuses only on stable output names, rows, and scene persistence.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime
from typing import Any

import slicer

from PelvicXrayMeasurementsCaseWorkflow import (
    filesystem_path,
    path_exists,
    repair_scene_bundle_in_place,
)
from PelvicXrayMeasurementsConstants import (
    FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
    FEMORAL_SHAFT_CONTOUR_CLASS_ATTRIBUTE,
    FEMORAL_SHAFT_CONTOUR_CLASS_LABELS,
    SIDE_KEYS,
    SIDE_LABELS,
    MeasurementKey,
    OtherAngleLockMode,
)
from PelvicXrayMeasurementsGeometry import sanitize_filename
from PelvicXrayMeasurementsNodeSpecs import EXPORT_FIELDS
from PelvicXrayMeasurementsPlanning import COMPONENTS, FRAGMENT_ANGLE, FRAGMENT_CUT, LENGTH_FIELDS, TEMPLATE_ATTRIBUTE, VIEW_AXES, TOOLS

CSV_EXPORT_ENCODING = "utf-8-sig"
CURVE_POINTS_TXT_EXPORT_ENCODING = "utf-8"
CSV_FORMULA_PREFIX_DANGEROUS_CHARS = ("=", "+", "-", "@", "\t", "\r")


class CaseExportMixin:
    """Provide caseexport behavior for the main logic class."""

    def _resolved_case_export_timestamp(self) -> str:
        """Return the stable export timestamp recorded for the current case.

        The timestamp is created only once per case scene and then stored with the scene metadata so
        repeated exports and replay-driven regression tests reuse the same recorded value.
        """

        existing_timestamp = self.case_export_timestamp() if hasattr(self, "case_export_timestamp") else ""
        if existing_timestamp:
            return existing_timestamp

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(self, "set_case_export_timestamp"):
            self.set_case_export_timestamp(timestamp)
        return timestamp

    def case_name(self, image_node: Any=None) -> Any:
        """Return the sanitized case name used for export filenames. The exported files keep the full
        image-derived name so the scene, CSV, and image remain obviously associated.
        """

        return sanitize_filename(image_node.GetName() if image_node is not None else "SlicerScene")

    def case_folder_name(self, image_node: Any=None) -> Any:
        """Return the sanitized case folder name derived from the image name without its extension. The
        folder omits the extension because the case is conceptually the study, not one file format.
        """

        base_name = image_node.GetName() if image_node is not None else "SlicerScene"
        stem_name, _extension = os.path.splitext(base_name)
        return sanitize_filename(stem_name or base_name)

    def case_folder_for_export(self, parent_directory: Any, image_node: Any=None) -> Any:
        """Ensure and return the export folder for the current case. Folder creation is centralized so
        every export action lands in the same location.
        """

        case_folder = os.path.join(parent_directory, self.case_folder_name(image_node))
        os.makedirs(self._filesystem_path(case_folder), exist_ok=True)
        return case_folder

    def default_scene_path(self, parent_directory: Any, image_node: Any=None) -> Any:
        """Return the default MRB export path for the current case. Scene, CSV, and image paths are
        generated from the same naming convention for easy browsing.
        """

        case_name = self.case_name(image_node)
        case_folder = self.case_folder_for_export(parent_directory, image_node)
        return os.path.join(case_folder, f"{case_name}.mrb")

    def default_csv_path(self, parent_directory: Any, image_node: Any=None) -> Any:
        """Return the default CSV export path for the current case. The suffix makes the numeric export
        distinguishable from the MRB and PNG files.
        """

        case_name = self.case_name(image_node)
        case_folder = self.case_folder_for_export(parent_directory, image_node)
        return os.path.join(case_folder, f"{case_name}_measurements.csv")

    def default_curve_points_txt_path(self, parent_directory: Any, image_node: Any=None) -> Any:
        """Return the companion TXT path used when CSV export includes sampled curve points."""

        return self._curve_points_txt_path_for_csv_path(
            self.default_csv_path(parent_directory, image_node)
        )

    def default_image_path(self, parent_directory: Any, image_node: Any=None) -> Any:
        """Return the default annotated-image export path for the current case. The filename makes it
        obvious that the PNG is a rendered figure, not the original radiograph.
        """

        case_name = self.case_name(image_node)
        case_folder = self.case_folder_for_export(parent_directory, image_node)
        return os.path.join(case_folder, f"{case_name}_annotated.png")

    def case_output_paths(self, parent_directory: Any, image_node: Any=None) -> Any:
        """Return the primary output paths that participate in overwrite or version prompts for
        combined save. Grouping them here keeps conflict handling synchronized.
        """

        return [
            self.default_scene_path(parent_directory, image_node),
            self.default_csv_path(parent_directory, image_node),
        ]

    def unique_output_path(self, path: Any) -> Any:
        """Return a versioned output path when the preferred path already exists. Users can keep prior
        exports without manually renaming files.
        """

        return self._unique_output_path(path)

    def _resolve_output_path(self, path: Any, conflict_policy: Any="version") -> Any:
        """Resolve a final output path under the chosen conflict policy. This keeps replace-versus-
        version behavior consistent across all export types.
        """

        if conflict_policy == "replace" or not self.path_exists(path):
            return path
        return self._unique_output_path(path)

    def scene_output_path(self, parent_directory: Any, image_node: Any=None, conflict_policy: Any="version") -> Any:
        """Return the MRB output path after conflict handling. Path resolution is separated from
        writing so UI prompts and export code remain simple.
        """

        return self._resolve_output_path(
            self.default_scene_path(parent_directory, image_node), conflict_policy
        )

    def csv_output_path(self, parent_directory: Any, image_node: Any=None, conflict_policy: Any="version") -> Any:
        """Return the CSV output path after conflict handling. The helper mirrors scene and image path
        handling for consistency.
        """

        return self._resolve_output_path(
            self.default_csv_path(parent_directory, image_node), conflict_policy
        )

    def csv_and_curve_points_txt_output_paths(
        self,
        parent_directory: Any,
        image_node: Any=None,
        conflict_policy: Any="version",
    ) -> tuple[Any, Any]:
        """Return paired CSV and curve TXT paths while respecting collisions on either file."""

        default_csv_path = self.default_csv_path(parent_directory, image_node)
        default_txt_path = self._curve_points_txt_path_for_csv_path(default_csv_path)
        if conflict_policy == "replace" or (
            not self.path_exists(default_csv_path) and not self.path_exists(default_txt_path)
        ):
            return default_csv_path, default_txt_path

        base_name, extension = os.path.splitext(default_csv_path)
        suffix = 2
        while True:
            csv_path = f"{base_name}_{suffix}{extension}"
            txt_path = self._curve_points_txt_path_for_csv_path(csv_path)
            if not self.path_exists(csv_path) and not self.path_exists(txt_path):
                return csv_path, txt_path
            suffix += 1

    def image_output_path(self, parent_directory: Any, image_node: Any=None, conflict_policy: Any="version") -> Any:
        """Return the annotated-image output path after conflict handling. The helper keeps image
        export aligned with the same overwrite or version rules as other outputs.
        """

        return self._resolve_output_path(
            self.default_image_path(parent_directory, image_node), conflict_policy
        )

    def save_scene(self, parent_directory: Any, image_node: Any=None, conflict_policy: Any="version") -> Any:
        """Save the full MRB scene for the current case. The module updates derived measurements first
        so the saved scene reflects the current visible state.
        """

        self.update_all_derived_measurements(image_node)
        case_folder = self.case_folder_for_export(parent_directory, image_node)
        scene_path = self.scene_output_path(parent_directory, image_node, conflict_policy)

        if not slicer.util.saveScene(scene_path):
            raise RuntimeError(f"Could not save MRB scene to {scene_path}")
        repair_scene_bundle_in_place(scene_path)

        return {
            "folder": case_folder,
            "scenePath": scene_path,
        }

    def export_csv(
        self,
        parent_directory: Any,
        image_node: Any=None,
        conflict_policy: Any="version",
        export_curve_points_txt: Any=False,
    ) -> Any:
        """Export the detailed measurement CSV for the current case. CSV export always rebuilds derived
        results first so coordinates and numbers stay synchronized.
        """

        self.update_all_derived_measurements(image_node)
        case_folder = self.case_folder_for_export(parent_directory, image_node)
        curve_points_txt_path = None
        if export_curve_points_txt:
            csv_path, curve_points_txt_path = self.csv_and_curve_points_txt_output_paths(
                parent_directory, image_node, conflict_policy
            )
        else:
            csv_path = self.csv_output_path(parent_directory, image_node, conflict_policy)
        self._write_csv_export(csv_path, self._build_export_rows(image_node))

        export_info = {
            "folder": case_folder,
            "csvPath": csv_path,
        }
        if curve_points_txt_path:
            self._write_curve_points_txt_export(curve_points_txt_path, image_node)
            export_info["curvePointsTxtPath"] = curve_points_txt_path
        return export_info

    def save_case(
        self,
        parent_directory: Any,
        image_node: Any=None,
        conflict_policy: Any="version",
        export_curve_points_txt: Any=False,
    ) -> Any:
        """Perform the combined MRB-plus-CSV export for the current case. The bundled action exists for
        the common workflow of archiving both scene and numeric results together.
        """

        scene_info = self.save_scene(parent_directory, image_node, conflict_policy)
        csv_info = self.export_csv(
            parent_directory,
            image_node,
            conflict_policy,
            export_curve_points_txt=export_curve_points_txt,
        )
        export_info = {
            "folder": scene_info["folder"],
            "scenePath": scene_info["scenePath"],
            "csvPath": csv_info["csvPath"],
        }
        if csv_info.get("curvePointsTxtPath"):
            export_info["curvePointsTxtPath"] = csv_info["curvePointsTxtPath"]
        return export_info

    def _unique_output_path(self, path: Any) -> Any:
        """Generate a numbered filename that does not collide with an existing file. Versioned export
        keeps prior revisions intact without user micromanagement.
        """

        if not self.path_exists(path):
            return path

        base_name, extension = os.path.splitext(path)
        suffix = 2
        candidate = f"{base_name}_{suffix}{extension}"
        while self.path_exists(candidate):
            suffix += 1
            candidate = f"{base_name}_{suffix}{extension}"
        return candidate

    def _curve_points_txt_path_for_csv_path(self, csv_path: Any) -> Any:
        """Return the sampled-curve TXT path paired to one concrete CSV path."""

        base_name, _extension = os.path.splitext(csv_path)
        return f"{base_name}_curve_points.txt"

    def _row(self, **values: Any) -> Any:
        """Create one CSV row with default empty fields. A row helper keeps the large export builder
        readable and resistant to missing-column mistakes.
        """

        row = dict.fromkeys(EXPORT_FIELDS, "")
        row.update(values)
        return {
            field_name: self._csv_safe_value(field_value)
            for field_name, field_value in row.items()
        }

    def _csv_safe_value(self, value: Any) -> Any:
        """Prefix dangerous string cells so spreadsheet programs do not execute them as formulas."""

        if (
            isinstance(value, str)
            and value
            and value[0] in CSV_FORMULA_PREFIX_DANGEROUS_CHARS
        ):
            return f"'{value}"
        return value

    def _write_csv_export(self, csv_path: Any, rows: list[Any]) -> None:
        """Write one CSV export atomically with explicit UTF-8 encoding for spreadsheet compatibility."""

        csv_directory = os.path.dirname(csv_path) or "."
        temporary_path = None
        os.makedirs(self._filesystem_path(csv_directory), exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                newline="",
                encoding=CSV_EXPORT_ENCODING,
                dir=self._filesystem_path(csv_directory),
                prefix=f".{os.path.basename(csv_path)}.",
                suffix=".tmp",
                delete=False,
            ) as output_stream:
                temporary_path = output_stream.name
                writer = csv.DictWriter(output_stream, fieldnames=EXPORT_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(self._filesystem_path(temporary_path), self._filesystem_path(csv_path))
        except Exception:
            if temporary_path is not None and self.path_exists(temporary_path):
                os.unlink(self._filesystem_path(temporary_path))
            raise

    def _write_curve_points_txt_export(self, txt_path: Any, image_node: Any=None) -> None:
        """Write sampled/generated curve points from every curve node into a companion TXT file."""

        txt_directory = os.path.dirname(txt_path) or "."
        temporary_path = None
        os.makedirs(self._filesystem_path(txt_directory), exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                newline="",
                encoding=CURVE_POINTS_TXT_EXPORT_ENCODING,
                dir=self._filesystem_path(txt_directory),
                prefix=f".{os.path.basename(txt_path)}.",
                suffix=".tmp",
                delete=False,
            ) as output_stream:
                temporary_path = output_stream.name
                output_stream.write(self._curve_points_txt_export_text(image_node))
            os.replace(self._filesystem_path(temporary_path), self._filesystem_path(txt_path))
        except Exception:
            if temporary_path is not None and self.path_exists(temporary_path):
                os.unlink(self._filesystem_path(temporary_path))
            raise

    def _is_curve_node(self, node: Any) -> bool:
        """Return whether one MRML node stores a Slicer markups curve."""

        return bool(node is not None and hasattr(node, "IsA") and node.IsA("vtkMRMLMarkupsCurveNode"))

    def _curve_metadata_for_node(self, node: Any) -> dict[str, Any]:
        """Return CSV-safe reconstruction settings for one Slicer curve node."""

        if not self._is_curve_node(node):
            return {
                "curve_type": "",
                "curve_points_per_segment": "",
            }

        curve_type = ""
        curve_type_value = None
        if hasattr(node, "GetCurveType"):
            curve_type_value = node.GetCurveType()
            curve_type = curve_type_value
        if hasattr(node, "GetCurveTypeAsString"):
            try:
                curve_type = node.GetCurveTypeAsString(curve_type_value)
            except TypeError:
                curve_type = node.GetCurveTypeAsString()

        points_per_segment = ""
        if hasattr(node, "GetNumberOfPointsPerInterpolatingSegment"):
            points_per_segment = node.GetNumberOfPointsPerInterpolatingSegment()

        return {
            "curve_type": curve_type,
            "curve_points_per_segment": points_per_segment,
        }

    def _curve_points_world(self, node: Any) -> list[tuple[float, float, float]]:
        """Return Slicer's sampled/generated world points for one curve node."""

        if not self._is_curve_node(node) or not hasattr(node, "GetCurvePointsWorld"):
            return []

        vtk_points = node.GetCurvePointsWorld()
        if vtk_points is None or not hasattr(vtk_points, "GetNumberOfPoints"):
            return []

        points = []
        for index in range(vtk_points.GetNumberOfPoints()):
            try:
                point = vtk_points.GetPoint(index)
            except TypeError:
                point = [0.0, 0.0, 0.0]
                vtk_points.GetPoint(index, point)
            points.append((float(point[0]), float(point[1]), float(point[2])))
        return points

    def _curve_roles_for_txt_export(self) -> list[Any]:
        """Return curve roles with at least one defined control point, in schema order."""

        roles = []
        for role in self._all_node_roles():
            node = self.get_node(role)
            if (
                self._is_curve_node(node)
                and hasattr(node, "GetNumberOfDefinedControlPoints")
                and node.GetNumberOfDefinedControlPoints() > 0
            ):
                roles.append(role)
        return roles

    def _curve_points_txt_export_text(self, image_node: Any=None) -> str:
        """Build a readable TXT dump of every sampled curve point in RAS/world coordinates."""

        image_name = image_node.GetName() if image_node is not None else ""
        lines = [
            "Pelvic X-ray Measurements - Curve Points",
            f"ImageNode: {image_name}",
            "CoordinateSystem: RAS/world",
            "Source: vtkMRMLMarkupsCurveNode.GetCurvePointsWorld()",
            "",
        ]

        curve_roles = self._curve_roles_for_txt_export()
        if not curve_roles:
            lines.append("No curve points available.")
            return "\n".join(lines) + "\n"

        for role in curve_roles:
            node = self.get_node(role)
            curve_metadata = self._curve_metadata_for_node(node)
            curve_points = self._curve_points_world(node)
            curve_header_lines = [
                f"Curve: {node.GetName()}",
                f"Role: {role}",
            ]
            class_key = (
                node.GetAttribute(FEMORAL_SHAFT_CONTOUR_CLASS_ATTRIBUTE)
                if hasattr(node, "GetAttribute")
                else ""
            )
            if class_key:
                class_label = FEMORAL_SHAFT_CONTOUR_CLASS_LABELS.get(class_key, class_key)
                curve_header_lines.append(f"FemoralShaftContourClass: {class_key} ({class_label})")
            curve_header_lines.extend(
                [
                    f"CurveType: {curve_metadata['curve_type']}",
                    (
                        "PointsPerInterpolatingSegment: "
                        f"{curve_metadata['curve_points_per_segment']}"
                    ),
                    f"ControlPointCount: {node.GetNumberOfDefinedControlPoints()}",
                    f"CurvePointCount: {len(curve_points)}",
                    "index\tx_ras\ty_ras\tz_ras",
                ]
            )
            lines.extend(curve_header_lines)
            for index, point in enumerate(curve_points):
                lines.append(
                    f"{index}\t{point[0]:.6f}\t{point[1]:.6f}\t{point[2]:.6f}"
                )
            lines.append("")

        return "\n".join(lines) + "\n"

    def _filesystem_path(self, path: Any) -> str:
        """Return the platform-safe filesystem path used for Python-managed file operations."""

        return filesystem_path(path)

    def path_exists(self, path: Any) -> bool:
        """Return whether one filesystem path already exists."""

        return path_exists(path)

    def _metadata_rows(self, image_node: Any, results: Any) -> list[Any]:
        """Build the export metadata rows that describe the case and saved options."""

        export_timestamp = self._resolved_case_export_timestamp()
        rows = [
            self._row(
                section="metadata",
                name="CaseName",
                details=sanitize_filename(
                    image_node.GetName() if image_node is not None else "SlicerScene"
                ),
            ),
            self._row(
                section="metadata",
                name="ImageNode",
                details=image_node.GetName() if image_node is not None else "",
            ),
            self._row(
                section="metadata",
                name="Annotator",
                details=getattr(self, "annotator_name", ""),
            ),
            self._row(
                section="metadata",
                name="Timestamp",
                details=export_timestamp,
            ),
            self._row(
                section="metadata",
                name="Comments",
                details=self.case_comments() if hasattr(self, "case_comments") else "",
            ),
            self._row(
                section="metadata",
                name="CalibrationBall_NotPresent",
                raw_value=1 if not results["calibration"]["ballPresent"] else 0,
                units="flag",
                details="1 means no calibration ball was present, so measurements are reported in su only.",
            ),
        ]

        if image_node is not None and image_node.GetStorageNode() is not None:
            import vtk

            frame = vtk.vtkMatrix4x4()
            image_node.GetIJKToRASMatrix(frame)
            matrix = [[frame.GetElement(i, j) for j in range(4)] for i in range(4)]
            dimensions = list(image_node.GetImageData().GetDimensions()[:2])
            rows.extend((
                self._row(section="metadata", name="ImageIJKToRAS", details=json.dumps(matrix)),
                self._row(section="metadata", name="ImageDimensions", details=json.dumps(dimensions)),
            ))
        for side in SIDE_KEYS:
            for component in COMPONENTS:
                implant = results["sides"][side]["template_" + component].get("implant")
                if implant:
                    rows.extend(self._row(section="metadata", name=name, details=value)
                                for name, value in implant["metadata"].items())
            for spec in TOOLS.values():
                role = self.side_role(spec[1], side)
                node = self.get_node(role)
                if node is None or not node.GetNumberOfDefinedControlPoints():
                    continue
                attrs = {k: node.GetAttribute(k) for k in (TEMPLATE_ATTRIBUTE, FRAGMENT_CUT, FRAGMENT_ANGLE, VIEW_AXES) if node.GetAttribute(k)}
                if attrs:
                    rows.append(self._row(section="metadata", name=role + "_attributes", details=json.dumps(attrs, sort_keys=True)))
        neck_axis_options = self.neck_axis_export_options()
        for measurement_key, export_prefix in (
            (MeasurementKey.NECK_AXIS, "FemoralNeckAxis"),
            (MeasurementKey.IMPLANT_NECK_AXIS, "ImplantNeckAxis"),
        ):
            rows.extend(
                self._neck_axis_option_rows(
                    neck_axis_options,
                    measurement_key,
                    export_prefix,
                )
            )
        return rows

    def _neck_axis_option_rows(
        self,
        neck_axis_options: Any,
        measurement_key: Any,
        export_prefix: str,
    ) -> list[Any]:
        """Build the metadata rows describing saved neck-axis mode choices."""

        rows = []
        for side_key in SIDE_KEYS:
            side_label = SIDE_LABELS[side_key]
            option_values = neck_axis_options[measurement_key][side_key]
            rows.append(
                self._row(
                    section="metadata",
                    name=f"{export_prefix}_{side_label}_LockToCenter",
                    raw_value=1 if option_values["lockToCenter"] else 0,
                    units="flag",
                    details=(
                        f"1 means the {side_label.lower()} {export_prefix} is forced to pass "
                        "through the fitted head center."
                    ),
                )
            )
            rows.append(
                self._row(
                    section="metadata",
                    name=f"{export_prefix}_{side_label}_UseSingleGuide",
                    raw_value=1 if option_values["useSingleGuide"] else 0,
                    units="flag",
                    details=(
                        f"1 means the {side_label.lower()} {export_prefix} is derived from only "
                        "the first guide line."
                    ),
                )
            )
        return rows

    def _global_measurement_rows(self, results: Any, length_units: str) -> list[Any]:
        """Build non-side-specific measurement rows."""

        return [
            self._row(
                section="measurement",
                name="CalibrationBall_KnownDiameter",
                corrected_value_mm=results["calibration"]["knownDiameterMm"]
                if results["calibration"]["ballPresent"]
                else "",
                units="mm",
                details="Known physical diameter of the calibration ball when available.",
            ),
            self._row(
                section="measurement",
                name="CalibrationBall_MeasuredDiameter",
                raw_value=results["calibration"]["rawDiameter"],
                corrected_value_mm=results["calibration"]["knownDiameterMm"]
                if results["calibration"]["defined"] and results["calibration"]["ballPresent"]
                else "",
                units=length_units,
                details="Circle fitted from 3 calibration ball points.",
            ),
            self._row(
                section="measurement",
                name="CalibrationScaleFactor",
                raw_value=results["calibration"]["scaleFactor"],
                units="mm per scene unit",
                details="Applied automatically to corrected measurements when the calibration ball is present.",
            ),
            self._row(
                section="measurement",
                name="ReferenceLine_Length",
                raw_value=results["referenceLine"]["rawLength"],
                corrected_value_mm=results["referenceLine"]["correctedLength"],
                units=length_units,
            ),
        ]

    def _side_head_and_angle_measurement_rows(
        self,
        side_label: str,
        side_results: Any,
        length_units: str,
    ) -> list[Any]:
        """Build the native side-specific head and angular measurement rows."""

        return [
            self._row(
                section="measurement",
                name=f"{side_label}_FemurHead_Diameter",
                raw_value=side_results["femurHead"]["rawValue"],
                corrected_value_mm=side_results["femurHead"]["correctedValue"],
                units=length_units,
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_CCDAngle",
                raw_value=side_results["ccdAngle"]["rawValue"],
                units="degrees",
                details=(
                    "Angle between the femoral shaft axis and femoral neck "
                    "axis, reported on the medial side of the intersection."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_AcetabularIndexTonnis",
                raw_value=side_results["tonnisAngle"]["rawValue"],
                units="degrees",
                details=(
                    "Signed angle between the user-defined Acetabular Index (Tönnis) line and "
                    "the side-specific lateral horizontal arm; values above the reference arm are "
                    "positive and below it are negative."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_SharpAngle",
                raw_value=side_results["sharpAngle"]["rawValue"],
                units="degrees",
                details=(
                    "Signed angle between the user-defined Sharp line and the side-specific lateral "
                    "horizontal arm; values above the reference arm are positive and below it are "
                    "negative."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_LCEAngle",
                raw_value=side_results["lceAngle"]["rawValue"],
                units="degrees",
                details=(
                    "Signed angle from the femur head center to the LCE point against the superior "
                    "line perpendicular to the reference line; medial points are negative."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_FemoralHeadExtrusionIndex",
                raw_value=side_results["femoralHeadExtrusionIndex"]["rawValue"],
                units="percent",
                details=(
                    "Signed percent ratio of uncovered lateral femoral head width over total "
                    "femoral head width; negative values indicate overcoverage beyond the lateral "
                    "head margin."
                ),
            ),
        ]

    def _side_morphology_measurement_rows(self, side_label: str, side_results: Any) -> list[Any]:
        """Build the side-specific morphology and shaft-axis quality rows."""

        return [
            self._row(
                section="measurement",
                name=f"{side_label}_CCR",
                raw_value=side_results["corticalCalcarRatio"]["rawValue"],
                units="ratio",
                details=(
                    "Canal-calcar ratio (B/A): width between the two inner 10 cm-below "
                    "morphology points divided by the mid-LT guide-cap width."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_CTI",
                raw_value=side_results["canalThicknessIndex"]["rawValue"],
                units="ratio",
                details=(
                    "Canal thickness index: outer 10 cm-below width minus inner 10 cm-below width, "
                    "divided by outer 10 cm-below width."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_CFI",
                raw_value=side_results["canalFlareIndex"]["rawValue"],
                units="ratio",
                details=(
                    "Canal flare index: 2 cm-above width divided by the width between the two inner "
                    "10 cm-below morphology points."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_FemoralShaftAxis_DeviationGuideA",
                raw_value=side_results["femoralShaftAxis"]["deviationGuideA"],
                units="degrees",
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_FemoralShaftAxis_DeviationGuideB",
                raw_value=side_results["femoralShaftAxis"]["deviationGuideB"],
                units="degrees",
            ),
        ]

    def _side_preop_measurement_rows(
        self,
        side_label: str,
        side_results: Any,
        length_units: str,
    ) -> list[Any]:
        """Build the side-specific pre-operative offset rows."""

        return [
            self._row(
                section="measurement",
                name=f"{side_label}_PreOp_AcetabularOffset",
                raw_value=side_results["acetabularOffset"]["rawValue"],
                corrected_value_mm=side_results["acetabularOffset"]["correctedValue"],
                units=length_units,
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_PreOp_FemoralOffset",
                raw_value=side_results["femoralOffset"]["rawValue"],
                corrected_value_mm=side_results["femoralOffset"]["correctedValue"],
                units=length_units,
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_PreOp_GlobalOffset",
                raw_value=side_results["preopGlobalOffset"]["rawValue"],
                corrected_value_mm=side_results["preopGlobalOffset"]["correctedValue"],
                units=length_units,
                details="Numerical sum of the pre-operative acetabular offset and femoral offset.",
            ),
        ]

    def _side_postop_measurement_rows(
        self,
        side_label: str,
        side_results: Any,
        length_units: str,
    ) -> list[Any]:
        """Build the side-specific post-operative angle, head, and offset rows."""

        return [
            self._row(
                section="measurement",
                name=f"{side_label}_AcetabularInclinationAngle_FreeHand_PostOp",
                raw_value=side_results["acetabularInclinationAngle"]["rawValue"],
                units="degrees",
                details="Acute angle between the side-specific free-hand inclination line and the reference line.",
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_CupOpeningEllipseFit_Inclination_PostOp",
                raw_value=side_results["cupOpeningEllipseInclinationAngle"]["rawValue"],
                units="degrees",
                details="Acute angle between the fitted cup opening ellipse major diameter and the reference line.",
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_CupAnteversionRetroversionAngle_PostOp",
                raw_value=side_results["cupOpeningAnteversionRetroversionAngle"]["rawValue"],
                units="degrees",
                details=(
                    "Theta = asin(minor diameter / major diameter) from the fitted cup opening "
                    "ellipse diameters."
                ),
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_ImplantFemoralCCD_PostOp",
                raw_value=side_results["implantFemoralCCD"]["rawValue"],
                units="degrees",
                details="Obtuse medial-side angle between the femoral shaft axis and the implant neck axis.",
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_PostOp_ImplantHead_Diameter",
                raw_value=side_results["implantHead"]["rawValue"],
                corrected_value_mm=side_results["implantHead"]["correctedValue"],
                units=length_units,
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_PostOp_AcetabularOffset",
                raw_value=side_results["postOpAcetabularOffset"]["rawValue"],
                corrected_value_mm=side_results["postOpAcetabularOffset"]["correctedValue"],
                units=length_units,
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_PostOp_FemoralOffset",
                raw_value=side_results["postOpFemoralOffset"]["rawValue"],
                corrected_value_mm=side_results["postOpFemoralOffset"]["correctedValue"],
                units=length_units,
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_PostOp_GlobalOffset",
                raw_value=side_results["postOpGlobalOffset"]["rawValue"],
                corrected_value_mm=side_results["postOpGlobalOffset"]["correctedValue"],
                units=length_units,
                details="Numerical sum of the post-operative acetabular offset and femoral offset.",
            ),
            self._row(
                section="measurement",
                name=f"{side_label}_StemAlignment",
                raw_value=side_results["implantAlignment"]["rawValue"],
                units="degrees",
                details="Acute angle difference between the derived stem axis and the femoral shaft axis.",
            ),
        ]

    def _side_measurement_rows(
        self,
        side_label: str,
        side_results: Any,
        length_units: str,
    ) -> list[Any]:
        """Build all side-specific measurement rows in their export order."""

        rows = []
        rows.extend(self._side_head_and_angle_measurement_rows(side_label, side_results, length_units))
        rows.extend(self._side_morphology_measurement_rows(side_label, side_results))
        rows.extend(self._side_preop_measurement_rows(side_label, side_results, length_units))
        rows.extend(self._side_postop_measurement_rows(side_label, side_results, length_units))
        for key, name, _title in LENGTH_FIELDS:
            result = side_results.get(key, {})
            if result.get("defined"):
                rows.append(self._row(section="measurement", name=f"{side_label}_{name}", raw_value=result["rawValue"],
                                      corrected_value_mm=result["correctedValue"], units=length_units,
                                      details="Projected head-to-shell centre distance on this film (inlay wear estimate)." if key == "inlay_wear" else ""))
        return rows

    def _other_line_measurement_rows(self, results: Any, length_units: str) -> list[Any]:
        """Build the measurement rows for user-created custom line tools."""

        rows = []
        for measurement in results["otherLines"]:
            rows.append(
                self._row(
                    section="measurement",
                    name=f"Line_{measurement['index']}_Length",
                    raw_value=measurement["rawValue"],
                    corrected_value_mm=measurement["correctedValue"],
                    units=length_units,
                    details=(
                        "Custom line measurement created from two placed points."
                        + self._other_line_lock_mode_details(measurement)
                    ),
                )
            )
        return rows

    def _other_line_lock_mode_details(self, measurement: Any) -> str:
        """Return the optional export note describing how a custom line was constrained."""

        lock_mode = measurement.get("lockMode")
        if lock_mode == OtherAngleLockMode.PARALLEL:
            return " Orientation locked parallel to the reference line."
        if lock_mode == OtherAngleLockMode.PERPENDICULAR:
            return " Orientation locked perpendicular to the reference line."
        return ""

    def _other_angle_lock_mode_details(self, measurement: Any) -> str:
        """Return the optional export note describing how a custom angle was constrained."""

        lock_mode = measurement.get("lockMode")
        if lock_mode == OtherAngleLockMode.PARALLEL:
            return " First arm locked parallel to the reference line."
        if lock_mode == OtherAngleLockMode.PERPENDICULAR:
            return " First arm locked perpendicular to the reference line."
        return ""

    def _other_angle_measurement_rows(self, results: Any) -> list[Any]:
        """Build the measurement rows for user-created custom angle tools."""

        rows = []
        for measurement in results["otherAngles"]:
            rows.append(
                self._row(
                    section="measurement",
                    name=f"Angle_{measurement['index']}",
                    raw_value=measurement["rawValue"],
                    units="degrees",
                    details=(
                        "Custom three-point angle measurement."
                        + self._other_angle_lock_mode_details(measurement)
                    ),
                )
            )
        return rows

    def _measurement_rows(self, results: Any, length_units: str) -> list[Any]:
        """Build all measurement rows in the canonical export order."""

        rows = []
        rows.extend(self._global_measurement_rows(results, length_units))
        for side_key in SIDE_KEYS:
            side_label = SIDE_LABELS[side_key]
            rows.extend(
                self._side_measurement_rows(
                    side_label,
                    results["sides"][side_key],
                    length_units,
                )
            )
        rows.extend(self._other_line_measurement_rows(results, length_units))
        rows.extend(self._other_angle_measurement_rows(results))
        rows.append(
            self._row(
                section="measurement",
                name="LLD",
                raw_value=results["lld"]["rawValue"],
                corrected_value_mm=results["lld"]["correctedValue"],
                units=length_units,
                details="Absolute height difference measured perpendicular to the reference line.",
            )
        )
        rows.append(
            self._row(
                section="measurement",
                name="LLD_Signed_LeftMinusRight",
                raw_value=results["lld"]["signedRawValue"],
                corrected_value_mm=results["lld"]["signedCorrectedValue"],
                units=length_units,
            )
        )
        return rows

    def _export_point_roles(self) -> list[Any]:
        """Return the logical roles whose explicit control points should be written to CSV."""

        point_roles = [
            "calibrationPoints",
            "referenceLine",
            "lldPoints",
            "lldLeftParallel",
            "lldRightParallel",
            "lldHeightDifference",
        ]
        point_roles.extend(self.other_point_roles())
        point_roles.extend(self.other_line_roles())
        point_roles.extend(self.other_angle_roles())
        for side_key in SIDE_KEYS:
            point_roles.extend(
                self.side_roles(
                    [
                        "extrusionIndexMedialLine",
                        "extrusionIndexMiddleLine",
                        "extrusionIndexLateralLine",
                        "shaftMorphologyLTPoints",
                        "shaftMorphologyMidline",
                        "shaftMorphologyPoints",
                        "shaftMorphologyGuideLineA",
                        "shaftMorphologyGuideLineB",
                        "tonnisAngleLine",
                        "tonnisAngleReferenceArm",
                        "sharpAngleLine",
                        "sharpAngleReferenceArm",
                        "lceAnglePoint",
                        "lceAngleVisual",
                        "lceAngleRadialArm",
                        "femurHeadPoints",
                        "femurHeadCenter",
                        "implantHeadPoints",
                        "implantHeadCenter",
                        *(spec[1] for spec in TOOLS.values()),
                        "cupShellCenter",
                        "inlayWearLine",
                        "cupOpeningEllipsePoints",
                        "cupOpeningEllipseMajorDiameter",
                        "cupOpeningEllipseMinorDiameter",
                        "shaftGuideProximal",
                        "shaftGuideDistal",
                        "shaftAxis",
                        "neckGuideProximal",
                        "neckGuideDistal",
                        "neckAxis",
                        "implantNeckGuideProximal",
                        "implantNeckGuideDistal",
                        "implantNeckAxis",
                        "acetabularOffsetLineA",
                        "acetabularOffsetLineB",
                        "femoralOffsetLine",
                        "acetabularInclinationLine",
                        "postOpAcetabularOffsetLineA",
                        "postOpAcetabularOffsetLineB",
                        "postOpFemoralOffsetLine",
                        "implantAlignmentGuideProximal",
                        "implantAlignmentGuideDistal",
                        "implantAlignmentLine",
                        "iliopectinealLine",
                        "ilioischialLine",
                        "shentonLine",
                        "acetabularRoofSourcil",
                    "anteriorAcetabularWall",
                    "posteriorAcetabularWall",
                        "lineaTerminalis",
                        *FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
                    ],
                    side_key,
                )
            )
        return point_roles

    def _point_row_details_for_node(self, role: Any, node: Any) -> str:
        """Return point-row details, including contour classification when available."""

        details = str(role)
        if node is None or not hasattr(node, "GetAttribute"):
            return details
        class_key = node.GetAttribute(FEMORAL_SHAFT_CONTOUR_CLASS_ATTRIBUTE)
        if class_key:
            class_label = FEMORAL_SHAFT_CONTOUR_CLASS_LABELS.get(class_key, class_key)
            details += f"; femoral_shaft_contour_class={class_key} ({class_label})"
        return details

    def _point_rows_for_role(self, role: Any) -> list[Any]:
        """Build point rows for one logical node role."""

        rows = []
        node = self.get_node(role)
        curve_metadata = self._curve_metadata_for_node(node)
        details = self._point_row_details_for_node(role, node)
        for index, point in enumerate(self._defined_points(node)):
            rows.append(
                self._row(
                    section="point",
                    name=node.GetName(),
                    index=index,
                    label=node.GetNthControlPointLabel(index),
                    x_ras=point[0],
                    y_ras=point[1],
                    z_ras=point[2],
                    curve_type=curve_metadata["curve_type"],
                    curve_points_per_segment=curve_metadata["curve_points_per_segment"],
                    details=details,
                )
            )
        return rows

    def _point_rows(self) -> list[Any]:
        """Build all explicit user-point rows in export order."""

        rows = []
        for role in self._export_point_roles():
            rows.extend(self._point_rows_for_role(role))
        return rows

    def _derived_point_row(
        self,
        name: str,
        label: str,
        point: Any,
        index: int=0,
    ) -> Any:
        """Create one derived-point export row."""

        return self._row(
            section="derived_point",
            name=name,
            index=index,
            label=label,
            x_ras=point[0],
            y_ras=point[1],
            z_ras=point[2],
        )

    def _optional_derived_point_rows(self, name: str, label: str, point: Any) -> list[Any]:
        """Return zero or one derived-point row depending on whether the point exists."""

        if point is None:
            return []
        return [self._derived_point_row(name, label, point)]

    def _derived_endpoint_rows(self, name: str, labels: tuple[str, str], points: Any) -> list[Any]:
        """Build the two endpoint rows for one derived axis-like construction."""

        rows = []
        for index, point in enumerate(points):
            rows.append(self._derived_point_row(name, labels[index], point, index=index))
        return rows

    def _calibration_derived_point_rows(self, results: Any) -> list[Any]:
        """Build derived-point rows for global calibration geometry."""

        return self._optional_derived_point_rows(
            "CalibrationBall_Center",
            "CalibrationBall_Center",
            results["calibration"]["center"],
        )

    def _side_derived_point_rows(self, side_key: Any, side_results: Any) -> list[Any]:
        """Build all derived-point rows for one side in the canonical export order."""

        side_label = SIDE_LABELS[side_key]
        rows = []
        rows.extend(
            self._derived_endpoint_rows(
                f"{side_label}_FemoralShaftAxis",
                (
                    f"FemoralShaftAxis_{side_label}_Start",
                    f"FemoralShaftAxis_{side_label}_End",
                ),
                side_results["femoralShaftAxis"]["endpoints"],
            )
        )
        rows.extend(
            self._optional_derived_point_rows(
                f"{side_label}_FemoralShaftAxis_Origin",
                f"FemoralShaftAxis_{side_label}_Origin",
                side_results["femoralShaftAxis"]["origin"],
            )
        )
        rows.extend(
            self._derived_endpoint_rows(
                f"{side_label}_FemoralNeckAxis",
                (
                    f"FemoralNeckAxis_{side_label}_Start",
                    f"FemoralNeckAxis_{side_label}_End",
                ),
                side_results["femoralNeckAxis"]["endpoints"],
            )
        )
        rows.extend(
            self._optional_derived_point_rows(
                f"{side_label}_FemoralNeckAxis_Origin",
                f"FemoralNeckAxis_{side_label}_Origin",
                side_results["femoralNeckAxis"]["origin"],
            )
        )
        rows.extend(
            self._derived_endpoint_rows(
                f"{side_label}_ImplantNeckAxis",
                (
                    f"ImplantNeckAxis_{side_label}_Start",
                    f"ImplantNeckAxis_{side_label}_End",
                ),
                side_results["implantNeckAxis"]["endpoints"],
            )
        )
        rows.extend(
            self._optional_derived_point_rows(
                f"{side_label}_ImplantNeckAxis_Origin",
                f"ImplantNeckAxis_{side_label}_Origin",
                side_results["implantNeckAxis"]["origin"],
            )
        )
        rows.extend(
            self._derived_endpoint_rows(
                f"{side_label}_StemAlignmentAxis",
                (
                    f"StemAlignment_{side_label}_Start",
                    f"StemAlignment_{side_label}_End",
                ),
                side_results["implantStemAxis"]["endpoints"],
            )
        )
        rows.extend(
            self._optional_derived_point_rows(
                f"{side_label}_StemAlignmentAxis_Origin",
                f"StemAlignment_{side_label}_Origin",
                side_results["implantStemAxis"]["origin"],
            )
        )
        rows.extend(
            self._optional_derived_point_rows(
                f"{side_label}_CupOpeningEllipse_Center",
                f"CupOpeningEllipse_{side_label}_Center",
                side_results["cupOpeningEllipseFit"]["center"],
            )
        )
        rows.extend(
            self._derived_endpoint_rows(
                f"{side_label}_CupOpeningEllipse_MajorAxis",
                (
                    f"CupOpeningEllipse_{side_label}_MajorAxis_Start",
                    f"CupOpeningEllipse_{side_label}_MajorAxis_End",
                ),
                side_results["cupOpeningEllipseFit"]["majorEndpoints"],
            )
        )
        rows.extend(
            self._derived_endpoint_rows(
                f"{side_label}_CupOpeningEllipse_MinorAxis",
                (
                    f"CupOpeningEllipse_{side_label}_MinorAxis_Start",
                    f"CupOpeningEllipse_{side_label}_MinorAxis_End",
                ),
                side_results["cupOpeningEllipseFit"]["minorEndpoints"],
            )
        )
        return rows

    def _lld_projection_rows(self, results: Any) -> list[Any]:
        """Build derived-point rows for the LLD projections."""

        rows = []
        rows.extend(
            self._optional_derived_point_rows(
                "LLD_LeftProjection",
                "LLD_LeftProjection",
                results["lld"]["leftProjection"],
            )
        )
        rows.extend(
            self._optional_derived_point_rows(
                "LLD_RightProjection",
                "LLD_RightProjection",
                results["lld"]["rightProjection"],
            )
        )
        return rows

    def _derived_point_rows(self, results: Any) -> list[Any]:
        """Build every derived-point row in the canonical export order."""

        rows = []
        rows.extend(self._calibration_derived_point_rows(results))
        for side_key in SIDE_KEYS:
            rows.extend(self._side_derived_point_rows(side_key, results["sides"][side_key]))
        rows.extend(self._lld_projection_rows(results))
        return rows

    def _build_export_rows(self, image_node: Any=None) -> Any:
        """Build every CSV row describing metadata, measurements, and coordinates. Export assembly is
        centralized so documentation, results, and saved data all reflect the same internal schema.
        """

        results = self.latest_results
        length_units = "su -> mm" if results["calibration"]["ballPresent"] else "su"

        rows = []
        rows.extend(self._metadata_rows(image_node, results))
        rows.extend(self._measurement_rows(results, length_units))
        rows.extend(self._point_rows())
        rows.extend(self._derived_point_rows(results))
        return rows
