"""Unit tests for MRML scene-node adoption safeguards."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any


sys.modules.setdefault("slicer", SimpleNamespace())
sys.modules.setdefault("vtk", SimpleNamespace())

import PelvicXrayMeasurementsScene as scene_module
from PelvicXrayMeasurementsConstants import (
    CASE_COMMENTS_ATTRIBUTE,
    LEGACY_CASE_COMMENTS_ATTRIBUTES,
    LEGACY_ROLE_ATTRIBUTES,
    ROLE_ATTRIBUTE,
)
from PelvicXrayMeasurementsScene import SceneNodeMixin


class FakeMarkupNode:
    """Small MRML-node stand-in with only the APIs needed by SceneNodeMixin."""

    def __init__(self, node_id: str, role: str, point_count: int) -> None:
        self.node_id = node_id
        self.role = role
        self.point_count = point_count
        self.configured = False

    def GetAttribute(self, name: str) -> str:
        return self.role if name == ROLE_ATTRIBUTE else ""

    def GetClassName(self) -> str:
        return "vtkMRMLMarkupsLineNode"

    def GetID(self) -> str:
        return self.node_id

    def IsA(self, class_name: str) -> bool:
        return class_name in {"vtkMRMLMarkupsNode", "vtkMRMLMarkupsLineNode"}

    def GetNumberOfDefinedControlPoints(self) -> int:
        return self.point_count


class FakeMetadataNode:
    """Small scripted-module-node stand-in for case metadata adoption tests."""

    def __init__(self, node_id: str, attributes: dict[str, str]) -> None:
        self.node_id = node_id
        self.attributes = dict(attributes)
        self.configured = False

    def GetAttribute(self, name: str) -> str:
        return self.attributes.get(name, "")

    def SetAttribute(self, name: str, value: str) -> None:
        self.attributes[name] = value

    def GetClassName(self) -> str:
        return "vtkMRMLScriptedModuleNode"

    def GetID(self) -> str:
        return self.node_id

    def IsA(self, class_name: str) -> bool:
        return class_name == "vtkMRMLScriptedModuleNode"


class FakeScene:
    """Scene stand-in that preserves node order for duplicate-role adoption tests."""

    def __init__(self, nodes: list[Any]) -> None:
        self.nodes = nodes

    def GetNodeByID(self, node_id: str) -> Any | None:
        for node in self.nodes:
            if node.GetID() == node_id:
                return node
        return None

    def GetNumberOfNodes(self) -> int:
        return len(self.nodes)

    def GetNthNode(self, index: int) -> Any:
        return self.nodes[index]

    def RemoveNode(self, node: Any) -> None:
        self.nodes.remove(node)


class SceneNodeHarness(SceneNodeMixin):
    """Harness exposing SceneNodeMixin lookup behavior without live Slicer."""

    def __init__(self) -> None:
        self._node_cache: dict[str, str] = {}
        self._dynamic_other_roles_scene_synced = True

    def _node_spec_for_role(self, _role: str) -> dict[str, Any]:
        if _role == "moduleMetadata":
            return {
                "className": "vtkMRMLScriptedModuleNode",
                "name": "Case Metadata",
                "color": (0.0, 0.0, 0.0),
            }
        return {
            "className": "vtkMRMLMarkupsLineNode",
            "name": "Reference",
            "color": (1.0, 1.0, 1.0),
        }

    def _configure_node(self, node: Any, role: str) -> None:
        node.configured = True
        if hasattr(node, "SetAttribute"):
            node.SetAttribute(ROLE_ATTRIBUTE, role)


def test_get_node_prefers_populated_duplicate_after_cache_clear() -> None:
    """A saved annotation node should beat an empty placeholder when both use the same role."""

    empty_placeholder = FakeMarkupNode("empty", "referenceLine", 0)
    saved_annotation = FakeMarkupNode("saved", "referenceLine", 2)
    scene_module.slicer.mrmlScene = FakeScene([empty_placeholder, saved_annotation])

    harness = SceneNodeHarness()
    harness._node_cache["referenceLine"] = "empty"
    assert harness.get_node("referenceLine") is empty_placeholder

    harness.clear_node_cache()

    assert harness.get_node("referenceLine") is saved_annotation
    assert harness._node_cache["referenceLine"] == "saved"
    assert saved_annotation.configured
    assert harness._dynamic_other_roles_scene_synced is False


def test_get_node_prefers_metadata_node_with_saved_comments() -> None:
    """A saved metadata node should beat an empty placeholder when both use the same role."""

    empty_placeholder = FakeMetadataNode("empty", {ROLE_ATTRIBUTE: "moduleMetadata"})
    saved_metadata = FakeMetadataNode(
        "saved",
        {
            ROLE_ATTRIBUTE: "moduleMetadata",
            CASE_COMMENTS_ATTRIBUTE: "MRB note",
        },
    )
    scene_module.slicer.mrmlScene = FakeScene([empty_placeholder, saved_metadata])

    harness = SceneNodeHarness()

    assert harness.get_node("moduleMetadata") is saved_metadata
    assert harness.case_comments() == "MRB note"
    assert harness._node_cache["moduleMetadata"] == "saved"


def test_case_comments_recovers_legacy_metadata_attribute() -> None:
    """Comments saved before the module rename should still load from a single MRB scene."""

    legacy_metadata = FakeMetadataNode(
        "legacy",
        {
            LEGACY_ROLE_ATTRIBUTES[0]: "moduleMetadata",
            LEGACY_CASE_COMMENTS_ATTRIBUTES[0]: "Legacy MRB note",
        },
    )
    scene_module.slicer.mrmlScene = FakeScene([legacy_metadata])

    harness = SceneNodeHarness()

    assert harness.case_comments() == "Legacy MRB note"
    assert legacy_metadata.GetAttribute(CASE_COMMENTS_ATTRIBUTE) == "Legacy MRB note"
    assert legacy_metadata.GetAttribute(ROLE_ATTRIBUTE) == "moduleMetadata"
