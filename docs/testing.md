# Software tests and validation

The automated checks answer whether the implementations reproduce defined
calculations, reconstruct saved annotations and support the tested workflows.
A validation study is being performed to compare the tool with established
medical software. That study is separate from the software checks; completed
clinical validity or regulatory approval is not claimed.

## Selected evidence

The [interactive review](https://kavehsame.github.io/Pelvic-X-ray-Measurements/tests/)
links the selected Slicer and web runs. Each edition retains one selected evidence
folder in source. New development runs go to an ignored build folder. Generated
results do not enter the downloadable Slicer or web bundles.

- **Slicer:** 116 unit tests; a full CSV replay matching 397 reference rows; Smart
  Point Placement; live multi-guide axes, morphology, bilateral leg-length lines,
  circle visibility and advancement through four shaft contours.
- **Web:** 25 unit tests covering import, image frames and editing regressions;
  a core measurement replay; and 18 Chrome workflow groups that exercise the built
  app, including offline operation, export, resume and compressed image decoding.
- **Measurement coverage:** the native replay gate requires 58 measurements, 114
  coordinate roles and 25 analytical constructions. The web replay compares 58
  measurements and 81 numeric values with the fixed reference.

The reference CSV is retained rather than regenerated during routine testing.
It was originally produced by the extension and is a regression reference, not an
independent medical-software comparator. Independent image-frame tests compare
NRRD, MetaImage and NIfTI coordinates with SimpleITK or NiBabel.

The Slicer CSV comparison requires exact column names, row order, labels, units,
metadata and blank values. Finite measurement values and point coordinates may
differ by at most eight representable binary64 floating-point steps to accommodate
rounding across operating systems. The report lists these fields separately and
records whether the file bytes are identical. This is a numerical regression rule,
not a clinical accuracy threshold.

## Run the checks

Install the dependencies in **requirements-dev.txt**, restore the pinned assets
and run the common verifier. Run commands from the repository root.

```sh
python scripts/fetch_assets.py
python scripts/verify.py --slicer SLICER_EXECUTABLE --chrome CHROME_EXECUTABLE
```

The executable arguments select installed Slicer and Chrome programs. The verifier
runs both unit suites, the live Slicer checks, the browser core replay, the web
build and the actual Chrome workflow. It records results, source hashes and the
runtime environment in a new folder under **build/**. Before website publication,
**scripts/check_site.py** also checks the landing page at desktop and narrow widths,
starts the app from a project subpath and opens a synthetic scene after the test
host is disconnected. This checks the URL structure used by GitHub Pages.

For a check without an installed Slicer, use **--web-only**. That mode still runs
the Slicer unit suite but explicitly omits the live Slicer replay. It must not be
reported as a full two-edition run.

GitHub Actions runs the checks supported by its configured runner. A workflow file
being present is not evidence that a remote run has passed. Local selected results
record the platform actually tested; they do not imply native testing on every OS.

## Updating expectations

Treat a changed measurement reference as a scientific change. Explain why it is
needed, review the relevant construction or formula independently and retain the
previous reference in history. Do not regenerate it merely to pass a failing test.
Run the same full workflow after changes to shared definitions, exports or models.

The optional files under **Testing/Python/validation/** support research work.
Their directory name does not imply completed clinical validation.

**Research use only.** The software is not a medical device and is not intended
for diagnosis, treatment planning or other clinical decision-making.
