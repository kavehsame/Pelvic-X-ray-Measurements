# Privacy and file handling

The web app reads the radiographs and saved annotations that the user selects on
their own device. It performs decoding, point placement, measurements and export
inside the browser. Images, annotations, filenames and export contents are not
sent to this project's website host. The Slicer extension performs its work in
the local Slicer session.

## What the website downloads

The browser loads the page and, after **Start**, the software package. This package
contains the code, runtime and Smart Point Placement models. The app checks its
checksum and may reuse the browser's cached copy for the same build. Clearing site
data, using a different browser profile or opening a new build may require another
download. The cache contains the software package, not a backup of annotations.

Once preparation finishes, the measurement workspace blocks network connections.
An open workspace can complete its work offline. A new visit still needs access
to the page. A locally selected image is read into the browser; choosing it is not
an upload operation.

## What the host sees

The host receives ordinary requests for the page and software. This is separate
from the image-processing workflow. GitHub states that Pages records visitor IP
addresses for security purposes. See [GitHub Pages data collection](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages#data-collection).
The project does not include analytics, advertising or an image-upload endpoint.

## Saving and closing

Exports are written to the chosen output folder where the browser supports that
permission, or through its download mechanism. Saved scenes and CSVs can contain
images, annotator names, comments and source filenames. Store and share them under
the rules applicable to the research project. The software does not anonymise
images or remove burned-in identifiers.

Export before closing a scene or browser tab. Unsaved working annotations are not
a durable backup. Browsers can revoke folder permissions or clear cached data.

**Research use only.** The software is not a medical device and is not intended
for clinical decision-making.
