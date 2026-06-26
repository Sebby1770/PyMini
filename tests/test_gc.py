from __future__ import annotations

import pytest

from pymini.gc import GarbageCollector


def test_duplicate_edges_do_not_double_count_references() -> None:
    gc = GarbageCollector()
    source = gc.track("source")
    target = gc.track("target")

    gc.add_edge(source, target)
    gc.add_edge(source, target)

    assert gc.objects[target].refcount == 1


def test_zero_refcount_release_cascades_through_owned_objects() -> None:
    gc = GarbageCollector()
    parent = gc.track("parent")
    child = gc.track("child")
    gc.incref(parent)
    gc.add_edge(parent, child)

    gc.decref(parent)

    assert gc.objects == {}


def test_cycle_collection_preserves_rooted_graphs() -> None:
    gc = GarbageCollector()
    rooted = gc.track("rooted")
    reachable = gc.track("reachable")
    cycle_a = gc.track("cycle-a")
    cycle_b = gc.track("cycle-b")
    gc.add_edge(rooted, reachable)
    gc.add_edge(cycle_a, cycle_b)
    gc.add_edge(cycle_b, cycle_a)

    assert gc.collect_cycles({rooted}) == [cycle_a, cycle_b]
    assert set(gc.objects) == {rooted, reachable}


def test_invalid_refcount_and_root_operations_fail_loudly() -> None:
    gc = GarbageCollector()
    object_id = gc.track("value")

    with pytest.raises(ValueError, match="zero refcount"):
        gc.decref(object_id)
    with pytest.raises(KeyError, match="unknown root"):
        gc.collect_cycles({999})
