"""Reference counting plus cycle detection simulation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TrackedObject:
    object_id: int
    value: object
    refcount: int = 0
    references: set[int] = field(default_factory=set)


class GarbageCollector:
    """A deterministic heap simulator for educational runtime experiments."""

    def __init__(self) -> None:
        self._next_id = 1
        self.objects: dict[int, TrackedObject] = {}

    def track(self, value: object) -> int:
        object_id = self._next_id
        self._next_id += 1
        self.objects[object_id] = TrackedObject(object_id, value)
        return object_id

    def incref(self, object_id: int) -> None:
        self.objects[object_id].refcount += 1

    def decref(self, object_id: int) -> None:
        tracked = self.objects[object_id]
        tracked.refcount -= 1
        if tracked.refcount <= 0:
            self._free(object_id)

    def add_edge(self, source_id: int, target_id: int) -> None:
        self.objects[source_id].references.add(target_id)
        self.incref(target_id)

    def remove_edge(self, source_id: int, target_id: int) -> None:
        if target_id in self.objects[source_id].references:
            self.objects[source_id].references.remove(target_id)
            self.decref(target_id)

    def collect_cycles(self, roots: set[int] | None = None) -> list[int]:
        roots = roots or set()
        reachable = self._reachable_from(roots)
        freed: list[int] = []
        for object_id in list(self.objects):
            if object_id not in reachable and self._only_referenced_by_unreachable(
                object_id, reachable
            ):
                self._free(object_id)
                freed.append(object_id)
        return freed

    def _reachable_from(self, roots: set[int]) -> set[int]:
        reachable: set[int] = set()
        stack = list(roots)
        while stack:
            object_id = stack.pop()
            if object_id in reachable or object_id not in self.objects:
                continue
            reachable.add(object_id)
            stack.extend(self.objects[object_id].references)
        return reachable

    def _only_referenced_by_unreachable(self, object_id: int, reachable: set[int]) -> bool:
        if object_id in reachable:
            return False
        for candidate in self.objects.values():
            if candidate.object_id in reachable and object_id in candidate.references:
                return False
        return True

    def _free(self, object_id: int) -> None:
        tracked = self.objects.pop(object_id, None)
        if tracked is None:
            return
        for target_id in list(tracked.references):
            if target_id in self.objects:
                self.objects[target_id].refcount -= 1
