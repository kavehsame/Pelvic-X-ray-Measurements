"""Constants and measurement metadata for the Pelvic X-ray Measurements Slicer module.

Keeping stable names, role groups, and measurement ordering outside the widget/logic code makes the
module easier to audit and reduces coupling between UI layout, MRML node management, and geometry.
"""
from __future__ import annotations

import os
import re
from enum import Enum


class StringEnum(str, Enum):
    """Compatibility-safe string enum for Slicer's Python runtime.

    The module passes these identifiers through Qt, MRML attributes, CSV, and JSON. Keeping enum
    members as `str` subclasses preserves those integrations while avoiding project-wide free-form
    identifier strings.
    """

    def __str__(self) -> str:
        """Return the serialized string value used by UI, MRML, CSV, and JSON layers."""

        return str(self.value)


class SideKey(StringEnum):
    """Stable identifiers for bilateral left/right measurement state."""

    LEFT = "left"
    RIGHT = "right"


class MeasurementKey(StringEnum):
    """Stable identifiers for logical measurement families throughout the module."""

    CALIBRATION = "calibration"
    REFERENCE_LINE = "referenceLine"
    LLD = "lld"
    ILIOPECTINEAL_LINE = "iliopectinealLine"
    ILIOISCHIAL_LINE = "ilioischialLine"
    SHENTON_LINE = "shentonLine"
    ACETABULAR_ROOF_SOURCIL = "acetabularRoofSourcil"
    LINEA_TERMINALIS = "lineaTerminalis"
    FEMORAL_SHAFT_CONTOUR = "femoralShaftContour"
    OTHER_POINT = "otherPoint"
    OTHER_LINE = "otherLine"
    OTHER_ANGLE = "otherAngle"
    FEMUR_HEAD = "femurHead"
    SHAFT_AXIS = "shaftAxis"
    NECK_AXIS = "neckAxis"
    IMPLANT_NECK_AXIS = "implantNeckAxis"
    TONNIS_ANGLE = "tonnisAngle"
    SHARP_ANGLE = "sharpAngle"
    LCE_ANGLE = "lceAngle"
    ACETABULAR_OFFSET = "acetabularOffset"
    FEMORAL_OFFSET = "femoralOffset"
    EXTRUSION_INDEX = "extrusionIndex"
    FEMUR_SHAFT_MORPHOLOGY = "femurShaftMorphology"
    IMPLANT_HEAD = "implantHead"
    INCLINATION_ANGLE = "inclinationAngle"
    CUP_OPENING_ELLIPSE_FIT = "cupOpeningEllipseFit"
    POSTOP_ACETABULAR_OFFSET = "postOpAcetabularOffset"
    POSTOP_FEMORAL_OFFSET = "postOpFemoralOffset"
    IMPLANT_ALIGNMENT = "implantAlignment"


class OtherAngleLockMode(StringEnum):
    """Stable identifiers for how a custom `Others` measurement constrains itself to the reference line.

    The enum name is kept for backward compatibility because saved scenes, exports, and tests
    already import it under this identifier.
    """

    NONE = "none"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"

LIB_DIR = os.path.dirname(__file__)
MODULE_DIR = os.path.dirname(LIB_DIR)

MODULE_NAME = "PelvicXrayMeasurements"
MODULE_VERSION = "V1.6.1"
ROLE_ATTRIBUTE = f"{MODULE_NAME}.Role"
ACTIVE_SIDE_BADGE_ROLE = "activeSideBadge"
CALIBRATION_BALL_DIAMETER_MM = 25.0
AXIS_LOCK_TO_CENTER_ATTRIBUTE = f"{MODULE_NAME}.AxisLockToCenter"
AXIS_USE_SINGLE_GUIDE_ATTRIBUTE = f"{MODULE_NAME}.AxisUseSingleGuide"
CASE_COMMENTS_ATTRIBUTE = f"{MODULE_NAME}.CaseComments"
CASE_EXPORT_TIMESTAMP_ATTRIBUTE = f"{MODULE_NAME}.CaseExportTimestamp"
LEGACY_MODULE_NAMES = ("HipXrayMeasurements",)
LEGACY_ROLE_ATTRIBUTES = tuple(f"{module_name}.Role" for module_name in LEGACY_MODULE_NAMES)
LEGACY_CASE_COMMENTS_ATTRIBUTES = tuple(
    f"{module_name}.CaseComments" for module_name in LEGACY_MODULE_NAMES
)
LEGACY_CASE_EXPORT_TIMESTAMP_ATTRIBUTES = tuple(
    f"{module_name}.CaseExportTimestamp" for module_name in LEGACY_MODULE_NAMES
)
MORPHOLOGY_REFERENCE_IMAGE_PATH = os.path.join(
    MODULE_DIR,
    "Resources",
    "morphology_parameters_pothong_2023.png",
)
MORPHOLOGY_REFERENCE_CITATION = (
    "Pothong W, Adulkasem N. Comparative evaluation of radiographic morphologic "
    "parameters for predicting subsequent contralateral fragility hip fracture. "
    "International Orthopaedics. 2023;47:1837–1843. "
    "https://doi.org/10.1007/s00264-023-05789-8"
)
EPSILON = 1e-6
# Keeps constrained helper lines visible when their effective length would otherwise collapse to zero.
DEFAULT_CONSTRUCTION_LINE_LENGTH_SU = 40.0
DEFAULT_CURVE_POINTS_PER_INTERPOLATING_SEGMENT = 30
SIDE_KEYS = (SideKey.LEFT, SideKey.RIGHT)
SIDE_LABELS = {
    SideKey.LEFT: "Left",
    SideKey.RIGHT: "Right",
}
OTHER_ANGLE_LOCK_ATTRIBUTE = f"{MODULE_NAME}.OtherAngleLockToReference"
OTHER_LINE_LOCK_ATTRIBUTE = f"{MODULE_NAME}.OtherLineLockToReference"
FEMORAL_SHAFT_CONTOUR_CLASS_ATTRIBUTE = f"{MODULE_NAME}.FemoralShaftContourClass"
FEMORAL_SHAFT_CONTOUR_BASE_ROLES = (
    "femoralShaftContour1",
    "femoralShaftContour2",
    "femoralShaftContour3",
    "femoralShaftContour4",
)
ANATOMY_EDGE_CONTOUR_ROLES = (
    "iliopectinealLine",
    "ilioischialLine",
    "shentonLine",
    "acetabularRoofSourcil",
    "lineaTerminalis",
    *FEMORAL_SHAFT_CONTOUR_BASE_ROLES,
)
FEMORAL_SHAFT_CONTOUR_CLASS_LABELS = {
    "medialOuter": "Medial Outer Cortex",
    "medialInner": "Medial Inner Cortex",
    "lateralInner": "Lateral Inner Cortex",
    "lateralOuter": "Lateral Outer Cortex",
}
ANATOMY_EDGE_CONTOUR_SNAP_RADIUS_PX = 6
ANATOMY_EDGE_CONTOUR_SNAP_SIGMA_PX = 3.0
ANATOMY_EDGE_CONTOUR_MIN_EDGE_ZSCORE = 1.0
OTHER_POINT_ROLE_PATTERN = re.compile(r"^otherPoint_(\d+)$")
OTHER_LINE_ROLE_PATTERN = re.compile(r"^otherLine_(\d+)$")
OTHER_ANGLE_POINTS_ROLE_PATTERN = re.compile(r"^otherAngle_(\d+)_points$")
OTHER_ANGLE_REFERENCE_ARM_ROLE_PATTERN = re.compile(r"^otherAngle_(\d+)_referenceArm$")
OTHER_ANGLE_FREE_ARM_ROLE_PATTERN = re.compile(r"^otherAngle_(\d+)_freeArm$")

GLOBAL_MEASUREMENT_KEYS = (
    MeasurementKey.CALIBRATION,
    MeasurementKey.REFERENCE_LINE,
    MeasurementKey.LLD,
    MeasurementKey.OTHER_POINT,
    MeasurementKey.OTHER_LINE,
    MeasurementKey.OTHER_ANGLE,
)

NECK_AXIS_MEASUREMENT_KEYS = (
    MeasurementKey.NECK_AXIS,
    MeasurementKey.IMPLANT_NECK_AXIS,
)

SIDE_MEASUREMENT_KEYS = (
    MeasurementKey.FEMUR_HEAD,
    MeasurementKey.SHAFT_AXIS,
    MeasurementKey.NECK_AXIS,
    MeasurementKey.IMPLANT_NECK_AXIS,
    MeasurementKey.TONNIS_ANGLE,
    MeasurementKey.SHARP_ANGLE,
    MeasurementKey.LCE_ANGLE,
    MeasurementKey.ACETABULAR_OFFSET,
    MeasurementKey.FEMORAL_OFFSET,
    MeasurementKey.EXTRUSION_INDEX,
    MeasurementKey.FEMUR_SHAFT_MORPHOLOGY,
    MeasurementKey.IMPLANT_HEAD,
    MeasurementKey.INCLINATION_ANGLE,
    MeasurementKey.CUP_OPENING_ELLIPSE_FIT,
    MeasurementKey.POSTOP_ACETABULAR_OFFSET,
    MeasurementKey.POSTOP_FEMORAL_OFFSET,
    MeasurementKey.IMPLANT_ALIGNMENT,
    MeasurementKey.ILIOPECTINEAL_LINE,
    MeasurementKey.ILIOISCHIAL_LINE,
    MeasurementKey.SHENTON_LINE,
    MeasurementKey.ACETABULAR_ROOF_SOURCIL,
    MeasurementKey.LINEA_TERMINALIS,
    MeasurementKey.FEMORAL_SHAFT_CONTOUR,
)

MEASUREMENT_ROLE_GROUPS = {
    MeasurementKey.CALIBRATION: ["calibrationPoints", "calibrationCircle"],
    MeasurementKey.REFERENCE_LINE: ["referenceLine"],
    MeasurementKey.LLD: [
        "lldPoints",
        "lldLeftProjection",
        "lldRightProjection",
        "lldLeftParallel",
        "lldRightParallel",
        "lldHeightDifference",
    ],
    MeasurementKey.ILIOPECTINEAL_LINE: ["iliopectinealLine"],
    MeasurementKey.ILIOISCHIAL_LINE: ["ilioischialLine"],
    MeasurementKey.SHENTON_LINE: ["shentonLine"],
    MeasurementKey.ACETABULAR_ROOF_SOURCIL: ["acetabularRoofSourcil"],
    MeasurementKey.LINEA_TERMINALIS: ["lineaTerminalis"],
    MeasurementKey.FEMORAL_SHAFT_CONTOUR: list(FEMORAL_SHAFT_CONTOUR_BASE_ROLES),
    MeasurementKey.FEMUR_HEAD: ["femurHeadPoints", "femurHeadCenter", "femurHeadCircle"],
    MeasurementKey.SHAFT_AXIS: ["shaftGuideProximal", "shaftGuideDistal", "shaftAxis"],
    MeasurementKey.NECK_AXIS: ["neckGuideProximal", "neckGuideDistal", "neckAxis"],
    MeasurementKey.IMPLANT_NECK_AXIS: ["implantNeckGuideProximal", "implantNeckGuideDistal", "implantNeckAxis"],
    MeasurementKey.TONNIS_ANGLE: ["tonnisAngleLine", "tonnisAngleReferenceArm"],
    MeasurementKey.SHARP_ANGLE: ["sharpAngleLine", "sharpAngleReferenceArm"],
    MeasurementKey.LCE_ANGLE: ["lceAnglePoint", "lceAngleVisual", "lceAngleRadialArm"],
    MeasurementKey.ACETABULAR_OFFSET: ["acetabularOffsetLineA", "acetabularOffsetLineB"],
    MeasurementKey.FEMORAL_OFFSET: ["femoralOffsetLine"],
    MeasurementKey.EXTRUSION_INDEX: [
        "extrusionIndexMedialLine",
        "extrusionIndexMiddleLine",
        "extrusionIndexLateralLine",
    ],
    MeasurementKey.FEMUR_SHAFT_MORPHOLOGY: [
        "shaftMorphologyLTPoints",
        "shaftMorphologyMidline",
        "shaftMorphologyPoints",
        "shaftMorphologyGuideLineA",
        "shaftMorphologyGuideLineB",
    ],
    MeasurementKey.IMPLANT_HEAD: ["implantHeadPoints", "implantHeadCenter", "implantHeadCircle"],
    MeasurementKey.INCLINATION_ANGLE: ["acetabularInclinationLine"],
    MeasurementKey.CUP_OPENING_ELLIPSE_FIT: [
        "cupOpeningEllipsePoints",
        "cupOpeningEllipse",
        "cupOpeningEllipseMajorDiameter",
        "cupOpeningEllipseMinorDiameter",
    ],
    MeasurementKey.POSTOP_ACETABULAR_OFFSET: [
        "postOpAcetabularOffsetLineA",
        "postOpAcetabularOffsetLineB",
    ],
    MeasurementKey.POSTOP_FEMORAL_OFFSET: ["postOpFemoralOffsetLine"],
    MeasurementKey.IMPLANT_ALIGNMENT: [
        "implantAlignmentGuideProximal",
        "implantAlignmentGuideDistal",
        "implantAlignmentLine",
    ],
    MeasurementKey.OTHER_POINT: [],
    MeasurementKey.OTHER_LINE: [],
    MeasurementKey.OTHER_ANGLE: [],
}

MEASUREMENT_RESULT_GROUPS = {
    MeasurementKey.CALIBRATION: ("global", "calibration"),
    MeasurementKey.REFERENCE_LINE: ("global", "referenceLine"),
    MeasurementKey.LLD: ("global", "lld"),
    MeasurementKey.FEMUR_HEAD: ("side", "femurHead"),
    MeasurementKey.SHAFT_AXIS: ("side", "femoralShaftAxis"),
    MeasurementKey.NECK_AXIS: ("side", "femoralNeckAxis"),
    MeasurementKey.IMPLANT_NECK_AXIS: ("side", "implantNeckAxis"),
    MeasurementKey.TONNIS_ANGLE: ("side", "tonnisAngle"),
    MeasurementKey.SHARP_ANGLE: ("side", "sharpAngle"),
    MeasurementKey.LCE_ANGLE: ("side", "lceAngle"),
    MeasurementKey.ACETABULAR_OFFSET: ("side", "acetabularOffset"),
    MeasurementKey.FEMORAL_OFFSET: ("side", "femoralOffset"),
    MeasurementKey.EXTRUSION_INDEX: ("side", "femoralHeadExtrusionIndex"),
    MeasurementKey.FEMUR_SHAFT_MORPHOLOGY: ("side", "femurShaftMorphology"),
    MeasurementKey.IMPLANT_HEAD: ("side", "implantHead"),
    MeasurementKey.INCLINATION_ANGLE: ("side", "acetabularInclinationAngle"),
    MeasurementKey.CUP_OPENING_ELLIPSE_FIT: ("side", "cupOpeningEllipseInclinationAngle"),
    MeasurementKey.POSTOP_ACETABULAR_OFFSET: ("side", "postOpAcetabularOffset"),
    MeasurementKey.POSTOP_FEMORAL_OFFSET: ("side", "postOpFemoralOffset"),
    MeasurementKey.IMPLANT_ALIGNMENT: ("side", "implantAlignment"),
}

IMAGE_OVERLAY_SIDE_ORDER = (SideKey.RIGHT, SideKey.LEFT)
IMAGE_OVERLAY_ENTRIES_PER_LINE = 4
FEMUR_SHAFT_MORPHOLOGY_MIDLINE_HALF_WIDTH_MM = 32.0
FEMUR_SHAFT_MORPHOLOGY_LAYOUT = (
    ("2cmAbove_A", 20.0, -20.0),
    ("2cmAbove_B", 20.0, 20.0),
    ("3cmBelow_A", -30.0, -20.0),
    ("3cmBelow_B", -30.0, 20.0),
    ("10cmBelow_OuterA", -100.0, -32.0),
    ("10cmBelow_InnerA", -100.0, -12.0),
    ("10cmBelow_InnerB", -100.0, 12.0),
    ("10cmBelow_OuterB", -100.0, 32.0),
    ("11cmBelow_A", -110.0, -20.0),
    ("11cmBelow_B", -110.0, 20.0),
)
FEMUR_SHAFT_MORPHOLOGY_GUIDE_A_INDICES = (2, 5)
FEMUR_SHAFT_MORPHOLOGY_GUIDE_B_INDICES = (3, 6)
FEMUR_SHAFT_MORPHOLOGY_FREE_POINT_INDICES = (8, 9)
IMAGE_OVERLAY_MEASUREMENT_ORDER = (
    ("globalLength", "calibration", "Cal"),
    ("globalLength", "referenceLine", "Ref"),
    ("sideLength", "femurHead", "Head"),
    ("sideAngle", "ccdAngle", "CCD"),
    ("sideAngle", "tonnisAngle", "Acetabular Index (Tönnis)"),
    ("sideAngle", "sharpAngle", "Sharp"),
    ("sideAngle", "lceAngle", "LCE"),
    ("sideLength", "acetabularOffset", "AO"),
    ("sideLength", "femoralOffset", "FO"),
    ("sideLength", "preopGlobalOffset", "GO"),
    ("sidePercent", "femoralHeadExtrusionIndex", "FEI"),
    ("sideRatio", "corticalCalcarRatio", "CCR"),
    ("sideRatio", "canalThicknessIndex", "CTI"),
    ("sideRatio", "canalFlareIndex", "CFI"),
    ("globalLength", "lld", "LLD"),
    ("sideLength", "implantHead", "ImplHead"),
    ("sideAngle", "acetabularInclinationAngle", "Incl FH"),
    ("sideAngle", "cupOpeningEllipseInclinationAngle", "Incl E"),
    ("sideAngle", "cupOpeningAnteversionRetroversionAngle", "Cup A/R"),
    ("sideAngle", "implantFemoralCCD", "Impl CCD"),
    ("sideAngle", "implantAlignment", "Stem"),
    ("sideLength", "postOpAcetabularOffset", "THA AO"),
    ("sideLength", "postOpFemoralOffset", "THA FO"),
    ("sideLength", "postOpGlobalOffset", "THA GO"),
)
