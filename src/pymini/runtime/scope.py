"""Lexical environments for PyMini."""

from __future__ import annotations

from dataclasses import dataclass, field

from pymini.runtime.errors import PyMiniNameError


@dataclass(slots=True)
class Environment:
    """A lexical scope with an optional parent."""

    name: str = "<scope>"
    parent: Environment | None = None
    values: dict[str, object] = field(default_factory=dict)

    def define(self, name: str, value: object) -> object:
        self.values[name] = value
        return value

    def get(self, name: str) -> object:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise PyMiniNameError(f"name {name!r} is not defined")

    def set_local(self, name: str, value: object) -> object:
        self.values[name] = value
        return value

    def contains_local(self, name: str) -> bool:
        return name in self.values

    def snapshot(self) -> dict[str, object]:
        return dict(self.values)
