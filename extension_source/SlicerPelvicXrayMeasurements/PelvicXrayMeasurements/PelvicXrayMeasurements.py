"""3D Slicer entry point for calibrated pelvic radiograph measurements.

The Slicer-facing classes remain in this file so the extension loader has the expected scripted
module shape. Constants, MRML node schemas, pure geometry helpers, image export rendering, and guided
workflow actions live in focused companion modules inside `PelvicXrayMeasurementsLib`.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import ctk
import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleWidget,
)
from slicer.util import VTKObservationMixin


MODULE_DIR = os.path.dirname(__file__)
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)
LIB_DIR = os.path.join(MODULE_DIR, "PelvicXrayMeasurementsLib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

TOGGLED_BOOL_SIGNAL = "toggled(bool)"
AUTO_FEATURE_MEASUREMENT_KEYS = {
    "shaft_axis": "shaftAxis", "neck_axis": "neckAxis", "tonnis": "tonnisAngle",
    "sharp": "sharpAngle", "lce": "lceAngle", "acetabular_offset": "acetabularOffset",
    "femoral_offset": "femoralOffset", "extrusion_index": "extrusionIndex",
    "shaft_morphology": "femurShaftMorphology", "inclination": "inclinationAngle",
    "cup_opening": "cupOpeningEllipseFit", "implant_neck_axis": "implantNeckAxis",
    "implant_alignment": "implantAlignment", "post_acetabular_offset": "postOpAcetabularOffset",
    "post_femoral_offset": "postOpFemoralOffset",
}
SESSION_DIRECTORY_STATE = {
    "lastDirectoryPath": "",
    "lastExportDirectoryPath": "",
    "inputFolderPath": "",
    "outputFolderPath": "",
}

from PelvicXrayMeasurementsConstants import (
    ACTIVE_SIDE_BADGE_ROLE,
    CALIBRATION_BALL_DIAMETER_MM,
    GLOBAL_MEASUREMENT_KEYS,
    MEASUREMENT_RESULT_GROUPS,
    MeasurementKey,
    MODULE_NAME,
    MODULE_VERSION,
    MORPHOLOGY_REFERENCE_CITATION,
    MORPHOLOGY_REFERENCE_IMAGE_PATH,
    OtherAngleLockMode,
    ROLE_ATTRIBUTE,
    SideKey,
    SIDE_KEYS,
    SIDE_LABELS,
    SIDE_MEASUREMENT_KEYS,
)
from PelvicXrayMeasurementsCalculations import MeasurementCalculationMixin
from PelvicXrayMeasurementsAutoPlacement import (
    enforce_morphology_side_constraints,
    feature_specs,
    make_frame,
    predict_feature,
    predict_shaft_from_image,
    read_model,
)
from PelvicXrayMeasurementsCaseWorkflow import (
    latest_saved_csv_path_for_image_filename,
    latest_saved_scene_path_for_image_filename,
    load_export_csv_rows,
    list_input_images,
    parse_saved_case_metadata,
    path_exists,
)
from PelvicXrayMeasurementsCaseExport import CaseExportMixin
from PelvicXrayMeasurementsFormatting import (
    build_measurement_overlay_text,
    format_calibration_summary,
    format_compact_angle,
    format_compact_length,
    format_compact_percent,
    format_compact_ratio,
    format_lld_summary,
    format_reference_summary,
)
from PelvicXrayMeasurementsImageExport import AnnotationImageExportMixin
from PelvicXrayMeasurementsResults import MeasurementResultsMixin
from PelvicXrayMeasurementsScene import SceneNodeMixin
from PelvicXrayMeasurementsWorkflow import WorkflowActionsMixin


class PelvicXrayMeasurements(ScriptedLoadableModule):
    """Register the scripted module with 3D Slicer. This class mainly exposes metadata so the extension
    appears correctly in the Slicer module catalogue.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize Slicer-facing metadata for the module. This constructor is intentionally light
        because Slicer may recreate the module object during reloads.
        """

        super().__init__(parent)
        self.parent.title = "Pelvic Xray Measurements"
        self.parent.categories = ["Orthopaedics"]
        self.parent.dependencies = []
        self.parent.contributors = [
            ("Developed by: Kaveh Same, MD, MPH, PhD Candidate; Michael Ogon Laboratory for Orthopedic Research, "
             "Orthopedic Hospital Speising, Vienna, Austria"),
            "In collaboration with: ImageBiopsy Lab GmbH, Vienna, Austria",
            "Code backbone created by: Codex; OpenAI, California, USA",
        ]
        self.parent.helpText = (
            "Research use only — not a medical device. Not intended for diagnosis, "
            "treatment planning or clinical decision-making. "
            "Editable, calibrated pelvic radiograph measurements with bilateral "
            "landmarks, fitted geometry, Smart Point Placement and scene/CSV/image export."
        )
        self.parent.acknowledgementText = (
            "Developed by Kaveh Same, MD, MPH, PhD Candidate, Michael Ogon Laboratory "
            "for Orthopedic Research, Orthopedic Hospital Speising, Vienna, Austria. "
            "In collaboration with ImageBiopsy Lab GmbH, Vienna, Austria. "
            "Code backbone created by Codex, OpenAI, California, USA."
        )

        icon_path = os.path.join(
            os.path.dirname(__file__), "Resources", "Icons", f"{MODULE_NAME}.png"
        )
        if os.path.exists(icon_path):
            self.parent.icon = qt.QIcon(icon_path)


class PelvicXrayMeasurementsWidget(
    WorkflowActionsMixin,
    AnnotationImageExportMixin,
    ScriptedLoadableModuleWidget,
    VTKObservationMixin,
):
    """Own the Qt user interface and translate user interactions into logic calls. The widget keeps
    presentation concerns separate from the geometry and export code in the logic layer.
    """

    def __init__(self, parent: Any=None) -> None:
        """Initialize widget-side state without yet touching MRML nodes or building the UI. Heavy setup
        is deferred to setup so module reloads remain reliable.
        """

        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self.active_placement_queue = []
        self.active_placement_name = None
        self.active_placement_measurement_key = None
        self.active_placement_side_key = None
        self.active_femoral_shaft_contour_step_index = None
        self.pending_auto_line_endpoints = {}
        self.last_export_summary = "Not saved yet."
        self.measurement_buttons = {}
        self.measurement_button_aliases = []
        self.measurement_dependency_tooltips = {}
        self.measurement_visibility_checks = {}
        self.export_buttons = []
        self.display_measurements_on_image = True
        self.export_curve_points_as_txt = False
        self.last_directory_path = ""
        self.last_export_directory_path = ""
        self.input_folder_path = ""
        self.output_folder_path = ""
        self.folder_image_paths: list[Path] = []
        self.current_folder_image_index = -1
        self.current_folder_image_path: Path | None = None
        self.loaded_image_node = None
        self.image_selector_sync_in_progress = False
        self.image_selector_signature: tuple[Any, ...] | None = None
        self.case_has_unsaved_changes = False
        self.case_transition_in_progress = False
        self.scene_node_added_refresh_scheduled = False
        self.external_scene_load_in_progress = False
        self.external_scene_load_refresh_scheduled = False
        self.suspend_dirty_tracking = False

    def setup(self) -> None:
        """Widget helper for setup. Keeping UI responsibilities in small methods makes the large
        measurement interface easier to follow and maintain.
        """

        super().setup()
        self.logic = PelvicXrayMeasurementsLogic()
        self._build_ui()
        self._restore_directory_preferences()
        if hasattr(slicer, "app"):
            slicer.app.connect("aboutToQuit()", self.on_application_about_to_quit)

        self._observe_scene_and_nodes()
        self.logic.ensure_nodes()
        self._select_default_image_if_needed()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def cleanup(self) -> None:
        """Widget helper for cleanup. Keeping UI responsibilities in small methods makes the large
        measurement interface easier to follow and maintain.
        """

        self._restore_standard_application_layout()
        self.removeObservers()

    def enter(self) -> None:
        """Widget helper for enter. Keeping UI responsibilities in small methods makes the large
        measurement interface easier to follow and maintain.
        """

        self._set_default_extension_layout()
        self.logic.ensure_nodes()
        self._observe_scene_and_nodes()
        self._select_default_image_if_needed()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def exit(self) -> None:
        """Restore Slicer's default multi-panel layout when the user leaves this module."""

        self._restore_standard_application_layout()

    def _build_ui(self) -> None:
        """Construct the full module interface, including case selection, measurement controls,
        results, and export actions. The top-level builder only orchestrates section creation so the
        Slicer-facing widget stays readable while each subsection keeps its original setup order.
        """

        self._build_version_label()
        self.layout.addWidget(self._build_case_section())
        self.layout.addWidget(self._build_measurement_section())
        self.layout.addWidget(self._build_results_section())
        self.layout.addWidget(self._build_export_section())
        self.layout.addStretch(1)

    def _build_version_label(self) -> None:
        """Create the module-version label shown above the workflow sections."""

        self.version_label = qt.QLabel(f"Version {MODULE_VERSION}")
        self.version_label.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
        self.version_label.setStyleSheet("QLabel { color: #5d7389; font-size: 11px; }")
        self.layout.addWidget(self.version_label)
        self.research_use_label = qt.QLabel("Research use only — not a medical device.")
        self.research_use_label.setWordWrap(True)
        self.research_use_label.setToolTip(
            "Not intended for diagnosis, treatment planning or clinical decision-making."
        )
        self.layout.addWidget(self.research_use_label)

    def _build_case_section(self) -> Any:
        """Create the case-level controls for folders, image selection, annotator, and calibration."""

        case_section = ctk.ctkCollapsibleButton()
        case_section.setText("Case")
        case_layout = qt.QFormLayout(case_section)

        self.input_folder_line_edit = qt.QLineEdit()
        self.input_folder_line_edit.setReadOnly(True)
        self.input_folder_line_edit.setPlaceholderText("No input folder selected")
        self.input_folder_line_edit.setToolTip(
            "Browse images in this folder with the navigation arrows."
        )
        self.input_folder_browse_button = qt.QPushButton("Browse")
        self.input_folder_browse_button.connect("clicked(bool)", self.on_input_folder_browse_clicked)
        self.input_folder_clear_button = qt.QPushButton("Clear")
        self.input_folder_clear_button.connect("clicked(bool)", self.on_input_folder_clear_clicked)
        input_folder_controls = qt.QWidget()
        input_folder_layout = qt.QHBoxLayout(input_folder_controls)
        input_folder_layout.setContentsMargins(0, 0, 0, 0)
        input_folder_layout.setSpacing(6)
        input_folder_layout.addWidget(self.input_folder_line_edit, 1)
        input_folder_layout.addWidget(self.input_folder_browse_button, 0)
        input_folder_layout.addWidget(self.input_folder_clear_button, 0)
        case_layout.addRow("Input Folder", input_folder_controls)

        self.output_folder_line_edit = qt.QLineEdit()
        self.output_folder_line_edit.setReadOnly(True)
        self.output_folder_line_edit.setPlaceholderText("No output folder selected")
        self.output_folder_line_edit.setToolTip(
            "Save and export to this folder."
        )
        self.output_folder_browse_button = qt.QPushButton("Browse")
        self.output_folder_browse_button.connect("clicked(bool)", self.on_output_folder_browse_clicked)
        self.output_folder_clear_button = qt.QPushButton("Clear")
        self.output_folder_clear_button.connect("clicked(bool)", self.on_output_folder_clear_clicked)
        output_folder_controls = qt.QWidget()
        output_folder_layout = qt.QHBoxLayout(output_folder_controls)
        output_folder_layout.setContentsMargins(0, 0, 0, 0)
        output_folder_layout.setSpacing(6)
        output_folder_layout.addWidget(self.output_folder_line_edit, 1)
        output_folder_layout.addWidget(self.output_folder_browse_button, 0)
        output_folder_layout.addWidget(self.output_folder_clear_button, 0)
        case_layout.addRow("Output Folder", output_folder_controls)

        self.image_selector = qt.QComboBox()
        self.image_selector.setToolTip(
            "Shows all images from the selected input folder, or the loaded scene image when no "
            "input folder is active."
        )
        self.image_selector.connect("currentIndexChanged(int)", self.on_image_changed)
        self.previous_image_button = qt.QPushButton("<")
        self.previous_image_button.setToolTip("Load the previous image from the selected input folder.")
        self.previous_image_button.connect("clicked(bool)", self.on_previous_image_clicked)
        self.next_image_button = qt.QPushButton(">")
        self.next_image_button.setToolTip("Load the next image from the selected input folder.")
        self.next_image_button.connect("clicked(bool)", self.on_next_image_clicked)
        self.image_position_label = qt.QLabel("Manual")
        self.image_position_label.setAlignment(qt.Qt.AlignCenter)
        self.image_position_label.setMinimumWidth(64)
        image_controls = qt.QWidget()
        image_controls_layout = qt.QHBoxLayout(image_controls)
        image_controls_layout.setContentsMargins(0, 0, 0, 0)
        image_controls_layout.setSpacing(6)
        image_controls_layout.addWidget(self.previous_image_button, 0)
        image_controls_layout.addWidget(self.image_selector, 1)
        image_controls_layout.addWidget(self.next_image_button, 0)
        image_controls_layout.addWidget(self.image_position_label, 0)
        case_layout.addRow("Image", image_controls)

        self.annotator_line_edit = qt.QLineEdit()
        self.annotator_line_edit.setPlaceholderText("Enter annotator name")
        self.annotator_line_edit.setToolTip(
            "Required for all save and export actions. This field persists "
            "across scene closes within the current Slicer session."
        )
        self.annotator_line_edit.connect("textChanged(QString)", self.on_annotator_changed)
        case_layout.addRow("Annotator:", self.annotator_line_edit)

        self.side_selector = qt.QComboBox()
        self.side_selector.addItem("Left", SideKey.LEFT)
        self.side_selector.addItem("Right", SideKey.RIGHT)
        self.side_selector.connect("currentIndexChanged(int)", self.on_side_changed)
        self.display_measurements_check = qt.QCheckBox("Display measurement values on exported image")
        self.display_measurements_check.setChecked(True)
        self.display_measurements_check.connect(
            TOGGLED_BOOL_SIGNAL, self.on_display_measurements_toggled
        )
        side_controls = qt.QWidget()
        side_controls_layout = qt.QHBoxLayout(side_controls)
        side_controls_layout.setContentsMargins(0, 0, 0, 0)
        side_controls_layout.setSpacing(8)
        side_controls_layout.addWidget(self.side_selector)
        side_controls_layout.addStretch(1)
        case_layout.addRow("Active Side", side_controls)

        self.ball_diameter_spin_box = qt.QDoubleSpinBox()
        self.ball_diameter_spin_box.setDecimals(1)
        self.ball_diameter_spin_box.setRange(0.1, 500.0)
        self.ball_diameter_spin_box.setSingleStep(0.5)
        self.ball_diameter_spin_box.setSuffix(" mm")
        self.ball_diameter_spin_box.setValue(self.logic.calibration_ball_diameter_mm)
        self.ball_diameter_spin_box.connect("valueChanged(double)", self.on_ball_diameter_changed)
        self.ball_not_present_check = qt.QCheckBox("Not Present")
        self.ball_not_present_check.setChecked(not self.logic.calibration_ball_present)
        self.ball_not_present_check.connect(TOGGLED_BOOL_SIGNAL, self.on_ball_not_present_toggled)
        ball_controls = qt.QWidget()
        ball_controls_layout = qt.QHBoxLayout(ball_controls)
        ball_controls_layout.setContentsMargins(0, 0, 0, 0)
        ball_controls_layout.setSpacing(8)
        ball_controls_layout.addWidget(self.ball_diameter_spin_box)
        ball_controls_layout.addWidget(self.ball_not_present_check)
        ball_controls_layout.addStretch(1)
        case_layout.addRow("Ball Diameter", ball_controls)

        self.instructions_label = qt.QLabel(
            "Start with the calibration ball using the diameter entered above, "
            "or check Not Present to work in su only. "
            "For bilateral measurements, choose Left or Right first."
        )
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setStyleSheet(
            "QLabel { background: #eef6ff; border: 1px solid #b9d8ff; border-radius: 6px; padding: 8px; }"
        )
        case_layout.addRow("Workflow", self.instructions_label)
        return case_section

    def _build_measurement_section(self) -> Any:
        """Create the measurement tool panel with buttons, repeat counts, and visibility controls."""

        workflow_section = ctk.ctkCollapsibleButton()
        workflow_section.setText("Measurements")
        workflow_layout = qt.QGridLayout(workflow_section)
        self._initialize_measurement_controls()
        self._wire_action_buttons()
        self._populate_measurement_layout(workflow_layout)
        return workflow_section

    def _initialize_measurement_controls(self) -> None:
        """Instantiate measurement and export action widgets without applying scene state."""

        self.calibration_button = qt.QPushButton("Calibration Ball")
        self.reference_line_button = qt.QPushButton("Reference Line")
        self.auto_place_button = qt.QPushButton("Auto-place points…")
        self.tonnis_angle_button = qt.QPushButton("Acetabular Index (Tönnis)")
        self.sharp_angle_button = qt.QPushButton("Sharp Angle")
        self.lce_angle_button = qt.QPushButton("LCE Angle")
        self.femur_head_button = qt.QPushButton("Femur Head")
        self.shaft_axis_button = qt.QPushButton("Femoral Shaft Axis")
        self.neck_axis_button = qt.QPushButton("Femoral Neck Axis")
        self.acetabular_offset_button = qt.QPushButton("Acetabular Offset")
        self.femoral_offset_button = qt.QPushButton("Femoral Offset")
        self.extrusion_index_button = qt.QPushButton("Femoral Head Extrusion Index")
        self.femur_shaft_morphology_button = qt.QPushButton("Femur Shaft Morphology")
        self.lld_button = qt.QPushButton("Leg Length Discrepancy")
        self.implant_head_center_button = qt.QPushButton("Implant Head Center")
        self.inclination_angle_button = qt.QPushButton("Acetabular Inclination Angle (Free Hand)")
        self.cup_opening_ellipse_fit_button = qt.QPushButton("Cup Opening Ellipse Fit")
        self.implant_neck_axis_button = qt.QPushButton("Implant Neck Axis")
        self.postop_shaft_axis_button = qt.QPushButton("Femoral Shaft Axis")
        self.postop_acetabular_offset_button = qt.QPushButton("Acetabular Offset")
        self.postop_femoral_offset_button = qt.QPushButton("Femoral Offset")
        self.implant_alignment_button = qt.QPushButton("Stem Alignment")
        self.iliopectineal_line_button = qt.QPushButton("Iliopectineal Line")
        self.ilioischial_line_button = qt.QPushButton("Ilioischial Line")
        self.shenton_line_button = qt.QPushButton("Shenton Line")
        self.acetabular_roof_sourcil_button = qt.QPushButton("Acetabular Roof (Sourcil)")
        self.anterior_acetabular_wall_button = qt.QPushButton("Anterior Acetabular Wall")
        self.posterior_acetabular_wall_button = qt.QPushButton("Posterior Acetabular Wall")
        self.linea_terminalis_button = qt.QPushButton("Linea Terminalis")
        self.femoral_shaft_contour_button = qt.QPushButton("Femoral Shaft")
        self.other_point_button = qt.QPushButton("Point")
        self.other_point_count_spin_box = qt.QSpinBox()
        self.other_point_count_spin_box.setRange(0, 999)
        self.other_point_count_spin_box.setMinimumWidth(64)
        self.other_point_count_spin_box.connect("valueChanged(int)", self.on_other_point_count_changed)
        self.other_line_button = qt.QPushButton("Line")
        self.other_angle_button = qt.QPushButton("Angle")
        self.other_line_count_spin_box = qt.QSpinBox()
        self.other_line_count_spin_box.setRange(0, 999)
        self.other_line_count_spin_box.setMinimumWidth(64)
        self.other_line_count_spin_box.connect("valueChanged(int)", self.on_other_line_count_changed)
        self.other_line_parallel_check = qt.QCheckBox("Lock || Ref")
        self.other_line_parallel_check.setToolTip(
            "Keep the custom line parallel to the reference line while allowing its length and "
            "position to be adjusted."
        )
        self.other_line_perpendicular_check = qt.QCheckBox("Lock _|_ Ref")
        self.other_line_perpendicular_check.setToolTip(
            "Keep the custom line perpendicular to the reference line while allowing its length and "
            "position to be adjusted."
        )
        self.other_line_parallel_check.connect(TOGGLED_BOOL_SIGNAL, self.on_other_line_parallel_toggled)
        self.other_line_perpendicular_check.connect(TOGGLED_BOOL_SIGNAL, self.on_other_line_perpendicular_toggled)
        self.other_angle_count_spin_box = qt.QSpinBox()
        self.other_angle_count_spin_box.setRange(0, 999)
        self.other_angle_count_spin_box.setMinimumWidth(64)
        self.other_angle_count_spin_box.connect("valueChanged(int)", self.on_other_angle_count_changed)
        self.other_angle_parallel_check = qt.QCheckBox("Lock || Ref")
        self.other_angle_parallel_check.setToolTip(
            "Keep the first angle arm parallel to the reference line for new "
            "angle measurements."
        )
        self.other_angle_perpendicular_check = qt.QCheckBox("Lock _|_ Ref")
        self.other_angle_perpendicular_check.setToolTip(
            "Keep the first angle arm perpendicular to the reference line for "
            "new angle measurements."
        )
        self.other_angle_parallel_check.connect(TOGGLED_BOOL_SIGNAL, self.on_other_angle_parallel_toggled)
        self.other_angle_perpendicular_check.connect(TOGGLED_BOOL_SIGNAL, self.on_other_angle_perpendicular_toggled)
        self.neck_axis_lock_to_center_check = qt.QCheckBox("Lock to center")
        self.neck_axis_lock_to_center_check.connect(TOGGLED_BOOL_SIGNAL, self.on_neck_axis_lock_to_center_toggled)
        self.neck_axis_use_single_guide_check = qt.QCheckBox("Use single guide")
        self.neck_axis_use_single_guide_check.connect(TOGGLED_BOOL_SIGNAL, self.on_neck_axis_use_single_guide_toggled)
        self.implant_neck_axis_lock_to_center_check = qt.QCheckBox("Lock to center")
        self.implant_neck_axis_lock_to_center_check.connect(
            TOGGLED_BOOL_SIGNAL,
            self.on_implant_neck_axis_lock_to_center_toggled,
        )
        self.implant_neck_axis_use_single_guide_check = qt.QCheckBox("Use single guide")
        self.implant_neck_axis_use_single_guide_check.connect(
            TOGGLED_BOOL_SIGNAL,
            self.on_implant_neck_axis_use_single_guide_toggled,
        )
        self.save_all_button = qt.QPushButton("Export All")
        self.save_all_and_next_button = qt.QPushButton("Export All / Load Next Image")
        self.save_scene_button = qt.QPushButton("Export Scene")
        self.export_csv_button = qt.QPushButton("Export CSV")
        self.export_image_button = qt.QPushButton("Export Image")
        self.export_buttons = [
            self.save_all_button,
            self.save_all_and_next_button,
            self.save_scene_button,
            self.export_csv_button,
            self.export_image_button,
        ]
        self.measurement_buttons = {
            MeasurementKey.CALIBRATION: self.calibration_button,
            MeasurementKey.REFERENCE_LINE: self.reference_line_button,
            MeasurementKey.FEMUR_HEAD: self.femur_head_button,
            MeasurementKey.SHAFT_AXIS: self.shaft_axis_button,
            MeasurementKey.NECK_AXIS: self.neck_axis_button,
            MeasurementKey.TONNIS_ANGLE: self.tonnis_angle_button,
            MeasurementKey.SHARP_ANGLE: self.sharp_angle_button,
            MeasurementKey.LCE_ANGLE: self.lce_angle_button,
            MeasurementKey.ACETABULAR_OFFSET: self.acetabular_offset_button,
            MeasurementKey.FEMORAL_OFFSET: self.femoral_offset_button,
            MeasurementKey.EXTRUSION_INDEX: self.extrusion_index_button,
            MeasurementKey.FEMUR_SHAFT_MORPHOLOGY: self.femur_shaft_morphology_button,
            MeasurementKey.LLD: self.lld_button,
            MeasurementKey.IMPLANT_HEAD: self.implant_head_center_button,
            MeasurementKey.INCLINATION_ANGLE: self.inclination_angle_button,
            MeasurementKey.CUP_OPENING_ELLIPSE_FIT: self.cup_opening_ellipse_fit_button,
            MeasurementKey.IMPLANT_NECK_AXIS: self.implant_neck_axis_button,
            MeasurementKey.POSTOP_ACETABULAR_OFFSET: self.postop_acetabular_offset_button,
            MeasurementKey.POSTOP_FEMORAL_OFFSET: self.postop_femoral_offset_button,
            MeasurementKey.IMPLANT_ALIGNMENT: self.implant_alignment_button,
            MeasurementKey.ILIOPECTINEAL_LINE: self.iliopectineal_line_button,
            MeasurementKey.ILIOISCHIAL_LINE: self.ilioischial_line_button,
            MeasurementKey.SHENTON_LINE: self.shenton_line_button,
            MeasurementKey.ACETABULAR_ROOF_SOURCIL: self.acetabular_roof_sourcil_button,
            MeasurementKey.ANTERIOR_ACETABULAR_WALL: self.anterior_acetabular_wall_button,
            MeasurementKey.POSTERIOR_ACETABULAR_WALL: self.posterior_acetabular_wall_button,
            MeasurementKey.LINEA_TERMINALIS: self.linea_terminalis_button,
            MeasurementKey.FEMORAL_SHAFT_CONTOUR: self.femoral_shaft_contour_button,
            MeasurementKey.OTHER_POINT: self.other_point_button,
            MeasurementKey.OTHER_LINE: self.other_line_button,
            MeasurementKey.OTHER_ANGLE: self.other_angle_button,
        }
        self.measurement_button_aliases = [
            (self.postop_shaft_axis_button, MeasurementKey.SHAFT_AXIS),
        ]

    def _wire_action_buttons(self) -> None:
        """Connect button callbacks and apply their baseline styling."""

        buttons = [
            (self.calibration_button, self.on_calibration_clicked),
            (self.reference_line_button, self.on_reference_line_clicked),
            (self.auto_place_button, self.on_auto_place_clicked),
            (self.tonnis_angle_button, self.on_tonnis_angle_clicked),
            (self.sharp_angle_button, self.on_sharp_angle_clicked),
            (self.lce_angle_button, self.on_lce_angle_clicked),
            (self.femur_head_button, self.on_femur_head_clicked),
            (self.shaft_axis_button, self.on_shaft_axis_clicked),
            (self.neck_axis_button, self.on_neck_axis_clicked),
            (self.acetabular_offset_button, self.on_acetabular_offset_clicked),
            (self.femoral_offset_button, self.on_femoral_offset_clicked),
            (self.extrusion_index_button, self.on_extrusion_index_clicked),
            (self.femur_shaft_morphology_button, self.on_femur_shaft_morphology_clicked),
            (self.lld_button, self.on_lld_clicked),
            (self.implant_head_center_button, self.on_implant_head_center_clicked),
            (self.inclination_angle_button, self.on_inclination_angle_clicked),
            (self.cup_opening_ellipse_fit_button, self.on_cup_opening_ellipse_fit_clicked),
            (self.implant_neck_axis_button, self.on_implant_neck_axis_clicked),
            (self.postop_shaft_axis_button, self.on_shaft_axis_clicked),
            (self.postop_acetabular_offset_button, self.on_postop_acetabular_offset_clicked),
            (self.postop_femoral_offset_button, self.on_postop_femoral_offset_clicked),
            (self.implant_alignment_button, self.on_implant_alignment_clicked),
            (self.iliopectineal_line_button, self.on_iliopectineal_line_clicked),
            (self.ilioischial_line_button, self.on_ilioischial_line_clicked),
            (self.shenton_line_button, self.on_shenton_line_clicked),
            (self.acetabular_roof_sourcil_button, self.on_acetabular_roof_sourcil_clicked),
            (self.anterior_acetabular_wall_button, self.on_anterior_acetabular_wall_clicked),
            (self.posterior_acetabular_wall_button, self.on_posterior_acetabular_wall_clicked),
            (self.linea_terminalis_button, self.on_linea_terminalis_clicked),
            (self.femoral_shaft_contour_button, self.on_femoral_shaft_contour_clicked),
            (self.other_point_button, self.on_other_point_clicked),
            (self.other_line_button, self.on_other_line_clicked),
            (self.other_angle_button, self.on_other_angle_clicked),
            (self.save_all_button, self.on_save_all_clicked),
            (self.save_all_and_next_button, self.on_save_all_and_load_next_clicked),
            (self.save_scene_button, self.on_save_scene_clicked),
            (self.export_csv_button, self.on_export_csv_clicked),
            (self.export_image_button, self.on_export_image_clicked),
        ]

        for button, callback in buttons:
            button.connect("clicked(bool)", callback)
            button.setMinimumHeight(32)
            if button in self._all_measurement_button_widgets():
                button.setStyleSheet(self._measurement_button_style("idle"))
                qt_constants = getattr(qt, "Qt", None)
                if (
                    hasattr(button, "setAttribute")
                    and qt_constants is not None
                    and hasattr(qt_constants, "WA_AlwaysShowToolTips")
                ):
                    button.setAttribute(qt_constants.WA_AlwaysShowToolTips, True)
            else:
                button.setStyleSheet("")
                if hasattr(button, "setAutoDefault"):
                    button.setAutoDefault(False)
                if hasattr(button, "setDefault"):
                    button.setDefault(False)

    def _measurement_button_items(self) -> Any:
        """Yield every measurement button widget with the measurement key it controls."""

        for measurement_key, button in self.measurement_buttons.items():
            yield measurement_key, button
        for button, measurement_key in self.measurement_button_aliases:
            yield measurement_key, button

    def _measurement_buttons_for_key(self, measurement_key: Any) -> Any:
        """Return all button widgets that trigger the same underlying measurement."""

        buttons = []
        primary_button = self.measurement_buttons.get(measurement_key)
        if primary_button is not None:
            buttons.append(primary_button)
        for alias_button, alias_key in self.measurement_button_aliases:
            if alias_key == measurement_key:
                buttons.append(alias_button)
        return buttons

    def _all_measurement_button_widgets(self) -> Any:
        """Return the complete set of primary and alias measurement buttons."""

        return list(self.measurement_buttons.values()) + [
            button for button, _measurement_key in self.measurement_button_aliases
        ]

    def _populate_measurement_layout(self, workflow_layout: Any) -> None:
        """Populate the measurement panel layout in the exact clinical workflow order."""

        row_index = 0
        workflow_layout.addWidget(self._measurement_title_label("Smart Point Placement"), row_index, 0)
        row_index += 1
        workflow_layout.addWidget(self.auto_place_button, row_index, 0)
        row_index += 1
        workflow_layout.addWidget(self._measurement_title_label("1: Setup"), row_index, 0)
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.calibration_button,
                MeasurementKey.CALIBRATION,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.reference_line_button,
                MeasurementKey.REFERENCE_LINE,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(self._measurement_title_label("2: Pre-Operative"), row_index, 0)
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.femur_head_button,
                MeasurementKey.FEMUR_HEAD,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.shaft_axis_button,
                MeasurementKey.SHAFT_AXIS,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.neck_axis_button,
                MeasurementKey.NECK_AXIS,
                [self.neck_axis_lock_to_center_check, self.neck_axis_use_single_guide_check],
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.tonnis_angle_button,
                MeasurementKey.TONNIS_ANGLE,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.sharp_angle_button,
                MeasurementKey.SHARP_ANGLE,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.lce_angle_button,
                MeasurementKey.LCE_ANGLE,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.acetabular_offset_button,
                MeasurementKey.ACETABULAR_OFFSET,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.femoral_offset_button,
                MeasurementKey.FEMORAL_OFFSET,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.extrusion_index_button,
                MeasurementKey.EXTRUSION_INDEX,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.femur_shaft_morphology_button,
                MeasurementKey.FEMUR_SHAFT_MORPHOLOGY,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.lld_button,
                MeasurementKey.LLD,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(self._measurement_title_label("3: Post-Operative (THA)"), row_index, 0)
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.implant_head_center_button,
                MeasurementKey.IMPLANT_HEAD,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.inclination_angle_button,
                MeasurementKey.INCLINATION_ANGLE,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.cup_opening_ellipse_fit_button,
                MeasurementKey.CUP_OPENING_ELLIPSE_FIT,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.implant_neck_axis_button,
                MeasurementKey.IMPLANT_NECK_AXIS,
                [
                    self.implant_neck_axis_lock_to_center_check,
                    self.implant_neck_axis_use_single_guide_check,
                ],
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.postop_shaft_axis_button,
                MeasurementKey.SHAFT_AXIS,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.implant_alignment_button,
                MeasurementKey.IMPLANT_ALIGNMENT,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.postop_acetabular_offset_button,
                MeasurementKey.POSTOP_ACETABULAR_OFFSET,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._measurement_row_widget(
                self.postop_femoral_offset_button,
                MeasurementKey.POSTOP_FEMORAL_OFFSET,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(self._measurement_title_label("4: Points & Lines & Angles"), row_index, 0)
        row_index += 1
        workflow_layout.addWidget(
            self._counted_measurement_row_widget(
                self.other_point_button,
                MeasurementKey.OTHER_POINT,
                self.other_point_count_spin_box,
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._counted_measurement_row_widget(
                self.other_line_button,
                MeasurementKey.OTHER_LINE,
                self.other_line_count_spin_box,
                extra_widgets=[self.other_line_parallel_check, self.other_line_perpendicular_check],
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(
            self._counted_measurement_row_widget(
                self.other_angle_button,
                MeasurementKey.OTHER_ANGLE,
                self.other_angle_count_spin_box,
                extra_widgets=[self.other_angle_parallel_check, self.other_angle_perpendicular_check],
            ),
            row_index,
            0,
        )
        row_index += 1
        workflow_layout.addWidget(self._measurement_title_label("5: Contours"), row_index, 0)
        row_index += 1
        for contour_button, contour_key in [
            (self.iliopectineal_line_button, MeasurementKey.ILIOPECTINEAL_LINE),
            (self.ilioischial_line_button, MeasurementKey.ILIOISCHIAL_LINE),
            (self.shenton_line_button, MeasurementKey.SHENTON_LINE),
            (self.acetabular_roof_sourcil_button, MeasurementKey.ACETABULAR_ROOF_SOURCIL),
            (self.anterior_acetabular_wall_button, MeasurementKey.ANTERIOR_ACETABULAR_WALL),
            (self.posterior_acetabular_wall_button, MeasurementKey.POSTERIOR_ACETABULAR_WALL),
            (self.linea_terminalis_button, MeasurementKey.LINEA_TERMINALIS),
            (self.femoral_shaft_contour_button, MeasurementKey.FEMORAL_SHAFT_CONTOUR),
        ]:
            workflow_layout.addWidget(
                self._measurement_row_widget(contour_button, contour_key),
                row_index,
                0,
            )
            row_index += 1

    def _build_results_section(self) -> Any:
        """Create the results panel and all read-only measurement summary fields."""

        results_section = ctk.ctkCollapsibleButton()
        results_section.setText("Results")
        results_layout = qt.QGridLayout(results_section)
        self._initialize_results_fields()
        self._populate_results_layout(results_layout)
        return results_section

    def _initialize_results_fields(self) -> None:
        """Instantiate the result display fields used by the results panel."""

        self.calibration_value = self._read_only_field()
        self.reference_value = self._read_only_field()
        self.left_extrusion_index_value = self._read_only_field()
        self.right_extrusion_index_value = self._read_only_field()
        self.left_tonnis_angle_value = self._read_only_field()
        self.right_tonnis_angle_value = self._read_only_field()
        self.left_sharp_angle_value = self._read_only_field()
        self.right_sharp_angle_value = self._read_only_field()
        self.left_lce_angle_value = self._read_only_field()
        self.right_lce_angle_value = self._read_only_field()
        self.left_ccd_angle_value = self._read_only_field()
        self.right_ccd_angle_value = self._read_only_field()
        self.left_femur_head_value = self._read_only_field()
        self.right_femur_head_value = self._read_only_field()
        self.left_acetabular_offset_value = self._read_only_field()
        self.right_acetabular_offset_value = self._read_only_field()
        self.left_femoral_offset_value = self._read_only_field()
        self.right_femoral_offset_value = self._read_only_field()
        self.left_preop_global_offset_value = self._read_only_field()
        self.right_preop_global_offset_value = self._read_only_field()
        self.left_ccr_value = self._read_only_field()
        self.right_ccr_value = self._read_only_field()
        self.left_cti_value = self._read_only_field()
        self.right_cti_value = self._read_only_field()
        self.left_cfi_value = self._read_only_field()
        self.right_cfi_value = self._read_only_field()
        self.lld_value = self._read_only_field()
        self.left_inclination_angle_value = self._read_only_field()
        self.right_inclination_angle_value = self._read_only_field()
        self.left_cup_opening_ellipse_inclination_value = self._read_only_field()
        self.right_cup_opening_ellipse_inclination_value = self._read_only_field()
        self.left_cup_anteversion_retroversion_value = self._read_only_field()
        self.right_cup_anteversion_retroversion_value = self._read_only_field()
        self.left_implant_femoral_ccd_value = self._read_only_field()
        self.right_implant_femoral_ccd_value = self._read_only_field()
        self.left_implant_head_value = self._read_only_field()
        self.right_implant_head_value = self._read_only_field()
        self.left_postop_acetabular_offset_value = self._read_only_field()
        self.right_postop_acetabular_offset_value = self._read_only_field()
        self.left_postop_femoral_offset_value = self._read_only_field()
        self.right_postop_femoral_offset_value = self._read_only_field()
        self.left_postop_global_offset_value = self._read_only_field()
        self.right_postop_global_offset_value = self._read_only_field()
        self.left_implant_alignment_value = self._read_only_field()
        self.right_implant_alignment_value = self._read_only_field()
        self.ccr_result_label = qt.QLabel("CCR")
        self.cti_result_label = qt.QLabel("CTI")
        self.cfi_result_label = qt.QLabel("CFI")
        self._apply_morphology_ratio_tooltips()
        self.other_results_container = qt.QWidget()
        self.other_results_layout = qt.QGridLayout(self.other_results_container)
        self.other_results_layout.setContentsMargins(0, 0, 0, 0)
        self.other_results_layout.setSpacing(6)
        self.export_value = qt.QLabel("Not exported yet.")
        self.export_value.setWordWrap(True)
        self.export_value.setStyleSheet("QLabel { color: #35526f; padding: 2px 0; }")

    def _populate_results_layout(self, results_layout: Any) -> None:
        """Populate the results panel layout without altering any measurement formatting logic."""

        preop_left_header = qt.QLabel("R")
        preop_right_header = qt.QLabel("L")
        postop_left_header = qt.QLabel("R")
        postop_right_header = qt.QLabel("L")
        for header in [preop_left_header, preop_right_header, postop_left_header, postop_right_header]:
            header.setAlignment(qt.Qt.AlignCenter)

        results_layout.addWidget(self._measurement_title_label("1: Setup"), 0, 0, 1, 3)
        results_layout.addWidget(qt.QLabel("Calibration"), 1, 0)
        results_layout.addWidget(self.calibration_value, 1, 1, 1, 2)
        results_layout.addWidget(qt.QLabel("Reference"), 2, 0)
        results_layout.addWidget(self.reference_value, 2, 1, 1, 2)
        results_layout.addWidget(self._measurement_title_label("2: Pre-Operative"), 3, 0, 1, 3)
        results_layout.addWidget(preop_left_header, 4, 1)
        results_layout.addWidget(preop_right_header, 4, 2)
        results_layout.addWidget(qt.QLabel("Head Dia."), 5, 0)
        results_layout.addWidget(self.right_femur_head_value, 5, 1)
        results_layout.addWidget(self.left_femur_head_value, 5, 2)
        results_layout.addWidget(qt.QLabel("CCD Angle"), 6, 0)
        results_layout.addWidget(self.right_ccd_angle_value, 6, 1)
        results_layout.addWidget(self.left_ccd_angle_value, 6, 2)
        results_layout.addWidget(qt.QLabel("AI (Tönnis)"), 7, 0)
        results_layout.addWidget(self.right_tonnis_angle_value, 7, 1)
        results_layout.addWidget(self.left_tonnis_angle_value, 7, 2)
        results_layout.addWidget(qt.QLabel("Sharp"), 8, 0)
        results_layout.addWidget(self.right_sharp_angle_value, 8, 1)
        results_layout.addWidget(self.left_sharp_angle_value, 8, 2)
        results_layout.addWidget(qt.QLabel("LCE"), 9, 0)
        results_layout.addWidget(self.right_lce_angle_value, 9, 1)
        results_layout.addWidget(self.left_lce_angle_value, 9, 2)
        results_layout.addWidget(qt.QLabel("Acetab. Off."), 10, 0)
        results_layout.addWidget(self.right_acetabular_offset_value, 10, 1)
        results_layout.addWidget(self.left_acetabular_offset_value, 10, 2)
        results_layout.addWidget(qt.QLabel("Femoral Off."), 11, 0)
        results_layout.addWidget(self.right_femoral_offset_value, 11, 1)
        results_layout.addWidget(self.left_femoral_offset_value, 11, 2)
        results_layout.addWidget(qt.QLabel("Global Off."), 12, 0)
        results_layout.addWidget(self.right_preop_global_offset_value, 12, 1)
        results_layout.addWidget(self.left_preop_global_offset_value, 12, 2)
        results_layout.addWidget(qt.QLabel("Extr. Idx"), 13, 0)
        results_layout.addWidget(self.right_extrusion_index_value, 13, 1)
        results_layout.addWidget(self.left_extrusion_index_value, 13, 2)
        results_layout.addWidget(self.ccr_result_label, 14, 0)
        results_layout.addWidget(self.right_ccr_value, 14, 1)
        results_layout.addWidget(self.left_ccr_value, 14, 2)
        results_layout.addWidget(self.cti_result_label, 15, 0)
        results_layout.addWidget(self.right_cti_value, 15, 1)
        results_layout.addWidget(self.left_cti_value, 15, 2)
        results_layout.addWidget(self.cfi_result_label, 16, 0)
        results_layout.addWidget(self.right_cfi_value, 16, 1)
        results_layout.addWidget(self.left_cfi_value, 16, 2)
        results_layout.addWidget(qt.QLabel("LLD"), 17, 0)
        results_layout.addWidget(self.lld_value, 17, 1, 1, 2)
        results_layout.addWidget(self._measurement_title_label("3: Post-Operative (THA)"), 18, 0, 1, 3)
        results_layout.addWidget(postop_left_header, 19, 1)
        results_layout.addWidget(postop_right_header, 19, 2)
        results_layout.addWidget(qt.QLabel("Impl. Head Dia."), 20, 0)
        results_layout.addWidget(self.right_implant_head_value, 20, 1)
        results_layout.addWidget(self.left_implant_head_value, 20, 2)
        results_layout.addWidget(qt.QLabel("Inclination (FH)"), 21, 0)
        results_layout.addWidget(self.right_inclination_angle_value, 21, 1)
        results_layout.addWidget(self.left_inclination_angle_value, 21, 2)
        results_layout.addWidget(qt.QLabel("Inclination (E)"), 22, 0)
        results_layout.addWidget(self.right_cup_opening_ellipse_inclination_value, 22, 1)
        results_layout.addWidget(self.left_cup_opening_ellipse_inclination_value, 22, 2)
        results_layout.addWidget(qt.QLabel("Cup Ant/Ret An."), 23, 0)
        results_layout.addWidget(self.right_cup_anteversion_retroversion_value, 23, 1)
        results_layout.addWidget(self.left_cup_anteversion_retroversion_value, 23, 2)
        results_layout.addWidget(qt.QLabel("Impl. Fem. CCD"), 24, 0)
        results_layout.addWidget(self.right_implant_femoral_ccd_value, 24, 1)
        results_layout.addWidget(self.left_implant_femoral_ccd_value, 24, 2)
        results_layout.addWidget(qt.QLabel("Stem Align."), 25, 0)
        results_layout.addWidget(self.right_implant_alignment_value, 25, 1)
        results_layout.addWidget(self.left_implant_alignment_value, 25, 2)
        results_layout.addWidget(qt.QLabel("Acetab. Off."), 26, 0)
        results_layout.addWidget(self.right_postop_acetabular_offset_value, 26, 1)
        results_layout.addWidget(self.left_postop_acetabular_offset_value, 26, 2)
        results_layout.addWidget(qt.QLabel("Femoral Off."), 27, 0)
        results_layout.addWidget(self.right_postop_femoral_offset_value, 27, 1)
        results_layout.addWidget(self.left_postop_femoral_offset_value, 27, 2)
        results_layout.addWidget(qt.QLabel("Global Off."), 28, 0)
        results_layout.addWidget(self.right_postop_global_offset_value, 28, 1)
        results_layout.addWidget(self.left_postop_global_offset_value, 28, 2)
        results_layout.addWidget(self._measurement_title_label("4: Points & Lines & Angles"), 29, 0, 1, 3)
        results_layout.addWidget(self.other_results_container, 30, 0, 1, 3)
        results_layout.addWidget(self._subtle_note_label("su = scene units"), 31, 0, 1, 3)
        results_layout.setColumnStretch(1, 1)
        results_layout.setColumnStretch(2, 1)

    def _build_export_section(self) -> Any:
        """Create the export panel with status text, comments, and export actions."""

        export_section = ctk.ctkCollapsibleButton()
        export_section.setText("Export and Save")
        export_layout = qt.QGridLayout(export_section)
        export_layout.addWidget(qt.QLabel("Last Export"), 0, 0)
        export_layout.addWidget(self.export_value, 0, 1)
        self.comments_text_edit = qt.QPlainTextEdit()
        self.comments_text_edit.setPlaceholderText("Optional case comments exported into the CSV metadata.")
        self.comments_text_edit.setMaximumHeight(72)
        self.comments_text_edit.textChanged.connect(self.on_comments_changed)
        export_layout.addWidget(qt.QLabel("Comments"), 1, 0)
        export_layout.addWidget(self.comments_text_edit, 1, 1)
        self.export_curve_points_txt_check = qt.QCheckBox("Export Curve Points as TXT")
        self.export_curve_points_txt_check.setToolTip(
            "Include sampled curve points in a companion TXT file. "
            "The CSV contains the placed control points."
        )
        self.export_curve_points_txt_check.connect(
            TOGGLED_BOOL_SIGNAL, self.on_export_curve_points_txt_toggled
        )
        export_layout.addWidget(self.display_measurements_check, 2, 0, 1, 2)
        export_layout.addWidget(self.export_curve_points_txt_check, 3, 0, 1, 2)
        export_layout.addWidget(self.save_all_button, 4, 0)
        export_layout.addWidget(self.save_all_and_next_button, 4, 1)
        export_layout.addWidget(self.export_csv_button, 5, 0)
        export_layout.addWidget(self.save_scene_button, 5, 1)
        export_layout.addWidget(self.export_image_button, 6, 0)
        export_layout.setColumnStretch(0, 1)
        export_layout.setColumnStretch(1, 1)
        return export_section

    def _set_default_extension_layout(self) -> None:
        """Switch the module to Slicer's built-in Red slice full-screen layout when possible."""

        layout_manager = slicer.app.layoutManager() if hasattr(slicer, "app") else None
        if layout_manager is None:
            return
        layout_manager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    def _restore_standard_application_layout(self) -> None:
        """Return Slicer to its default 4-up layout outside the extension."""

        layout_manager = slicer.app.layoutManager() if hasattr(slicer, "app") else None
        if layout_manager is None:
            return
        layout_manager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

    def on_application_about_to_quit(self) -> None:
        """Reset the persisted layout before Slicer writes its shutdown state."""

        self._restore_standard_application_layout()

    def _load_saved_scene(self, saved_scene_path: Path) -> None:
        """Load one saved MRB scene using the same direct workflow as the working patella module."""

        try:
            load_result = slicer.util.loadScene(str(saved_scene_path))
        except Exception as error:
            slicer.mrmlScene.Clear(0)
            raise RuntimeError(f"Could not load saved annotations from {saved_scene_path}: {error}") from error

        if load_result is False:
            slicer.mrmlScene.Clear(0)
            raise RuntimeError(f"Could not load saved annotations from {saved_scene_path}")

    def _read_only_field(self) -> Any:
        """Create a compact read-only line edit for result display. A shared factory keeps the results
        panel visually consistent and avoids repetitive widget configuration.
        """

        field = qt.QLineEdit()
        field.setReadOnly(True)
        field.setStyleSheet("QLineEdit { padding: 2px 4px; }")
        return field

    def _morphology_reference_tooltip(self) -> Any:
        """Build the rich tooltip used for CCR, CTI, and CFI. Bundling the supplied schematic in module
        resources keeps the explanatory hover text portable with the open-source extension.
        """

        if hasattr(qt, "QUrl"):
            image_url = qt.QUrl.fromLocalFile(MORPHOLOGY_REFERENCE_IMAGE_PATH).toString()
        else:
            image_url = Path(MORPHOLOGY_REFERENCE_IMAGE_PATH).resolve().as_uri()
        image_width = 1000
        desktop = qt.QApplication.desktop()
        if desktop is not None:
            available = desktop.availableGeometry(self.parent)
            image_width = max(320, min(1100, available.width() - 50,
                                       int(max(180, available.height() - 230) * 1.8)))
        image_html = (
            f'<img src="{image_url}" width="{image_width}"><br>'
            if os.path.exists(MORPHOLOGY_REFERENCE_IMAGE_PATH)
            else ""
        )
        return (
            "<html><body>"
            "<p>CCR = B/A: inner canal width at -10 cm / proximal guide-cap width. "
            "CTI = (outer - inner width) / outer width at -10 cm. "
            "CFI = canal width at +2 cm / width at -10 cm.</p>"
            f"{image_html}"
            f'<p style="white-space: normal; width: {image_width}px;">{MORPHOLOGY_REFERENCE_CITATION}</p>'
            "</body></html>"
        )

    def _apply_morphology_ratio_tooltips(self) -> None:
        """Attach the morphologic-parameter reference tooltip to the three morphology result labels.
        The same source image explains CCR, CTI, and CFI, so hovering on the names keeps value boxes
        uncluttered while preserving discoverability.
        """

        tooltip = self._morphology_reference_tooltip()
        for label in [
            self.ccr_result_label,
            self.cti_result_label,
            self.cfi_result_label,
            self.left_ccr_value, self.right_ccr_value,
            self.left_cti_value, self.right_cti_value,
            self.left_cfi_value, self.right_cfi_value,
        ]:
            label.setToolTip(tooltip)

    def _measurement_title_label(self, text: Any) -> Any:
        """Create a section title label used in measurement and result panels. Consistent section
        styling helps operators scan the module quickly during repeated workflows.
        """

        label = qt.QLabel(text)
        label.setStyleSheet("QLabel { font-weight: 600; margin-top: 6px; color: #35526f; }")
        return label

    def _subtle_note_label(self, text: Any) -> Any:
        """Create a low-emphasis note label for supporting text. Small explanatory notes are visually
        separated so they help without competing with measurements.
        """

        label = qt.QLabel(text)
        label.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
        label.setStyleSheet("QLabel { color: #5d7389; font-size: 11px; margin-top: 4px; }")
        return label

    def _measurement_row_widget(self, button: Any, measurement_key: Any, extra_widgets: Any=None) -> Any:
        """Build one measurement row with its button and visibility toggle. Packaging the row keeps the
        UI layout uniform across many tools.
        """

        checkbox = qt.QCheckBox("Hide")
        checkbox.setChecked(False)
        checkbox.setToolTip("Hide this measurement overlay on the image.")
        checkbox.connect(
            TOGGLED_BOOL_SIGNAL,
            lambda checked, key=measurement_key: self.on_measurement_visibility_toggled(key, checked),
        )
        self._register_measurement_visibility_check(measurement_key, checkbox)

        row_widget = qt.QWidget()
        row_layout = qt.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(button, 1)
        for extra_widget in extra_widgets or []:
            row_layout.addWidget(extra_widget, 0)
        row_layout.addWidget(checkbox, 0)
        return row_widget

    def _counted_measurement_row_widget(
        self,
        button: Any,
        measurement_key: Any,
        counter_widget: Any,
        extra_widgets: Any=None,
    ) -> Any:
        """Build a measurement row that also includes a repeat-count control and optional extra
        widgets. The composite widget keeps repeated tools aligned with the simpler single-instance
        tools.
        """

        checkbox = qt.QCheckBox("Hide")
        checkbox.setChecked(False)
        checkbox.setToolTip("Hide this measurement overlay on the image.")
        checkbox.connect(
            TOGGLED_BOOL_SIGNAL,
            lambda checked, key=measurement_key: self.on_measurement_visibility_toggled(key, checked),
        )
        self._register_measurement_visibility_check(measurement_key, checkbox)

        row_widget = qt.QWidget()
        row_layout = qt.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(counter_widget, 0)
        row_layout.addWidget(button, 1)
        for extra_widget in extra_widgets or []:
            row_layout.addWidget(extra_widget, 0)
        row_layout.addWidget(checkbox, 0)
        return row_widget

    def _register_measurement_visibility_check(self, measurement_key: Any, checkbox: Any) -> None:
        """Register one of possibly several visibility checkboxes for a measurement."""

        self.measurement_visibility_checks.setdefault(measurement_key, []).append(checkbox)

    def _active_side_badge_position(self, image_node: Any) -> Any:
        """Return an out-of-the-way default image position for the moveable active-side badge."""

        if image_node is None:
            return None
        image_data = image_node.GetImageData() if hasattr(image_node, "GetImageData") else None
        if image_data is not None and hasattr(image_data, "GetDimensions"):
            dimensions = image_data.GetDimensions()
            if dimensions and dimensions[0] > 1 and dimensions[1] > 1:
                ijk_to_ras = vtk.vtkMatrix4x4()
                image_node.GetIJKToRASMatrix(ijk_to_ras)
                ijk_point = [
                    max(1.0, 0.05 * float(dimensions[0] - 1)),
                    max(1.0, 0.06 * float(dimensions[1] - 1)),
                    0.5 * float(max(dimensions[2] - 1, 0)),
                    1.0,
                ]
                ras_point = [0.0, 0.0, 0.0, 1.0]
                ijk_to_ras.MultiplyPoint(ijk_point, ras_point)
                return tuple(float(value) for value in ras_point[:3])

        bounds = [0.0] * 6
        image_node.GetRASBounds(bounds)
        return (
            bounds[0] + 0.06 * (bounds[1] - bounds[0]),
            bounds[3] - 0.06 * (bounds[3] - bounds[2]),
            0.5 * (bounds[4] + bounds[5]),
        )

    def _set_or_add_single_badge_point(self, node: Any, position: Any) -> None:
        """Ensure the active-side badge has one moveable control point."""

        if node is None or position is None:
            return
        while node.GetNumberOfControlPoints() > 1:
            node.RemoveNthControlPoint(node.GetNumberOfControlPoints() - 1)
        if node.GetNumberOfControlPoints() == 0:
            if hasattr(node, "AddControlPointWorld"):
                try:
                    node.AddControlPointWorld(vtk.vtkVector3d(*position))
                except TypeError:
                    node.AddControlPointWorld(float(position[0]), float(position[1]), float(position[2]))
            else:
                try:
                    node.AddControlPoint(vtk.vtkVector3d(*position))
                except TypeError:
                    node.AddControlPoint(float(position[0]), float(position[1]), float(position[2]))

    def _set_active_side_badge_color(self, node: Any, color: Any) -> None:
        """Apply the active-side color to the badge glyph and its large text label."""

        if node is None:
            return
        display_node = node.GetDisplayNode()
        if display_node is None:
            return
        display_node.SetColor(*color)
        if hasattr(display_node, "SetSelectedColor"):
            display_node.SetSelectedColor(*color)
        if hasattr(display_node, "SetVisibility"):
            display_node.SetVisibility(True)
        if hasattr(display_node, "SetPointLabelsVisibility"):
            display_node.SetPointLabelsVisibility(True)
        if hasattr(display_node, "SetTextScale"):
            display_node.SetTextScale(4.0)
        if hasattr(display_node, "SetGlyphScale"):
            display_node.SetGlyphScale(0.8)
        self._disable_active_side_badge_text_shadow(display_node, color)

    def _disable_active_side_badge_text_shadow(self, display_node: Any, color: Any) -> None:
        """Remove text shadow/halo styling from the active-side badge when the API exposes it."""

        for method_name in (
            "SetTextShadow",
            "SetUseTextShadow",
            "SetLabelShadow",
            "SetUseLabelShadow",
            "SetPointLabelsShadow",
            "SetUsePointLabelsShadow",
        ):
            if not hasattr(display_node, method_name):
                continue
            try:
                getattr(display_node, method_name)(False)
            except TypeError:
                continue

        text_properties = []
        for getter_name in (
            "GetTextProperty",
            "GetLabelTextProperty",
            "GetPointLabelsTextProperty",
        ):
            if not hasattr(display_node, getter_name):
                continue
            try:
                text_property = getattr(display_node, getter_name)()
            except TypeError:
                continue
            if text_property is not None:
                text_properties.append(text_property)

        for text_property in text_properties:
            if hasattr(text_property, "SetColor"):
                text_property.SetColor(*color)
            if hasattr(text_property, "ShadowOff"):
                text_property.ShadowOff()
            elif hasattr(text_property, "SetShadow"):
                text_property.SetShadow(False)
            if hasattr(text_property, "SetShadowOffset"):
                try:
                    text_property.SetShadowOffset(0, 0)
                except TypeError:
                    text_property.SetShadowOffset([0, 0])
            if hasattr(text_property, "SetShadowColor"):
                text_property.SetShadowColor(*color)
            if hasattr(text_property, "SetBackgroundOpacity"):
                text_property.SetBackgroundOpacity(0.0)
            if hasattr(text_property, "SetFrame"):
                text_property.SetFrame(False)

    def _sync_active_side_badge(self) -> None:
        """Refresh the single moveable on-image active-side reminder."""

        if self.logic is None:
            return
        image_node = self.current_image_node()
        node = self.logic.get_node(ACTIVE_SIDE_BADGE_ROLE, create_if_missing=True)
        side_key = self.current_side_key()
        side_label = SIDE_LABELS[side_key]
        color_by_side = {
            SideKey.LEFT: (0.10, 0.42, 0.90),
            SideKey.RIGHT: (0.95, 0.45, 0.05),
        }
        self._set_or_add_single_badge_point(node, self._active_side_badge_position(image_node))
        if node.GetNumberOfControlPoints() > 0:
            node.SetNthControlPointLabel(0, f"ACTIVE SIDE: {side_label.upper()}")
        node.SetDisplayVisibility(image_node is not None)
        node.SetLocked(False)
        self._set_active_side_badge_color(node, color_by_side[side_key])
        if hasattr(slicer.util, "forceRenderAllViews"):
            slicer.util.forceRenderAllViews()

    def _set_active_side_badge_display_visibility(self, visible: Any) -> Any:
        """Set badge visibility and return the previous state for temporary export hiding."""

        if self.logic is None:
            return None
        node = self.logic.get_node(ACTIVE_SIDE_BADGE_ROLE, create_if_missing=False)
        if node is None:
            return None
        display_node = node.GetDisplayNode() if hasattr(node, "GetDisplayNode") else None

        def _refresh_views() -> None:
            if hasattr(slicer.util, "forceRenderAllViews"):
                slicer.util.forceRenderAllViews()
            if hasattr(slicer.app, "processEvents"):
                slicer.app.processEvents()

        def _display_state() -> dict[str, bool]:
            if display_node is None:
                return {}
            state = {}
            for name in (
                "Visibility",
                "Visibility2D",
                "Visibility3D",
                "PointLabelsVisibility",
            ):
                getter = getattr(display_node, f"Get{name}", None)
                if getter is not None:
                    state[name] = bool(getter())
            return state

        def _restore_display_state(state: dict[str, bool]) -> None:
            if display_node is None:
                return
            for name, value in state.items():
                setter = getattr(display_node, f"Set{name}", None)
                if setter is not None:
                    setter(bool(value))

        if isinstance(visible, dict):
            node.SetDisplayVisibility(bool(visible.get("nodeDisplayVisibility", False)))
            _restore_display_state(visible.get("displayNodeVisibility", {}))
            _refresh_views()
            return visible

        previous_state = {
            "nodeDisplayVisibility": bool(node.GetDisplayVisibility()),
            "displayNodeVisibility": _display_state(),
        }
        target_visible = bool(visible)
        node.SetDisplayVisibility(target_visible)
        if display_node is not None:
            if hasattr(display_node, "SetVisibility"):
                display_node.SetVisibility(target_visible)
            if hasattr(display_node, "SetVisibility2D"):
                display_node.SetVisibility2D(target_visible)
            if hasattr(display_node, "SetVisibility3D"):
                display_node.SetVisibility3D(False)
            if not target_visible and hasattr(display_node, "SetPointLabelsVisibility"):
                display_node.SetPointLabelsVisibility(False)
            elif target_visible and hasattr(display_node, "SetPointLabelsVisibility"):
                display_node.SetPointLabelsVisibility(True)
        _refresh_views()
        return previous_state

    def _clear_layout(self, layout: Any) -> None:
        """Remove every child widget from a layout. Dynamic result sections use this helper so repeated
        measurements can be rebuilt cleanly without stale rows.
        """

        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child_widget = item.widget()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if child_widget is not None:
                child_widget.deleteLater()

    def _refresh_other_results_rows(self, results: Any) -> None:
        """Rebuild the dynamic result rows for user-added lines and angles. The rows are generated from
        current results so the UI scales naturally as custom measurements are added or removed.
        """

        self._clear_layout(self.other_results_layout)
        row_index = 0

        for measurement in results.get("otherPoints", []):
            label = qt.QLabel(f"Point {measurement['index']}")
            value = self._read_only_field()
            point = measurement.get("point")
            if measurement.get("defined") and point is not None:
                value.setText(f"({float(point[0]):.1f}, {float(point[1]):.1f}, {float(point[2]):.1f})")
            else:
                value.setText("Not defined")
            self.other_results_layout.addWidget(label, row_index, 0)
            self.other_results_layout.addWidget(value, row_index, 1, 1, 2)
            row_index += 1

        for measurement in results["otherLines"]:
            label_text = f"Line {measurement['index']}"
            lock_mode = measurement.get("lockMode")
            if lock_mode == OtherAngleLockMode.PARALLEL:
                label_text += " (Ref ||)"
            elif lock_mode == OtherAngleLockMode.PERPENDICULAR:
                label_text += " (Ref _|_)"
            label = qt.QLabel(label_text)
            value = self._read_only_field()
            value.setText(
                format_compact_length(measurement, self.logic.calibration_ball_present)
            )
            self.other_results_layout.addWidget(label, row_index, 0)
            self.other_results_layout.addWidget(value, row_index, 1, 1, 2)
            row_index += 1

        for measurement in results["otherAngles"]:
            label_text = f"Angle {measurement['index']}"
            lock_mode = measurement.get("lockMode")
            if lock_mode == OtherAngleLockMode.PARALLEL:
                label_text += " (Ref ||)"
            elif lock_mode == OtherAngleLockMode.PERPENDICULAR:
                label_text += " (Ref _|_)"
            label = qt.QLabel(label_text)
            value = self._read_only_field()
            value.setText(format_compact_angle(measurement))
            self.other_results_layout.addWidget(label, row_index, 0)
            self.other_results_layout.addWidget(value, row_index, 1, 1, 2)
            row_index += 1

        if row_index == 0:
            empty_label = qt.QLabel("No custom measurements.")
            empty_label.setStyleSheet("QLabel { color: #5d7389; }")
            self.other_results_layout.addWidget(empty_label, 0, 0, 1, 3)
        self.other_results_layout.setColumnStretch(1, 1)
        self.other_results_layout.setColumnStretch(2, 1)

    def _custom_measurement_can_add(self, measurement_key: Any, results: Any=None) -> Any:
        """Check whether another user-added point, line, or angle may be created. The guard prevents users from
        stacking multiple unfinished ad hoc tools, which would make scene state ambiguous.
        """

        results = results if results is not None else self.logic.latest_results
        if measurement_key == MeasurementKey.OTHER_POINT:
            measurements = results.get("otherPoints", [])
        elif measurement_key == MeasurementKey.OTHER_LINE:
            measurements = results.get("otherLines", [])
        elif measurement_key == MeasurementKey.OTHER_ANGLE:
            measurements = results.get("otherAngles", [])
        else:
            return True
        if not measurements:
            return True
        return bool(measurements[-1].get("defined"))

    def _sync_other_measurement_limits(self, results: Any) -> None:
        """Synchronize counter limits for user-added points, lines, and angles with actual scene state. The
        counters are constrained from the scene so the UI cannot drift away from what really exists.
        """

        point_count = self.logic.other_point_count()
        point_max = point_count + (1 if self._custom_measurement_can_add(MeasurementKey.OTHER_POINT, results) else 0)
        self.other_point_count_spin_box.blockSignals(True)
        self.other_point_count_spin_box.setRange(0, max(point_count, point_max))
        self.other_point_count_spin_box.setValue(point_count)
        self.other_point_count_spin_box.blockSignals(False)

        line_count = self.logic.other_line_count()
        line_max = line_count + (1 if self._custom_measurement_can_add(MeasurementKey.OTHER_LINE, results) else 0)
        self.other_line_count_spin_box.blockSignals(True)
        self.other_line_count_spin_box.setRange(0, max(line_count, line_max))
        self.other_line_count_spin_box.setValue(line_count)
        self.other_line_count_spin_box.blockSignals(False)

        angle_count = self.logic.other_angle_count()
        angle_max = angle_count + (1 if self._custom_measurement_can_add(MeasurementKey.OTHER_ANGLE, results) else 0)
        self.other_angle_count_spin_box.blockSignals(True)
        self.other_angle_count_spin_box.setRange(0, max(angle_count, angle_max))
        self.other_angle_count_spin_box.setValue(angle_count)
        self.other_angle_count_spin_box.blockSignals(False)

    def _measurement_button_style(self, state: Any) -> Any:
        """Return the stylesheet for one measurement button state. Button color communicates idle,
        active, and completed states without adding extra labels or status widgets.
        """

        styles = {
            "idle": (
                "QPushButton { background: #f6f8fa; border: 1px solid #d6dde5; "
                "border-radius: 6px; padding: 6px 10px; } "
                "QPushButton:disabled { background: #f3f5f7; color: #99a6b3; border: 1px solid #e2e7ec; }"
            ),
            "active": (
                "QPushButton { background: #e2efff; border: 1px solid #6f9ee8; "
                "border-radius: 6px; padding: 6px 10px; font-weight: 600; } "
                "QPushButton:disabled { background: #eef3f9; color: #9aa6b1; border: 1px solid #dbe3eb; }"
            ),
            "applied": (
                "QPushButton { background: #edf8f0; border: 1px solid #76b486; "
                "border-radius: 6px; padding: 6px 10px; } "
                "QPushButton:disabled { background: #eef5ef; color: #9aa6b1; border: 1px solid #dbe3de; }"
            ),
            "activeApplied": (
                "QPushButton { background: #dcf4ea; border: 1px solid #4d9b7b; "
                "border-radius: 6px; padding: 6px 10px; font-weight: 700; } "
                "QPushButton:disabled { background: #e9f2ed; color: #9aa6b1; border: 1px solid #d6e2db; }"
            ),
        }
        return styles.get(state, styles["idle"])

    def _measurement_overlay_text(
        self,
        results: Any=None,
        entries_per_line: Any=None,
        include_measurements: Any=True,
    ) -> Any:
        """Assemble exported overlay text from annotator metadata and optional measurements.

        The annotator must be present on every exported image, while measurement values remain
        user-toggleable. Building both concerns here keeps image-export formatting centralized.
        """

        results = results if results is not None else self.logic.latest_results
        return build_measurement_overlay_text(
            results=results,
            annotator_text=self._annotator_overlay_text(),
            entries_per_line=entries_per_line,
            include_measurements=include_measurements,
        )

    def _choose_conflict_policy(self, action_name: Any, output_paths: Any) -> Any:
        """Ask the user whether existing export files should be replaced or versioned. Centralizing the
        prompt ensures the same overwrite rules are used for CSV, scene, and image export.
        """

        existing_paths = [path for path in output_paths if self.logic.path_exists(path)]
        if not existing_paths:
            return "replace"

        message_box = qt.QMessageBox(slicer.util.mainWindow())
        message_box.setIcon(qt.QMessageBox.Question)
        message_box.setWindowTitle("Existing File Detected")
        message_box.setText(f"{action_name}: one or more output files already exist.")
        message_box.setInformativeText(
            "Choose Replace to overwrite the existing file(s), or Save New Version to create new numbered files.\n\n"
            + "\n".join(os.path.basename(path) for path in existing_paths)
        )
        replace_button = message_box.addButton("Replace", qt.QMessageBox.AcceptRole)
        save_new_button = message_box.addButton("Save New Version", qt.QMessageBox.ActionRole)
        cancel_button = message_box.addButton("Cancel", qt.QMessageBox.RejectRole)
        message_box.exec_()

        clicked_button = message_box.clickedButton()
        if clicked_button == replace_button:
            return "replace"
        if clicked_button == save_new_button:
            return "version"
        if clicked_button == cancel_button:
            return None
        return None

    def _sync_ball_controls(self) -> None:
        """Synchronize the calibration-diameter controls with current calibration mode. The UI makes a
        clear distinction between calibrated millimetres and scene-unit-only workflows.
        """

        self.ball_diameter_spin_box.blockSignals(True)
        self.ball_diameter_spin_box.setValue(self.logic.calibration_ball_diameter_mm)
        self.ball_diameter_spin_box.setEnabled(self.logic.calibration_ball_present)
        self.ball_diameter_spin_box.blockSignals(False)
        self.ball_not_present_check.blockSignals(True)
        self.ball_not_present_check.setChecked(not self.logic.calibration_ball_present)
        self.ball_not_present_check.blockSignals(False)
        self.display_measurements_check.blockSignals(True)
        self.display_measurements_check.setChecked(self.display_measurements_on_image)
        self.display_measurements_check.blockSignals(False)
        if hasattr(self, "export_curve_points_txt_check"):
            self.export_curve_points_txt_check.blockSignals(True)
            self.export_curve_points_txt_check.setChecked(self.export_curve_points_as_txt)
            self.export_curve_points_txt_check.blockSignals(False)

    def _axis_option_nodes(self, measurement_key: Any, side_key: Any) -> Any:
        """Return the relevant guide and center keys for one neck-axis tool and side.

        The inline controls need to know both whether center-lock is allowed and whether the current
        measurement has already started, because options become fixed after the first placed point.
        """

        if measurement_key == MeasurementKey.IMPLANT_NECK_AXIS:
            return {
                "guideRole": self.logic.side_role("implantNeckGuideProximal", side_key),
                "centerResultKey": "implantHead",
                "centerLabel": "Implant Head Center",
            }
        return {
            "guideRole": self.logic.side_role("neckGuideProximal", side_key),
            "centerResultKey": "femurHead",
            "centerLabel": "Femur Head",
        }

    def _defined_point_count(self, node: Any) -> Any:
        """Return how many control points on a markup are currently defined.

        The lock timing for the neck-axis options is tied to the first placed point, so this helper
        gives the widget a small scene-truth query without reaching into calculation internals.
        """

        if node is None:
            return 0
        if hasattr(node, "GetNumberOfDefinedControlPoints"):
            return int(node.GetNumberOfDefinedControlPoints())
        return 0

    def _axis_options_locked(self, measurement_key: Any, side_key: Any) -> Any:
        """Report whether the current neck-axis mode selection should be frozen.

        Once the first proximal-guide point exists, mode changes would alter the meaning of an
        in-progress or completed measurement. The options therefore stay fixed until the tool is
        restarted, which clears its annotations first.
        """

        context = self._axis_option_nodes(measurement_key, side_key)
        guide_node = self.logic.get_node(context["guideRole"])
        return self._defined_point_count(guide_node) > 0

    def _sync_neck_axis_option_controls(self) -> None:
        """Synchronize the inline neck-axis option controls from scene state.

        The controls remain side-specific, but they are only editable before the current tool's
        first proximal-guide point is placed. Center-lock also stays unavailable until the
        prerequisite head center exists.
        """

        side_key = self.current_side_key()
        locked_tooltip = (
            "Restart this tool to reset its points and change the mode."
        )
        editable_tooltip = (
            "Choose before the first point; restart the tool to change it."
        )

        for measurement_key, center_check, single_guide_check in [
            (
                MeasurementKey.NECK_AXIS,
                self.neck_axis_lock_to_center_check,
                self.neck_axis_use_single_guide_check,
            ),
            (
                MeasurementKey.IMPLANT_NECK_AXIS,
                self.implant_neck_axis_lock_to_center_check,
                self.implant_neck_axis_use_single_guide_check,
            ),
        ]:
            context = self._axis_option_nodes(measurement_key, side_key)
            center_available = bool(self.logic.latest_results["sides"][side_key][context["centerResultKey"]]["defined"])
            options_locked = self._axis_options_locked(measurement_key, side_key)
            current_lock_to_center = bool(
                self.logic.axis_lock_to_center_enabled(measurement_key, side_key)
            )
            current_use_single_guide = bool(
                self.logic.axis_use_single_guide_enabled(measurement_key, side_key)
            )

            if not center_available and not options_locked and current_lock_to_center:
                current_lock_to_center = False
                self.logic.set_axis_lock_to_center_enabled(measurement_key, side_key, False)

            center_check.blockSignals(True)
            center_check.setChecked(current_lock_to_center)
            center_check.setEnabled(center_available and not options_locked)
            center_check.blockSignals(False)

            single_guide_check.blockSignals(True)
            single_guide_check.setChecked(current_use_single_guide)
            single_guide_check.setEnabled(not options_locked)
            single_guide_check.blockSignals(False)

            if options_locked:
                center_check.setToolTip(locked_tooltip)
                single_guide_check.setToolTip(locked_tooltip)
            else:
                single_guide_check.setToolTip(editable_tooltip)
                if center_available:
                    center_check.setToolTip(
                        f"Force the derived axis through the fitted center for the active side. {editable_tooltip}"
                    )
                else:
                    center_check.setToolTip(
                        f'Define "{context["centerLabel"]}" for the active side before enabling this option.'
                    )

    def _annotator_text(self) -> Any:
        """Return the trimmed annotator text currently shown in the UI.

        The widget owns the session-visible field, so export and persistence checks read through one
        helper instead of reaching into the line edit in multiple places.
        """

        text_value = self.annotator_line_edit.text
        if callable(text_value):
            text_value = text_value()
        return str(text_value or "").strip()

    def _sync_annotator_control(self) -> None:
        """Synchronize the annotator line edit from logic state after scene recreation.

        The logic object is rebuilt on scene close, but the widget stays alive. Reapplying the
        session annotator here keeps the new logic instance aligned without clearing the visible
        field.
        """

        annotator_name = self.logic.annotator_name if self.logic is not None else ""
        if self._annotator_text() == annotator_name:
            return
        self.annotator_line_edit.blockSignals(True)
        self.annotator_line_edit.setText(annotator_name)
        self.annotator_line_edit.blockSignals(False)

    def _restore_directory_preferences(self) -> None:
        """Restore session-only path-selector values without forcing an immediate case load."""

        self.last_directory_path = str(SESSION_DIRECTORY_STATE["lastDirectoryPath"] or "").strip()
        self.last_export_directory_path = str(SESSION_DIRECTORY_STATE["lastExportDirectoryPath"] or "").strip()
        self.input_folder_path = str(SESSION_DIRECTORY_STATE["inputFolderPath"] or "").strip()
        self.output_folder_path = str(SESSION_DIRECTORY_STATE["outputFolderPath"] or "").strip()
        self._refresh_input_folder_images()
        self._sync_directory_controls()

    def _sync_directory_controls(self) -> None:
        """Reflect remembered folder paths and navigation availability in the UI."""

        self.input_folder_line_edit.setText(self.input_folder_path)
        self.output_folder_line_edit.setText(self.output_folder_path)
        self.input_folder_clear_button.setEnabled(bool(self.input_folder_path))
        self.output_folder_clear_button.setEnabled(bool(self.output_folder_path))
        self._sync_image_selector_contents()
        self._sync_image_navigation_controls()

    def _directory_dialog_start_path(self, preferred_path: Any="") -> str:
        """Return the best available starting folder for a directory chooser."""

        candidates = [
            str(preferred_path or "").strip(),
            self.output_folder_path,
            self.input_folder_path,
            self.last_directory_path,
            qt.QDir.homePath(),
        ]
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                return candidate
        return qt.QDir.homePath()

    def _remember_directory_path(self, directory_path: Any) -> None:
        """Store the most recent directory used by any chooser for the current Slicer session."""

        normalized_path = str(directory_path or "").strip()
        if not normalized_path:
            return
        self.last_directory_path = normalized_path
        SESSION_DIRECTORY_STATE["lastDirectoryPath"] = normalized_path

    def _remember_export_directory_path(self, directory_path: Any) -> None:
        """Store the most recent export destination for the current Slicer session."""

        normalized_path = str(directory_path or "").strip()
        if not normalized_path:
            return
        self.last_export_directory_path = normalized_path
        SESSION_DIRECTORY_STATE["lastExportDirectoryPath"] = normalized_path
        self._remember_directory_path(normalized_path)

    def _set_input_folder_path(self, directory_path: Any) -> None:
        """Store the current input folder selection for the current Slicer session only."""

        normalized_path = str(directory_path or "").strip()
        self.input_folder_path = normalized_path
        SESSION_DIRECTORY_STATE["inputFolderPath"] = normalized_path
        if normalized_path:
            self._remember_directory_path(normalized_path)
        self._sync_directory_controls()

    def _set_output_folder_path(self, directory_path: Any) -> None:
        """Store the current output folder selection for the current Slicer session only."""

        normalized_path = str(directory_path or "").strip()
        self.output_folder_path = normalized_path
        SESSION_DIRECTORY_STATE["outputFolderPath"] = normalized_path
        if normalized_path:
            self._remember_export_directory_path(normalized_path)
        self._sync_directory_controls()

    def _export_directory_dialog_start_path(self) -> str:
        """Return the best available starting folder specifically for export actions."""

        candidates = [
            self.output_folder_path,
            self.last_export_directory_path,
            self.last_directory_path,
            self.input_folder_path,
            qt.QDir.homePath(),
        ]
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                return candidate
        return qt.QDir.homePath()

    def _refresh_input_folder_images(self) -> None:
        """Reload the current input-folder image list from disk."""

        previous_path = self.current_folder_image_path
        self.folder_image_paths = list_input_images(self.input_folder_path) if self.input_folder_path else []
        if previous_path is not None and previous_path in self.folder_image_paths:
            self.current_folder_image_index = self.folder_image_paths.index(previous_path)
        else:
            self.current_folder_image_index = -1
            self.current_folder_image_path = None

    def _scene_image_nodes(self) -> list[Any]:
        """Return the scalar-volume nodes currently available in the active MRML scene."""

        return list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode") or [])

    def _scene_image_node_for_path(self, image_path: Path | None=None) -> Any:
        """Return the scene image node that best matches one folder-managed image path."""

        scene_nodes = self._scene_image_nodes()
        if not scene_nodes:
            return None
        if image_path is None:
            return scene_nodes[0]

        expected_names = {
            image_path.name,
            Path(image_path.name).stem,
        }
        for scene_node in scene_nodes:
            node_name = str(scene_node.GetName() or "")
            if node_name in expected_names or Path(node_name).stem in expected_names:
                return scene_node
        return scene_nodes[0]

    def _node_belongs_to_scene(self, node: Any) -> bool:
        """Report whether a cached image node still belongs to the active MRML scene."""

        return bool(
            node is not None
            and hasattr(node, "GetScene")
            and node.GetScene() == slicer.mrmlScene
            and hasattr(node, "GetID")
            and node.GetID()
        )

    def _set_current_image_node(self, node: Any) -> Any:
        """Cache the currently active image node for measurement and export actions."""

        self.loaded_image_node = node if self._node_belongs_to_scene(node) else None
        return self.loaded_image_node

    def _sync_current_image_node(self, preferred_node: Any=None) -> Any:
        """Ensure one current scalar-volume node stays associated with the active case."""

        if self._node_belongs_to_scene(preferred_node):
            return self._set_current_image_node(preferred_node)
        if self._node_belongs_to_scene(self.loaded_image_node):
            return self.loaded_image_node
        default_node = self.logic.guess_default_image_node() if self.logic is not None else None
        return self._set_current_image_node(default_node)

    def _image_selector_state_signature(self) -> tuple[Any, ...]:
        """Describe the current selector contents so redundant UI rebuilds can be skipped."""

        if self.input_folder_path:
            return (
                "folder",
                tuple(path.name for path in self.folder_image_paths),
                self.current_folder_image_index,
            )
        scene_nodes = self._scene_image_nodes()
        current_node = self._sync_current_image_node()
        return (
            "scene",
            tuple((node.GetID(), node.GetName()) for node in scene_nodes),
            current_node.GetID() if current_node is not None else "",
        )

    def _sync_image_selector_contents(self) -> None:
        """Keep the visible image dropdown aligned with folder navigation or scene image state."""

        state_signature = self._image_selector_state_signature()
        if state_signature == self.image_selector_signature:
            return

        self.image_selector_signature = state_signature
        self.image_selector_sync_in_progress = True
        try:
            self.image_selector.clear()
            if self.input_folder_path:
                if self.folder_image_paths:
                    for image_index, image_path in enumerate(self.folder_image_paths):
                        self.image_selector.addItem(image_path.name, image_index)
                    current_index = (
                        self.current_folder_image_index
                        if 0 <= self.current_folder_image_index < len(self.folder_image_paths)
                        else 0
                    )
                    self.image_selector.setCurrentIndex(current_index)
                    self.image_selector.setEnabled(True)
                else:
                    self.image_selector.addItem("No images in folder", "")
                    self.image_selector.setCurrentIndex(0)
                    self.image_selector.setEnabled(False)
                return

            scene_nodes = self._scene_image_nodes()
            current_node = self._sync_current_image_node()
            if scene_nodes:
                current_node_id = current_node.GetID() if current_node is not None else ""
                selected_index = 0
                for image_index, image_node in enumerate(scene_nodes):
                    node_id = image_node.GetID()
                    self.image_selector.addItem(image_node.GetName(), node_id)
                    if node_id == current_node_id:
                        selected_index = image_index
                self.image_selector.setCurrentIndex(selected_index)
                self.image_selector.setEnabled(True)
            else:
                self.image_selector.addItem("No image loaded", "")
                self.image_selector.setCurrentIndex(0)
                self.image_selector.setEnabled(False)
        finally:
            self.image_selector_sync_in_progress = False

    def _sync_image_navigation_controls(self) -> None:
        """Update previous/next navigation affordances for the folder-driven image workflow."""

        total_images = len(self.folder_image_paths)
        has_folder_navigation = total_images > 0 and self.current_folder_image_index >= 0
        self.previous_image_button.setEnabled(has_folder_navigation and self.current_folder_image_index > 0)
        self.next_image_button.setEnabled(
            has_folder_navigation and self.current_folder_image_index < (total_images - 1)
        )
        if has_folder_navigation:
            self.image_position_label.setText(f"{self.current_folder_image_index + 1}/{total_images}")
        elif self.input_folder_path and total_images > 0:
            self.image_position_label.setText(f"0/{total_images}")
        elif self.input_folder_path:
            self.image_position_label.setText("0/0")
        else:
            self.image_position_label.setText("Manual")

    def _sync_folder_image_index_from_current_node(self, preferred_path: Path | None=None) -> None:
        """Align the folder-navigation index with the currently loaded image node."""

        if preferred_path is not None and preferred_path in self.folder_image_paths:
            self.current_folder_image_path = preferred_path
            self.current_folder_image_index = self.folder_image_paths.index(preferred_path)
            return
        current_node = self.current_image_node()
        current_name = current_node.GetName() if current_node is not None else ""
        for image_index, image_path in enumerate(self.folder_image_paths):
            if image_path.name == current_name:
                self.current_folder_image_path = image_path
                self.current_folder_image_index = image_index
                return
        self.current_folder_image_index = -1
        self.current_folder_image_path = None

    def _comments_text(self) -> str:
        """Return the trimmed case comments shown in the export section."""

        return str(self.comments_text_edit.toPlainText() or "").strip()

    def _sync_comments_control(self) -> None:
        """Synchronize the visible comments field from the currently loaded scene metadata."""

        if self.logic is None:
            return
        comments_text = self.logic.case_comments()
        if self._comments_text() == comments_text:
            return
        self.comments_text_edit.blockSignals(True)
        self.comments_text_edit.setPlainText(comments_text)
        self.comments_text_edit.blockSignals(False)

    def _restore_saved_case_comments(self, saved_comments: Any) -> None:
        """Restore CSV comments only when the loaded MRB scene does not already carry comments."""

        if self.logic is None:
            return
        comments_in_scene = self.logic.case_comments()
        comments_from_csv = str(saved_comments or "").strip()
        if comments_in_scene or not comments_from_csv:
            return
        self.logic.set_case_comments(comments_from_csv)

    def _set_case_dirty(self, dirty: Any=True) -> None:
        """Track whether the current case has unsaved scene-level changes."""

        if self.suspend_dirty_tracking:
            return
        self.case_has_unsaved_changes = bool(dirty)

    def _mark_case_saved(self) -> None:
        """Mark the current case as saved after an MRB-producing action succeeds."""

        self.case_has_unsaved_changes = False

    def _save_all_case(
        self,
        parent_directory: Any,
        image_node: Any=None,
        conflict_policy: Any="version",
    ) -> Any:
        """Save the MRB, export the CSV, and export the annotated image in one action."""

        save_info = self.logic.save_case(
            parent_directory,
            image_node,
            conflict_policy,
            export_curve_points_txt=self.export_curve_points_as_txt,
        )
        image_info = self._export_annotation_image(parent_directory, image_node, conflict_policy)
        export_info = {
            "folder": save_info["folder"],
            "scenePath": save_info["scenePath"],
            "csvPath": save_info["csvPath"],
            "imagePath": image_info["imagePath"],
        }
        if save_info.get("curvePointsTxtPath"):
            export_info["curvePointsTxtPath"] = save_info["curvePointsTxtPath"]
        return export_info

    def _csv_export_paths(self, parent_directory: Any, image_node: Any=None) -> list[Any]:
        """Return planned CSV-related paths for overwrite prompts."""

        output_paths = [self.logic.default_csv_path(parent_directory, image_node)]
        if self.export_curve_points_as_txt:
            output_paths.append(self.logic.default_curve_points_txt_path(parent_directory, image_node))
        return output_paths

    def _save_all_output_paths(self, parent_directory: Any, image_node: Any=None) -> list[Any]:
        """Return planned save-all paths for overwrite prompts."""

        output_paths = [
            self.logic.default_scene_path(parent_directory, image_node),
            self.logic.default_csv_path(parent_directory, image_node),
            self.logic.default_image_path(parent_directory, image_node),
        ]
        if self.export_curve_points_as_txt:
            output_paths.append(self.logic.default_curve_points_txt_path(parent_directory, image_node))
        return output_paths

    def _export_csv_case(
        self,
        parent_directory: Any,
        image_node: Any=None,
        conflict_policy: Any="version",
    ) -> Any:
        """Export CSV and optional curve-point TXT according to the current UI option."""

        return self.logic.export_csv(
            parent_directory,
            image_node,
            conflict_policy=conflict_policy,
            export_curve_points_txt=self.export_curve_points_as_txt,
        )

    def _csv_export_success_message(self, export_info: Any) -> str:
        """Return a concise status message for CSV-related exports."""

        message = f"Exported CSV to {export_info['csvPath']}."
        if export_info.get("curvePointsTxtPath"):
            message += f" Exported curve points TXT to {export_info['curvePointsTxtPath']}."
        return message

    def _save_all_success_message(self, export_info: Any) -> str:
        """Return a concise status message for combined exports."""

        message = (
            "Exported scene, CSV, and annotated image into "
            f"{export_info['folder']}."
        )
        if export_info.get("curvePointsTxtPath"):
            message += f" Curve points TXT: {export_info['curvePointsTxtPath']}."
        return message

    def _save_all_exports(self) -> Any:
        """Run the combined save-all workflow and clear the dirty flag only on success."""

        export_info = self._run_export_action(
            "Export All",
            self._save_all_output_paths,
            self._save_all_case,
            self._save_all_success_message,
        )
        if export_info is not None:
            self._mark_case_saved()
        return export_info

    def _confirm_case_transition(self, next_action: str) -> bool:
        """Prompt before leaving a case that has unsaved scene-level changes."""

        if not self.case_has_unsaved_changes:
            return True

        message_box = qt.QMessageBox(slicer.util.mainWindow())
        message_box.setIcon(qt.QMessageBox.Warning)
        message_box.setWindowTitle("Unsaved Changes")
        message_box.setText("The current case has unsaved changes.")
        message_box.setInformativeText(
            f"Choose Export All to preserve the current annotations before {next_action}."
        )
        save_button = message_box.addButton("Export All", qt.QMessageBox.AcceptRole)
        discard_button = message_box.addButton("Discard Changes", qt.QMessageBox.DestructiveRole)
        cancel_button = message_box.addButton("Cancel", qt.QMessageBox.RejectRole)
        message_box.exec_()

        clicked_button = message_box.clickedButton()
        if clicked_button == save_button:
            return self._save_all_exports() is not None
        if clicked_button == discard_button:
            return True
        if clicked_button == cancel_button:
            return False
        return False

    def _load_image_file(self, image_path: Path) -> Any:
        """Load one image file into a cleared scene.

        The folder workflow treats each listed file as one case, so the volume reader is forced to
        load just that file instead of scanning neighboring files for a stack or related series.
        """

        return slicer.util.loadVolume(
            str(image_path),
            {
                "name": image_path.name,
                "singleFile": True,
                "show": True,
            },
        )

    def _show_image_node_in_slice_views(self, image_node: Any) -> None:
        """Explicitly assign the active image node to Slicer's slice-view background layer.

        The `B:` corner annotation in slice views reflects the current background volume. Updating
        the background layer here keeps that annotation synchronized with folder-driven case
        switching, regardless of whether the case came from a raw image load or a saved MRB scene.
        """

        if image_node is None:
            return
        slicer.util.setSliceViewerLayers(background=image_node)
        layout_manager = slicer.app.layoutManager() if hasattr(slicer, "app") else None
        if layout_manager is not None:
            for slice_view_name in layout_manager.sliceViewNames():
                slice_widget = layout_manager.sliceWidget(slice_view_name)
                if slice_widget is None or not hasattr(slice_widget, "sliceLogic"):
                    continue
                slice_logic = slice_widget.sliceLogic()
                composite_node = (
                    slice_logic.GetSliceCompositeNode() if slice_logic is not None else None
                )
                if composite_node is None:
                    continue
                composite_node.SetBackgroundVolumeID(image_node.GetID())
                composite_node.Modified()
        application_logic = slicer.app.applicationLogic() if hasattr(slicer, "app") else None
        selection_node = (
            application_logic.GetSelectionNode() if application_logic is not None else None
        )
        if selection_node is not None:
            if hasattr(selection_node, "SetActiveVolumeID"):
                selection_node.SetActiveVolumeID(image_node.GetID())
            elif hasattr(selection_node, "SetReferenceActiveVolumeID"):
                selection_node.SetReferenceActiveVolumeID(image_node.GetID())
        if application_logic is not None:
            if hasattr(application_logic, "PropagateBackgroundVolumeSelection"):
                application_logic.PropagateBackgroundVolumeSelection(0)
            elif hasattr(application_logic, "PropagateVolumeSelection"):
                application_logic.PropagateVolumeSelection(0)
        data_probe = getattr(slicer.modules, "DataProbeInstance", None)
        info_widget = getattr(data_probe, "infoWidget", None)
        slice_annotations = getattr(info_widget, "sliceAnnotations", None)
        if slice_annotations is not None and hasattr(slice_annotations, "updateSliceViewFromGUI"):
            slice_annotations.updateSliceViewFromGUI()
        if self.logic is not None:
            self._sync_active_side_badge()
        if hasattr(slicer.util, "forceRenderAllViews"):
            slicer.util.forceRenderAllViews()

    def _restore_saved_case_runtime_state(
        self,
        target_image_path: Path | None=None,
        saved_scene_path: Path | None=None,
    ) -> None:
        """Reset per-case runtime state, then restore saved CSV-backed case settings when available.

        Calibration presence and known diameter are not stored inside MRML nodes, so folder-driven
        case switching must explicitly restore them for saved cases and reset them for new cases.
        """

        if self.logic is None:
            return

        self.logic.set_calibration_ball_present(True)
        self.logic.set_calibration_ball_diameter_mm(CALIBRATION_BALL_DIAMETER_MM)
        if target_image_path is None or saved_scene_path is None or not self.output_folder_path:
            return

        csv_path = latest_saved_csv_path_for_image_filename(
            self.output_folder_path,
            target_image_path.name,
            saved_scene_path,
        )
        if csv_path is None:
            return

        try:
            saved_metadata = parse_saved_case_metadata(load_export_csv_rows(csv_path))
        except Exception:
            logging.exception("Could not restore saved case metadata from %s", csv_path)
            return

        self.logic.set_calibration_ball_present(saved_metadata["calibrationBallPresent"])
        self.logic.set_calibration_ball_diameter_mm(saved_metadata["calibrationBallDiameterMm"])
        if saved_metadata["exportTimestamp"] != self.logic.case_export_timestamp():
            self.logic.set_case_export_timestamp(saved_metadata["exportTimestamp"])
        self._restore_saved_case_comments(saved_metadata["comments"])

    def _finalize_case_load(
        self,
        target_image_path: Path | None=None,
        saved_scene_path: Path | None=None,
    ) -> None:
        """Reconnect observers and refresh the module after a case transition."""

        if self.logic is None:
            self.logic = PelvicXrayMeasurementsLogic()
        self.logic.set_annotator_name(self._annotator_text())
        self._observe_scene_and_nodes()
        self._set_current_image_node(self._scene_image_node_for_path(target_image_path))
        self._restore_saved_case_runtime_state(target_image_path, saved_scene_path)
        self._show_image_node_in_slice_views(self.current_image_node())
        self._select_default_image_if_needed()
        self._sync_folder_image_index_from_current_node(target_image_path)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.case_transition_in_progress = False
        self.suspend_dirty_tracking = True
        try:
            self.refresh_ui()
            self._mark_case_saved()
        finally:
            self.suspend_dirty_tracking = False

    def _load_case_from_folder_image(self, target_index: int) -> bool:
        """Load one folder-managed case, preferring a saved MRB when available."""

        if target_index < 0 or target_index >= len(self.folder_image_paths):
            return False
        if not self._confirm_case_transition("loading another image"):
            return False

        target_image_path = self.folder_image_paths[target_index]
        saved_scene_path = None
        if self.output_folder_path:
            saved_scene_path = latest_saved_scene_path_for_image_filename(
                self.output_folder_path,
                target_image_path.name,
            )

        self.case_transition_in_progress = True
        self.suspend_dirty_tracking = True
        try:
            self._set_current_image_node(None)
            slicer.mrmlScene.Clear(0)
            if saved_scene_path is not None and path_exists(saved_scene_path):
                self._load_saved_scene(saved_scene_path)
            else:
                if self._load_image_file(target_image_path) in {None, False}:
                    raise RuntimeError(f"Could not load image file {target_image_path}")
        except Exception as error:
            self.case_transition_in_progress = False
            self.suspend_dirty_tracking = False
            self._warn(str(error))
            return False

        self.current_folder_image_path = target_image_path
        self.current_folder_image_index = target_index
        self._finalize_case_load(target_image_path, saved_scene_path)
        self.instructions_label.setText(f"Loaded {target_image_path.name}.")
        return True

    def _load_adjacent_folder_image(self, step: int) -> bool:
        """Load the previous or next image from the selected input folder."""

        if not self.folder_image_paths:
            self._warn("Select an input folder before using previous or next image navigation.")
            return False
        target_index = self.current_folder_image_index + int(step)
        if target_index < 0 or target_index >= len(self.folder_image_paths):
            return False
        return self._load_case_from_folder_image(target_index)

    def _annotator_overlay_text(self) -> Any:
        """Return the annotator line shown in exported images.

        The annotator is treated as export provenance metadata, so it is rendered explicitly above
        measurement values rather than being hidden inside the scene or file name.
        """

        annotator_name = self._annotator_text()
        return f"Annotator: {annotator_name}" if annotator_name else ""

    def _ensure_annotator_for_export(self, action_name: Any) -> Any:
        """Require a non-empty annotator before any save or export action.

        The module should never produce outward-facing files without identifying the annotator, so
        export entry points validate the field and return focus to it when missing.
        """

        annotator_name = self._annotator_text()
        self.logic.set_annotator_name(annotator_name)
        if annotator_name:
            return True
        qt.QMessageBox.warning(
            slicer.util.mainWindow(),
            "Annotator Required",
            f'Fill the "Annotator" field before {action_name}.',
        )
        self.annotator_line_edit.setFocus()
        self.annotator_line_edit.selectAll()
        return False

    def _observe_scene_and_nodes(self) -> None:
        """Attach scene and node observers needed for live updates. Observation is centralized so the
        widget can remain responsive without scattering event wiring across handlers.
        """

        self.removeObservers()
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.on_scene_start_close)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.on_scene_end_close)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeAddedEvent, self.on_scene_node_added)
        for event_name, callback in (
            ("StartImportEvent", self.on_scene_start_import_or_restore),
            ("StartRestoreEvent", self.on_scene_start_import_or_restore),
            ("EndImportEvent", self.on_scene_end_import_or_restore),
            ("EndRestoreEvent", self.on_scene_end_import_or_restore),
        ):
            event_id = getattr(slicer.mrmlScene, event_name, None)
            if event_id is not None:
                self.addObserver(slicer.mrmlScene, event_id, callback)

        self.logic.ensure_nodes()
        interaction_node = self._interaction_node()
        if interaction_node is not None:
            self.addObserver(
                interaction_node,
                self._interaction_mode_changed_event(),
                self.on_interaction_node_modified,
            )
        for node in self.logic.observed_input_nodes():
            self.addObserver(
                node,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                self.on_measurement_node_modified,
            )
            self.addObserver(
                node,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                self.on_measurement_node_modified,
            )

    def _interaction_node(self) -> Any:
        """Return Slicer's global interaction node when a live application is available."""

        application = getattr(slicer, "app", None)
        if application is None:
            return None
        application_logic = application.applicationLogic()
        if application_logic is None:
            return None
        return application_logic.GetInteractionNode()

    def _interaction_mode_changed_event(self) -> Any:
        """Return the most specific interaction-mode event exposed by this Slicer build."""

        interaction_node_class = getattr(slicer, "vtkMRMLInteractionNode", None)
        if (
            interaction_node_class is not None
            and hasattr(interaction_node_class, "InteractionModeChangedEvent")
        ):
            return interaction_node_class.InteractionModeChangedEvent
        return vtk.vtkCommand.ModifiedEvent

    def _interaction_node_is_in_place_mode(self, interaction_node: Any) -> bool:
        """Report whether the interaction node is currently in markup placement mode."""

        if interaction_node is None or not hasattr(interaction_node, "GetCurrentInteractionMode"):
            return False
        place_mode = getattr(interaction_node, "Place", None)
        if place_mode is None:
            return False
        return interaction_node.GetCurrentInteractionMode() == place_mode

    def current_image_node(self) -> Any:
        """Return the image currently selected in the module. Most workflows depend on a single active
        radiograph, so this helper keeps that lookup trivial.
        """

        return self._sync_current_image_node()

    def current_side_key(self) -> Any:
        """Return the currently selected side key. Bilateral workflows read side state through one
        helper so UI and logic stay in sync.
        """

        current_index = self.side_selector.currentIndex
        if callable(current_index):
            current_index = current_index()
        current_data = self.side_selector.itemData(int(current_index))
        current_key = str(current_data).strip().lower()
        if current_key in SIDE_LABELS:
            return SideKey(current_key)
        current_text = self.side_selector.currentText
        if callable(current_text):
            current_text = current_text()
        current_key = str(current_text).strip().lower()
        return SideKey(current_key) if current_key in SIDE_LABELS else SideKey.LEFT

    def current_side_label(self) -> Any:
        """Return the human-readable label for the currently selected side. The helper keeps status
        messages and labels consistent with the side selector.
        """

        return SIDE_LABELS[self.current_side_key()]

    def _measurement_side_key(self, measurement_key: Any) -> Any:
        """Resolve which side a measurement should use, if any. Global tools bypass side state, while
        bilateral tools inherit the active side from a single decision point.
        """

        return self.current_side_key() if measurement_key in SIDE_MEASUREMENT_KEYS else None

    def _measurement_is_active(self, measurement_key: Any) -> Any:
        """Report whether a measurement button corresponds to the workflow currently being placed.
        Button styling is driven from this helper so state handling stays simple.
        """

        if self.active_placement_measurement_key != measurement_key:
            return False
        if measurement_key in GLOBAL_MEASUREMENT_KEYS:
            return True
        return self.active_placement_side_key == self.current_side_key()

    def _measurement_is_applied(self, results: Any, measurement_key: Any) -> Any:
        """Report whether a measurement already has a valid result. The UI highlights applied
        measurements so users can tell at a glance what has been completed.
        """

        contour_roles = {
            MeasurementKey.ILIOPECTINEAL_LINE: "iliopectinealLine",
            MeasurementKey.ILIOISCHIAL_LINE: "ilioischialLine",
            MeasurementKey.SHENTON_LINE: "shentonLine",
            MeasurementKey.ACETABULAR_ROOF_SOURCIL: "acetabularRoofSourcil",
            MeasurementKey.ANTERIOR_ACETABULAR_WALL: "anteriorAcetabularWall",
            MeasurementKey.POSTERIOR_ACETABULAR_WALL: "posteriorAcetabularWall",
            MeasurementKey.LINEA_TERMINALIS: "lineaTerminalis",
        }
        if measurement_key in contour_roles:
            role = self.logic.side_role(contour_roles[measurement_key], self.current_side_key())
            node = self.logic.get_node(role, create_if_missing=False)
            return bool(node is not None and self.logic._node_has_visible_content(node))
        if measurement_key == MeasurementKey.FEMORAL_SHAFT_CONTOUR:
            side_results = results["sides"][self.current_side_key()]
            return bool(side_results["femoralShaftContours"].get("defined"))
        if measurement_key == MeasurementKey.OTHER_POINT:
            return len(results.get("otherPoints", [])) > 0
        if measurement_key == MeasurementKey.OTHER_LINE:
            return len(results.get("otherLines", [])) > 0
        if measurement_key == MeasurementKey.OTHER_ANGLE:
            return len(results.get("otherAngles", [])) > 0
        result_group = MEASUREMENT_RESULT_GROUPS.get(measurement_key)
        if result_group is None:
            return False

        scope, result_key = result_group
        if scope == "global":
            measurement = results[result_key]
        else:
            measurement = results["sides"][self.current_side_key()][result_key]
        return bool(measurement.get("defined"))

    def _sync_measurement_visibility_checks(self) -> None:
        """Update measurement visibility checkboxes from the logic state. The widget reflects scene
        truth rather than assuming the user last touched the UI control.
        """

        for measurement_key, checkboxes in self.measurement_visibility_checks.items():
            visible = self.logic.measurement_visible(
                measurement_key, self._measurement_side_key(measurement_key)
            )
            for checkbox in checkboxes:
                checkbox.blockSignals(True)
                checkbox.setChecked(not visible)
                checkbox.blockSignals(False)

    def _sync_measurement_button_states(self, results: Any) -> None:
        """Refresh measurement button colours and enabled states from current results. Centralized
        state styling is easier to audit than ad hoc per-button updates.
        """

        for measurement_key, button in self._measurement_button_items():
            applied = self._measurement_is_applied(results, measurement_key)
            active = self._measurement_is_active(measurement_key)
            if active and applied:
                state = "activeApplied"
            elif active:
                state = "active"
            elif applied:
                state = "applied"
            else:
                state = "idle"
            button.setStyleSheet(self._measurement_button_style(state))
            tooltip_parts = []
            if active:
                tooltip_parts.append("Active placement")
            if applied:
                tooltip_parts.append("Applied on image")
            disabled_tooltip = self.measurement_dependency_tooltips.get(measurement_key)
            if disabled_tooltip and not button.isEnabled():
                tooltip_parts.append(disabled_tooltip)
            if measurement_key == MeasurementKey.REFERENCE_LINE:
                tooltip_parts.append("Place at teardrop level whenever feasible for automatic point suggestions")
            if not tooltip_parts:
                tooltip_parts.append("Ready")
            button.setToolTip(" | ".join(tooltip_parts))

    def _dependency_tooltip(self, *dependency_names: Any) -> str:
        """Build a compact disabled-button tooltip from missing prerequisite names."""

        names = [str(name).strip() for name in dependency_names if str(name).strip()]
        if not names:
            return "This tool is unavailable until its prerequisites are complete."
        if len(names) == 1:
            dependency_text = names[0]
        elif len(names) == 2:
            dependency_text = f"{names[0]} and {names[1]}"
        else:
            dependency_text = f"{', '.join(names[:-1])}, and {names[-1]}"
        return f"Requires {dependency_text} before this tool can be used."

    def _set_measurement_enabled(
        self,
        measurement_key: Any,
        enabled: Any,
        disabled_tooltip: Any=None,
    ) -> None:
        """Set a measurement button enabled state and remember why it is disabled."""

        buttons = self._measurement_buttons_for_key(measurement_key)
        if not buttons:
            return
        for button in buttons:
            button.setEnabled(bool(enabled))
        if enabled:
            self.measurement_dependency_tooltips.pop(measurement_key, None)
            return
        self.measurement_dependency_tooltips[measurement_key] = (
            str(disabled_tooltip).strip()
            if disabled_tooltip
            else "This tool is unavailable until its prerequisites are complete."
        )

    def _select_default_image_if_needed(self) -> None:
        """Pick a default image when the user has not selected one yet. The module tries to reduce
        setup friction by automatically using the first available radiograph.
        """

        self._sync_current_image_node()

    def _refresh_static_controls(self) -> None:
        """Refresh top-level controls that mirror stored widget and scene state."""

        self._sync_ball_controls()
        self._sync_neck_axis_option_controls()
        self._sync_annotator_control()
        self._sync_comments_control()
        self._sync_directory_controls()

    def _refresh_result_values(
        self,
        results: Any,
        left_results: Any,
        right_results: Any,
    ) -> None:
        """Refresh every read-only result field from the current calculated measurements."""

        self.calibration_value.setText(
            format_calibration_summary(results, self.logic.calibration_ball_diameter_mm)
        )
        self.reference_value.setText(format_reference_summary(results))
        self.left_extrusion_index_value.setText(
            format_compact_percent(left_results["femoralHeadExtrusionIndex"])
        )
        self.right_extrusion_index_value.setText(
            format_compact_percent(right_results["femoralHeadExtrusionIndex"])
        )
        self.left_tonnis_angle_value.setText(
            format_compact_angle(left_results["tonnisAngle"])
        )
        self.right_tonnis_angle_value.setText(
            format_compact_angle(right_results["tonnisAngle"])
        )
        self.left_sharp_angle_value.setText(
            format_compact_angle(left_results["sharpAngle"])
        )
        self.right_sharp_angle_value.setText(
            format_compact_angle(right_results["sharpAngle"])
        )
        self.left_lce_angle_value.setText(
            format_compact_angle(left_results["lceAngle"])
        )
        self.right_lce_angle_value.setText(
            format_compact_angle(right_results["lceAngle"])
        )
        self.left_ccd_angle_value.setText(
            format_compact_angle(left_results["ccdAngle"])
        )
        self.right_ccd_angle_value.setText(
            format_compact_angle(right_results["ccdAngle"])
        )
        self.left_femur_head_value.setText(
            format_compact_length(left_results["femurHead"], self.logic.calibration_ball_present)
        )
        self.right_femur_head_value.setText(
            format_compact_length(right_results["femurHead"], self.logic.calibration_ball_present)
        )
        self.left_acetabular_offset_value.setText(
            format_compact_length(
                left_results["acetabularOffset"], self.logic.calibration_ball_present
            )
        )
        self.right_acetabular_offset_value.setText(
            format_compact_length(
                right_results["acetabularOffset"], self.logic.calibration_ball_present
            )
        )
        self.left_femoral_offset_value.setText(
            format_compact_length(
                left_results["femoralOffset"], self.logic.calibration_ball_present
            )
        )
        self.right_femoral_offset_value.setText(
            format_compact_length(
                right_results["femoralOffset"], self.logic.calibration_ball_present
            )
        )
        self.left_preop_global_offset_value.setText(
            format_compact_length(
                left_results["preopGlobalOffset"], self.logic.calibration_ball_present
            )
        )
        self.right_preop_global_offset_value.setText(
            format_compact_length(
                right_results["preopGlobalOffset"], self.logic.calibration_ball_present
            )
        )
        self.left_ccr_value.setText(format_compact_ratio(left_results["corticalCalcarRatio"]))
        self.right_ccr_value.setText(format_compact_ratio(right_results["corticalCalcarRatio"]))
        self.left_cti_value.setText(format_compact_ratio(left_results["canalThicknessIndex"]))
        self.right_cti_value.setText(format_compact_ratio(right_results["canalThicknessIndex"]))
        self.left_cfi_value.setText(format_compact_ratio(left_results["canalFlareIndex"]))
        self.right_cfi_value.setText(format_compact_ratio(right_results["canalFlareIndex"]))
        self.left_inclination_angle_value.setText(
            format_compact_angle(left_results["acetabularInclinationAngle"])
        )
        self.right_inclination_angle_value.setText(
            format_compact_angle(right_results["acetabularInclinationAngle"])
        )
        self.left_cup_opening_ellipse_inclination_value.setText(
            format_compact_angle(left_results["cupOpeningEllipseInclinationAngle"])
        )
        self.right_cup_opening_ellipse_inclination_value.setText(
            format_compact_angle(right_results["cupOpeningEllipseInclinationAngle"])
        )
        self.left_cup_anteversion_retroversion_value.setText(
            format_compact_angle(left_results["cupOpeningAnteversionRetroversionAngle"])
        )
        self.right_cup_anteversion_retroversion_value.setText(
            format_compact_angle(right_results["cupOpeningAnteversionRetroversionAngle"])
        )
        self.left_implant_femoral_ccd_value.setText(
            format_compact_angle(left_results["implantFemoralCCD"])
        )
        self.right_implant_femoral_ccd_value.setText(
            format_compact_angle(right_results["implantFemoralCCD"])
        )
        self.left_implant_head_value.setText(
            format_compact_length(left_results["implantHead"], self.logic.calibration_ball_present)
        )
        self.right_implant_head_value.setText(
            format_compact_length(right_results["implantHead"], self.logic.calibration_ball_present)
        )
        self.left_postop_acetabular_offset_value.setText(
            format_compact_length(
                left_results["postOpAcetabularOffset"], self.logic.calibration_ball_present
            )
        )
        self.right_postop_acetabular_offset_value.setText(
            format_compact_length(
                right_results["postOpAcetabularOffset"], self.logic.calibration_ball_present
            )
        )
        self.left_postop_femoral_offset_value.setText(
            format_compact_length(
                left_results["postOpFemoralOffset"], self.logic.calibration_ball_present
            )
        )
        self.right_postop_femoral_offset_value.setText(
            format_compact_length(
                right_results["postOpFemoralOffset"], self.logic.calibration_ball_present
            )
        )
        self.left_postop_global_offset_value.setText(
            format_compact_length(
                left_results["postOpGlobalOffset"], self.logic.calibration_ball_present
            )
        )
        self.right_postop_global_offset_value.setText(
            format_compact_length(
                right_results["postOpGlobalOffset"], self.logic.calibration_ball_present
            )
        )
        self.left_implant_alignment_value.setText(
            format_compact_angle(left_results["implantAlignment"])
        )
        self.right_implant_alignment_value.setText(
            format_compact_angle(right_results["implantAlignment"])
        )
        self.lld_value.setText(format_lld_summary(results))
        self._refresh_other_results_rows(results)
        self.export_value.setText(self.last_export_summary)

    def _sync_measurement_enablement(self, results: Any, active_side_results: Any) -> None:
        """Refresh measurement-button enabled states from prerequisite measurements."""

        reference_ready = results["referenceLine"]["defined"]
        shaft_ready = active_side_results["femoralShaftAxis"]["defined"]
        femur_head_ready = active_side_results["femurHead"]["defined"]
        calibration_ready = results["calibration"]["defined"]
        native_ready = active_side_results["femurHead"]["defined"]
        implant_ready = active_side_results["implantHead"]["defined"]
        model_ready = os.path.isfile(self._auto_point_model_path())
        self.auto_place_button.setEnabled(
            bool(calibration_ready and reference_ready and native_ready != implant_ready and model_ready)
        )
        self.auto_place_button.setToolTip(
            "Suggest editable points on the active side after Calibration Ball, a teardrop-level "
            "Reference Line, and exactly one fitted Femur Head or Implant Head."
            if model_ready else "The local coordinate model has not been trained or installed."
        )
        reference_tooltip = self._dependency_tooltip("the Reference Line")
        shaft_tooltip = self._dependency_tooltip("the active-side Femoral Shaft Axis")

        lce_missing = []
        if not reference_ready:
            lce_missing.append("the Reference Line")
        if not femur_head_ready:
            lce_missing.append("the active-side Femur Head")

        morphology_missing = []
        if not shaft_ready:
            morphology_missing.append("the active-side Femoral Shaft Axis")
        if not calibration_ready:
            morphology_missing.append("a defined Calibration Ball")

        self._set_measurement_enabled(MeasurementKey.TONNIS_ANGLE, reference_ready, reference_tooltip)
        self._set_measurement_enabled(MeasurementKey.SHARP_ANGLE, reference_ready, reference_tooltip)
        self._set_measurement_enabled(
            MeasurementKey.LCE_ANGLE,
            reference_ready and femur_head_ready,
            self._dependency_tooltip(*lce_missing),
        )
        self._set_measurement_enabled(MeasurementKey.ACETABULAR_OFFSET, reference_ready, reference_tooltip)
        self._set_measurement_enabled(MeasurementKey.EXTRUSION_INDEX, reference_ready, reference_tooltip)
        self._set_measurement_enabled(
            MeasurementKey.FEMUR_SHAFT_MORPHOLOGY,
            shaft_ready and calibration_ready,
            self._dependency_tooltip(*morphology_missing),
        )
        self._set_measurement_enabled(MeasurementKey.LLD, reference_ready, reference_tooltip)
        self._set_measurement_enabled(MeasurementKey.IMPLANT_HEAD, True)
        self._set_measurement_enabled(MeasurementKey.INCLINATION_ANGLE, reference_ready, reference_tooltip)
        self._set_measurement_enabled(MeasurementKey.CUP_OPENING_ELLIPSE_FIT, reference_ready, reference_tooltip)
        self._set_measurement_enabled(MeasurementKey.NECK_AXIS, True)
        self._set_measurement_enabled(MeasurementKey.IMPLANT_NECK_AXIS, True)
        self._set_measurement_enabled(MeasurementKey.FEMORAL_OFFSET, shaft_ready, shaft_tooltip)
        self._set_measurement_enabled(MeasurementKey.POSTOP_ACETABULAR_OFFSET, reference_ready, reference_tooltip)
        self._set_measurement_enabled(MeasurementKey.POSTOP_FEMORAL_OFFSET, shaft_ready, shaft_tooltip)
        self._set_measurement_enabled(MeasurementKey.IMPLANT_ALIGNMENT, shaft_ready, shaft_tooltip)
        self._set_measurement_enabled(
            MeasurementKey.OTHER_POINT,
            self._custom_measurement_can_add(MeasurementKey.OTHER_POINT, results),
            "Finish the current Point annotation before adding another Point.",
        )
        self._set_measurement_enabled(
            MeasurementKey.OTHER_LINE,
            self._custom_measurement_can_add(MeasurementKey.OTHER_LINE, results),
            "Finish the current Line annotation before adding another Line.",
        )
        self._set_measurement_enabled(
            MeasurementKey.OTHER_ANGLE,
            self._custom_measurement_can_add(MeasurementKey.OTHER_ANGLE, results),
            "Finish the current Angle annotation before adding another Angle.",
        )

    def refresh_ui(self) -> None:
        """Refresh every visible widget from the current logic state. This is the main UI sync pass
        that keeps results, button states, counters, and status text aligned with the MRML scene.
        """

        results = self.logic.latest_results
        left_results = results["sides"]["left"]
        right_results = results["sides"]["right"]
        active_side_results = results["sides"][self.current_side_key()]
        self._sync_active_side_badge()
        self._refresh_static_controls()
        self._refresh_result_values(results, left_results, right_results)
        self._sync_measurement_visibility_checks()
        self._sync_other_measurement_limits(results)
        self._sync_measurement_enablement(results, active_side_results)
        self._sync_measurement_button_states(results)

    def _auto_point_model_path(self) -> str:
        return os.path.join(MODULE_DIR, "Resources", "AutoPlacement", "auto_point_model.json")

    def _auto_point_image_model_path(self) -> str:
        return os.path.join(MODULE_DIR, "Resources", "AutoPlacement", "auto_point_image_model.npz")

    def _auto_point_inside_image(self, point: Any) -> bool:
        image = self.current_image_node()
        if image is None or image.GetImageData() is None:
            return False
        matrix = vtk.vtkMatrix4x4()
        image.GetRASToIJKMatrix(matrix)
        ijk = matrix.MultiplyPoint([float(point[0]), float(point[1]), float(point[2]), 1.0])
        extent = image.GetImageData().GetExtent()
        return all(extent[2 * axis] <= ijk[axis] <= extent[2 * axis + 1] for axis in range(3))

    def on_auto_place_clicked(self, _checked: Any=False) -> None:
        """Offer validated feature groups, then place ordinary editable active-side markups."""
        side = self.current_side_key()
        side_results = self.logic.latest_results["sides"][side]
        native = side_results["femurHead"]
        implant = side_results["implantHead"]
        reference = self.logic.latest_results["referenceLine"]
        calibration = self.logic.latest_results["calibration"]
        if not calibration["defined"] or not reference["defined"] or native["defined"] == implant["defined"]:
            self._warn(
                "Place the calibration ball, teardrop-level reference line, "
                "and exactly one fitted head on the active side first."
            )
            return
        mode = "pre" if native["defined"] else "post"
        head = native if mode == "pre" else implant
        try:
            model = read_model(self._auto_point_model_path())
            frame = make_frame(side, reference["points"][:2], head["center"], head["rawValue"])
            available = model["modes"][mode]["features"]
            proposals = {}
            for key, _label, _roles in feature_specs(mode):
                if key not in available:
                    continue
                if key == "shaft_axis":
                    try:
                        image_node = self.current_image_node()
                        pixels = slicer.util.arrayFromVolume(image_node)
                        if pixels.ndim != 3 or pixels.shape[0] != 1:
                            raise ValueError("A single-slice radiograph is required.")
                        matrix = vtk.vtkMatrix4x4()
                        image_node.GetRASToIJKMatrix(matrix)
                        ras_to_ijk = [[matrix.GetElement(row, column) for column in range(4)] for row in range(4)]
                        proposals[key] = predict_shaft_from_image(
                            model, mode, frame, pixels[0], ras_to_ijk, calibration["scaleFactor"],
                            self._auto_point_image_model_path(),
                        )
                    except (OSError, KeyError, TypeError, ValueError) as error:
                        logging.warning("Image-guided shaft placement unavailable: %s", error)
                elif key == "shaft_morphology":
                    # Defer this prediction until the selected shaft guides have been placed and
                    # Slicer has calculated the actual shaft axis used by the morphology builder.
                    proposals[key] = None
                else:
                    proposals[key] = predict_feature(model, mode, key, frame)
        except (OSError, KeyError, TypeError, ValueError) as error:
            self._warn(f"Automatic placement is unavailable: {error}")
            return
        if not proposals:
            self._warn("No validated point groups are available for this case type.")
            return

        dialog = qt.QDialog(slicer.util.mainWindow())
        dialog.setWindowTitle(f"Auto-place {mode}-operative points — {side.title()}")
        dialog.setMinimumWidth(560)
        dialog.resize(560, 450)
        dialog.setMaximumHeight(500)
        layout = qt.QVBoxLayout(dialog)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_body = qt.QWidget()
        scroll_layout = qt.QVBoxLayout(scroll_body)
        explanation = qt.QLabel(
            "Select the features to suggest. All are selected by default. Existing placed points "
            "keep their coordinates; every new point remains editable. Predictions use the fitted "
            "head and its relationship to the pelvic reference line. Place the reference line at "
            "the teardrops whenever feasible: an ischial-tuberosity-level line can make the "
            "suggestions inaccurate. Check each point against the radiograph before using results."
        )
        explanation.setWordWrap(True)
        scroll_layout.addWidget(explanation)
        if "shaft_axis" in proposals:
            shaft_note = qt.QLabel(
                "The femoral shaft guide lines use the radiograph and saved annotations. "
                "They remain rough estimates: held-out errors exceeded the usual accuracy "
                "threshold. Check and adjust both lines against the shaft cortex."
            )
            shaft_note.setWordWrap(True)
            scroll_layout.addWidget(shaft_note)
        if mode == "pre" and "shaft_morphology" in proposals:
            morphology_note = qt.QLabel(
                "Femur shaft morphology suggests the two lesser-trochanter landmarks and "
                "ten cortex control points learned from the annotated cases. Their axial "
                "stations follow the calibrated measurement definition. The shaft axis is "
                "derived first, then the two LT points are placed, followed by the cortex "
                "points. Points inferred across the axis are moved to their assigned "
                "medial or lateral side; review all cortical positions on the image."
            )
            morphology_note.setWordWrap(True)
            scroll_layout.addWidget(morphology_note)
        checkboxes = {}
        for key, label, _roles in feature_specs(mode):
            if key not in proposals:
                continue
            checkbox = qt.QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.setToolTip(
                f"Held-out median point error: {available[key]['held_out_median_error_mm']:.1f} mm; "
                f"90th percentile: {available[key].get('held_out_p90_error_mm', float('nan')):.1f} mm."
            )
            scroll_layout.addWidget(checkbox)
            checkboxes[key] = checkbox
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_body)
        layout.addWidget(scroll, 1)
        footer = qt.QHBoxLayout()
        footer.addStretch(1)
        cancel_button = qt.QPushButton("Cancel")
        place_button = qt.QPushButton("Place selected points")
        place_button.setObjectName("autoPlaceConfirmButton")
        place_button.setDefault(True)
        cancel_button.connect("clicked(bool)", lambda _checked: dialog.reject())
        place_button.connect("clicked(bool)", lambda _checked: dialog.accept())
        footer.addWidget(cancel_button)
        footer.addWidget(place_button)
        layout.addLayout(footer)
        if dialog.exec() != qt.QDialog.Accepted:
            return
        chosen = [key for key, checkbox in checkboxes.items() if checkbox.isChecked()]
        if not chosen:
            return

        # Stop any older placement queue before adding suggested points through normal MRML nodes.
        self.logic.stop_placement_mode()
        self.active_placement_queue = []
        self.active_placement_name = None
        self.active_placement_measurement_key = None
        self.active_placement_side_key = None

        # The trained post-op proposal contains the proximal implant-neck guide.  Configure the
        # corresponding derived-axis construction before writing that guide so the calculation can
        # complete the axis from the guide direction and fitted implant-head center.  These flags are
        # persisted on the axis node, refresh the visible checkboxes below, and make the automatic
        # result behave exactly like the documented single-guide/through-center workflow.
        if "implant_neck_axis" in chosen:
            self.logic.set_axis_use_single_guide_enabled(
                MeasurementKey.IMPLANT_NECK_AXIS,
                side,
                True,
            )
            self.logic.set_axis_lock_to_center_enabled(
                MeasurementKey.IMPLANT_NECK_AXIS,
                side,
                True,
            )
        morphology_existing_points = {}
        if "shaft_morphology" in chosen:
            morphology_role = self.logic.side_role("shaftMorphologyPoints", side)
            morphology_node = self.logic.get_node(morphology_role, create_if_missing=True)
            if morphology_node is not None:
                morphology_existing_points = {
                    index: self.logic._markup_control_point_position(morphology_node, index)
                    for index in range(morphology_node.GetNumberOfControlPoints())
                    if self.logic._markup_control_point_is_defined(morphology_node, index)
                }
        placed, skipped = 0, []
        for key in sorted(chosen, key=lambda item: (item != "shaft_axis", item == "shaft_morphology")):
            if key == "shaft_morphology":
                self.logic.update_all_derived_measurements(self.current_image_node())
                shaft_axis = self.logic.latest_results["sides"][side]["femoralShaftAxis"]
                if not shaft_axis["defined"]:
                    skipped.append(key)
                    continue
                try:
                    morphology = predict_feature(model, mode, key, frame)
                    morphology["shaftMorphologyPoints"] = enforce_morphology_side_constraints(
                        morphology["shaftMorphologyPoints"],
                        shaft_axis["origin"],
                        shaft_axis["direction"],
                        frame,
                        side,
                    )
                    proposals[key] = morphology
                except (KeyError, TypeError, ValueError) as error:
                    logging.warning("Shaft morphology placement unavailable: %s", error)
                    skipped.append(key)
                    continue
            prepared = []
            invalid = False
            for base_role, predicted in proposals[key].items():
                role = self.logic.side_role(base_role, side)
                node = self.logic.get_node(role, create_if_missing=True)
                if node is None or not node.IsA("vtkMRMLMarkupsNode"):
                    invalid = True
                    break
                if ((key != "shaft_morphology" or base_role != "shaftMorphologyPoints")
                        and node.GetNumberOfDefinedControlPoints() > len(predicted)):
                    invalid = True
                    break
                existing_points = (
                    morphology_existing_points
                    if key == "shaft_morphology" and base_role == "shaftMorphologyPoints"
                    else {
                        index: self.logic._markup_control_point_position(node, index)
                        for index in range(min(node.GetNumberOfControlPoints(), len(predicted)))
                        if self.logic._markup_control_point_is_defined(node, index)
                    }
                )
                if len(existing_points) > len(predicted) or any(index >= len(predicted) for index in existing_points):
                    invalid = True
                    break
                if len(existing_points) == len(predicted):
                    continue
                merged = list(predicted)
                for index, point in existing_points.items():
                    if index < len(merged):
                        merged[index] = point
                if base_role in {"sharpAngleLine", "tonnisAngleLine", "lceAnglePoint"}:
                    if base_role == "sharpAngleLine":
                        known = self._sharp_teardrop_point(side)
                        if known is not None and node.GetNumberOfDefinedControlPoints() == 0:
                            merged[0] = known
                    lateral = self._lateral_sourcil_point(side)
                    if lateral is not None and node.GetNumberOfDefinedControlPoints() == 0:
                        merged[0 if base_role == "lceAnglePoint" else 1] = lateral
                if not all(self._auto_point_inside_image(point) for point in merged):
                    invalid = True
                    break
                labels = self.logic._node_spec_for_role(role).get("labels", [])
                prepared.append((node, merged, labels))
            if invalid:
                skipped.append(key)
                continue
            if not prepared:
                if key == "shaft_axis":
                    self.logic.update_all_derived_measurements(self.current_image_node())
                continue
            for node, merged, labels in prepared:
                self.logic._set_named_points(node, merged, labels)
                self._make_seeded_markup_editable(node)
                placed += 1
            self.logic.set_measurement_visible(MeasurementKey(AUTO_FEATURE_MEASUREMENT_KEYS[key]), True, side)
            if key == "shaft_axis":
                self.logic.update_all_derived_measurements(self.current_image_node())
        if placed or "implant_neck_axis" in chosen:
            self._set_case_dirty(True)
            self.logic.update_all_derived_measurements(self.current_image_node())
            self.refresh_ui()
        message = f"Suggested {placed} editable point group(s) on the {side} side. Review and adjust them on the image."
        if "shaft_axis" in chosen and "shaft_axis" not in skipped:
            message += " The image-guided shaft lines are rough estimates and need careful adjustment."
        if ("shaft_morphology" in chosen
                and not self.logic.latest_results["sides"][side]["femurShaftMorphology"]["defined"]):
            message += " Complete the femoral shaft axis to generate the remaining morphology points."
        if skipped:
            message += f" Skipped {len(skipped)} group(s) outside the image or with unexpected existing points."
        self.instructions_label.setText(message)

    def _choose_export_parent_directory(self) -> Any:
        """Ask the user where case exports should be written. The module separates directory choice
        from file naming so case naming rules remain deterministic.
        """

        if self.output_folder_path and os.path.isdir(self.output_folder_path):
            return self.output_folder_path

        return qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            "Select Export Parent Folder",
            self._export_directory_dialog_start_path(),
        )

    def _complete_export(self, summary: Any, message: Any) -> None:
        """Update the UI after a successful export action. Completion handling is centralized so every
        export button reports results in the same style.
        """

        self.last_export_summary = summary
        self.instructions_label.setText(message)
        self.refresh_ui()

    def _run_export_action(
        self,
        action_name: Any,
        planned_paths_callback: Any,
        export_callback: Any,
        success_message_callback: Any,
    ) -> None:
        """Execute one export action with conflict handling, error reporting, and summary updates. This
        shared path keeps save and export buttons visually separate but behaviorally consistent.
        """

        if not self._ensure_annotator_for_export(action_name):
            return
        self.logic.update_all_derived_measurements(self.current_image_node())
        parent_directory = self._choose_export_parent_directory()
        if not parent_directory:
            return None
        self._remember_export_directory_path(parent_directory)

        conflict_policy = self._choose_conflict_policy(
            action_name, planned_paths_callback(parent_directory, self.current_image_node())
        )
        if conflict_policy is None:
            return None

        try:
            export_info = export_callback(
                parent_directory, self.current_image_node(), conflict_policy=conflict_policy
            )
        except Exception as error:
            logging.exception("%s failed", action_name)
            self._warn(f"{action_name} failed: {error}")
            return None

        exported_items = []
        if export_info.get("scenePath"):
            exported_items.append("MRB")
        if export_info.get("csvPath"):
            exported_items.append("CSV")
        if export_info.get("curvePointsTxtPath"):
            exported_items.append("Curve TXT")
        if export_info.get("imagePath"):
            exported_items.append("Image")
        export_kind = " + ".join(exported_items) if exported_items else action_name
        timestamp = qt.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        summary = f"{timestamp} | {export_kind}"
        self._complete_export(summary, success_message_callback(export_info))
        return export_info

    def _export_annotation_image(
        self,
        parent_directory: Any,
        image_node: Any=None,
        conflict_policy: Any="version",
    ) -> Any:
        """Export the annotated image using the module’s dedicated high-resolution path. The image
        export is kept separate from CSV and MRB export because it has its own rendering and overlay
        pipeline.
        """

        self.logic.update_all_derived_measurements(image_node if image_node is not None else self.current_image_node())
        case_folder = self.logic.case_folder_for_export(parent_directory, image_node)
        image_path = self.logic.image_output_path(
            parent_directory,
            image_node,
            conflict_policy=conflict_policy,
        )

        annotated_image = self._capture_annotation_image(image_node)
        if annotated_image is None or annotated_image.isNull():
            raise RuntimeError("Could not generate annotated image export.")
        if not annotated_image.save(image_path, "PNG"):
            raise RuntimeError(f"Could not save annotated image to {image_path}")

        return {
            "folder": case_folder,
            "imagePath": image_path,
        }

    def on_image_changed(self, index: Any) -> None:
        """Handle changes to Image. Small UI event handlers stay intentionally thin so the actual
        measurement rules remain centralized in the logic layer.
        """

        if self.image_selector_sync_in_progress:
            return
        if self.input_folder_path:
            target_index = int(index)
            if target_index == self.current_folder_image_index:
                return
            if not self._load_case_from_folder_image(target_index):
                self.image_selector_signature = None
                self._sync_image_selector_contents()
            return
        node_id = self.image_selector.itemData(int(index))
        selected_node = slicer.mrmlScene.GetNodeByID(str(node_id)) if node_id else None
        self._set_current_image_node(selected_node)
        self._sync_folder_image_index_from_current_node()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_ball_diameter_changed(self, value: Any) -> None:
        """Handle changes to Ball Diameter. Small UI event handlers stay intentionally thin so the
        actual measurement rules remain centralized in the logic layer.
        """

        self.logic.set_calibration_ball_diameter_mm(value)
        self._set_case_dirty(True)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_annotator_changed(self, value: Any) -> None:
        """Handle changes to Annotator. Session-scoped export metadata is synchronized immediately so
        scene closes can recreate the logic without dropping the visible field value.
        """

        self.logic.set_annotator_name(value)

    def on_comments_changed(self) -> None:
        """Handle changes to the case comments stored with the current scene."""

        self.logic.set_case_comments(self._comments_text())
        self._set_case_dirty(True)

    def on_input_folder_browse_clicked(self, _checked: Any=False) -> None:
        """Select an input folder and immediately load the first available image from it."""

        selected_directory = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            "Select Input Folder",
            self._directory_dialog_start_path(self.input_folder_path),
        )
        if not selected_directory:
            return
        selected_directory = str(selected_directory)
        same_directory = os.path.normpath(selected_directory) == os.path.normpath(self.input_folder_path or "")
        if not same_directory and not self._confirm_case_transition("changing the input folder"):
            return

        current_image_path = self.current_folder_image_path if same_directory else None
        self._set_input_folder_path(selected_directory)
        self._refresh_input_folder_images()
        if not self.folder_image_paths:
            self.current_folder_image_index = -1
            self.current_folder_image_path = None
            self.refresh_ui()
            self._warn("The selected input folder does not contain any supported image files.")
            return

        if current_image_path is not None and current_image_path in self.folder_image_paths:
            self.current_folder_image_index = self.folder_image_paths.index(current_image_path)
            self.current_folder_image_path = current_image_path
            self.refresh_ui()
            return

        self._load_case_from_folder_image(0)

    def on_input_folder_clear_clicked(self, _checked: Any=False) -> None:
        """Clear the remembered input folder without changing the currently loaded scene."""

        self.folder_image_paths = []
        self.current_folder_image_index = -1
        self.current_folder_image_path = None
        self._set_input_folder_path("")
        self.refresh_ui()

    def on_output_folder_browse_clicked(self, _checked: Any=False) -> None:
        """Select the default output folder used by save and export actions."""

        selected_directory = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            "Select Output Folder",
            self._directory_dialog_start_path(self.output_folder_path),
        )
        if not selected_directory:
            return
        self._set_output_folder_path(str(selected_directory))
        self.refresh_ui()

    def on_output_folder_clear_clicked(self, _checked: Any=False) -> None:
        """Clear the remembered default output folder."""

        self._set_output_folder_path("")
        self.refresh_ui()

    def on_previous_image_clicked(self, _checked: Any=False) -> None:
        """Load the previous image from the current input folder selection."""

        self._load_adjacent_folder_image(-1)

    def on_next_image_clicked(self, _checked: Any=False) -> None:
        """Load the next image from the current input folder selection."""

        self._load_adjacent_folder_image(1)

    def on_ball_not_present_toggled(self, checked: Any) -> None:
        """Handle changes to Ball Not Present. Small UI event handlers stay intentionally thin so the
        actual measurement rules remain centralized in the logic layer.
        """

        self.logic.set_calibration_ball_present(not bool(checked))
        self._set_case_dirty(True)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_side_changed(self, _index: Any) -> None:
        """Handle changes to Side. Small UI event handlers stay intentionally thin so the actual
        measurement rules remain centralized in the logic layer.
        """

        self.refresh_ui()

    def on_neck_axis_lock_to_center_toggled(self, checked: Any) -> None:
        """Handle changes to the femoral neck-axis center-lock option for the active side."""

        self.logic.set_axis_lock_to_center_enabled(
            MeasurementKey.NECK_AXIS,
            self.current_side_key(),
            checked,
        )
        self._set_case_dirty(True)
        self._sync_active_axis_workflow_if_editable(MeasurementKey.NECK_AXIS)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_neck_axis_use_single_guide_toggled(self, checked: Any) -> None:
        """Handle changes to the femoral neck-axis single-guide option for the active side."""

        self.logic.set_axis_use_single_guide_enabled(
            MeasurementKey.NECK_AXIS,
            self.current_side_key(),
            checked,
        )
        self._set_case_dirty(True)
        self._sync_active_axis_workflow_if_editable(MeasurementKey.NECK_AXIS)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_implant_neck_axis_lock_to_center_toggled(self, checked: Any) -> None:
        """Handle changes to the implant neck-axis center-lock option for the active side."""

        self.logic.set_axis_lock_to_center_enabled(
            MeasurementKey.IMPLANT_NECK_AXIS, self.current_side_key(), checked
        )
        self._set_case_dirty(True)
        self._sync_active_axis_workflow_if_editable(MeasurementKey.IMPLANT_NECK_AXIS)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_implant_neck_axis_use_single_guide_toggled(self, checked: Any) -> None:
        """Handle changes to the implant neck-axis single-guide option for the active side."""

        self.logic.set_axis_use_single_guide_enabled(
            MeasurementKey.IMPLANT_NECK_AXIS, self.current_side_key(), checked
        )
        self._set_case_dirty(True)
        self._sync_active_axis_workflow_if_editable(MeasurementKey.IMPLANT_NECK_AXIS)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def on_display_measurements_toggled(self, checked: Any) -> None:
        """Handle changes to Display Measurements. Small UI event handlers stay intentionally thin so
        the actual measurement rules remain centralized in the logic layer.
        """

        self.display_measurements_on_image = bool(checked)

    def on_export_curve_points_txt_toggled(self, checked: Any) -> None:
        """Handle changes to optional sampled-curve TXT export."""

        self.export_curve_points_as_txt = bool(checked)

    def on_scene_start_close(self, _caller: Any, _event: Any) -> None:
        """Prepare the widget for an MRML scene close operation. Scene-close hooks prevent observers
        and cached widgets from referencing nodes that are about to disappear.
        """

        if not self.case_transition_in_progress:
            self.external_scene_load_in_progress = True
        if self.logic is not None:
            self.logic.clear_dynamic_other_specs()
        self.active_placement_queue = []
        self.active_placement_name = None
        self.active_placement_measurement_key = None
        self.active_placement_side_key = None
        self.active_femoral_shaft_contour_step_index = None
        self.pending_auto_line_endpoints = {}
        self.last_export_summary = "Not saved yet."
        self.measurement_dependency_tooltips = {}
        self.loaded_image_node = None
        self.image_selector_signature = None
        self.case_has_unsaved_changes = False
        self.scene_node_added_refresh_scheduled = False

    def on_scene_end_close(self, _caller: Any, _event: Any) -> None:
        """Rebuild the widget state after an MRML scene close operation. The module restores its
        required nodes and UI state explicitly so reloading a case feels stable.
        """

        self.logic = PelvicXrayMeasurementsLogic()
        self.logic.set_annotator_name(self._annotator_text())
        self._set_current_image_node(None)
        if self.case_transition_in_progress:
            return
        self._schedule_external_scene_load_refresh(250)

    def on_scene_start_import_or_restore(self, _caller: Any, _event: Any) -> None:
        """Track manual MRML scene loading while the module panel is already open."""

        if self.case_transition_in_progress:
            return
        self.external_scene_load_in_progress = True

    def on_scene_end_import_or_restore(self, _caller: Any, _event: Any) -> None:
        """Adopt loaded MRB nodes after Slicer finishes importing or restoring the scene."""

        if self.case_transition_in_progress:
            return
        self.external_scene_load_in_progress = False
        self._schedule_external_scene_load_refresh(0, force=True)

    def _scene_is_loading(self) -> bool:
        """Return whether Slicer still reports an active scene load/restore operation."""

        for method_name in ("IsImporting", "IsRestoring", "IsBatchProcessing"):
            method = getattr(slicer.mrmlScene, method_name, None)
            if method is None:
                continue
            try:
                if bool(method()):
                    return True
            except TypeError:
                continue
        return False

    def _schedule_external_scene_load_refresh(self, delay_ms: int=0, force: bool=False) -> None:
        """Schedule one deferred adoption pass for a manually loaded scene."""

        if self.case_transition_in_progress:
            return
        if self.external_scene_load_refresh_scheduled and not force:
            return
        self.external_scene_load_refresh_scheduled = True
        qt.QTimer.singleShot(int(delay_ms), self._refresh_after_external_scene_load)

    def _refresh_after_external_scene_load(self) -> None:
        """Refresh module state after a manual Slicer scene load has finished.

        Folder-driven/batch case changes use `_finalize_case_load`; this path is only for scenes
        loaded externally while the module UI is already open.
        """

        self.external_scene_load_refresh_scheduled = False
        if self.logic is None or self.case_transition_in_progress:
            return
        if self._scene_is_loading():
            self._schedule_external_scene_load_refresh(100, force=True)
            return

        self.external_scene_load_in_progress = False
        if hasattr(self.logic, "clear_node_cache"):
            self.logic.clear_node_cache()
        self.logic.set_annotator_name(self._annotator_text())
        self._observe_scene_and_nodes()
        self._select_default_image_if_needed()
        image_node = self.current_image_node()
        if image_node is not None:
            self._show_image_node_in_slice_views(image_node)
        self.logic.update_all_derived_measurements(image_node)
        self.suspend_dirty_tracking = True
        try:
            self.refresh_ui()
            self._mark_case_saved()
        finally:
            self.suspend_dirty_tracking = False

    def on_scene_node_added(self, _caller: Any, _event: Any) -> None:
        """Refresh once after scene additions so newly loaded images get an active-side badge."""

        if self.logic is None or self.case_transition_in_progress:
            return
        if self.external_scene_load_in_progress:
            self._schedule_external_scene_load_refresh(250)
            return
        if self.scene_node_added_refresh_scheduled:
            return
        self.scene_node_added_refresh_scheduled = True
        qt.QTimer.singleShot(0, self._refresh_after_scene_node_added)

    def _refresh_after_scene_node_added(self) -> None:
        """Debounced scene-add refresh used when users load an image while this module is open."""

        self.scene_node_added_refresh_scheduled = False
        if self.logic is None or self.case_transition_in_progress:
            return
        self._select_default_image_if_needed()
        image_node = self.current_image_node()
        if image_node is not None:
            self._show_image_node_in_slice_views(image_node)
        self.logic.update_all_derived_measurements(image_node)
        self.refresh_ui()

    def on_measurement_node_modified(self, caller: Any, _event: Any) -> None:
        """React to measurement-node edits by recomputing derived results. This is the core live-update
        hook that gives the module its interactive editing behavior.
        """

        if self.logic is None or self.logic.is_updating_measurements():
            return
        if self.external_scene_load_in_progress:
            return
        if self.logic.is_snapping_anatomy_curve_points():
            return
        role = caller.GetAttribute(ROLE_ATTRIBUTE) if caller is not None and hasattr(caller, "GetAttribute") else None
        self.logic.snap_anatomy_curve_to_edges(role, self.current_image_node())
        self.logic.note_cup_opening_ellipse_control_role(role)
        self._complete_pending_auto_line_endpoint(role)
        self._set_case_dirty(True)
        self.logic.update_all_derived_measurements(self.current_image_node())
        self._advance_workflow_if_complete()
        self.refresh_ui()

    def on_interaction_node_modified(self, caller: Any, _event: Any) -> None:
        """Advance open-ended femoral-shaft contour placement when Slicer exits place mode."""

        if (
            self.active_placement_measurement_key != MeasurementKey.FEMORAL_SHAFT_CONTOUR
            or self.active_placement_side_key is None
            or self.active_femoral_shaft_contour_step_index is None
        ):
            return
        if self._interaction_node_is_in_place_mode(caller):
            return
        qt.QTimer.singleShot(0, self._maybe_auto_advance_femoral_shaft_contour)

    def _maybe_auto_advance_femoral_shaft_contour(self) -> None:
        """Advance the femoral-shaft contour step after the user finishes the current curve."""

        if self.logic is None or self.logic.is_updating_measurements():
            return
        if (
            self.active_placement_measurement_key != MeasurementKey.FEMORAL_SHAFT_CONTOUR
            or self.active_placement_side_key is None
            or self.active_femoral_shaft_contour_step_index is None
        ):
            return
        if self._interaction_node_is_in_place_mode(self._interaction_node()):
            return
        self._advance_or_finish_femoral_shaft_contour(self.active_placement_side_key)

    def _start_workflow(
        self,
        workflow_name: Any,
        steps: Any,
        initial_message: Any,
        measurement_key: Any=None,
        side_key: Any=None,
    ) -> None:
        """Start a guided placement workflow made of one or more queued steps. The queue-based approach
        lets complex measurements behave like simple tools from the user’s perspective.
        """

        self._set_case_dirty(True)
        if hasattr(self, "_pending_auto_line_endpoint_map"):
            pending_endpoints = self._pending_auto_line_endpoint_map()
            workflow_roles = {step.get("role") for step in steps}
            for pending_role in list(pending_endpoints):
                if pending_role not in workflow_roles:
                    pending_endpoints.pop(pending_role, None)
        self.active_placement_name = workflow_name
        self.active_placement_measurement_key = measurement_key
        self.active_placement_side_key = side_key
        self.active_femoral_shaft_contour_step_index = None
        if measurement_key is not None:
            self.logic.set_measurement_visible(measurement_key, True, side_key)
        self.active_placement_queue = list(steps)
        self.instructions_label.setText(initial_message)
        self._activate_current_step()
        self.logic.update_all_derived_measurements(self.current_image_node())
        self.refresh_ui()

    def _activate_current_step(self) -> None:
        """Activate placement for the current step in the workflow queue. Keeping activation separate
        from workflow creation makes multi-step tools easier to maintain.
        """

        while self.active_placement_queue and self.logic.node_is_complete(
            self.active_placement_queue[0]["role"]
        ):
            self.active_placement_queue.pop(0)

        if not self.active_placement_queue:
            self.active_placement_name = None
            self.active_placement_measurement_key = None
            self.active_placement_side_key = None
            self.active_femoral_shaft_contour_step_index = None
            self.instructions_label.setText(
                "Placement complete. You can adjust the points or lines at any time."
            )
            self.logic.stop_placement_mode()
            self.refresh_ui()
            return

        current_step = self.active_placement_queue[0]
        node = self.logic.get_node(current_step["role"])
        self.instructions_label.setText(current_step["instruction"])
        self.logic.activate_placement(node, persistent=current_step["persistent"])
        self.refresh_ui()

    def _advance_workflow_if_complete(self) -> None:
        """Advance the active workflow when the current input node has enough points. Completion is
        determined from node content so editing and replay stay robust.
        """

        if not self.active_placement_queue:
            return

        current_step = self.active_placement_queue[0]
        if self.logic.node_is_complete(current_step["role"]):
            self.active_placement_queue.pop(0)
            qt.QTimer.singleShot(0, self._activate_current_step)


class PelvicXrayMeasurementsLogic(
    SceneNodeMixin,
    MeasurementResultsMixin,
    MeasurementCalculationMixin,
    CaseExportMixin,
    ScriptedLoadableModuleLogic,
):
    """Own MRML node management, geometric calculations, and export data assembly. Centralizing logic
    here keeps the module deterministic and easier to test, reload, and document.
    """

    def __init__(self) -> None:
        """Initialize caches, visibility state, calibration defaults, and the latest result snapshot.
        The logic owns mutable measurement state so the widget can stay focused on presentation.
        """

        super().__init__()
        self._updating = False
        self._node_cache = {}
        self._dynamic_node_spec_registry = {}
        self._dynamic_other_roles_scene_synced = False
        self._measurement_visibility = {}
        self._snapping_anatomy_curve_points = False
        self._cup_opening_ellipse_control_source = dict.fromkeys(SIDE_KEYS, "points")
        self._morphology_free_pair_station_cache = dict.fromkeys(SIDE_KEYS)
        self.calibration_ball_diameter_mm = float(CALIBRATION_BALL_DIAMETER_MM)
        self.calibration_ball_present = True
        self.annotator_name = ""
        self.latest_results = self._empty_results()
