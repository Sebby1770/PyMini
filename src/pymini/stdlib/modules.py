"""A deliberately small, safe standard library registry."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from pymini.runtime.errors import PyMiniNameError
from pymini.runtime.objects import ModuleNamespace, NativeFunction
from pymini.version import VERSION


def _wrap_function(name: str, func: Callable[..., object]) -> NativeFunction:
    return NativeFunction(name=name, func=func)


@dataclass(slots=True)
class StandardLibrary:
    """Loads safe modules by explicit allow-list."""

    modules: dict[str, ModuleNamespace] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.modules:
            return
        self.modules.update(
            {
                "math": ModuleNamespace(
                    "math",
                    {
                        "pi": math.pi,
                        "e": math.e,
                        "sqrt": _wrap_function("math.sqrt", math.sqrt),
                        "sin": _wrap_function("math.sin", math.sin),
                        "cos": _wrap_function("math.cos", math.cos),
                        "floor": _wrap_function("math.floor", math.floor),
                        "ceil": _wrap_function("math.ceil", math.ceil),
                    },
                ),
                "pymini": ModuleNamespace(
                    "pymini",
                    {
                        "version": VERSION,
                    },
                ),
            }
        )

    def load(self, name: str) -> ModuleNamespace:
        root = name.split(".", maxsplit=1)[0]
        if root not in self.modules:
            raise PyMiniNameError(f"module {name!r} is not available in PyMini stdlib")
        return self.modules[root]
