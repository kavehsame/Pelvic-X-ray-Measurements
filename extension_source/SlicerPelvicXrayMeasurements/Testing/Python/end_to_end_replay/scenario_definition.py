"""Randomizable full-coverage point scenario for Pelvic X-ray Measurements.

The scenario intentionally exercises every built-in measurement family plus repeatable custom line
and angle tools. Bilateral tools are populated on both sides so the exported CSV contains the full
set of rows the extension can produce in a comprehensive use case, and the replay bundle also
covers non-default line, angle, and neck-axis mode combinations inside the same canonical test.
"""
# ruff: noqa: E402, I001

from __future__ import annotations

import math
import random
# Portable synthetic fixture: no product-runtime imports.
class MeasurementKey:
    NECK_AXIS = "neckAxis"
    IMPLANT_NECK_AXIS = "implantNeckAxis"

class OtherAngleLockMode:
    NONE = "none"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"

class SideKey:
    LEFT = "left"
    RIGHT = "right"


def point(x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
    """Create one RAS point tuple."""

    return (float(x), float(y), float(z))


def side_role(side_key: str, base_role: str) -> str:
    """Mirror the extension's bilateral role naming scheme without importing the module itself."""

    return f"{side_key}_{base_role}"


def other_line_role(index: int) -> str:
    """Return the dynamic role name for a custom line."""

    return f"otherLine_{int(index)}"


def other_point_role(index: int) -> str:
    """Return the dynamic role name for a labelled custom point."""

    return f"otherPoint_{int(index)}"


def other_angle_points_role(index: int) -> str:
    """Return the dynamic role name for the point markup of a custom angle."""

    return f"otherAngle_{int(index)}_points"


def circle_points(
    center: tuple[float, float, float],
    radius: float,
    angles_degrees: tuple[float, ...],
) -> list[tuple[float, float, float]]:
    """Sample exact points on a 2D circle in the synthetic image plane."""

    cx, cy, cz = center
    return [
        point(cx + radius * math.cos(math.radians(angle)), cy + radius * math.sin(math.radians(angle)), cz)
        for angle in angles_degrees
    ]


def ellipse_points(
    center: tuple[float, float, float],
    major_radius: float,
    minor_radius: float,
    major_angle_degrees: float,
    sample_angles_degrees: tuple[float, ...],
) -> list[tuple[float, float, float]]:
    """Sample exact points on a 2D ellipse with a rotated major axis."""

    cx, cy, cz = center
    angle_radians = math.radians(major_angle_degrees)
    cos_major = math.cos(angle_radians)
    sin_major = math.sin(angle_radians)
    major_direction = (cos_major, sin_major)
    minor_direction = (-sin_major, cos_major)
    points = []
    for sample_angle in sample_angles_degrees:
        theta = math.radians(sample_angle)
        dx = major_radius * math.cos(theta)
        dy = minor_radius * math.sin(theta)
        x_value = cx + major_direction[0] * dx + minor_direction[0] * dy
        y_value = cy + major_direction[1] * dx + minor_direction[1] * dy
        points.append(point(x_value, y_value, cz))
    return points


def transform_point(
    point_value: tuple[float, float, float],
    scale: float,
    rotation_degrees: float,
    translation_xy: tuple[float, float],
) -> tuple[float, float, float]:
    """Apply one shared 2D similarity transform to a synthetic point.

    The automated test must keep the scenario mathematically coherent while still varying exported
    coordinates between regenerations. A single scale-plus-rotation-plus-translation transform
    preserves all parallel, perpendicular, circular, and elliptical relationships encoded in the
    base scenario, so the extension still receives a fully valid synthetic case.
    """

    x_value, y_value, z_value = point_value
    angle_radians = math.radians(rotation_degrees)
    cos_angle = math.cos(angle_radians)
    sin_angle = math.sin(angle_radians)
    scaled_x = float(x_value) * float(scale)
    scaled_y = float(y_value) * float(scale)
    rotated_x = scaled_x * cos_angle - scaled_y * sin_angle
    rotated_y = scaled_x * sin_angle + scaled_y * cos_angle
    return point(
        rotated_x + float(translation_xy[0]),
        rotated_y + float(translation_xy[1]),
        float(z_value),
    )


def transform_points(
    points: list[tuple[float, float, float]],
    scale: float,
    rotation_degrees: float,
    translation_xy: tuple[float, float],
) -> list[tuple[float, float, float]]:
    """Apply the same transform to a point sequence.

    Keeping one shared transform per regeneration means every tool sees a new coordinate layout,
    while the relative geometry between tools remains internally consistent.
    """

    return [
        transform_point(point_value, scale, rotation_degrees, translation_xy)
        for point_value in points
    ]


def build_randomized_full_scenario(seed: int | None = None) -> dict:
    """Return a randomized-but-valid full synthetic measurement case.

    The base scenario is transformed as a whole rather than being reauthored point by point. In
    practice the automation uses a shared translation only: that is enough to change coordinates
    between regenerations, while also keeping replay exports byte-identical by avoiding the tiny
    floating-point drift that a rotated synthetic case can introduce in recomputed helper geometry.
    """

    if seed is None:
        seed = random.SystemRandom().randrange(1, 2**63)
    rng = random.Random(seed)
    scale = 1.0
    rotation_degrees = 0.0
    translation_xy = (
        float(rng.randint(-120, 120)),
        float(rng.randint(-120, 120)),
    )

    static_role_points = {
        role: transform_points(points, scale, rotation_degrees, translation_xy)
        for role, points in STATIC_ROLE_POINTS.items()
        if role not in SCENARIO_OMITTED_ROLES
    }
    custom_lines = {
        index: {
            "lockMode": line_data["lockMode"],
            "points": transform_points(line_data["points"], scale, rotation_degrees, translation_xy),
        }
        for index, line_data in CUSTOM_LINES.items()
    }
    custom_points = {
        index: {
            "points": transform_points(point_data["points"], scale, rotation_degrees, translation_xy),
        }
        for index, point_data in CUSTOM_POINTS.items()
    }
    custom_angles = {
        index: {
            "lockMode": angle_data["lockMode"],
            "points": transform_points(angle_data["points"], scale, rotation_degrees, translation_xy),
        }
        for index, angle_data in CUSTOM_ANGLES.items()
    }
    return {
        "seed": seed,
        "scale": scale,
        "rotationDegrees": rotation_degrees,
        "translationXY": translation_xy,
        "staticRolePoints": static_role_points,
        "customLines": custom_lines,
        "customPoints": custom_points,
        "customAngles": custom_angles,
        "neckAxisOptions": NECK_AXIS_OPTIONS,
    }


SYNTHETIC_VOLUME = {
    "caseName": "SyntheticFullCase.dcm",
    "dimensions": (2000, 2000, 1),
    "spacing": (1.0, 1.0, 1.0),
    "origin": (-1000.0, -1000.0, 0.0),
}

CALIBRATION_BALL_DIAMETER_MM = 25.0
CALIBRATION_BALL_PRESENT = True

NECK_AXIS_OPTIONS = {
    MeasurementKey.NECK_AXIS: {
        SideKey.LEFT: {"lockToCenter": True, "useSingleGuide": True},
        SideKey.RIGHT: {"lockToCenter": False, "useSingleGuide": False},
    },
    MeasurementKey.IMPLANT_NECK_AXIS: {
        SideKey.LEFT: {"lockToCenter": True, "useSingleGuide": False},
        SideKey.RIGHT: {"lockToCenter": False, "useSingleGuide": True},
    },
}

SCENARIO_OMITTED_ROLES = {
    side_role(SideKey.LEFT, "neckGuideDistal"),
    side_role(SideKey.RIGHT, "implantNeckGuideDistal"),
}


STATIC_ROLE_STAGES = [
    [
        "calibrationPoints",
        "referenceLine",
    ],
    [
        side_role("left", "femurHeadPoints"),
        side_role("right", "femurHeadPoints"),
        side_role("left", "implantHeadPoints"),
        side_role("right", "implantHeadPoints"),
    ],
    [
        side_role("left", "shaftGuideProximal"),
        side_role("left", "shaftGuideDistal"),
        side_role("right", "shaftGuideProximal"),
        side_role("right", "shaftGuideDistal"),
    ],
    [
        side_role("left", "neckGuideProximal"),
        side_role("left", "neckGuideDistal"),
        side_role("left", "implantNeckGuideProximal"),
        side_role("left", "implantNeckGuideDistal"),
        side_role("left", "implantAlignmentGuideProximal"),
        side_role("left", "implantAlignmentGuideDistal"),
        side_role("right", "neckGuideProximal"),
        side_role("right", "neckGuideDistal"),
        side_role("right", "implantNeckGuideProximal"),
        side_role("right", "implantNeckGuideDistal"),
        side_role("right", "implantAlignmentGuideProximal"),
        side_role("right", "implantAlignmentGuideDistal"),
    ],
    [
        side_role("left", "extrusionIndexMedialLine"),
        side_role("left", "extrusionIndexMiddleLine"),
        side_role("left", "extrusionIndexLateralLine"),
        side_role("left", "tonnisAngleLine"),
        side_role("left", "sharpAngleLine"),
        side_role("left", "lceAnglePoint"),
        side_role("left", "acetabularOffsetLineA"),
        side_role("left", "acetabularOffsetLineB"),
        side_role("left", "femoralOffsetLine"),
        side_role("left", "shaftMorphologyLTPoints"),
        side_role("right", "extrusionIndexMedialLine"),
        side_role("right", "extrusionIndexMiddleLine"),
        side_role("right", "extrusionIndexLateralLine"),
        side_role("right", "tonnisAngleLine"),
        side_role("right", "sharpAngleLine"),
        side_role("right", "lceAnglePoint"),
        side_role("right", "acetabularOffsetLineA"),
        side_role("right", "acetabularOffsetLineB"),
        side_role("right", "femoralOffsetLine"),
        side_role("right", "shaftMorphologyLTPoints"),
    ],
    [
        side_role("left", "iliopectinealLine"),
        side_role("left", "ilioischialLine"),
        side_role("left", "shentonLine"),
        side_role("left", "acetabularRoofSourcil"),
        side_role("left", "lineaTerminalis"),
        side_role("right", "iliopectinealLine"),
        side_role("right", "ilioischialLine"),
        side_role("right", "shentonLine"),
        side_role("right", "acetabularRoofSourcil"),
        side_role("right", "lineaTerminalis"),
    ],
    [
        side_role("left", "acetabularInclinationLine"),
        side_role("left", "cupOpeningEllipsePoints"),
        side_role("left", "postOpAcetabularOffsetLineA"),
        side_role("left", "postOpAcetabularOffsetLineB"),
        side_role("left", "postOpFemoralOffsetLine"),
        side_role("right", "acetabularInclinationLine"),
        side_role("right", "cupOpeningEllipsePoints"),
        side_role("right", "postOpAcetabularOffsetLineA"),
        side_role("right", "postOpAcetabularOffsetLineB"),
        side_role("right", "postOpFemoralOffsetLine"),
    ],
    [
        "lldPoints",
    ],
    [
        side_role("left", "shaftMorphologyPoints"),
        side_role("right", "shaftMorphologyPoints"),
    ],
    [
        side_role("left", "femoralShaftContour1"),
        side_role("left", "femoralShaftContour2"),
        side_role("left", "femoralShaftContour3"),
        side_role("left", "femoralShaftContour4"),
        side_role("right", "femoralShaftContour1"),
        side_role("right", "femoralShaftContour2"),
        side_role("right", "femoralShaftContour3"),
        side_role("right", "femoralShaftContour4"),
    ],
]


STATIC_ROLE_POINTS = {
    "calibrationPoints": circle_points(point(0.0, -300.0), 12.5, (180.0, 90.0, 0.0)),
    "referenceLine": [point(-250.0, 0.0), point(250.0, 0.0)],
    "lldPoints": [point(-115.0, 95.0), point(125.0, 82.0)],
    side_role("right", "femurHeadPoints"): circle_points(point(-85.0, -120.0), 30.0, (180.0, 90.0, 30.0)),
    side_role("left", "femurHeadPoints"): circle_points(point(110.0, -112.0), 28.0, (0.0, 90.0, 210.0)),
    side_role("right", "implantHeadPoints"): circle_points(point(-80.0, -118.0), 18.0, (180.0, 90.0, 30.0)),
    side_role("left", "implantHeadPoints"): circle_points(point(118.0, -110.0), 19.0, (0.0, 90.0, 210.0)),
    side_role("right", "shaftGuideProximal"): [point(-165.0, -35.0), point(-75.0, -35.0)],
    side_role("right", "shaftGuideDistal"): [point(-168.0, 95.0), point(-72.0, 95.0)],
    side_role("left", "shaftGuideProximal"): [point(75.0, -40.0), point(175.0, -40.0)],
    side_role("left", "shaftGuideDistal"): [point(74.0, 100.0), point(176.0, 100.0)],
    side_role("right", "neckGuideProximal"): [point(-125.0, -110.0), point(-85.0, -80.0)],
    side_role("right", "neckGuideDistal"): [point(-112.0, -80.0), point(-72.0, -50.0)],
    side_role("left", "neckGuideProximal"): [point(94.1, -74.3), point(135.9, -101.7)],
    side_role("left", "neckGuideDistal"): [point(105.1, -44.3), point(146.9, -71.7)],
    side_role("right", "implantNeckGuideProximal"): [point(-122.0, -116.0), point(-78.0, -94.0)],
    side_role("right", "implantNeckGuideDistal"): [point(-112.0, -83.0), point(-68.0, -61.0)],
    side_role("left", "implantNeckGuideProximal"): [point(100.0, -83.0), point(146.0, -63.0)],
    side_role("left", "implantNeckGuideDistal"): [point(112.0, -48.0), point(158.0, -28.0)],
    side_role("right", "implantAlignmentGuideProximal"): [point(-140.0, -12.2), point(-96.0, -7.8)],
    side_role("right", "implantAlignmentGuideDistal"): [point(-138.0, 107.8), point(-94.0, 112.2)],
    side_role("left", "implantAlignmentGuideProximal"): [point(101.0, -12.4), point(145.0, -17.6)],
    side_role("left", "implantAlignmentGuideDistal"): [point(101.0, 107.6), point(145.0, 102.4)],
    side_role("right", "extrusionIndexMedialLine"): [point(-75.0, -160.0), point(-75.0, -60.0)],
    side_role("right", "extrusionIndexMiddleLine"): [point(-105.0, -160.0), point(-105.0, -60.0)],
    side_role("right", "extrusionIndexLateralLine"): [point(-140.0, -160.0), point(-140.0, -60.0)],
    side_role("left", "extrusionIndexMedialLine"): [point(80.0, -150.0), point(80.0, -55.0)],
    side_role("left", "extrusionIndexMiddleLine"): [point(108.0, -150.0), point(108.0, -55.0)],
    side_role("left", "extrusionIndexLateralLine"): [point(142.0, -150.0), point(142.0, -55.0)],
    side_role("right", "tonnisAngleLine"): [point(-150.0, -30.0), point(-95.0, -50.0)],
    side_role("left", "tonnisAngleLine"): [point(90.0, -28.0), point(150.0, -5.0)],
    side_role("right", "sharpAngleLine"): [point(-150.0, 10.0), point(-100.0, -18.0)],
    side_role("left", "sharpAngleLine"): [point(88.0, 8.0), point(145.0, 30.0)],
    side_role("right", "lceAnglePoint"): [point(-105.0, -145.0)],
    side_role("left", "lceAnglePoint"): [point(98.0, -138.0)],
    side_role("right", "acetabularOffsetLineA"): [point(-170.0, -60.0), point(-170.0, 40.0)],
    side_role("right", "acetabularOffsetLineB"): [point(-105.0, -55.0), point(-105.0, 45.0)],
    side_role("left", "acetabularOffsetLineA"): [point(90.0, -58.0), point(90.0, 42.0)],
    side_role("left", "acetabularOffsetLineB"): [point(148.0, -55.0), point(148.0, 45.0)],
    side_role("right", "femoralOffsetLine"): [point(-60.0, -45.0), point(-60.0, 60.0)],
    side_role("left", "femoralOffsetLine"): [point(178.0, -45.0), point(178.0, 70.0)],
    side_role("right", "shaftMorphologyLTPoints"): [point(-118.0, 18.0), point(-122.0, 38.0)],
    side_role("left", "shaftMorphologyLTPoints"): [point(122.0, 20.0), point(128.0, 40.0)],
    side_role("right", "acetabularInclinationLine"): [point(-165.0, -70.0), point(-110.0, -105.0)],
    side_role("left", "acetabularInclinationLine"): [point(88.0, -82.0), point(146.0, -110.0)],
    side_role("right", "cupOpeningEllipsePoints"): ellipse_points(
        point(-125.0, -40.0), 34.0, 20.0, 18.0, (0.0, 60.0, 120.0, 180.0, 240.0, 300.0)
    ),
    side_role("left", "cupOpeningEllipsePoints"): ellipse_points(
        point(135.0, -30.0), 30.0, 16.0, 33.0, (0.0, 60.0, 120.0, 180.0, 240.0, 300.0)
    ),
    side_role("right", "postOpAcetabularOffsetLineA"): [point(-180.0, -62.0), point(-180.0, 38.0)],
    side_role("right", "postOpAcetabularOffsetLineB"): [point(-120.0, -60.0), point(-120.0, 40.0)],
    side_role("left", "postOpAcetabularOffsetLineA"): [point(82.0, -62.0), point(82.0, 38.0)],
    side_role("left", "postOpAcetabularOffsetLineB"): [point(140.0, -60.0), point(140.0, 40.0)],
    side_role("right", "postOpFemoralOffsetLine"): [point(-68.0, -50.0), point(-68.0, 58.0)],
    side_role("left", "postOpFemoralOffsetLine"): [point(173.0, -48.0), point(173.0, 65.0)],
    side_role("right", "iliopectinealLine"): [
        point(-170.0, -135.0),
        point(-146.0, -106.0),
        point(-123.0, -78.0),
        point(-96.0, -52.0),
    ],
    side_role("left", "iliopectinealLine"): [
        point(82.0, -130.0),
        point(108.0, -98.0),
        point(133.0, -65.0),
        point(160.0, -32.0),
    ],
    side_role("right", "ilioischialLine"): [
        point(-104.0, -120.0),
        point(-118.0, -70.0),
        point(-124.0, -20.0),
        point(-130.0, 35.0),
    ],
    side_role("left", "ilioischialLine"): [
        point(112.0, -118.0),
        point(124.0, -68.0),
        point(134.0, -18.0),
        point(142.0, 38.0),
    ],
    side_role("right", "shentonLine"): [
        point(-155.0, -58.0),
        point(-132.0, -70.0),
        point(-105.0, -72.0),
        point(-78.0, -62.0),
    ],
    side_role("left", "shentonLine"): [
        point(76.0, -56.0),
        point(103.0, -68.0),
        point(130.0, -66.0),
        point(156.0, -52.0),
    ],
    side_role("right", "acetabularRoofSourcil"): [
        point(-158.0, -84.0),
        point(-138.0, -102.0),
        point(-115.0, -108.0),
        point(-94.0, -98.0),
    ],
    side_role("left", "acetabularRoofSourcil"): [
        point(88.0, -86.0),
        point(112.0, -104.0),
        point(136.0, -106.0),
        point(158.0, -92.0),
    ],
    side_role("right", "lineaTerminalis"): [
        point(-192.0, -42.0),
        point(-166.0, -16.0),
        point(-138.0, 6.0),
        point(-108.0, 28.0),
    ],
    side_role("left", "lineaTerminalis"): [
        point(72.0, -40.0),
        point(101.0, -12.0),
        point(132.0, 10.0),
        point(164.0, 32.0),
    ],
    side_role("right", "femoralShaftContour1"): [
        point(-158.0, -6.0),
        point(-160.0, 28.0),
        point(-162.0, 72.0),
        point(-164.0, 116.0),
    ],
    side_role("right", "femoralShaftContour2"): [
        point(-134.0, -5.0),
        point(-136.0, 29.0),
        point(-138.0, 72.0),
        point(-140.0, 115.0),
    ],
    side_role("right", "femoralShaftContour3"): [
        point(-101.0, -4.0),
        point(-101.0, 30.0),
        point(-102.0, 74.0),
        point(-103.0, 116.0),
    ],
    side_role("right", "femoralShaftContour4"): [
        point(-74.0, -5.0),
        point(-73.0, 30.0),
        point(-72.0, 75.0),
        point(-71.0, 117.0),
    ],
    side_role("left", "femoralShaftContour1"): [
        point(78.0, -4.0),
        point(77.0, 31.0),
        point(76.0, 75.0),
        point(75.0, 118.0),
    ],
    side_role("left", "femoralShaftContour2"): [
        point(104.0, -5.0),
        point(104.0, 30.0),
        point(105.0, 73.0),
        point(106.0, 116.0),
    ],
    side_role("left", "femoralShaftContour3"): [
        point(137.0, -6.0),
        point(139.0, 29.0),
        point(141.0, 72.0),
        point(143.0, 115.0),
    ],
    side_role("left", "femoralShaftContour4"): [
        point(164.0, -5.0),
        point(166.0, 30.0),
        point(168.0, 74.0),
        point(170.0, 118.0),
    ],
}


# The new wall curves extend the fixed contour scenario without changing any
# existing measurement inputs. They do not seed the shared sourcil landmarks.
for _side in ("left", "right"):
    for _wall, _dy in (("anterior", -8.0), ("posterior", 8.0)):
        _role = side_role(_side, f"{_wall}AcetabularWall")
        STATIC_ROLE_POINTS[_role] = [
            point(x, y + _dy, z)
            for x, y, z in STATIC_ROLE_POINTS[side_role(_side, "acetabularRoofSourcil")]
        ]
        STATIC_ROLE_STAGES[-2].append(_role)


CUSTOM_LINES = {
    1: {
        "lockMode": OtherAngleLockMode.NONE,
        "points": [point(-220.0, 140.0), point(-160.0, 170.0)],
    },
    2: {
        "lockMode": OtherAngleLockMode.PARALLEL,
        "points": [point(160.0, 150.0), point(215.0, 150.0)],
    },
    3: {
        "lockMode": OtherAngleLockMode.PERPENDICULAR,
        "points": [point(230.0, 110.0), point(230.0, 170.0)],
    },
}

CUSTOM_POINTS = {
    1: {
        "points": [point(-255.0, 225.0)],
    },
    2: {
        "points": [point(248.0, 218.0)],
    },
}

CUSTOM_ANGLES = {
    1: {
        "lockMode": OtherAngleLockMode.NONE,
        "points": [point(-220.0, -200.0), point(-180.0, -180.0), point(-145.0, -220.0)],
    },
    2: {
        "lockMode": OtherAngleLockMode.PARALLEL,
        "points": [point(-40.0, 160.0), point(0.0, 160.0), point(22.0, 128.0)],
    },
    3: {
        "lockMode": OtherAngleLockMode.PERPENDICULAR,
        "points": [point(60.0, 140.0), point(60.0, 180.0), point(92.0, 202.0)],
    },
}


REPLAY_EDITABLE_ROLE_STAGES = [
    stage[:] for stage in STATIC_ROLE_STAGES
] + [
    [other_point_role(1), other_point_role(2)],
    [other_line_role(1), other_line_role(2), other_line_role(3)],
    [
        other_angle_points_role(1),
        other_angle_points_role(2),
        other_angle_points_role(3),
    ],
]
