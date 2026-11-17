# Optional research comparison utilities

This folder contains a CSV comparison helper and PNG-to-DICOM conversion utility.
They are optional research tools, separate from unit tests and synthetic CSV replay.
No research images, clinical annotations or ground-truth dataset are supplied.

**generate_validation_report.py** compares an extension export with a user-supplied
reference CSV. Select the export with **--actual**, the reference with
**--ground-truth**, and a new report folder with **--output-dir**. Use **--help** for
format and tolerance options. The helper grades the rows in the reference; use
**--include-actual-only** to list extra exported rows as well.

Reports include HTML, Markdown and a CSV comparison. Tolerances are configurable
software-comparison settings, not validated clinical acceptance limits. A passing
report against a supplied reference does not establish general accuracy.

**png_to_dicom.py** converts a suitable controlled PNG into DICOM. Supply the image
and output selections through **--png-path** and **--dcm-path**, and set image spacing
intentionally. Conversion does not establish a radiograph's true calibration or
remove identifying information automatically.

**Research use only.** This is a research tool, not a medical device. Independent
validation against established measurement software remains planned separately.
