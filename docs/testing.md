# Software tests and validation

The automated checks answer whether the implementations reproduce defined
calculations, reconstruct saved annotations and support the tested workflows.
A validation study is being performed to compare the tool with established
medical software. That study is separate from the software checks; completed
clinical validity or regulatory approval is not claimed.

## Planning checks

The Planning checks place both cuts, trace and move a fragment, fit the spherical cup shell and choose concrete implant references on synthetic images. A head offset of three pixels in one direction and four in the other yields five pixels, or 6.25 mm at 1.25 mm per pixel. A concentric fit gives zero. A collinear shell fit leaves the value undefined.

The interchange check rotates and mirrors an oblique image, saves a browser CSV, reorders its rows and columns, opens it in Slicer and returns a Slicer CSV to the web engine. It compares eight groups of landmarks and template vertices, the wear estimate and sampled fragment intensities. Both editions also open historical CSV fixtures. The accepted numerical replay for the published version remains a separate regression check.

## Selected evidence

The [interactive review](https://kavehsame.github.io/Pelvic-X-ray-Measurements/tests/)
links the selected Slicer and web runs. Each edition retains one selected evidence
folder in source. New development runs go to an ignored build folder. Generated
results do not enter the downloadable Slicer or web bundles.

- **Slicer:** 117 unit tests; a full CSV replay matching 413 reference rows; Smart
  Point Placement; live multi-guide axes, morphology, bilateral leg-length lines,
  circle visibility and advancement through four shaft contours.
- **Web:** 69 unit tests covering import, image frames, editing regressions and
  component packaging; a core measurement replay; and 18 Chrome workflow groups that exercise the built
  app, including offline operation, export, resume and compressed image decoding.
- **Startup:** 11 browser scenarios covering blocked binary routes, temporary and
  permanent HTTP errors, altered or incomplete responses, timeouts, interrupted
  downloads and unavailable or corrupt caches. These are controlled simulations,
  not evidence of access through a particular hospital network.
- **Measurement coverage:** the native replay gate requires 58 measurements, 118
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

Ten presentation checks cover full-frame low-resolution PNG export, the centred
translucent summary, bilateral wall controls, curved provisional drawing, larger
morphology help, picking and dragging overlapping points, pixel rendering during
a high-zoom pan and jumping within a 1,000-image list while retaining edits.
They also exercise the Planning controls and open the implant guide offline.

## Run the checks

Install the dependencies in **requirements-dev.txt**, restore the pinned assets
and run the common verifier. Run commands from the repository root.

```sh
python scripts/fetch_assets.py
python scripts/verify.py --slicer SLICER_EXECUTABLE --chrome CHROME_EXECUTABLE
```

The executable arguments select installed Slicer and Chrome programs. The verifier
runs both unit suites, the live Slicer checks, the browser core replay, the web
build, component-download scenarios and the actual Chrome workflow. It records results, source hashes and the
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
