# Changelog

## 1.7.0

- Render exported annotations and text at a useful resolution for small source images while the radiograph fills the frame.
- Centre the web PNG measurement summary at the bottom.
- Add bilateral Anterior Acetabular Wall and Posterior Acetabular Wall contours, with distinct colours and complete coordinate export.
- Preview the curve towards the pointer during web contour placement.
- Enlarge morphology-index help to fit the screen.
- Add a technical agent handover and extend synthetic replay and presentation checks.

## 1.6.1

- Smaller JSON component transfers, verified caching, interrupted-download reuse and transient retries for web startup.
- Clear download errors with details for IT support and a restricted-network notice on the landing page.
- Existing measurement, annotation and export behaviour retained; matching Slicer version label.

## 1.6.0

- Slicer extension and browser-based web application with dedicated manuals.
- Editable native and implant measurements, shared-landmark placement, custom
  points, lines and angles, pelvic contours and four femoral-shaft contours.
- Smart Point Placement with selectable feature groups and editable suggestions.
- CCR defined as B/A, with the project morphology schematic and study citation.
- Local CSV, image and scene exports, annotator names, comments and case resume.
- Live web measurement updates, panning during placement, Shift-drag window
  adjustment and verified reuse of the browser's cached software package.
- Corrected CSV restoration of curve interpolation, neck-axis settings, calibration
  and visibility; a newer CSV takes precedence over an older scene in the same export.
- Corrected NIfTI spacing when a valid sform differs from the header's pixdim values.
- Updated unit tests, full measurement replay and interactive workflow checks.

The edition-specific manuals retain their earlier development history. This log
describes the combined publication version; it does not imply that every feature
was introduced at the same time.
