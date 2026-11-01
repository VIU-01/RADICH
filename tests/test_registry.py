"""M06 tests: node registration and identity, without graph semantics."""

import pytest

from radich import DuplicateNodeError, NodeRegistry, NodeSpec, UnknownNodeError


def spec(node_id="a", config=None):
    return NodeSpec(node_id, "transform", "0.1", config or {})


def test_register_lookup_contains_and_length():
    registry = NodeRegistry()
    registry.register(spec())
    assert len(registry) == 1
    assert registry.contains("a")
    assert not registry.contains("missing")
    assert registry.get("a").capability == "transform"


def test_duplicate_rejected_without_overwrite():
    registry = NodeRegistry()
    registry.register(spec())
    with pytest.raises(DuplicateNodeError):
        registry.register(NodeSpec("a", "different", "0.2"))
    assert registry.get("a").version == "0.1"
    assert len(registry) == 1


def test_unknown_and_invalid_ids():
    registry = NodeRegistry()
    with pytest.raises(UnknownNodeError):
        registry.get("missing")
    with pytest.raises(ValueError):
        registry.get("  ")
    assert not registry.contains("  ")


def test_invalid_spec_rejected():
    registry = NodeRegistry()
    with pytest.raises(TypeError):
        registry.register("a")
    assert len(registry) == 0


def test_listing_is_sorted_and_immutable_snapshot():
    registry = NodeRegistry()
    registry.register(spec("z"))
    registry.register(spec("a"))
    assert [item.node_id for item in registry.list_nodes()] == ["a", "z"]
    assert isinstance(registry.list_nodes(), tuple)


def test_registry_defensively_copies_mutable_config():
    registry = NodeRegistry()
    original = spec(config={"nested": {"x": 1}})
    registry.register(original)
    original.config["nested"]["x"] = 2
    assert registry.get("a").config["nested"]["x"] == 1
    returned = registry.get("a")
    returned.config["nested"]["x"] = 3
    assert registry.get("a").config["nested"]["x"] == 1
    listed = registry.list_nodes()[0]
    listed.config["nested"]["x"] = 4
    assert registry.get("a").config["nested"]["x"] == 1


def test_independent_registries():
    first, second = NodeRegistry(), NodeRegistry()
    first.register(spec())
    assert len(first) == 1
    assert len(second) == 0
