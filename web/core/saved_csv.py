"""Named CSV coordinates used by both PXM editions, independent of table order."""

import math


def indexed_coordinates(rows, specs, dynamic_spec):
    """Resolve editable roles by stable ID, then assemble their explicit point indices."""
    by_name = {spec["name"]: role for role, spec in specs.items()}
    records = {}
    for row in rows:
        if row.get("section") not in ("point", "derived_point"):
            continue
        role = (row.get("role") or (row.get("details") or "").split(";", 1)[0]).strip()
        if not role:
            role = by_name.get(row.get("name"), "")
        spec = specs.get(role) or dynamic_spec(role)
        if not spec or spec.get("locked") or "Markups" not in spec["className"]:
            continue
        if row.get("point_index") and all(row.get(key) for key in ("r", "a", "s")):
            index = int(row["point_index"]) - 1
            columns = ("r", "a", "s")
        else:
            index = int(row["index"])
            columns = ("x_ras", "y_ras", "z_ras")
        xyz = tuple(float(row[key]) for key in columns)
        limit = spec.get("completionCount") or (2 if spec["className"].endswith("LineNode") else 5000)
        if not 0 <= index < limit or not all(map(math.isfinite, xyz)):
            raise ValueError(f"Invalid saved coordinate for {role}.")
        track = records.setdefault(role, {})
        if index in track:
            raise ValueError(f"Duplicate point index for {role}.")
        track[index] = (xyz, row)
    ordered = {}
    for role in sorted(records):
        track = records[role]
        if len(track) != max(track) + 1:
            raise ValueError(f"Saved point indices are incomplete for {role}.")
        ordered[role] = [track[index] for index in range(len(track))]
    return ordered
