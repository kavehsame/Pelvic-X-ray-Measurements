# PXM AP implant overlay format

The [illustrated guide to implant overlays](implant-overlays.html) explains how to prepare a pack, check scale and review a placed template. The original collections are Medacta International’s *MEDACTA Templates* and Mathys Ltd. Bettlach’s *Mathys Templates*, distributed with the OsiriX plugin (version 3.6.5). The guide includes references for both collections, the plugin’s terms and a working example.

An overlay pack is a local UTF-8 JSON file. In **3: Planning**, choose **Import overlay pack…** in the web app or Slicer. Imported entries are available for all cases during that session. Reopen the same pack in a new session to display its drawings. The PNG prints the component, family and size for each side where a template was placed. The CSV also saves its ID. Both the CSV and scene retain the family and size labels, pivot and rotation. The drawings stay on the device.

## File and coordinates

At the top level, set `format` to `pxm-overlay-pack-1`, `view` to `AP`, `units` to `mm` and `axes` to `x-lateral-y-superior`. Supply an array named `items` with one entry per size and outline. Each entry has the following fields.

| Field | Meaning |
| --- | --- |
| `id` | Stable identifier for this exact geometry. Give a revised geometry a new identifier. |
| `manufacturer`, `family`, `size`, `reference` | Display strings and source reference for this component. Include the size and any clinically distinct variant. |
| `component` | Either `cup` or `stem`. |
| `side` | `left`, `right` or `both`. Use `both` only for a design authorised for either side. |
| `source`, `scale_method` | Identify the drawing and how its physical scale was established. Keep the original drawing and its revision with your review. |
| `pivot` | Two coordinates in the same millimetre frame as the outline. This point moves to the user's placement and serves as the rotation centre. |
| `outline` | Ordered exterior vertices `[x, y]` with the first vertex repeated at the end. Each segment joins consecutive points. Use one simple exterior loop. |

Positive x points towards the patient's lateral side and positive y towards superior. Supply coordinates in this anatomical frame for all designs, including a side-specific stem. PXM applies the appropriate display direction for the active side. The source origin can be anywhere. PXM subtracts the declared pivot before rendering. Use the product's physical dimensions at 1:1. A scanned print magnification or a pixel count alone cannot establish physical scale.

Each pack can contain 1–1,500 entries and occupy up to 12 MiB. Each outline accepts 4–4,096 coordinate pairs including closure, requires finite coordinates within ±2,000 mm and encloses an area of at least 1 mm². Identifying strings are limited to 512 characters. Pack import is atomic. An identical existing reference can be reused. A conflict in the outline, family, size, component or side rejects the whole import. Self-crossings and repeated intermediate vertices also cause a visible import error.

## Reviewing a drawing

Compare the exterior outline to the original source drawing. Check the AP view, patient side, independent physical scale, pivot and product reference. Symbols and guides can extend beyond the implant. Record the two endpoints used for a size check and keep the source revision with your pack.

[Example pack](overlay-example.json) · [JSON Schema](overlay.schema.json)
