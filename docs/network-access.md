# Restricted networks

The web app may not work on some restricted networks, including hospital networks.
The landing page can load even when a network filter blocks the components needed
after **Start**. If preparation fails, open **Download details for IT support**
under the error. It identifies the requested component, response status when
available and verification stage. These details contain no selected images or
annotations.

## For IT support

The application is hosted at
[kavehsame.github.io/Pelvic-X-ray-Measurements/](https://kavehsame.github.io/Pelvic-X-ray-Measurements/).
Preparation uses HTTPS GET requests to this same host. Component URLs are under
**/Pelvic-X-ray-Measurements/app/components/** and return **application/json**.
There are no third-party runtime downloads during a visitor's session.

Each JSON document contains a labelled base64 segment of the compressed runtime,
with its checksum and position. The browser checks every segment and the complete
package before starting. The package includes WebAssembly, Python
libraries, aggregate Smart Point Placement models and processed implant overlays. Some internal Python
library packages use ZIP format. Content inspection may therefore still block the
runtime even when JSON requests are permitted. This delivery format does not
override an organisation's network or software policy; access may need IT approval.

An HTTP status such as **403** indicates that the request was refused, but does not
by itself identify whether the website or a network intermediary refused it.
An HTML response may be a sign-in or filtering page. A verification failure means
the returned bytes did not match this build. The app does not run unverified
components. Transient failures are retried once, and verified partial downloads
can be reused when **Start** is tried again.

Once preparation finishes, the workspace blocks network connections. Image
loading, annotation, measurement and export happen locally. See
[privacy and file handling](privacy.md).

**Research use only.** This software is not a medical device and is not intended
for diagnosis, treatment planning or other clinical decision-making.
