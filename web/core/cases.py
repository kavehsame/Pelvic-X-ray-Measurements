"""Enumerate in-memory roles using the shared measurement CSV contract."""

from .schema import ROLE_ATTRIBUTE


def coordinate_rows(scene):
    rows = []
    for node in scene.GetNodesByClass("vtkMRMLMarkupsNode"):
        role = node.GetAttribute(ROLE_ATTRIBUTE)
        if not role:
            continue
        for index, point in enumerate(node.points):
            rows.append(
                dict(
                    role=role,
                    point_index=str(index + 1),
                    label=node.labels[index],
                    **{key: format(value, ".17g") for key, value in zip(("r", "a", "s"), point, strict=True)},
                )
            )
    return sorted(rows, key=lambda row: (row["role"], int(row["point_index"])))
