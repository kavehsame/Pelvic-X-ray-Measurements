# Agent handover

This is the technical starting point for an agent taking over Pelvic X-ray
Measurements. Read the current source, `release.json` and the relevant tests
alongside this document. User workflows are in the [web manual](web-manual.md)
and the Slicer extension's `documentation.md`. Testing methods and limitations
are in [testing](testing.md).

## Planning and implant overlays

Maintain the shared [implant overlay guide](implant-overlays.html) in `docs/implant-overlays.html`. Its downloadable sample and schema come from the adjacent JSON files. Run `python -B scripts/sync_metadata.py` after editing them or the guide, then run it with `--check`. The web build embeds the self-contained HTML for offline use and ships a separate readable copy. The Slicer package installs the same bytes in the module's Resources directory and opens them with the system browser. Keep the PDF conversion method, source attribution and sheet-scale checks aligned with the catalogue when it changes.

The paired planning modules in the web core and the Slicer helper library share stable role names, physical outline coordinates, saved template identifiers and fragment transforms. The paired CSV readers group points by role and explicit index. Preserve these identifiers when adding a tool. Keep the historical CSV fixtures and run the planning interaction tests in both editions.

**Retained Bone Fragment Placement** computes a lateral-to-medial boundary in physical image axes, using any available head, shaft and lesser-trochanter landmarks. Manual points can extend beyond the film. Both modes store the same explicit boundary and cut type. A completed trace is hidden. The web canvas and Slicer red-view event handlers translate and rotate both the fragment and implants. The fragment uses its existing fragmentTarget position, saved view axes and FragmentAngle on both sides. Its Hide control covers the image patch and pivot. Keep the internal fragment_pose workflow key and fragmentTarget markup role when revising this panel. Interactive rotation handles stay out of PNG and CSV exports. The optional session import uses the shared atomic validator described in [Overlay format](overlay-standard.md). Its pose is a rigid transform about the midpoint of the cut ends. The Slicer preview is a disposable foreground volume. The web viewer uses the same transform when drawing the source pixels into the canvas and exported PNG. The source image and its landmarks stay in their original frame. Cup-shell and head circles are independent. Wear is their projected centre separation on one image.

Both release builds include the catalogue and the processed AP overlays. Each bundled AP record stores a PNG checksum, physical pixel pitch, pivot in cropped-image pixels, drawing side and permitted patient side. A missing reference retains its saved ID and anchor. Use the same four-corner map for the live view and image export. Local patient pixel spacing defines the base scale. A measured ball provides one magnification correction. The web preparation includes the artwork in its verified cache. The original session JSON format continues to accept vector outlines. Restore both processed files from the versioned release specified in `implant-assets.json`. The build verifies the catalogue and image archive before packaging them. [Third-party materials](../THIRD_PARTY.md#implant-planning-drawings)

Each bundled raster record links to its source sheet through `scaleSheet`. The catalogue's `scaleSheets` stores the physical reference interval and its vector in original PNG pixels. The physical pixel pitch comes from that sheet's ruler, its printed 1:1 scale, or its dimensioned head-centre marks. Preserve the scale when cropping, rotating or mirroring. Recheck the original sheet when replacing artwork. The numerical tests in both editions exercise every sheet through the template placement transform.

## Product and current scope

Version 1.8.1 reports only implants with a placed pivot. Both editions use `node_template_choice` and `implant_report` in their matching planning modules. Each anchor keeps its catalogue ID, angle, family and size. For raster templates, preserve the saved rotation frame. Keep the ordinary CSV columns and the existing coordinate and attribute rows. The additional named metadata rows use `{Left|Right}_Planning_{Cup|Stem}_{Component|Family|Size|ID}`. The PNG prints one implant per line even with numeric results off. The resection tools still calculate and export the cut geometry and lengths. Keep those lengths out of the panel and PNG.

The maintained editions are a 3D Slicer scripted extension and a static website
whose measurement workspace runs entirely in the visitor's browser. Their common
measurement definitions and saved-data meaning must agree. The web interface is
purpose-built for one radiograph and does not reproduce Slicer's full interface.

Version 1.8.0 adds bilateral hip templating, femoral resection and fragment placement, CSV import by field and a single-film wear estimate. Version 1.7.1 makes landmark selection easier, keeps pixels sharp during high-zoom
panning and adds direct case navigation in the web viewer. Version 1.7.0 introduced
high-resolution exports, a bottom-centre web PNG summary, bilateral acetabular
wall contours, curved web placement previews and larger morphology help. The wall
contours belong directly after Acetabular Roof (Sourcil). See the [changelog](https://github.com/kavehsame/Pelvic-X-ray-Measurements/blob/main/CHANGELOG.md).

The software is for research and is not a medical device. It is not intended for
diagnosis, treatment planning or other clinical decision-making. A validation
study comparing it with established medical software is in progress. Regression
checks and synthetic replays must not be described as clinical validation.

- Repository: [kavehsame/Pelvic-X-ray-Measurements](https://github.com/kavehsame/Pelvic-X-ray-Measurements).
- Website: [GitHub Pages](https://kavehsame.github.io/Pelvic-X-ray-Measurements/).
- Software releases contain the complete extension ZIP, a web hosting ZIP and
  `SHA256SUMS.txt`. Normal website visitors do not download or unpack the hosting ZIP.
- Slicer extension catalogue submission is a separate publication step. Do not
  claim that a GitHub release is already listed in the catalogue.

## Repository map

| Location | Responsibility |
| --- | --- |
| `release.json` | Product version, repository and public addresses |
| `model-assets.json` | Immutable model release, asset names, sizes and SHA-256 hashes |
| `extension_source/SlicerPelvicXrayMeasurements/` | Complete Slicer framework tree, resources, documentation and tests |
| `web/core/` | Python measurement session, geometry, import, export, interaction and suggestion logic |
| `web/ui/` | Browser interface, viewer, local file access, startup loader and worker |
| `web/assets/` | Icons, schematic, hover help, notices and restored model assets |
| `web/runtime/manifest.json` | Pinned browser runtime downloads and checksums |
| `web/tests/` | Unit tests and synthetic MRB/CSV references |
| `web/scripts/` | Build, restricted local server, replay and real-browser checks |
| `scripts/` | Asset restoration, common verification, site build, packaging and audit |
| `docs/` | Dedicated web manual, development, privacy, models, network and release documentation |
| `.github/workflows/` | Reusable checks, Pages deployment and release preparation |
| `build/` | Ignored build products, caches and new verification runs |
| `test_reports/current/` within each edition | One selected, sanitised evidence run |

Do not spread the extension's internals into repository-level folders. CMake,
Slicer module and resource names are framework requirements. Models and runtime
binaries are restored build inputs, not ordinary source-history additions.

## Slicer implementation

The module entry point is `PelvicXrayMeasurements/PelvicXrayMeasurements.py` inside
the extension. It constructs the panel and connects actions. Most behaviour is
in `PelvicXrayMeasurementsLib/`:

- `Constants.py` defines stable measurement keys, bilateral roles, visibility
  groups, morphology layout, help resources and the module version. The full
  filenames begin with `PelvicXrayMeasurements`.
- `NodeSpecs.py` defines MRML classes, names, labels, colours and completion counts.
- `Scene.py` manages owned nodes and placement mode.
- `Workflow.py` handles placement queues, shared landmarks, edge attraction,
  custom measurements and four successive femoral-shaft contours.
- `Calculations.py` derives geometry and values from current control points.
- `Geometry.py` contains numerical helpers; `Results.py` defines result records.
- `AutoPlacement.py` applies model suggestions to normal editable markups.
- `CaseWorkflow.py` handles saved metadata and case loading; `CaseExport.py`
  produces scene, coordinate CSV and optional sampled-curve TXT exports.
- `ImageExport.py` renders the full radiograph and annotation layer at export
  resolution, then draws the optional measurement summary.

Control points and derived nodes remain separate. Derived circles, ellipses and
axes must follow edits and Hide state. Avoid coupling independent placement
queues or allowing one tool's completion to finish another.

## Browser implementation

`web/ui/app.js` coordinates the panel, local files, cases, worker requests,
resume, exports, hover help and unsaved-edit state. `viewer.js` draws the
radiograph and markups, translates pointer coordinates and manages pan, zoom,
window adjustment, edit previews and PNG rendering. `style.css` and `index.html`
define the interface. Keep button text aligned with the extension where the
same action exists.

`worker.js` starts the pinned Python/WebAssembly runtime and routes requests to
`core.engine`. The Python `Session` holds the image, settings, scene,
`BrowserPlacement` controller and suggestion controller. There is no Slicer
process or application server in the visitor's workspace.

`core.scene` provides the MRML-like accessors needed by the browser's calculation
and workflow code. `schema` defines node roles and appearance. `workflow`,
`interaction_rules`, `landmarks` and `custom` implement placement and calculations.
`geometry` holds numerical helpers. `imaging` decodes and reorients images;
`scene_files` handles MRB/CSV reconstruction. `csv_export` writes the shared table.
`suggestions` applies the coordinate and image model through `auto_placement`.

Some browser files retain descriptions of their original porting source. The
current fork owns these files. No automatic source generator is needed for a
normal build; verify a referenced script exists before attempting to run it.

## Privacy and startup boundary

The website is a static GitHub Pages deployment. Before Start completes, the
browser makes same-origin HTTPS GET requests for the page and labelled JSON
software components. The builder compresses the existing runtime with gzip,
splits it into bounded segments and base64-encodes each segment with checksums.
The loader verifies each segment, the compressed stream and the expanded payload.
It retries transient failures once and can reuse verified partial downloads.

Verified software is cached with the Cache API under `pelvic-xray-software`.
`runtime.bin?sha256=...` is a virtual cache key, not a binary network request.
Unavailable or full storage may prevent caching but must not stop a valid
current-session startup. An interrupted start must not enable image selection
or execute unverified software.

After preparation the workspace adds a restrictive network policy, including
`connect-src 'none'`. Runtime resources are supplied locally to the worker.
Do not introduce analytics, remote image decoding, API inference, external
fonts, remote workers or fallback CDN requests after image selection.
Check [privacy](privacy.md) before changing file or network handling.

The JSON transport does not remove the ZIP-based Python packages inside the
runtime. Restricted networks may still inspect or block them. Hospital-network
startup was reported working by a user after 1.6.1; this is not general network
acceptance or an Edge regression test. Retain the landing-page notice and useful
download diagnostics. See [network access](network-access.md).

## Coordinates and saved-data contract

- Native Slicer geometry uses RAS coordinates. Image dimensions, spacing,
  origin and orientation all affect conversion to and from pixel coordinates.
- The web viewer displays pixel coordinates. The Python scene preserves an
  affine image frame. Reorientation maps coordinates deliberately; it must not
  silently reinterpret saved RAS coordinates as pixels.
- Use role identifiers such as `left_shaftMorphologyPoints`, rather than
  display names, to identify a node. Bilateral roles start with `left_` or `right_`.
  Custom points, lines and angles use stable indexed role names.
- Slicer CSVs use `section`, `name`, zero-based `index`, `label`, `x_ras`,
  `y_ras`, `z_ras`, curve settings and measurement fields. Point `details`
  identifies the role, sometimes followed by classification metadata.
- Web CSVs retain those columns and add `role`, one-based `point_index`,
  `r`, `a`, `s` and `annotator`. Check which index field a reader uses.
- Preserve CSV quoting, Unicode, multiline comments and the optional UTF-8 BOM.
  CSV files are tracked without newline conversion. Numeric comparison and raw
  byte comparison are reported separately.
- Saved scenes and CSV metadata carry the image frame, annotator, comments,
  calibration, neck-axis options and other reconstruction settings. Do not
  change a saved-data meaning without compatibility tests.
- MRB files are ZIP containers holding a scene, image and markups. Treat them
  as untrusted input. Retain path, transform, size and supported-role checks.
  No external referenced file is fetched by the browser importer.
- The browser's MRB support covers its single-radiograph workflow, not arbitrary
  Slicer scenes. Its writer currently supports linear and cardinal-spline curve
  names; non-default interpolation and sampling settings are more fully represented
  in the coordinate CSV. Review `scene_files.py` before extending these options.

## Measurement and interaction invariants

Length-like values use scene units (`su`) before calibration. A fitted calibration
ball supplies millimetres per scene unit. Ratios and angles are dimensionless or
degrees. Preserve the `su` explanation and the calibrated reference-line value.

The reference line should be at teardrop height whenever feasible. Smart Point
Placement uses this relationship; a line at ischial-tuberosity height can reduce
suggestion accuracy. The prerequisites are calibration, reference and exactly one
head type on the active side. Native head versus implant head determines pre- or
post-operative suggestions. Selection opens a checklist before placement.

Suggestions remain editable markups. Shaft-axis guides, LT points and morphology
controls are inferred before their constructions are derived. Preserve existing
points, guide-length sanity checks and medial/lateral morphology constraints.
New wall contours do not have trained suggestion models.

Shared-landmark tools alternate between shared and manual redraws, starting with
shared placement. Clear the full previous construction, including angle arms,
when redrawing. The sourcil contour can seed the lateral sourcil landmark; the
anterior and posterior wall curves do not participate in that landmark reuse.

Neck axes support single-guide and through-centre options. Automatic implant-neck
placement selects both. Multi-guide tools advance independently through every
required guide. Femoral Shaft contour placement advances through four curves and
classifies medial/lateral and inner/outer only after all four are present.

Morphology uses ten controls in addition to two lesser-trochanter landmarks:

| Zero-based control indices | Station and use |
| --- | --- |
| 0–1 | Canal width 2 cm above the LT midpoint, used by CFI |
| 2–3 | Canal controls 3 cm below the midpoint, defining the proximal CCR guide caps with indices 5–6 |
| 4–7 | Outer and inner widths 10 cm below the midpoint, used by CCR, CTI and CFI |
| 8–9 | Adjustable distal pair seeded 11 cm below the midpoint; exported but unused by these three indices |

CCR is distal inner canal width divided by proximal guide-cap width, B/A.
CTI is (outer width − inner width)/outer width at 10 cm below the LT midpoint.
CFI is canal width at 2 cm above divided by inner width at 10 cm below.
Do not invert CCR or infer medial/lateral meaning from a point's A/B suffix.
The last pair shares an adjustable axial station.

The web viewer keeps pan and window gestures distinct from placement. Space-drag,
Ctrl-drag, middle-button drag and the Pan toggle preserve an unfinished tool.
Shift-drag moves both window limits together. Escape cancels an edit preview.
Preview state must not modify the saved scene until an action commits.

Landmark picking uses an 8 CSS-pixel radius independent of zoom. Focus persists
until another candidate is clearly closer or the pointer leaves the radius.
Clicking cycles overlapping candidates. A drag captures the chosen role and
control index and preserves the offset from pointer to point. Show the hand only
while the image pans. Display smoothing is disabled when a source pixel spans at
least two backing pixels in both axes. The case jump uses the same `loadCase`
path as the arrows, including working annotations and saved-export lookup.

PNG exports fill the frame with the radiograph at preserved proportions. Small
images are enlarged before annotations and text are rendered. The minimum long
edge is 2,048 pixels, bounded by 40 megapixels and 15,500 pixels per edge. Upscaling
does not add anatomical information. The web summary is bottom-centred and
translucent; annotations keep their colours over it. Export size and zoom must
not change measurement values or saved coordinates.

## Models, resources and licensing

The current software uses `models-v1.6.0`. Do not retrain or replace weights for
an interface change. `scripts/fetch_assets.py` verifies both models and runtime
downloads. `model-assets.json` is authoritative for URLs, sizes and SHA-256 hashes;
the extension's `ResolveModels.cmake` must agree.

- `auto_point_model.json`: `0884740f04ab921995de9ae73cb116a92273a5f782b7ff7b74d3a420ef23550e`.
- `auto_point_image_model.npz`: `b1e0dcc0bc7be8bbd4af9d1510ef955fc469adea15eed665d645a6da1a699ebc`.

The models are aggregate assets. Training images and individual annotation tables
do not belong in the public source or release. The project licence is Apache-2.0.
Preserve `LICENSE.txt`, `NOTICE.md`, `CREDITS.md`, `CITATION.cff`, `THIRD_PARTY.md`
and upstream runtime licences. The morphology schematic and citation are bundled
resources in both editions. Use `scripts/sync_metadata.py` after metadata changes.

## Build and local checks

Run commands from the repository root with Python 3.11 or later. Use the task's
designated development environment. Visitors need no Python installation.

```sh
python -m pip install -r requirements-dev.txt
python scripts/fetch_assets.py
python scripts/build.py
python web/scripts/serve_local.py
```

The app preview serves `build/web/`; the complete documentation site is
`build/site/`. Keep `index.html` and the entire components directory together.
Opening the HTML through a file URL is not the supported launch method.

```sh
python scripts/verify.py --slicer SLICER_EXECUTABLE --chrome CHROME_EXECUTABLE
python scripts/check_site.py
python scripts/package_release.py
python scripts/audit_release.py
```

The full verifier restores assets, checks Python source, runs both unit suites,
executes the native CSV replay and live Slicer workflows, runs the web core replay,
builds the app and exercises component delivery, Chrome workflows and presentation.
It records source hashes and fails if source changes during the run. On Linux,
live Slicer checks need the rendering prerequisites and a display such as Xvfb;
see the checked workflow for the exact setup.

`--web-only` omits live Slicer checks while retaining its unit suite. Report that
limitation. Browser checks use isolated profiles and synthetic inputs, not the
user's active browser session. Chrome's Linux temporary socket path uses a short
descriptor alias to the same project-contained temporary directory.

The fixed comprehensive CSV covers all 58 measurements and their explicit and
derived constructions. Version 1.7.0 extends it to 413 rows and 118 coordinate
roles, including both wall curves on both sides; all existing expectations are
retained. The reference came from an earlier implementation and is a regression
reference, not an independent clinical comparator.

The native comparator requires exact schema, ordering, labels, units, metadata
and blanks. Finite numeric measurement and coordinate fields may differ by at
most eight representable binary64 steps for cross-platform rounding. Never
broaden that rule to conceal a material discrepancy. The web measurement replay
compares 58 measurements and 81 numeric values with its fixed reference. See
`docs/testing.md` for the current selected suite counts.

`check_presentation.py` checks low-resolution export, centred translucent summary,
both wall controls, curved provisional drawing and larger help. `check_downloads.py`
tests blocked binary routes, failures, altered components, cache conditions and
recovery. These simulations do not prove network access at a particular hospital.

## Select evidence and prepare a release

Retain prior source and product releases. Use a new verification directory for
each run. Preserve the prior selected reports before replacing their files.
`scripts/select_evidence.py --run RUN_DIRECTORY` accepts a passing full run whose
source hashes match the current checkout. It requires a new destination folder;
do not bypass its source or pass checks. Each edition's `test_reports/` must end
with exactly one `current/` directory, not multiple copies.

Selected evidence belongs in source and on the documentation website. Product
ZIPs exclude generated reports and runtime logs, while keeping the extension's
test source. Do not pack an entire developer working folder as a product.

For a version change, align `release.json`, Slicer's `MODULE_VERSION`, the web
engine's `VERSION`, `CITATION.cff`, current download names, both manual changelogs,
root changelog and release notes. Run `scripts/sync_metadata.py` and the audit.
Model versions stay independent. Add focused commits for distinct features and
include relevant tests and documentation with them.

Before authorised publication, review the diff, source hashes, passing full run,
site check, product contents, licences and checksums. Do not include patient data,
private paths, credentials, cached environments or obsolete product descriptions.
Do not publish with failed or omitted required checks.

The Pages workflow runs reusable Linux checks, builds and audits the site, then
deploys the static build. A push to `main` triggers deployment, so it is a public
action. Release preparation has its own workflow and creates a draft. Inspect the
actual workflow result and release asset hashes; workflow files alone are not
evidence of a passing run. Never replace an existing tag or immutable model asset.

## Starting a new task

1. Read the user's requested scope and current Git status. Preserve existing work.
2. Check the affected code and saved-data implications in both editions.
3. Make the smallest coherent change and add behavioural checks proportionate to it.
4. Update the manuals and this handover where their facts change.
5. Run the relevant focused checks, then the required full release pipeline.
6. Review actual outputs, including PNGs and the interactive CSV comparison.
7. Report the implementation, evidence, omissions and publication state accurately.

If a task is interrupted, use the branch history, source hashes and verification
summaries to establish its state. A cached model, old successful report or existing
product ZIP does not establish that the current source has passed its checks.
