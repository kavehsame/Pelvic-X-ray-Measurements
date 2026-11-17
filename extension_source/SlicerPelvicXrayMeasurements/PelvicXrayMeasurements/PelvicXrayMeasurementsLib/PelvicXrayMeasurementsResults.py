"""Result-state factories for Pelvic X-ray Measurements.

The logic stores every derived value in one nested dictionary. Keeping the default schema in one
small mixin makes result consumers explicit and prevents UI/export code from inventing missing keys.
"""
from __future__ import annotations

from PelvicXrayMeasurementsConstants import SIDE_KEYS

ResultMap = dict[str, object]


class MeasurementResultsMixin:
    """Provide result-schema behavior for the main logic class."""

    def _empty_side_results(self) -> ResultMap:
        """Create the default result structure for one side. A complete schema is used so the UI and
        export code can read results without constant key-existence checks.
        """

        return {
            "femurHead": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
                "center": None,
                "normal": None,
            },
            "implantHead": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
                "center": None,
                "normal": None,
            },
            "femoralShaftAxis": {
                "defined": False,
                "origin": None,
                "direction": None,
                "endpoints": [],
                "deviationGuideA": None,
                "deviationGuideB": None,
            },
            "femoralShaftContours": {
                "defined": False,
                "classifications": {},
                "records": [],
            },
            "femoralNeckAxis": {
                "defined": False,
                "origin": None,
                "direction": None,
                "endpoints": [],
                "deviationGuideA": None,
                "deviationGuideB": None,
            },
            "implantNeckAxis": {
                "defined": False,
                "origin": None,
                "direction": None,
                "endpoints": [],
                "deviationGuideA": None,
                "deviationGuideB": None,
            },
            "implantStemAxis": {
                "defined": False,
                "origin": None,
                "direction": None,
                "endpoints": [],
                "deviationGuideA": None,
                "deviationGuideB": None,
            },
            "ccdAngle": {
                "defined": False,
                "rawValue": None,
            },
            "implantFemoralCCD": {
                "defined": False,
                "rawValue": None,
            },
            "acetabularOffset": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
            },
            "femoralOffset": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
            },
            "preopGlobalOffset": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
            },
            "femoralHeadExtrusionIndex": {
                "defined": False,
                "rawValue": None,
            },
            "femurShaftMorphology": {
                "defined": False,
                "midline": [],
                "points": [],
                "guideLineA": [],
                "guideLineB": [],
            },
            "corticalCalcarRatio": {
                "defined": False,
                "rawValue": None,
            },
            "canalThicknessIndex": {
                "defined": False,
                "rawValue": None,
            },
            "canalFlareIndex": {
                "defined": False,
                "rawValue": None,
            },
            "acetabularInclinationAngle": {
                "defined": False,
                "rawValue": None,
            },
            "cupOpeningEllipseFit": {
                "defined": False,
                "center": None,
                "majorRadius": None,
                "minorRadius": None,
                "majorDirection": None,
                "minorDirection": None,
                "majorEndpoints": [],
                "minorEndpoints": [],
            },
            "cupOpeningEllipseInclinationAngle": {
                "defined": False,
                "rawValue": None,
            },
            "cupOpeningAnteversionRetroversionAngle": {
                "defined": False,
                "rawValue": None,
            },
            "postOpAcetabularOffset": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
            },
            "postOpFemoralOffset": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
            },
            "postOpGlobalOffset": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
            },
            "implantAlignment": {
                "defined": False,
                "rawValue": None,
            },
            "tonnisAngle": {
                "defined": False,
                "rawValue": None,
            },
            "sharpAngle": {
                "defined": False,
                "rawValue": None,
            },
            "lceAngle": {
                "defined": False,
                "rawValue": None,
            },
        }

    def _empty_results(self) -> ResultMap:
        """Create the full default result structure for the current case. Rebuilding results from
        scratch on each update keeps derived state deterministic.
        """

        return {
            "calibration": {
                "ballPresent": self.calibration_ball_present,
                "defined": False,
                "knownDiameterMm": self.calibration_ball_diameter_mm,
                "rawDiameter": None,
                "scaleFactor": None,
                "center": None,
                "normal": None,
            },
            "referenceLine": {
                "defined": False,
                "rawLength": None,
                "correctedLength": None,
                "points": [],
                "direction": None,
            },
            "sides": {
                side_key: self._empty_side_results() for side_key in SIDE_KEYS
            },
            "lld": {
                "defined": False,
                "rawValue": None,
                "correctedValue": None,
                "signedRawValue": None,
                "signedCorrectedValue": None,
                "leftProjection": None,
                "rightProjection": None,
            },
            "otherLines": [],
            "otherPoints": [],
            "otherAngles": [],
        }
