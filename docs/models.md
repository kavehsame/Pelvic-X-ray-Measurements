# Smart Point Placement

Smart Point Placement suggests editable landmarks after the active side has a
calibration ball, a pelvic reference and exactly one fitted head type. A native
femoral head selects pre-operative features; an implant head selects post-operative
features. The selection window lets the user choose which feature groups to place.
Inspect every suggestion before using the measurements in research.

The model combines coordinate relationships with an image-guided shaft component.
Shaft and lesser-trochanter relationships guide morphology placement, with
medial/lateral and line-size constraints. Automatic implant-neck placement uses a
single guide through the fitted head centre. These constraints do not establish
anatomical correctness.

## Reference and training scope

Place the pelvic reference at teardrop level whenever feasible. A reference at
ischial-tuberosity level, unusual projection, anatomy, implants or image quality
can alter the suggestions. Manual correction remains part of the workflow.

The expanded annotation set contains repeated annotations of the same images.
They are grouped by image for training; repeated annotations do not count as new
independent images. They may reduce observer noise but do not expand the range
of anatomy represented by the image set.

## Versioned assets

The **models-v1.6.0** release provides **auto_point_model.json** and
**auto_point_image_model.npz**, under Apache License 2.0. The fixed sizes, SHA-256
checksums and download URLs are in **model-assets.json**. The Slicer build checks
the same hashes. A changed model requires a new asset version and new checks;
published assets must not be replaced under the same version.

The full Slicer bundle and web runtime already contain both files. Training images
and individual annotation records are not distributed. Source checkouts restore
only the aggregate assets using **scripts/fetch_assets.py**.

A validation study is being performed to compare the tool with established
medical software. It is separate from the automated software tests and does not
constitute completed validation of automatic placement accuracy.

**Research use only. This software is not a medical device.** It is not intended
for diagnosis, treatment planning or other clinical decision-making.
