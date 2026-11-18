# Development

The repository contains two implementations with a shared measurement and export
contract. The complete Slicer framework tree is under **extension_source/**. The
web application is under **web/**, with its Python measurement core, browser
interface, resources and synthetic tests kept together.

## Build the web app

Use Python 3.11 or later in a development environment. These dependencies are for
building and testing; website visitors do not install Python or any packages.

```sh
python -m pip install -r requirements-dev.txt
python scripts/fetch_assets.py
python scripts/build.py
python web/scripts/serve_local.py
```

The preview command prints its loopback address. **build/web/** contains
**index.html** and the **components/** folder. Serve the entire folder tree and
use **application/json** for its JSON files. The build manifest identifies every
required file. The runtime is compressed before being encoded into bounded JSON
components, then verified and expanded inside the browser.
**build/site/** contains the landing page, app, rendered manuals and test review
for GitHub Pages. Only build output is deployed, never the repository or test data.

The fetch command restores model assets from their versioned GitHub release and
the browser runtime from pinned upstream distributions. It verifies checksums and
does not accept changed files. All caches and build products remain inside the
repository and are ignored by Git. After asset restoration, builds can run offline.

## Check and package

```sh
python scripts/verify.py --slicer SLICER_EXECUTABLE --chrome CHROME_EXECUTABLE
python scripts/package_release.py
python scripts/audit_release.py
```

The full verifier requires installed Slicer and Chrome executables. Its output
records both complete and omitted stages. Select an explicitly reviewed passing
run with **scripts/select_evidence.py --run RUN_DIRECTORY**; this refreshes the one
published evidence folder per edition. Never label a skipped or failed run as passed.

Packaging writes new versioned ZIPs and checksums under **build/releases/**.
It excludes generated test reports, caches and private data. The complete extension
bundle includes its models, manuals and test source. The web ZIP contains the
application runtime, licences and hosting instructions. Test results remain in the
source evidence folders and on the documentation website.

## Keep the editions aligned

For a measurement, export or common-placement change, update both implementations
and their relevant tests in the same pull request. Keep the version in
**release.json**, the Slicer constants, web engine, citation and release notes
consistent. The release audit checks these values and model checksums.

UI changes may be edition-specific. Do not force Slicer viewing controls into the
focused web workspace. Preserve the same measurement definitions and saved-data
meaning. Document actual format limitations and test round trips when they change.

New model weights need a new immutable model asset release and updated hashes in
**model-assets.json** and the extension's **ResolveModels.cmake**. Run the shared
verification pipeline before publishing an updated model or software release.
