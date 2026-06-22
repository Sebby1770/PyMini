"""Deterministic reference-counting and reachability simulation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TrackedObject:
    object_id: int
    value: object
    refcount: int = 0
    references: set[int] = field(default_factory=set)


class GarbageCollector:
    """A small heap model with reference counts and explicit root tracing."""

    def __init__(self) -> None:
        self._next_id = 1
        self.objects: dict[int, TrackedObject] = {}

    def track(self, value: object) -> int:
        object_id = self._next_id
        self._next_id += 1
        self.objects[object_id] = TrackedObject(object_id, value)
        return object_id

    def incref(self, object_id: int) -> None:
        self._get(object_id).refcount += 1

    def decref(self, object_id: int) -> None:
        tracked = self._get(object_id)
        if tracked.refcount == 0:
            raise ValueError(f"cannot decrement zero refcount for object {object_id}")
        tracked.refcount -= 1
        if tracked.refcount == 0:
            self._release_zero_refcounts([object_id])

    def add_edge(self, source_id: int, target_id: int) -> None:
        source = self._get(source_id)
        self._get(target_id)
        if target_id in source.references:
            return
        source.references.add(target_id)
        self.incref(target_id)

    def remove_edge(self, source_id: int, target_id: int) -> None:
        source = self._get(source_id)
        if target_id not in source.references:
            return
        source.references.remove(target_id)
        self.decref(target_id)

    def collect_cycles(self, roots: set[int] | None = None) -> list[int]:
        """Collect every object unreachable from the supplied root IDs."""

        root_ids = roots or set()
        unknown_roots = sorted(root_ids - self.objects.keys())
        if unknown_roots:
            raise KeyError(f"unknown root object id(s): {unknown_roots}")

        reachable = self._reachable_from(root_ids)
        unreachable = set(self.objects) - reachable
        if not unreachable:
            return []

        removed = {object_id: self.objects.pop(object_id) for object_id in unreachable}
        for tracked in removed.values():
            for target_id in tracked.references:
                target = self.objects.get(target_id)
                if target is not None:
                    target.refcount = max(0, target.refcount - 1)
        return sorted(unreachable)

    def _reachable_from(self, roots: set[int]) -> set[int]:
        reachable: set[int] = set()
        stack = list(roots)
        while stack:
            object_id = stack.pop()
            if object_id in reachable:
                continue
            tracked = self._get(object_id)
            reachable.add(object_id)
            stack.extend(tracked.references)
        return reachable

    def _release_zero_refcounts(self, candidates: list[int]) -> None:
        pending = candidates
        while pending:
            object_id = pending.pop()
            tracked = self.objects.get(object_id)
            if tracked is None or tracked.refcount != 0:
                continue
            self.objects.pop(object_id)
            for target_id in tracked.references:
                target = self.objects.get(target_id)
                if target is None:
                    continue
                target.refcount -= 1
                if target.refcount == 0:
                    pending.append(target_id)

    def _get(self, object_id: int) -> TrackedObject:
        try:
            return self.objects[object_id]
        except KeyError as exc:
            raise KeyError(f"unknown object id: {object_id}") from exc
