# Pelvic Xray Measurements — User Manual

**Research use only.** This software is a research tool, not a medical device. It is not intended for diagnosis, treatment planning or other clinical decision-making.

A validation study is being performed to compare the tool with established medical
software. Completed clinical validation is not claimed.

## Version changelog

### V1.8.0

- Add straight and stepped femoral neck cuts, a movable bone fragment and 794 calibrated AP implant templates.
- Add an independent cup-shell circle and a single-film estimate of inlay wear.
- Restore editable annotations by their recorded names and point indices when reading earlier or reordered PXM CSVs.

### V1.7.1

- Matches the version of the web release.

### V1.7.0

- Render annotation exports at a useful resolution for small source images.
- Add anterior and posterior acetabular wall contours with distinct colours, Hide controls and coordinate export.
- Enlarge the morphology-index diagram to fit the screen.

### V1.6.1

- Matches the web release version; Slicer measurement and annotation behaviour is unchanged.

### V1.6.0

- Shared-landmark seeding across Tönnis, Sharp, LCE, offsets and head extrusion, including sourcil-contour landmarks.
- Single-base-point completion of Tönnis and Sharp when the lateral sourcil is known.
- Repeatable labelled Point annotations and bilateral edge-attracted pelvic contours.
- Four automatically advancing femoral-shaft cortex contours, classified as medial/lateral and inner/outer.
- Missing prerequisites in disabled-tool hover help.
- Selectable Smart Point Placement after calibration, reference and active-side head fitting, including shaft and morphology suggestions.
- Automatic implant-neck placement with single-guide and through-center options.
- Clearer extrusion placement guidance, distinct saved-scene file references, full coordinate CSVs and optional sampled-curve TXT export.
- Corrected CCR to B/A and supplied morphology schematic with its full study citation.
- Shorter hover help and a changelog separated from workflow instructions.

## Overview

`Pelvic Xray Measurements` is a 3D Slicer scripted module for calibrated pelvic radiograph analysis. It is designed for AP pelvis and pelvic x-rays where the operator wants a fast, reproducible workflow for common pre-operative and post-operative measurements, while still keeping every markup editable after placement.

The module has the following major design goals:

1. Keep the workflow interactive.
   Every measurement is driven by normal Slicer markup editing, so users can place, drag, and refine points and lines at any time.

2. Keep derived geometry visible.
   When a measurement depends on a fitted circle, fitted ellipse, reference arm, or helper line, the module creates that geometry explicitly so the user can see what is being measured.

3. Keep calibration centralized.
   If a calibration ball is present, all length-like outputs are corrected from the same scale factor. If no ball is present, the module reports only `su` values, where `su` means `scene units`.

4. Keep export comprehensive.
   The scene can be saved as an MRB, the measurements can be exported as a CSV, and an annotated image can be exported as a PNG. The CSV contains both summary measurements and detailed coordinate-level output.

5. Supporting material.
   Validation tools, fixtures, and automated tests are included under `Testing/Python`.

## Smart Point Placement

The measurement panel labels the feature as `Smart Point Placement` and places that heading directly
above `Auto-place points…`. The button is enabled only when the active side has a calibration ball,
the pelvic reference line, exactly one fitted head (native femur or implant), and the local model
resource. The reference line should be placed at tear-drop level whenever feasible. A line placed at
the ischial tuberosities can change the learned distances and reduce accuracy.

Pressing the button opens a confirmation dialog. The available feature groups are checked by default,
but the operator can clear any group before pressing `Place selected points`. The module writes ordinary
editable Slicer markups and preserves any existing control-point coordinates. The suggestions are a
starting point for review, not a replacement for checking the radiograph.

Pre-operative suggestions include the femoral neck and pelvic point groups and the femur shaft
morphology group. The shaft-axis proposal uses the radiograph as an image-guided correction of the
coordinate prior and is explicitly labelled rough; both guide lines should be adjusted to the cortex.
The morphology proposal includes the learned lesser-trochanter and shaft-cortex points, after which
the existing calibrated construction derives the remaining geometry. Review both shaft guides, the lesser-trochanter landmarks and the cortex controls.
Morphology suggestions keep cortex controls on their corresponding medial or lateral side of the
shaft axis. Existing manually placed points are retained.

Post-operative suggestions include the implant neck axis and offset groups. When `Implant Neck Axis`
is selected, the module automatically turns on `Use single guide` and `Lock to center`; the learned
proximal implant-neck guide and the fitted implant-head center then produce the complete displayed
axis line. The inline axis controls reflect and lock this state once the guide is present.

Smart Point Placement is an editable research aid. Its suggestions require review
and are not evidence of clinical accuracy.

## Quick Start

### Install the extension bundle

Download and unzip the complete extension bundle from the project's GitHub Release.
In Slicer, open **Application Settings → Modules → Additional module paths** and
add the extracted **PelvicXrayMeasurements** module folder containing
**PelvicXrayMeasurements.py**. Keep the helper and Resources folders beside it.
Restart Slicer and select **Pelvic Xray Measurements**, under **Orthopaedics**.
Use the Slicer version listed in the release notes.

The bundle includes the models needed for Smart Point Placement. GitHub's generic
Source code archives are for developers and do not include those separate assets.
An Extensions Manager listing is planned; use the direct bundle until catalog
approval and factory packaging are complete. A source ZIP is not an Extensions
Manager package. Avoid keeping two versions in Additional module paths.

### Typical case workflow

1. Load the radiograph into Slicer, or choose an `Input Folder` if you want the module to drive a one-by-one case workflow from disk.
2. Optionally choose an `Output Folder` so save and export actions use that folder automatically.
3. Select the image in the `Case` section, or use the `<` and `>` buttons beside the selector to move through the input-folder queue.
4. Fill the `Annotator` field. This field is required for all save and export actions.
5. If a calibration ball is visible, leave `Not Present` unchecked and confirm the real ball diameter.
6. If no calibration ball is visible, check `Not Present`.
7. Place the `Calibration Ball` if available.
8. Place the `Reference Line`.
9. Choose `Left` or `Right` for side-specific measurements.
10. Perform pre-operative and post-operative measurements as needed.
11. Review the `Results` panel.
12. Add optional case comments in the `Export and Save` section if needed.
13. Use `Export All`, `Export All / Load Next Image`, or the more targeted export buttons as appropriate.

## General Measurement Conventions

### Image and side conventions

The module uses image-space conventions rather than raw world-space conventions. This is important because radiographs are viewed as images, and the displayed left and right sides are not the same thing as arbitrary world-axis directions in Slicer.

Side-aware measurements therefore use:

- the image's displayed right direction,
- the image's displayed up direction,
- the selected side (`Left` or `Right`),
- the user-defined reference line.

### Smart shared-landmark seeding

Several measurements share the same anatomical landmarks. To reduce repeated clicking, the module looks for already placed markups on the active side when a related tool is started. If a needed landmark is available, the new measurement is pre-filled with that point or with a short generated line through that point.

The behavior is opportunistic and non-destructive:

- only empty markups created by the just-clicked tool are seeded,
- existing user-edited points or lines are never overwritten,
- seeded points and lines are explicitly unlocked/selectable and remain standard Slicer markups that can be dragged, refined, deleted, or redrawn,
- if the measurement already has points when its button is clicked, the tool resets to a clean manual redraw rather than immediately reusing the same smart seed,
- if the lateral sourcil is known but the Tönnis/Sharp base is not, the user places only the base point and the module inserts the lateral endpoint automatically,
- if only part of a measurement can be inferred, the workflow continues from the remaining missing point or line.

Current shared landmarks include:

- the teardrop/base point for the base of Tönnis, the base of Sharp, and the medial acetabular-offset line,
- the lateral sourcil point for the lateral endpoint of Tönnis/Sharp, the LCE point, and the middle FEI line,
- the femoral-head center for femoral offset and the femoral-head-side acetabular-offset line,
- the fitted femoral-head circle for FEI medial and lateral tangent lines,
- the acetabular roof/sourcil contour, whose lateral-most point can seed the lateral sourcil landmark.

This keeps signed measurements consistent with what the user actually sees on the x-ray.

### Calibration and units

If a calibration ball is present:

- the module fits a circle to the three ball points,
- computes the measured diameter in scene units,
- compares that diameter with the entered real-world diameter in millimetres,
- derives a scale factor,
- applies that same scale factor to all length-like outputs.

If `Not Present` is checked:

- no scale factor is applied,
- no millimetre values are reported,
- lengths are shown only in `su`,
- the CSV records that calibration was not present.

### Editable versus derived geometry

The module distinguishes between:

- user inputs: points and lines the operator places directly,
- derived geometry: fitted circles, fitted ellipses, axis lines, reference arms, and helper lines.

Derived geometry updates automatically whenever the underlying inputs are edited.

### Bilateral behavior

Most anatomical measurements are bilateral. The module uses the `Active Side` selector to decide which side a new bilateral measurement belongs to. Left and right measurements are stored separately and exported separately.

Global tools such as the session-scoped `Annotator` field, calibration, reference line, LLD, and the repeatable `Point`, `Line`, and `Angle` tools are not bilateral.

### Signed angles and signed relationships

Some measurements are intentionally signed rather than always positive. The module uses image-space superior and lateral directions so the sign reflects the visual construction on the radiograph, not arbitrary point order.

## Full Tool Reference

## 1. Setup

### Calibration Ball

**Definition**

The calibration ball is a sphere of known real-world diameter visible in the radiograph.

**Research context**

Without calibration, distances on an x-ray are only image distances. The calibration ball allows those distances to be converted into real millimetres.

**How it is usually measured**

The user identifies the projected outline of the ball and places points on its visible circumference.

**How the module measures it**

- The user places 3 points on the visible ball outline.
- The module fits a circle through those 3 points.
- The fitted diameter in scene units is compared with the entered real diameter.

**How the module calculates it**

- A 3-point circle fit gives:
  - circle center,
  - radius,
  - diameter,
  - local plane normal.
- The scale factor is:

  `scale factor = known ball diameter in mm / measured ball diameter in su (scene units)`

- All length-like measurements use that scale factor from this point onward.

**Important notes**

- If `Not Present` is checked, calibration is bypassed entirely.
- In that mode, the module reports only `su` values and never infers millimetres.

### Reference Line

**Definition**

The reference line is the baseline against which many distances and angles are defined.

**Research context**

The module uses the reference line as the main orientation anchor for:

- signed angle direction,
- offset constructions,
- LLD,
- free-hand inclination,
- cup ellipse inclination.

**How it is usually measured**

A line is drawn between two chosen anatomical landmarks or a chosen pelvic baseline, depending on the intended workflow.

**How the module measures it**

- The user places 2 points.
- The module stores the line direction and length.

**How the module calculates it**

- The direction is the normalized vector between the two endpoints.
- The raw length is the Euclidean endpoint-to-endpoint distance.
- If calibration is available, the corrected length is also reported.

## 2. Pre-Operative

### Femur Head

**Definition**

The femoral head tool estimates the native femoral head circle and center.

**Research context**

It provides:

- femoral head diameter,
- femoral head center,
- input for the LCE angle,
- a visual reference for preoperative morphological analysis.

**How it is usually measured**

Three points are placed on the visible femoral head contour.

**How the module measures it**

- The user places 3 contour points.
- The module fits a circle.
- A center point is created automatically.
- The fitted circle is shown on the image.

**How the module calculates it**

- Uses a 3-point circle fit.
- Reports diameter in `su` and in `mm` if calibrated.
- Stores the center for downstream tools such as `LCE Angle`.

### Femoral Shaft Axis

**Definition**

The femoral shaft axis is the main longitudinal axis of the femoral shaft.

**Research context**

It is used for:

- femoral offset,
- stem alignment,
- CCD angle,
- general femoral alignment interpretation.

**How it is usually measured**

Two short guide lines are drawn perpendicular to the shaft direction at two levels on the cortex, and a representative axis is derived from them wich runs perpendicular to the two lines.

**How the module measures it**

- The user draws 2 guide lines.
- The module derives one displayed shaft axis line from those guides.
- The `Femoral Shaft Axis` button appears in both the main measurement flow and the `Post-Operative (THA)` section; both buttons edit the same bilateral axis nodes.
- Export names and CSV fields remain the same regardless of which button was used.

**How the module calculates it**

- Each guide line is converted into a direction vector.
- The module computes the best common perpendicular inside the image plane.
- The midpoints of the two guide lines define the axis origin.
- A representative display span is chosen from image extent.
- The shown axis is intentionally shortened relative to full image size so it remains legible.

### Femoral Neck Axis

**Definition**

The femoral neck axis is the representative axis of the femoral neck.

**Research context**

It is used together with the shaft axis to derive the `CCD Angle`.

**How it is usually measured**

As with the shaft, two short guide lines are placed along the neck and a single representative axis is derived perpendicular to them.

**How the module measures it**

- `Lock to center` and `Use single guide` checkboxes are shown inline beside the button and apply to the active side.
- By default, the user draws 2 guide lines.
- If `Use single guide` is enabled for the active side, only the first guide line is required.
- If `Lock to center` is enabled for the active side, the derived axis is forced to pass through the fitted femur-head center, so `Femur Head` must be defined first.
- If the femur head is not yet defined for the active side, `Lock to center` is greyed out and explains why on hover.
- Once the first proximal-guide point is placed, both option checkboxes are locked for that measurement until the tool is clicked again and its annotations are reset.
- The module derives a displayed neck axis line.
- If neither box is checked, the user places two guide lines on the image, and the axis line is calculated from them.

**How the module calculates it**

- Uses the same best-common-perpendicular logic as the shaft axis.
- With the default two-guide mode, the displayed axis origin is the midpoint between the two guide-line midpoints.
- With `Use single guide`, the displayed axis origin is the midpoint of that single guide line.
- With `Lock to center`, that default origin is replaced by the fitted femur-head center while preserving the derived neck-axis direction.
- Uses a shorter display span than the shaft axis so the neck construction reads more naturally on the x-ray.

### CCD Angle

**Definition**

The CCD angle is the caput-collum-diaphyseal angle, also called the neck-shaft angle.

**Research context**

It reflects the angular relationship between the femoral neck and shaft.

**How it is usually measured**

It is measured between the femoral neck axis and the femoral shaft axis.

**How the module measures it**

- There is no separate button.
- It appears automatically once both:
  - `Femoral Shaft Axis`
  - `Femoral Neck Axis`
  are defined.

**How the module calculates it**

- The module takes the acute angle between the two derived axis directions.
- It reports the medial interior angle convention used by this measurement workflow.

### Acetabular Index (Tönnis)

**Definition**

The Acetabular Index (Tönnis) is an acetabular sourcil inclination angle.

**Research context**

It is commonly used in dysplasia and coverage assessment.

**How it is usually measured**

One arm follows the sourcil line, while the reference arm is horizontal or parallel to the chosen pelvic baseline.

**How the module measures it**

- The user places 2 points defining the measured arm.
- If both the teardrop/base point and lateral sourcil are already available from related active-side measurements, the line is pre-filled.
- If only the lateral sourcil is already available, the user places the medial sourcil/base point and the lateral endpoint is inserted automatically.
- The module draws the second arm automatically, parallel to the reference line.

**How the module calculates it**

- Uses the drawn line as the measured arm.
- Uses a derived arm parallel to the reference line through the first user point.
- Computes a signed angle so above-versus-below behavior follows the image-space superior direction.

### Sharp Angle

**Definition**

The Sharp angle is another acetabular coverage-related angle measured relative to a horizontal baseline.

**Research context**

It is used in acetabular dysplasia assessment and related pre-operative radiographic analysis.

**How it is usually measured**

One arm follows the relevant acetabular line, and the second arm follows the pelvic horizontal or equivalent baseline.

**How the module measures it**

- The user places 2 points defining the measured arm.
- If both the teardrop/base point and lateral sourcil are already available from related active-side measurements, the line is pre-filled.
- If only the lateral sourcil is already available, the user places the teardrop/base point and the lateral endpoint is inserted automatically.
- The module draws the reference arm automatically, parallel to the module reference line.

**How the module calculates it**

- Computes a signed angle between:
  - the user-drawn arm,
  - the derived reference arm.
- Sign is based on whether the measured arm lies above or below the reference arm in image space.

### LCE Angle

**Definition**

The lateral center-edge angle measures lateral coverage of the femoral head.

**Research context**

It is a standard measure in hip dysplasia and femoral head coverage assessment.

**How it is usually measured**

One arm runs from the femoral head center to the lateral edge point, and the other arm is vertical.

**How the module measures it**

- The user first defines the femur head.
- Then the user places 1 point at the relevant lateral edge.
- If the lateral sourcil is already available from a related active-side measurement or contour, the LCE point is pre-filled.
- The module draws:
  - the radial arm from head center to the user point,
  - the reference arm perpendicular to the reference line.

**How the module calculates it**

- Uses the automatically fitted femoral head center.
- Uses image-space superior direction as the vertical-like reference.
- Reports a signed value according to the side-aware radiographic convention implemented in the module.

### Acetabular Offset (Pre-Op)

**Definition**

Acetabular offset is the distance between two reference lines used to describe acetabular medial-lateral position.

**Research context**

It supports research analysis of hip offset and preoperative morphology.

**How it is usually measured**

Two parallel lines are constructed perpendicular to a pelvic baseline.

**How the module measures it**

- The user draws 2 lines.
- If the teardrop/base point or femoral-head center are already available, the corresponding editable offset line is pre-filled.
- Both lines are automatically constrained to remain perpendicular to the reference line.

**How the module calculates it**

- The distance is measured between the two parallel lines in the image plane.
- If calibration exists, the corrected value in millimetres is reported.

### Femoral Offset (Pre-Op)

**Definition**

Femoral offset describes the lateral displacement of the femoral axis relative to the femoral head-side construction.

**Research context**

It is a biomechanical parameter used in studies of hip morphology.

**How it is usually measured**

A line parallel to the femoral shaft axis is used to measure offset relative to the shaft axis.

**How the module measures it**

- The user draws 1 line.
- If the femoral-head center is already available, the editable offset line is pre-filled through that center.
- That line is constrained parallel to the femoral shaft axis.

**How the module calculates it**

- Distance is measured between:
  - the user line,
  - the derived shaft axis.
- Corrected millimetres are reported if calibration exists.

### Global Offset (Pre-Op)

**Definition**

Global offset is the sum of acetabular offset and femoral offset.

**Research context**

It gives a combined view of total hip offset.

**How it is usually measured**

It is usually derived rather than measured by a separate construction.

**How the module measures it**

- There is no separate button.
- The result is populated automatically when both component offsets exist.

**How the module calculates it**

- `Global Offset = Acetabular Offset + Femoral Offset`
- Both raw and corrected values follow the same component logic.

### Femoral Head Extrusion Index

**Definition**

The femoral head extrusion index estimates the proportion of the femoral head that remains uncovered.

**Research context**

It is commonly used in hip dysplasia and coverage assessment.

**How it is usually measured**

Three parallel reference lines are used:

- the first line at the most medial femoral-head position,
- the second line crossing the lateral sourcil,
- the final line tangent to the lateral side of the femoral head.

**How the module measures it**

- The user draws 3 lines.
- The workflow asks for the most medial line first, the lateral-sourcil crossing line second, and the lateral femoral-head tangent line last.
- If the femoral head circle is available, the medial and lateral tangent lines are pre-filled; if the lateral sourcil is available, the middle line is pre-filled.
- The module constrains them to remain perpendicular to the reference line.

**How the module calculates it**

- The denominator is the medial-to-lateral head width.
- The numerator is the middle-to-lateral uncovered width.
- The reported value is:

  `100 × (uncovered width / total head width)`

- The sign convention preserves geometry rather than forcing all results positive.

### Femur Shaft Morphology

**Definition**

The femur shaft morphology tool creates a calibrated construction grid around the lesser trochanter and proximal shaft and calculates CCR, CTI and CFI from its editable cortex points.

**Research context**

Standardized levels around the lesser trochanter are useful when describing proximal femoral shape because they keep width and canal-related landmarks tied to reproducible distances from a visible anatomical reference.

**How it is usually measured**

The operator identifies the level of the lesser trochanter, then assesses the femoral shaft at fixed proximal and distal distances relative to that level. The shaft axis is used as the vertical reference so the construction follows femoral alignment rather than the screen axes.

**How the module measures it**

- The tool is bilateral and lives in the `Pre-Operative` section.
- It requires both:
  - `Calibration Ball`
  - `Femoral Shaft Axis`
- The user places 2 points bracketing the lesser trochanter, one above and one below it.
- The module draws a mid-lesser-trochanter line at the halfway height between those points, centered on the femoral shaft axis.
- That line is constrained perpendicular to the femoral shaft axis.
- The module automatically creates:
  - 2 points at 2 cm above the midline,
  - 2 points at 3 cm below the midline,
  - 4 points at 10 cm below the midline,
  - 2 points at 11 cm below the midline.
- The 2 cm, 3 cm, and 10 cm points are locked vertically to their calibrated station heights along the shaft axis.
- Those vertically locked points remain horizontally editable, so the user can move each point across the shaft contour without changing its station level.
- The 11 cm point pair is initially placed at its calibrated station height.
- The 11 cm pair can be moved vertically, but the two points share one shaft-axis station so the pair remains parallel to the mid-lesser-trochanter line.
- Two guide lines pass through the 3 cm-below points and the two inner 10 cm-below points, ending exactly on the mid-lesser-trochanter line.
- The pre-operative results panel reports `CCR`, `CTI`, and `CFI` once the construction is defined.
- Hovering over the `CCR`, `CTI`, or `CFI` result names or value boxes shows the explanatory schematic and the study citation below.

**How the module calculates it**

- The 2 user points define the lesser-trochanter reference level by their midpoint height.
- The construction center is the projection of that midpoint onto the femoral shaft axis.
- The femoral shaft axis defines the vertical direction.
- The in-plane perpendicular to the shaft axis defines the horizontal direction.
- The calibration scale converts 20 mm, 30 mm, 100 mm, and 110 mm offsets into scene units.
- `CCR` (canal-calcar ratio) is **B/A**: the distance between the two inner 10 cm-below points (B) divided by the distance between the two guide-line cap points on the mid-lesser-trochanter line (A). It is dimensionless. A zero proximal width leaves CCR undefined.
- `CTI` is `(outer 10 cm-below width - inner 10 cm-below width) / outer 10 cm-below width`.
- `CFI` is the distance between the two 2 cm-above points divided by the distance between the two inner 10 cm-below points.
- The ratios are dimensionless and are included in the CSV export.
- All construction point coordinates and guide-line coordinates are also included in the CSV export for audit and reproducibility.

**Reference**

Pothong W, Adulkasem N. Comparative evaluation of radiographic morphologic parameters for predicting subsequent contralateral fragility hip fracture. International Orthopaedics. 2023;47:1837–1843. https://doi.org/10.1007/s00264-023-05789-8

### Leg Length Discrepancy

**Definition**

Leg length discrepancy, in this module, is the signed difference in position of two minor trochanter points relative to the reference line.

**Research context**

It is commonly used in pelvic and hip templating to compare left versus right height.

**How it is usually measured**

Two landmark points are compared using a pelvic baseline and parallel projection lines.

**How the module measures it**

- The user places 2 points on the minor trochanters.
- Placement order does not matter.
- The module automatically identifies which point belongs to left and right based on image-space position.
- It draws:
  - projection lines to the reference line,
  - medial helper lines through each point,
  - the measured height-difference segment.

**How the module calculates it**

- Each point is projected relative to the reference line in the image plane.
- The signed difference between the two in-plane offsets is computed.
- The absolute value is shown as the magnitude.
- Signed raw and signed corrected values are retained in the result structure and CSV.

## 3. Planning

Select the side you want to work on. Use a calibration ball at hip level when available. PXM uses the horizontal and vertical pixel spacing recorded in the image. A fitted ball corrects the scale for magnification and immediately resizes placed implants around their pivots. Detector spacing alone or an ordinary PNG requires a ball. Each side can hold one straight cut, one stepped cut, one movable fragment, one cup template and one stem template.

Each bundled implant uses the scale on its own manufacturer's drawing. A 40 mm interval on the drawing represents 40 mm on a calibrated image. The catalogue size can differ from the width of the drawn shell. For a manual comparison, use the mm value in the Line result after fitting the ball.

1. **Straight Neck Resection**. Click the medial and lateral cortices at the proposed cut. The result is the distance between those points. For a **Stepped Neck Resection**, add the medial end, the corner and the lateral end in that order. The results show each segment and their sum. Drag a landmark to revise the cut.
2. **Retained Bone Fragment Placement**. Click once after completing a neck cut. If both cuts are present, choose the one to use. PXM follows the cut, clears the trochanter regions and uses the image borders to enclose the distal femur. Existing head, lesser-trochanter and shaft landmarks help orient the region. This geometric selection can include soft tissue or overlapping pelvic anatomy. Drag the fragment or its point to move it. Drag the round handle to rotate about that point, or enter an angle in **Rotation** beside **Trace manually**. Click **Retained Bone Fragment Placement** again to clear the fragment and its movement on this side. If you edit the cut or shaft landmarks, clear and select the fragment again to recalculate its boundary.
3. **Trace manually** lets you adjust which tissue moves. The boundary starts at the lateral cut end. Place points around the retained bone, including beyond the film edge when necessary. Right-click to close at the medial end. The original straight or stepped cut completes the border. The tracing disappears after selection.
4. **Import overlay pack…** opens a local JSON file of AP outlines in millimetres. Imported sizes remain available across cases for this session. If you reopen a plan that uses an external template, import the same pack to display it again. Select **How It Works** beside the import button to open the guide in your browser.
5. **Place Cup Template** and **Place Stem Template**. Select a family and size, then place its pivot on the calibrated image. Drag the implant to translate it. Drag the round handle to rotate it around the pivot, or enter the angle in **Rotation**. Select an existing implant by clicking its body or pivot. The pivot may lie away from the joint centre.

**Making a pack.** The [implant overlay guide](PelvicXrayMeasurements/Resources/implant-overlays.html) explains the PDF conversion, the physical scale of each drawing, size verification and the complete import format. It includes a downloadable synthetic example and the JSON Schema.

The local library contains 794 AP entries from Medacta and Mathys. Cups and reinforcement cages appear under **Place Cup Template**. Complete stems and proximal or distal components appear under **Place Stem Template**. The two slots on each side hold one acetabular and one femoral drawing at a time. Rotation starts in the printed AP position. PXM mirrors a neutral drawing for the opposite hip and offers a side-specific reference only on its designated side. Check the radiograph’s side marker, especially on an image without orientation metadata.

The drawings retain their original size and guide marks. Dots, crosshairs and extended lines can project outside the implant. Use the shell or stem body when judging fit. Export the annotated PNG to show the plan. Use the CSV or MRB to resume editing with the same library installed.

### Implant references

1. OsiriX Team and volz.io. *Hip Arthroplasty Templating Plugin* [software for OsiriX]. Version 3.6.5. OsiriX Foundation. [Plugin record](https://www.osirixfoundation.com/medacta/).
2. Medacta International. *MEDACTA Templates* [hip implant drawings and product records]. Distributed with Hip Arthroplasty Templating Plugin, version 3.6.5. OsiriX Foundation. [Medacta collection record](https://github.com/aglv/HipArthroplastyTemplating/blob/270476e057eecb6dec4eb6b7fb4e49dbab8e90e9/.gitmodules#L9-L12).
3. Mathys Ltd. Bettlach. *Mathys Templates* [hip implant drawings and product records]. Distributed with Hip Arthroplasty Templating Plugin, version 3.6.5. OsiriX Foundation. [Mathys collection record](https://github.com/aglv/HipArthroplastyTemplating/blob/270476e057eecb6dec4eb6b7fb4e49dbab8e90e9/.gitmodules#L5-L8).
4. Holzer N, Christofilopoulos P, Volz A, Ratib O, Peter R. *Filmless total hip arthroplasty templating on surgeon’s own personal computers: a reliable & user friendly solution at no cost* [conference abstract]. Swiss Medical Weekly. 2011, 141(Suppl 186), 6S–7S. Abstract FM21. [Journal abstract](https://smw.ch/index.php/smw/article/download/5290/6514#page=7).

[Licence terms](PelvicXrayMeasurements/Resources/implant-overlays.html#sources) · [Publisher's terms](https://www.osirixfoundation.com/medacta/)

## 4. Post-Operative (THA)

The `Post-Operative (THA)` section also shows `Femoral Shaft Axis` below `Implant Neck Axis`.
This is the same shared bilateral shaft-axis tool described above, not a separate post-operative
measurement.

### Implant Head Center

**Definition**

This tool estimates the prosthetic head circle and center.

**Research context**

It provides a post-operative implant head size and center without affecting any other measurement automatically.

**How it is usually measured**

Three points are placed on the visible implant head contour.

**How the module measures it**

- The user places 3 points.
- The module fits a circle and creates a center point.

**How the module calculates it**

- Same 3-point circle fit logic as the native femoral head.
- Reports raw diameter and corrected diameter if calibration is available.

### Cup Center and inlay wear estimate

Place three well-separated points on the visible spherical outer margin of the metal shell, away from the cup opening, screw holes and projections. PXM fits a circle through those points. The separate six-point **Cup Opening Ellipse Fit** serves inclination and version.

When **Implant Head Center** and **Cup Center** are both defined on the same side, **Inlay wear estimate** shows the distance between their centres in the AP image plane. It is reported in millimetres after calibration and in scene units (su) otherwise. A concentric fit gives zero. If either circle cannot be fitted, the result stays blank. This single-film measurement describes projected head eccentricity. Implant design, initial liner deformation and projection can all contribute. Assessing change over time requires comparable dated radiographs.

### Acetabular Inclination Angle (Free Hand)

**Definition**

This is a post-operative free-hand inclination measurement based on a manually drawn cup-related line.

**Research context**

It provides a direct, operator-defined inclination measure when a simple manual line is preferred.

**How it is usually measured**

A single line is drawn along the intended cup opening or acetabular reference.

**How the module measures it**

- The user draws 1 line.

**How the module calculates it**

- The module takes the acute angle between:
  - the drawn line,
  - the reference line.

### Cup Opening Ellipse Fit

**Definition**

This tool fits an ellipse to the visible opening of the cup.

**Research context**

It provides:

- an ellipse-derived inclination,
- a cup opening anteversion or retroversion style angle based on ellipse eccentricity.

**How it is usually measured**

Multiple rim points are placed along the cup opening. The opening projects as an ellipse on the x-ray.

**How the module measures it**

- The user places 6 rim points.
- The module fits the best ellipse it can in the image plane.
- The fitted ellipse is shown in the slice view.

**How the module calculates it**

- The ellipse is fitted in image coordinates.
- The major axis direction is compared to the reference line to get `Inclination (E)`.
- The cup anteversion/retroversion angle is currently derived from:

  `theta = asin(minor diameter / major diameter)`

- This means:
  - `0°` when the minor diameter approaches `0`,
  - `90°` when the major and minor diameters are equal.

### Inclination (E)

**Definition**

This is the ellipse-derived inclination angle of the cup opening.

**Research context**

It provides a model-based alternative to the free-hand inclination line.

**How it is measured in the module**

- It is populated automatically from `Cup Opening Ellipse Fit`.

**How it is calculated**

- It is the acute angle between:
  - the ellipse major axis,
  - the reference line.

### Cup Ant/Ret An.

**Definition**

This result reports the current ellipse-derived opening angle based on the major and minor diameters.

**Research context**

It is intended to capture cup opening anteversion or retroversion style information from the ellipse geometry.

**How it is measured in the module**

- It is populated automatically from `Cup Opening Ellipse Fit`.

**How it is calculated**

- Uses the current implementation:

  `theta = asin(minor diameter / major diameter)`

### Implant Neck Axis

**Definition**

The implant neck axis is a post-operative axis representing the direction of the implant neck.

**Research context**

It provides the post-operative neck-direction analogue of the native femoral neck axis and is used to derive the implant-femoral CCD angle.

**How it is usually measured**

As with the native neck axis, two short guide lines are placed along the visible implant neck orientation and a single representative axis is derived from them perpendicular to both.

**How the module measures it**

- `Lock to center` and `Use single guide` checkboxes are shown inline beside the button and apply to the active side.
- By default, the user draws 2 implant neck guide lines.
- If `Use single guide` is enabled for the active side, only the first implant neck guide line is required.
- If `Lock to center` is enabled for the active side, the derived axis is forced to pass through the fitted implant-head center, so `Implant Head Center` must be defined first.
- If the implant head is not yet defined for the active side, `Lock to center` is greyed out and explains why on hover.
- Once the first proximal-guide point is placed, both option checkboxes are locked for that measurement until the tool is clicked again and its annotations are reset.
- The module derives one displayed implant neck axis from those guide lines.
- If neither box is checked, the user places two guide lines on the image, and the axis line is calculated from them.
- When `Auto-place points…` places `Implant Neck Axis`, it enables both `Use single guide` and `Lock to center` automatically. The learned proximal guide and the fitted implant-head center then generate the complete displayed axis line.

**How the module calculates it**

- Uses the same best-common-perpendicular approach as the native femoral neck axis.
- With the default two-guide mode, the displayed axis origin is the midpoint between the two guide-line midpoints.
- With `Use single guide`, the displayed axis origin is the midpoint of that single guide line.
- With `Lock to center`, that default origin is replaced by the fitted implant-head center while preserving the derived implant-neck-axis direction.
- Uses the same short display-span style as the native neck axis so the visual construction remains compact.

### Impl. Fem. CCD

**Definition**

This is the post-operative implant-femoral CCD angle.

**Research context**

It compares the implant neck orientation with the native femoral shaft axis and provides a post-operative counterpart to the native CCD angle.

**How it is measured in the module**

- There is no separate button.
- It appears automatically once both:
  - `Femoral Shaft Axis`
  - `Implant Neck Axis`
  are defined.

**How it is calculated**

- The module takes the obtuse medial-side angle between:
  - the native femoral shaft axis,
  - the implant neck axis.
- The same angular convention is used as the native CCD angle so the two values are directly comparable.

### Stem Alignment

**Definition**

Stem alignment is the angular difference between the implant stem axis and the femoral shaft axis.

**Research context**

It helps evaluate implant alignment relative to the femoral shaft after THA.

**How it is usually measured**

Two short guide lines are placed along the visible implant stem, and a representative stem axis is then compared with the femoral shaft axis.

**How the module measures it**

- The femoral shaft axis must already exist.
- The user draws 2 stem guide lines.
- The module derives one displayed stem axis from those guide lines.

**How the module calculates it**

- Uses the same axis-fitting logic as the femoral shaft axis tool for the implant stem.
- Reports the acute angle between:
  - the derived stem axis,
  - the native femoral shaft axis.

### Acetabular Offset (Post-Op)

**Definition**

This is the THA/post-operative version of acetabular offset.

**Research context**

It allows offset analysis after implantation without mixing results with the pre-operative measurements.

**How it is measured in the module**

- Same interaction as the pre-op version.
- Stored in a completely separate result channel.

**How it is calculated**

- Same parallel-line distance construction as pre-op acetabular offset.

### Femoral Offset (Post-Op)

**Definition**

This is the THA/post-operative version of femoral offset.

**Research context**

It allows direct comparison with pre-operative femoral offset.

**How it is measured in the module**

- Same interaction as the pre-op version.
- Stored separately.

**How it is calculated**

- Same axis-parallel distance construction as pre-op femoral offset.

### Global Offset (Post-Op)

**Definition**

This is the derived total post-operative offset.

**Research context**

It summarizes the combined post-operative acetabular and femoral offset reconstruction.

**How it is measured in the module**

- No separate button.
- It appears automatically once both THA offsets are available.

**How it is calculated**

- `Post-Op Global Offset = Post-Op Acetabular Offset + Post-Op Femoral Offset`

## 5. Points & Lines & Angles

### Point

**Definition**

An ad hoc labelled point annotation tool.

**Research context**

Useful for marking landmarks or observations that do not yet have a dedicated measurement workflow.

**How it is measured in the module**

- The user clicks `Point`.
- A numbered point is added.
- The point label, such as `Point_1`, remains visible beside the marker in Slicer.
- Additional custom points can be added with the button or counter.

**How it is calculated**

- The module stores the point coordinate.
- No numeric distance or angle is inferred from a single point.
- Point coordinates are exported in the CSV point rows.

### Line

**Definition**

An ad hoc distance measurement tool.

**Research context**

Useful for measurements that do not yet have a dedicated workflow.

**How it is measured in the module**

- The user clicks `Line`.
- A numbered line is added.
- The user places 2 points.
- Optional lock checkboxes can force the line to remain:
  - parallel to the reference line,
  - perpendicular to the reference line.
- When a lock is used, the line keeps that orientation while its length and placement remain editable.
- Additional custom lines can be added.

**How it is calculated**

- The module reports point-to-point length.
- When a lock mode is active, the line is re-aligned to the requested reference orientation before the length is evaluated.
- Uses calibration if available.

### Angle

**Definition**

An ad hoc angle measurement tool.

**Research context**

Useful for custom geometric checks that are not covered by the predefined tools. It measures the angle always in positive and between 0 and 180 degrees.

**How it is measured in the module**

- The user clicks `Angle`.
- A numbered angle is added.
- The user places 3 points:
  - first arm endpoint,
  - vertex,
  - second arm endpoint.
- Optional lock checkboxes can force the first arm to remain:
  - parallel to the reference line,
  - perpendicular to the reference line.

**How it is calculated**

- The module draws both arms explicitly after placement.
- The reported angle is the acute angle between the two arms.
- Locking affects the first arm geometry before the angle is evaluated.

## 6. Contours

### Pelvic contour tools

**Definition**

The contour tools store editable Slicer markups curves for anatomical borders.

**Included contours**

- `Iliopectineal Line`
- `Ilioischial Line`
- `Shenton Line`
- `Acetabular Roof (Sourcil)`
- `Anterior Acetabular Wall` (yellow)
- `Posterior Acetabular Wall` (pink)
- `Linea Terminalis`

**How they are measured in the module**

- The tools are bilateral; the `Active Side` selector chooses the left or right curve.
- The user places curve control points along the anatomy.
- Control points use local contrast-edge attraction to move toward nearby sharp image gradients.
- The curves remain editable after placement.

### Femoral Shaft contour

**Definition**

The `Femoral Shaft` contour tool captures the four cortex curves around the selected femoral shaft side.

**How it is measured in the module**

- The tool is bilateral.
- Clicking `Femoral Shaft` starts contour 1 of 4 for the active side.
- The user places many points along one shaft cortex contour.
- Right-clicking finishes the current contour and automatically advances to the next contour.
- After contour 4 is right-click-finished, placement stops and the module classifies the four curves.
- The user may place medial/lateral and inner/outer cortices in any order.

**How the module classifies it**

- Classification waits until all four curves have at least two points.
- The module projects the four contour centroids onto a side-aware medial-lateral coordinate axis.
- If a femoral shaft axis already exists, it is used only to stabilize that coordinate axis.
- If no shaft axis exists, the module derives a local long-axis from the contour coordinates themselves.
- The two medial contours are ordered as medial outer and medial inner.
- The two lateral contours are ordered as lateral inner and lateral outer.
- The assigned class is stored on the curve node and included in CSV point-row details.

**Export behavior**

- CSV point rows include curve type and interpolation settings for contour control points.
- If `Export Curve Points as TXT` is enabled, Slicer's sampled/interpolated curve points are written to a companion TXT file.

## Module Manual

## Loading and preparing a case

### Image selection

- The `Image` selector defines the active radiograph for:
  - display assumptions,
  - export naming,
  - image export.
- If the user does not manually select an image, the module tries to choose the first scalar volume automatically.

### Active side

- The `Active Side` selector determines which side receives new bilateral measurements.
- A large moveable on-image badge shows the current active side and changes color when the side changes.
- The badge is a visual reminder only; it does not create measurement rows in CSV export and is hidden during annotated image export.
- Changing the side does not delete or overwrite existing measurements.
- Left and right results are stored independently.

### Ball diameter and `Not Present`

- `Ball Diameter` sets the real calibration-ball size in millimetres.
- `Not Present` disables calibration entirely.

Use `Not Present` when:

- there is no calibration sphere on the radiograph,
- the visible object is not trustworthy for scale,
- only relative or scene-unit measurements are needed.

## Using measurement buttons

### General interaction model

Most buttons behave the same way:

- clicking the button resets that tool's current input for the active side or global tool,
- the module enters guided placement,
- instructions update in the workflow banner,
- editing continues to update the measurement live after placement.

### Button state appearance

Measurement buttons use shading to communicate state:

- idle,
- active and awaiting placement,
- already applied,
- active while already applied.

### Hide checkboxes

Each measurement row includes a `Hide` checkbox.

This checkbox:

- hides the overlay geometry for that measurement,
- does not delete the measurement,
- does not remove the numeric result,
- can be reversed at any time.

## Using repeatable `Points & Lines & Angles` tools

### Counter behavior

The repeatable `Point`, `Line`, and `Angle` tools have counters.

- Increasing the counter adds one new measurement.
- Decreasing the counter removes the most recently added one.
- The counter cannot advance more than one unfinished measurement ahead.

This prevents the scene from accumulating multiple half-finished ad hoc tools.

### Reference-lock options

The repeatable `Line` and `Angle` tools both provide optional reference-lock checkboxes.

- `Lock || Ref` constrains the custom tool to stay parallel to the reference line.
- `Lock _|_ Ref` constrains the custom tool to stay perpendicular to the reference line.
- Leaving both unchecked keeps the custom tool fully free.
- These lock modes require the reference line to exist before a new locked custom measurement can be created.
- `Point` annotations have no reference-lock option because a single point has no orientation.

## Results panel

The results panel groups the values under these headings.

1. **Setup**
2. **Pre-Operative**
3. **Planning**
4. **Post-Operative (THA)**
5. **Points & Lines & Angles**

### Units

- `mm` appears when calibration exists.
- `su` appears when calibration is unavailable or intentionally disabled.
- Percent and angle measurements are reported independently of length calibration.

### Bilateral display convention

The left and right result boxes follow x-ray viewing convention, so the displayed columns are arranged to match the image view rather than a naive internal storage order.

## Case Section

The `Case` section contains:

- a version indicator at the top of the panel,
- an `Input Folder` selector,
- an `Output Folder` selector,
- an image selector with `<` and `>` navigation buttons,
- the required `Annotator` field,
- the active-side selector,
- calibration controls,
- the workflow guidance banner.

### Input folder workflow

If an `Input Folder` is selected:

- the module builds a sorted list of supported image files from that folder,
- the `<` and `>` buttons load the previous or next case from that list,
- if the chosen `Output Folder` already contains a saved MRB for that image, the latest matching saved scene is loaded instead of a fresh image-only scene,
- if there are unsaved scene-level changes, the module prompts the user before changing cases.
- the selector remembers the last chosen path and reuses it as the next browse starting point while the current Slicer session remains open.

This keeps one-image-at-a-time review practical while still reloading prior annotations when they exist.

### Output folder workflow

If an `Output Folder` is selected:

- all save/export actions use that folder automatically,
- the module does not ask for a destination folder each time,
- case names and file naming remain unchanged; only the parent folder becomes fixed.
- the selector remembers the last chosen path and reuses it as the next browse starting point while the current Slicer session remains open.

If no `Output Folder` is selected, save/export actions still ask for a parent folder exactly as before.

## Export and Save

### Available export buttons

The `Export and Save` section contains:

- `Export All`
  - exports MRB, CSV, and annotated PNG
- `Export All / Load Next Image`
  - exports MRB, CSV, and annotated PNG,
  - then loads the next image from the selected input folder if one exists
- `Export CSV`
  - exports CSV only
- `Export Scene`
  - exports MRB only
- `Export Image`
  - exports annotated PNG only

The section also contains an optional `Comments` field. Those comments are exported into the CSV metadata and are saved with the MRB scene so they reload with previously saved annotations.

### Annotator requirement

All five export actions require a non-empty `Annotator` value.

If the field is empty when the user tries to save or export, the module shows a warning pop-up and does not continue until the field is filled.

The `Annotator` value is kept in session-scoped module state rather than in the MRML scene. That means:

- it persists across `Close Scene` within the same Slicer session,
- it is restored into the field after scene recreation,
- it resets naturally when Slicer is fully closed and restarted.

### Last export information

The panel records:

- the time of the last export,
- which output types were written.

### Display measurement values on exported image

This checkbox controls whether the bottom-center measurement summary is drawn onto the exported PNG.

It affects only the exported image, not the interactive slice view.

The `Annotator` line is still included on exported images even when the measurement-summary rows are hidden with this checkbox.

### File name conflict handling

If an MRB, CSV, or PNG of the same name already exists, the module asks whether to:

- replace the existing file,
- or save a new version.

### Export folder naming

- The export folder is named after the selected image node.
- The folder uses the image name **without** its extension.
- The files inside use the case naming convention:
  - `<case>.mrb`
  - `<case>_measurements.csv`
  - `<case>_annotated.png`

## CSV Output

To restore a coordinate CSV, open the same radiograph and select **Open a CSV…**. The folder workflow also restores a CSV when a matching saved scene is absent. Landmark roles, named columns and saved point indices identify each measurement. Rows and columns can move. Older files can omit new features. Use the same geometry and orientation as the original case. The app recalculates fitted geometry and measurement values from the saved editable points.


The CSV is intentionally detailed.

It includes:

- metadata rows,
- annotator metadata,
- timestamp metadata,
- comments metadata,
- neck-axis mode metadata for both sides of the native and implant neck-axis tools,
- calibration mode and calibration values,
- summary measurements,
- point coordinates,
- derived centers,
- derived axis endpoints,
- ellipse endpoints and fitted values,
- repeated custom line and angle results.

### Why the CSV is so detailed

The module is meant to be audit-friendly and reusable for research, validation, and open-source workflows. Exporting only the final numbers would make it much harder to verify or reproduce a case later.

## Annotated Image Export

The image export is designed to produce a publication-friendly annotated figure.

Exports render at a minimum long edge of 2,048 pixels for ordinary image proportions,
with landmarks and measurement text drawn at the final resolution. The radiograph
retains its original information; enlargement does not add anatomical detail.
Large exports are limited to 40 megapixels and 15,500 pixels per edge.

### What is included

- the radiograph itself,
- visible markups,
- visible helper lines and models,
- fitted circles,
- fitted ellipse,
- the annotator line,
- optional measurement summary text at the bottom center.

### Why the module uses a dedicated export path

A plain screenshot would depend too strongly on zoom, crop, and window layout. The dedicated image export path exists so:

- the exported image is high resolution,
- the annotations are high resolution,
- the result is more reproducible than a normal screen capture.

## Verification and research limitations

The extension includes unit tests and a synthetic end-to-end CSV replay. The replay
restores editable coordinates, recalculates helper geometry and compares the full
export. It covers both sides, preoperative and postoperative tools, morphology,
all contours, custom measurements and saved settings. Tests and their instructions
are included under **Testing/Python**.

The optional comparison and image-conversion utilities in **Testing/Python/validation**
can help organize a research comparison. No patient image or clinical ground-truth
dataset is supplied. Their configurable tolerances are software-comparison settings,
not established clinical acceptance limits. A self-generated reference CSV is a
regression reference, not an independent accuracy standard.

**Research use only.** This software is a research tool, not a medical device. It is not intended for diagnosis, treatment planning or other clinical decision-making.

A validation study comparing the tool with established medical software is in progress. No completed
clinical validation or regulatory approval is claimed. Image quality, projection,
landmark choice and calibration affect results. Review every automatic suggestion.
The cup ellipse cannot establish anteversion/retroversion sign on its own.
Saved scenes and exports may retain identifying information; they are not an
anonymization service. Do not share patient material in public support requests.

## License and citation

Original project code is licensed under the [Apache License 2.0](LICENSE.txt).
Third-party materials retain their own licenses. See [NOTICE](NOTICE.md) and
[THIRD_PARTY.md](THIRD_PARTY.md) for distribution information. Please cite Kaveh Same,
Pelvic X-ray Measurements, the repository and the version used in research reports.
This scholarly citation request is separate from license requirements.

## Credits

## Developed by

**Kaveh Same, MD, MPH, PhD Candidate**

Michael Ogon Laboratory for Orthopedic Research, Orthopedic Hospital Speising, Vienna, Austria

## In collaboration with

**ImageBiopsy Lab GmbH**, Vienna, Austria

## Code backbone created by

**Codex**

OpenAI, California, USA
