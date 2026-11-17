# Pelvic X-ray Measurements

Editable pelvic radiograph measurements for research, available as a **3D Slicer
extension** and a **web application**. Place and refine landmarks, inspect the
geometry behind each measurement and export coordinates, results and annotated images.

**Research use only. This software is not a medical device.** It is not intended
for diagnosis, treatment planning or other clinical decision-making.

[Open the web app](https://kavehsame.github.io/Pelvic-X-ray-Measurements/app/)
· [Download the Slicer extension](https://github.com/kavehsame/Pelvic-X-ray-Measurements/releases/latest)
· [User manuals](docs/README.md)
· [Software checks](https://kavehsame.github.io/Pelvic-X-ray-Measurements/tests/)

## Choose an edition

| | Web application | 3D Slicer extension |
| --- | --- | --- |
| Start | Open the website and select **Start** | Add the module to an existing Slicer installation |
| Processing | Runs in the browser on the user's device | Runs in the user's Slicer session |
| Best suited to | A focused, single-radiograph workspace without installation | Work involving Slicer scenes and its imaging tools |
| Export | CSV, annotated PNG and MRB scene | CSV, annotated PNG, MRB scene and optional sampled contour coordinates |
| Guide | [Web manual](docs/web-manual.md) | [Slicer manual](extension_source/SlicerPelvicXrayMeasurements/documentation.md) |

Both editions use editable landmarks and the same measurement definitions. The web
app uses a browser runtime and does not require Slicer, Python or an application
server on the user's computer. Chrome or Edge provides the most convenient folder
export workflow. See [privacy and file handling](docs/privacy.md).

## Start a case

1. Open a radiograph, enter an annotator name and choose an output folder.
2. Place the calibration ball when one is available and place the pelvic reference
   at teardrop level whenever feasible.
3. Select the anatomical side. Fit the native or implant head, then place the
   measurements manually or use **Auto-place points…**.
4. Inspect and adjust every landmark. Read the results and export the case.

Tools cover native and implant head fitting, shaft and neck axes, acetabular angles,
offsets, leg-length discrepancy, femoral morphology, cup opening geometry, pelvic
and shaft contours, labelled points and custom lines and angles. Shared landmarks
reduce repeated placement while remaining editable. Automatic placement is a
starting estimate, not an anatomical assessment.

## Install in Slicer

Download **PelvicXrayMeasurements_1.6.0_Slicer_extension.zip** from the release.
Extract it and keep the complete folder together. In Slicer, add the inner
**PelvicXrayMeasurements** folder containing **PelvicXrayMeasurements.py** through
**Application Settings → Modules → Additional module paths**, then restart Slicer.
The module is under **Orthopaedics**.

This ZIP is a complete scripted-module bundle, not an Extensions Manager installer.
It includes the Smart Point Placement models. GitHub's automatically generated
source archives omit these separately versioned assets. An Extensions Manager
listing requires a separate Slicer catalogue submission; it is not claimed here.
See [installation and downloads](docs/installation.md).

## Tests and evidence

**Selected release checks are available as an [interactive review](https://kavehsame.github.io/Pelvic-X-ray-Measurements/tests/).**
The source retains one selected run for each edition:

- [Slicer unit tests and full CSV replay](extension_source/SlicerPelvicXrayMeasurements/test_reports/current/index.html).
- [Web unit tests and Chrome workflow replay](web/test_reports/current/index.html).

The release check covers 116 Slicer unit tests, 25 web unit tests, all 397 rows of
the native synthetic CSV replay and 18 Chrome workflow groups. The web measurement
replay compares 58 measurements and 81 numeric values with a fixed reference.
Interactive checks include multi-guide placement, shaft morphology, four shaft
contours, shared landmarks, Smart Point Placement, visibility, export and resume.

These tests establish software behaviour on the tested configuration, not clinical
accuracy. A validation study is being performed to compare the tool with established
medical software. See [testing methods and limitations](docs/testing.md). Generated results
are excluded from the downloadable extension and web bundles. Source HTML reports
can be opened locally after downloading the repository.

## Repository layout

```text
.github/                 Automated checks, website deployment and issue templates
docs/                    Manuals, release notes and contributor guidance
extension_source/        Complete Slicer extension, its resources and tests
web/                     Browser measurement core, interface, assets and tests
scripts/                 Shared build, asset, test and packaging commands
```

Runtime dependencies, model weights and generated builds are excluded from Git.
Pinned downloads and checksums make them reproducible build inputs. Finished
bundles and models are distributed through GitHub Releases. The website is deployed
through GitHub Pages. [Development and release instructions](docs/development.md)
explain how both editions are updated and checked together.

## Credits and licence

**Developed by:** Kaveh Same, MD, MPH, PhD Candidate, Michael Ogon Laboratory for
Orthopedic Research, Orthopedic Hospital Speising, Vienna, Austria.

**In collaboration with:** ImageBiopsy Lab GmbH, Vienna, Austria.

**Code backbone created by:** Codex, OpenAI, California, USA.

Original project code and project artwork use the [Apache License 2.0](LICENSE.txt).
The aggregate Smart Point Placement models use the same licence. Dependencies
retain their own terms; see [third-party notices](THIRD_PARTY.md) and [NOTICE.md](NOTICE.md).
Please cite Kaveh Same, the repository and the software version in research reports.
The [citation file](CITATION.cff) provides structured citation metadata.

[Contributing](CONTRIBUTING.md) · [Support](SUPPORT.md) · [Security](SECURITY.md)
