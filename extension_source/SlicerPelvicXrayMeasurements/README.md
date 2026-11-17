# Pelvic X-ray Measurements for 3D Slicer

A scripted Slicer module for calibrated pelvic radiograph research. Place editable
landmarks, inspect fitted geometry, calculate bilateral measurements and save a
scene, coordinate CSV or annotated image.

**Research use only.** This software is a research tool, not a medical device. It is not intended for diagnosis, treatment planning or other clinical decision-making.

## Install the extension bundle

1. Install the Slicer version listed in the release notes.
2. Download and unzip the complete extension bundle from the project's
   [Releases page](https://github.com/kavehsame/Pelvic-X-ray-Measurements/releases).
3. In Slicer, open **Application Settings → Modules → Additional module paths**.
4. Add the **PelvicXrayMeasurements** module folder containing
   **PelvicXrayMeasurements.py**. Keep its helper and Resources folders intact.
5. Restart Slicer and open **Pelvic Xray Measurements**, under **Orthopaedics**.

This bundle includes Smart Point Placement models. GitHub's automatically generated
source archive does not include those separately distributed assets. Developers
building from a checkout must retrieve the checksum-pinned models first.
An Extensions Manager listing is planned; direct bundle installation is available
independently of catalog approval. Do not install this source ZIP as a compiled
Extensions Manager package.

## Start measuring

Choose a radiograph, enter the annotator name and select an output folder. Place
the calibration ball when present, then the pelvic reference at teardrop level
whenever feasible. Select Left or Right. Use the manual tools or **Auto-place
points…**, inspect every landmark and read the results. Export the editable scene
alongside the CSV when you want to continue the case later.

The [user manual](documentation.md) describes every measurement, contour, shared
landmark, option and export format. Tests are included under **Testing**.

## License, credit and evidence

**Selected software checks: 87 unit tests; a full replay covering all 397 reference
CSV rows; Smart Point Placement; and live multi-guide, morphology, leg-length,
circle-visibility and shaft-contour workflows.** The selected results are available
in the source tree's [interactive test review](test_reports/current/index.html),
including its [CSV replay comparison](test_reports/current/replay/comparison_report.html).
The review records the run date, outcomes and limitations. Only one selected run
is retained in source; reports are excluded from the downloadable extension bundle.
The checks can be rerun with **Testing/Python/verify.py** using **--slicer** and
**--output**. They exercise synthetic cases rather than patient data.

Original project code uses the [Apache License 2.0](LICENSE.txt). Dependencies retain
their own terms; see [NOTICE](NOTICE.md), [credits](CREDITS.md) and
[third-party information](THIRD_PARTY.md). Please cite Kaveh Same, the repository
and the version used in research reports.

Unit tests and synthetic CSV replay verify software behavior. Independent
validation against established medical software is in progress; no completed
clinical validation or medical-device approval is claimed.
