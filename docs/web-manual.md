# Pelvic X-ray Measurements for the web

**Research use only. This software is not a medical device.** It is not intended
for diagnosis, treatment planning or other clinical decision-making.

A validation study is being performed to compare the tool with established
medical software. Completed clinical validation is not claimed.

## Version history

**1.7.1**

- Shows the arrow cursor unless you are dragging to pan.
- Highlights nearby landmarks and lets you cycle through overlapping points.
- Keeps source pixels sharp at high magnification, including during panning.
- Adds direct navigation below the current image name and count.

**1.7.0**

- Sharper annotations and text on exported images from low-resolution sources.
- Bottom-centred measurement summary on PNGs.
- Anterior and posterior acetabular wall contours below the acetabular roof.
- Curved dashed continuation while placing contours.
- Larger morphology-index diagram in hover help.

**1.6.1**

- Improves component downloads, verified caching and recovery after interruptions.
- Adds clearer startup errors and a notice about restricted networks.

**1.6.0**

- Matches the Slicer extension version number.
- Adds live Shift-drag window adjustment and preserves saved curve, neck-axis and visibility settings.
- Reuses the browser's verified copy of the software package when available.
- Shows the next segment during placement and supports panning while a tool stays active.
- Shows the reference line length in scene units and calibrated millimetres when a calibration ball is defined.

**1.0.1**

- Updates constructions and values during a landmark drag.
- Defines scene units beside the results and keeps annotations visible over the exported PNG panel.
- Adds a note about folder exports on the start screen.

**1.0.0**

- Opens the measurement workspace from a website in Chrome.
- Runs radiograph decoding, annotation, measurement and Smart Point Placement on the user's device.
- Opens existing single-radiograph Slicer scenes and coordinate CSVs. Exports annotated PNGs, CSVs and MRB scenes.

## Start

Open the site in a desktop browser and select **Start**. The browser downloads the software package once and can reuse it when the same build opens again. The browser stores this package under the site's data. It contains software and models. Radiographs and annotations stay in the workspace until export or until the scene closes. Exporting to folders works best in Chrome or Edge. Once the workspace is ready, it blocks network connections and can finish the session offline.

The app reads only the files you select. It does not send images, annotations, file names or exports to the host. The host receives the initial requests for the web page and its software. To start a new session after closing the tab, open the site again.

Some restricted networks, including hospital networks, may prevent the app from starting. If preparation fails, open **Download details for IT support** beneath the error. It shows the failed component and response status when available. Your IT team may need to approve access.

## Open a case

1. Select **Browse** under **Input Folder** and select a radiograph folder. You can also use **Open a file...** or drop selected radiographs onto the viewer.
2. Select **Browse** under **Output Folder** and choose where to save the results. Chrome asks for permission to write to that folder. The fields show the names of the folders you select.
3. Enter **Annotator Name** before exporting. Use the case arrows for adjacent images. To jump farther, enter a number in **Go to image** below the filename and image count, then press Enter or select **Go**. For example, enter `500` to open the 500th image in the list. Unsaved edits stay in the tab when you move between cases.

The viewer shows one radiograph at a time. It accepts PNG, JPEG, TIFF, BMP and WebP. It also opens single-frame monochrome DICOM, single-slice NRRD, NIfTI-1 and MetaImage, and MRB scenes containing one stored radiograph. For detached NRRD or MetaImage, select the header and its pixel file from the same folder. DICOM files can use native encoding, RLE, baseline JPEG, JPEG 2000, JPEG-LS or lossless JPEG Process 14. If a DICOM transfer syntax or multi-frame study cannot open, export a single radiograph as uncompressed DICOM or a lossless image.

When the output folder contains exports for the case, the app opens the most recent export group. It prefers the MRB within that group, which contains the image and annotations together. A more recent CSV-only export is used with the selected input image. To import a specific CSV, open the corresponding radiograph and use **Open a CSV...**. Older CSVs without an image coordinate frame assume the same image orientation and geometry.

**Close Scene** clears the viewer and the tab's working annotations. The selected folders and annotator remain available. Export before closing a scene or the tab. Use the next case arrow to reopen the first image after closing the scene.

## View and edit

- **Fit** restores the whole image. Use **Zoom +**, **Zoom −** or the wheel to change magnification. At high zoom, the viewer shows the original pixels without smoothing. To pan during placement, hold **Space** and drag, or toggle **Pan** and drag. The hand appears during the drag. Release Space or turn Pan off to continue placing points. Middle-button drag and Ctrl-drag also pan.
- **Rotate** turns the image 90° clockwise and **Mirror** flips it left to right. Set the orientation before annotating. Confirm the patient side using the radiograph's orientation markers.
- **Window** adjusts the grayscale limits and can invert the image. Hold **Shift** and drag up or down over the radiograph to move both limits together while keeping their separation. Drag up to brighten the image or down to darken it. The display updates during the drag. Release to keep the adjustment or press Escape to cancel, including during point placement. These controls change the display only. The underlying intensities remain available for contour snapping and Smart Point Placement.
- Choose **Left** or **Right** to set the active anatomical side. The badge in the viewer displays the same side.
- Select a measurement, then follow the prompt beneath the viewer. A dashed line follows the pointer from the latest point as you place a line, a contour or another landmark that needs several clicks. Tools with several guides advance after each pair of endpoints.
- To edit a point, move the pointer near it until a ring appears, then drag. If points overlap, the label identifies the selected point. Click to cycle through the candidates, then drag the point you want. The constructions and results update during the drag. Release to keep the new position or press Escape to cancel the drag. Escape also exits Pan or stops an active point or line tool.
- The selected tool is highlighted. Completed tools change colour. A disabled tool's help explains its prerequisites. **Hide** changes visibility and leaves the annotations and values available.
- Hold the pointer over a tool or result for 2.5 seconds to read its help. The shaft morphology help includes the diagrams for CCR, CTI and CFI.

## 1: Setup

**Calibration Ball.** Enter the known diameter in millimetres. Place three spaced points on the ball boundary. The fitted circle sets the scale for lengths and calibrated shaft stations. If the image has no ball, leave this tool unused. Lengths remain in scene units.

**Reference Line.** Place one endpoint at each teardrop whenever feasible. The reference defines the pelvic horizontal for angles, offsets and leg length. Smart Point Placement can be inaccurate if the line is instead at the ischial tuberosities.

## 2: Pre-operative measurements

| Tool | Placement and result |
| --- | --- |
| Femur Head | Place three boundary points to fit the head circle and centre. |
| Femoral Shaft Axis | Place two endpoints across the shaft at each of two levels. The derived axis crosses the guide region. |
| Femoral Neck Axis | Place two neck-width guides, or one with **Use single guide**. **Lock to center** constrains the line through the fitted native head. The shaft and neck axes give the CCD angle. |
| Acetabular Index (Tönnis) | Draw from the medial sourcil to its lateral edge. The app adds the pelvic reference arm. |
| Sharp Angle | Draw from the teardrop to the lateral acetabular point. The app adds the pelvic reference arm. |
| LCE Angle | Fit the native head and place the lateral sourcil point. The angle uses the superior perpendicular to the pelvic reference. |
| Acetabular Offset | Place two guides at the pelvic landmark and at head-centre level. |
| Femoral Offset | Place the guide at head-centre level after drawing the shaft axis. The app also reports Global Offset when both component offsets are available. |
| Femoral Head Extrusion Index | Place three guides at the medial head tangent, lateral sourcil and lateral head tangent. |
| Femur Shaft Morphology | Complete calibration and the shaft axis, then place two lesser-trochanter landmarks. Adjust the ten cortex controls on the displayed guides. |
| Leg Length Discrepancy | Mark the corresponding lesser trochanter on each side. The app compares their heights perpendicular to the pelvic reference. |

The first placement of a tool that supports shared landmarks can reuse available points or guides. Select the tool again to place the whole measurement manually. Subsequent starts alternate between shared and manual placement on that side.

For shaft morphology, the lesser-trochanter points define the mid-level station. The **CCR** is distal inner canal width at 10 cm divided by the proximal guide-cap width at the mid-level station (**B/A**). The **CTI** is outer minus inner width divided by outer width at 10 cm. The **CFI** is inner width 2 cm proximal to the mid-level station divided by inner width at 10 cm.

## 3: Post-operative measurements

| Tool | Placement and result |
| --- | --- |
| Implant Head Center | Place three boundary points to fit the implant head and centre. |
| Acetabular Inclination Angle (Free Hand) | Draw the cup-opening line relative to the pelvic reference. |
| Cup Opening Ellipse Fit | Place six points around the cup opening. The fit gives inclination and version magnitude. Use other information to determine anteversion or retroversion. |
| Implant Neck Axis | Place one or two transverse implant-neck guides. **Lock to center** requires the fitted implant head. |
| Femoral Shaft Axis | Place proximal and distal guides as in the pre-operative section. Both sections use the same shaft axis. |
| Stem Alignment | Place two stem guides. The result compares the derived stem and femoral shaft axes. |
| Acetabular Offset and Femoral Offset | Place the post-operative guides using the implant-head level. Global offset is available when both offsets are defined. |

## Smart Point Placement

Place a valid calibration ball, teardrop reference line and exactly one fitted head on the active side. Select **Auto-place points…**, review the checked features and select **Place selected points**. The native head enables pre-operative suggestions. The implant head enables post-operative suggestions, including the neck axis with a single guide through the centre.

The app checks the anchor geometry and reports features it could not place. The shaft guides use an image-based correction. Morphology proposals use the derived shaft axis to keep inferred medial and lateral points on their respective sides. Every proposed point remains editable. Check the placement on the image before saving it.

## 4: Points, lines and angles

- **Point** places a numbered marker and reports its coordinates.
- **Line** takes two points and reports length.
- **Angle** takes the first arm point, the vertex and the second arm point. It reports the included angle.
- For lines and angles, set **Lock ∥ Ref** or **Lock ⟂ Ref** before placement if needed. The line or first angle arm follows the reference. Define the reference first.
- Increasing a count starts another measurement. Decreasing it removes the last measurement in that group.

## 5: Contours

The contour tools trace the iliopectineal line, ilioischial line, Shenton line, acetabular roof (sourcil), anterior acetabular wall, posterior acetabular wall, linea terminalis and femoral shaft. The anterior wall is yellow and the posterior wall is pink. Click along the structure. Nearby strong image edges can attract a control point. Drag a point after placement to refine the trace.

While placing a contour, the dashed continuation previews the curve towards the
pointer. The preceding curve segment updates to join it smoothly. This preview
does not add a saved point until you click. Straight-line tools retain a straight
dashed continuation.

Right-click or press Escape to finish a contour. **Femoral Shaft** collects four contours in succession. Place at least two points on each contour, then right-click or press Escape to advance. Review all four traces after placement.

## Results and export

The **Results** section shows both sides and the custom measurements. Calibrated lengths use millimetres. Uncalibrated lengths use scene units (**su**). For ordinary raster files, one scene unit corresponds to a pixel. Medical file spacing can define a different scale. The CSV preserves the calculation frame and records the original image frame when available.

Add **Comments** and complete **Annotator Name**. **Export All** saves a coordinate and measurement CSV, an MRB scene and an annotated PNG. With an output folder selected, **Export All / Load Next Image** advances after saving. The individual export buttons save one format. The PNG includes the annotator and can include the measurement values.

PNG exports use at least 2,048 pixels on the long edge for ordinary image proportions.
Landmarks, contours and text are drawn at the export resolution, so they remain
clear on small source images. Enlarging the radiograph does not add anatomical
detail. Large exports are limited to 40 megapixels and 15,500 pixels per edge.
The measurement box sits at the bottom centre. Its background is translucent,
and annotations retain their colours within it.

With an output folder selected, the app saves files in a subfolder named for the case. If an export group exists, choose **Replace** or **Save new version**. Without an output folder, Chrome saves an individual download or a ZIP for **Export All**. To resume from a downloaded ZIP, extract it into the chosen output folder or open its MRB directly. MRB scenes include the radiograph. Keep scene and image exports in your authorised local storage.

## Research use and credits

This software is a research tool, not a medical device. It is not intended for diagnosis, treatment planning or clinical decision-making.

Developed by **Kaveh Same, MD, MPH, PhD Candidate**, Michael Ogon Laboratory for Orthopedic Research, Orthopedic Hospital Speising, Vienna, Austria. In collaboration with **ImageBiopsy Lab GmbH**, Vienna, Austria. Code backbone created by **Codex**, OpenAI, California, USA.

If you use the tool in research, cite Kaveh Same, *Pelvic X-ray Measurements*, the project repository and the software version used.

For the morphology schematic, see Pothong W, Adulkasem N. Comparative evaluation of radiographic morphologic parameters for predicting subsequent contralateral fragility hip fracture. *International Orthopaedics*. 2023;47:1837–1843. DOI 10.1007/s00264-023-05789-8.
