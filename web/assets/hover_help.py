"""Concise web hover text; full workflows are in the user manual."""

HELP = {
    "calibration": (
        "Calibration Ball",
        "Enter the known ball diameter, then place three points around its boundary.",
    ),
    "reference": (
        "Reference Line",
        "Draw between the teardrops whenever feasible. A line at the ischial tuberosities can "
        "reduce Smart Point Placement accuracy.",
    ),
    "femur_head": (
        "Femur Head",
        "Place three points around the native femoral head to fit its circle and center.",
    ),
    "shaft_axis": (
        "Femoral Shaft Axis",
        "Place two transverse shaft-width guides: proximal, then distal. Each guide needs two "
        "endpoints.",
    ),
    "neck_axis": (
        "Femoral Neck Axis",
        "Place two neck-width guides, or one with Use single guide. Lock to center requires a "
        "fitted head.",
    ),
    "tonnis": (
        "Acetabular Index (Tönnis)",
        "Place the medial sourcil/base point, then the lateral sourcil. The reference arm is drawn "
        "automatically.",
    ),
    "sharp": (
        "Sharp Angle",
        "Place the teardrop/base point, then the lateral sourcil. The reference arm is drawn "
        "automatically.",
    ),
    "lce": ("LCE Angle", "Fit the native head, then place the lateral sourcil point."),
    "acetabular_offset": (
        "Acetabular Offset",
        "Place two guides at the medial pelvic landmark and head-center level.",
    ),
    "femoral_offset": (
        "Femoral Offset",
        "Place a two-point guide at head-center level; its midpoint supplies the offset "
        "landmark.",
    ),
    "extrusion": (
        "Femoral Head Extrusion Index",
        "Place three guides: medial head tangent, lateral sourcil, then lateral head tangent.",
    ),
    "morphology": (
        "Femur Shaft Morphology",
        "After calibration and shaft axis, place two lesser-trochanter points. Adjust the "
        "cortex controls to the shaft boundaries.",
    ),
    "lld": (
        "Leg Length Discrepancy",
        "Place corresponding lesser-trochanter landmarks on both sides to compare their "
        "reference-perpendicular heights.",
    ),
    "implant_head": (
        "Implant Head Center",
        "Place three points around the implant head to fit its circle and center.",
    ),
    "inclination": (
        "Acetabular Inclination Angle (Free Hand)",
        "Draw a two-point line across the cup opening to measure inclination.",
    ),
    "cup_opening": (
        "Cup Opening Ellipse Fit",
        "Place six points around the cup rim. The ellipse gives inclination and version "
        "magnitude, not anteversion/retroversion sign.",
    ),
    "implant_neck": (
        "Implant Neck Axis",
        "Place one or two transverse neck guides. Lock to center requires the implant head; "
        "smart placement selects both options.",
    ),
    "stem_alignment": (
        "Stem Alignment",
        "Place proximal and distal stem-width guides, two endpoints each. Their axis is "
        "compared with the shaft axis.",
    ),
    "post_acetabular_offset": (
        "Postoperative Acetabular Offset",
        "Place two postoperative guides at the pelvic landmark and implant-head level.",
    ),
    "post_femoral_offset": (
        "Postoperative Femoral Offset",
        "Place a two-point guide at implant-head level; its midpoint supplies the "
        "offset landmark.",
    ),
    "other_point": (
        "Point",
        "Add a numbered point. Adjust Point count to add or remove points.",
    ),
    "other_line": (
        "Line",
        "Place two endpoints. Choose any reference lock before placement; drag endpoints to "
        "adjust.",
    ),
    "other_angle": (
        "Angle",
        "Place first arm point, vertex, then second arm point. Choose any reference lock "
        "before placement.",
    ),
    "iliopectineal": (
        "Iliopectineal Line",
        "Trace the anterior column. Right-click or Escape finishes; drag points to refine.",
    ),
    "ilioischial": (
        "Ilioischial Line",
        "Trace the posterior column. Right-click or Escape finishes; drag points to refine.",
    ),
    "shenton": (
        "Shenton Line",
        "Trace the obturator-to-inferomedial-neck arc. Right-click or Escape finishes.",
    ),
    "sourcil": (
        "Acetabular Roof (Sourcil)",
        "Trace the roof from medial to lateral. Its lateral point can seed shared landmarks. "
        "Right-click or Escape finishes.",
    ),
    "linea_terminalis": (
        "Linea Terminalis",
        "Trace the pelvic brim. Right-click or Escape finishes; check points against the "
        "image.",
    ),
    "shaft_contour": (
        "Femoral Shaft",
        "Trace four cortex contours. After two or more points, right-click to advance; "
        "Escape or clicking the tool also advances.",
    ),
}

RESULTS = {
    "head": ("Native Head Diameter", "Diameter of the fitted native-head circle."),
    "ccd": ("CCD Angle", "Obtuse angle between native neck and shaft axes."),
    "tonnis": (
        "Acetabular Index (Tönnis)",
        "Signed sourcil angle relative to the pelvic reference.",
    ),
    "sharp": (
        "Sharp Angle",
        "Signed base-to-sourcil angle relative to the pelvic reference.",
    ),
    "lce": (
        "LCE Angle",
        "Signed head-center-to-sourcil angle from the superior reference perpendicular.",
    ),
    "acetabular_offset": (
        "Acetabular Offset",
        "Guide separation projected along the pelvic reference.",
    ),
    "femoral_offset": (
        "Femoral Offset",
        "Perpendicular distance from the native-head landmark to the shaft axis.",
    ),
    "global_offset": ("Global Offset", "Native acetabular offset + femoral offset."),
    "extrusion": (
        "Femoral Head Extrusion Index",
        "Uncovered lateral head width / total head width, as a percentage.",
    ),
    "ccr": (
        "CCR",
        "B/A: inner canal width 10 cm below the lesser trochanter / proximal guide-cap width at its "
        "level.",
    ),
    "cti": (
        "CTI",
        "At 10 cm below the lesser trochanter: (outer shaft width − inner canal width) / outer shaft "
        "width.",
    ),
    "cfi": (
        "CFI",
        "Inner canal width 2 cm above the lesser trochanter / width 10 cm below it.",
    ),
    "implant_head": (
        "Implant Head Diameter",
        "Diameter of the fitted implant-head circle.",
    ),
    "inclination": (
        "Free-hand Cup Inclination",
        "Acute cup-opening angle relative to the pelvic reference.",
    ),
    "ellipse_inclination": (
        "Ellipse Cup Inclination",
        "Cup inclination from the fitted opening ellipse.",
    ),
    "cup_version": (
        "Cup Ante/Retroversion",
        "Cup version magnitude from the ellipse. Anteversion/retroversion sign requires other "
        "information.",
    ),
    "implant_ccd": (
        "Implant CCD Angle",
        "Obtuse angle between implant-neck and shaft axes.",
    ),
    "stem_alignment": ("Stem Alignment", "Angle between stem and shaft axes."),
    "post_acetabular_offset": (
        "Postoperative Acetabular Offset",
        "Postoperative guide separation projected along the pelvic reference.",
    ),
    "post_femoral_offset": (
        "Postoperative Femoral Offset",
        "Perpendicular distance from the implant-head landmark to the shaft axis.",
    ),
    "post_global_offset": (
        "Postoperative Global Offset",
        "Postoperative acetabular offset + femoral offset.",
    ),
    "calibration": (
        "Calibration",
        "Fitted ball size and the scale used to convert lengths to millimetres.",
    ),
    "reference": ("Reference", "Status and direction of the pelvic reference line."),
    "lld": (
        "Leg Length Discrepancy",
        "Absolute difference in lesser-trochanter heights perpendicular to the reference.",
    ),
    "custom": (
        "Custom Measurement",
        "Coordinates, length or angle of a numbered custom measurement.",
    ),
}
