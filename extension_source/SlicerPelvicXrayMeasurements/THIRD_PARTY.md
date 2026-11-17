# Third-party software and materials

The Apache 2.0 licence covers this project's original code, artwork and aggregate
Smart Point Placement models. It does not replace the terms of other components.
Keep their copyright and licence notices when redistributing them.

## Slicer extension

The extension runs inside an existing 3D Slicer installation. It uses Slicer's
Python, NumPy, VTK, Qt and MRML facilities. The extension download does not contain
a Slicer distribution. Slicer's own distribution supplies its component licences.
See the [Slicer licence](https://github.com/Slicer/Slicer/blob/main/License.txt).

## Web application

The browser runtime includes the following components. Exact files and SHA-256
checksums are recorded in **web/runtime/manifest.json**. The build checks them
before packaging. Full licence texts are accessible through **User Manual →
Software licences** in the web app.

| Component | Use | Licence family |
| --- | --- | --- |
| Pyodide | Runs the Python measurement code in the browser | Mozilla Public License 2.0, with bundled dependency notices |
| CPython | Python interpreter and standard library | Python Software Foundation licence and included notices |
| NumPy | Numerical calculations | BSD 3-Clause and included notices |
| Pillow | Image decoding and export | HPND/PIL licence and included notices |
| pydicom | DICOM parsing | MIT |
| jpeg-lossless-decoder-js | Lossless JPEG decoding | MIT |
| Cornerstone OpenJPEG and CharLS codecs | JPEG 2000 and JPEG-LS decoding | Wrapper and upstream notices supplied with the exact files |
| OpenJPEG | JPEG 2000 codec | BSD 2-Clause and included notices |
| CharLS | JPEG-LS codec | BSD 3-Clause and included notices |

The browser uses unmodified upstream runtime binaries. The fetch scripts identify
the versioned upstream source locations and verify pinned downloads. Upstream
licences and notices take precedence over this summary. Runtime dependencies are
downloaded at build time, then bundled; visitors do not install them separately.
Development-only packages in **requirements-dev.txt** are not part of the web runtime.

The corresponding source for the bundled Pyodide version is available from
[Pyodide 314.0.8](https://github.com/pyodide/pyodide/tree/314.0.8), including its
build recipes. The interpreter source is available from
[CPython 3.14.2](https://github.com/python/cpython/tree/v3.14.2). These upstream
sources and their licences remain available independently of this project's code.

## Artwork and scientific reference

The project icon and explanatory morphology schematic were created for this
project and are distributed under Apache License 2.0. The schematic accompanies:

Pothong W, Adulkasem N. Comparative evaluation of radiographic morphologic parameters
for predicting subsequent contralateral fragility hip fracture. International
Orthopaedics. 2023;47:1837–1843. https://doi.org/10.1007/s00264-023-05789-8

The citation identifies the scientific reference and does not imply endorsement.
See [model information](docs/models.md) for model scope, licence and limitations.
