"""A deliberately small, safe standard library registry."""

from __future__ import annotations

import json
import math
import random as py_random
from collections.abc import Callable
from dataclasses import dataclass, field

from pymini import __version__
from pymini.runtime.errors import PyMiniNameError
from pymini.runtime.objects import ModuleNamespace, NativeFunction


def _wrap_function(name: str, func: Callable[..., object]) -> NativeFunction:
    return NativeFunction(name=name, func=func)


def _build_math_module() -> ModuleNamespace:
    members: dict[str, object] = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "inf": math.inf,
        "nan": math.nan,
        "sqrt": _wrap_function("math.sqrt", math.sqrt),
        "sin": _wrap_function("math.sin", math.sin),
        "cos": _wrap_function("math.cos", math.cos),
        "tan": _wrap_function("math.tan", math.tan),
        "asin": _wrap_function("math.asin", math.asin),
        "acos": _wrap_function("math.acos", math.acos),
        "atan": _wrap_function("math.atan", math.atan),
        "atan2": _wrap_function("math.atan2", math.atan2),
        "floor": _wrap_function("math.floor", math.floor),
        "ceil": _wrap_function("math.ceil", math.ceil),
        "fabs": _wrap_function("math.fabs", math.fabs),
        "log": _wrap_function("math.log", math.log),
        "log10": _wrap_function("math.log10", math.log10),
        "log2": _wrap_function("math.log2", math.log2),
        "exp": _wrap_function("math.exp", math.exp),
        "pow": _wrap_function("math.pow", math.pow),
        "degrees": _wrap_function("math.degrees", math.degrees),
        "radians": _wrap_function("math.radians", math.radians),
        "factorial": _wrap_function("math.factorial", math.factorial),
        "gcd": _wrap_function("math.gcd", math.gcd),
        "isfinite": _wrap_function("math.isfinite", math.isfinite),
        "isinf": _wrap_function("math.isinf", math.isinf),
        "isnan": _wrap_function("math.isnan", math.isnan),
    }
    return ModuleNamespace("math", members)


def _build_random_module() -> ModuleNamespace:
    rng = py_random.Random()

    def seed(a: object | None = None) -> None:
        rng.seed(a)
        return None

    def random() -> float:
        return rng.random()

    def randint(a: object, b: object) -> int:
        return rng.randint(int(a), int(b))  # type: ignore[arg-type]

    def choice(seq: object) -> object:
        return rng.choice(list(seq))  # type: ignore[arg-type]

    def random_range(start: object, stop: object | None = None, step: object = 1) -> int:
        if stop is None:
            return rng.randrange(int(start))  # type: ignore[arg-type]
        return rng.randrange(int(start), int(stop), int(step))  # type: ignore[arg-type]

    def uniform(a: object, b: object) -> float:
        return rng.uniform(float(a), float(b))  # type: ignore[arg-type]

    return ModuleNamespace(
        "random",
        {
            "seed": _wrap_function("random.seed", seed),
            "random": _wrap_function("random.random", random),
            "randint": _wrap_function("random.randint", randint),
            "choice": _wrap_function("random.choice", choice),
            "randrange": _wrap_function("random.randrange", random_range),
            "uniform": _wrap_function("random.uniform", uniform),
        },
    )


def _build_json_module() -> ModuleNamespace:
    def loads(s: object) -> object:
        if not isinstance(s, (str, bytes, bytearray)):
            raise TypeError("json.loads() argument must be str, bytes or bytearray")
        return json.loads(s)

    def dumps(obj: object, *, indent: object | None = None) -> str:
        return json.dumps(obj, indent=indent)  # type: ignore[arg-type]

    return ModuleNamespace(
        "json",
        {
            "loads": _wrap_function("json.loads", loads),
            "dumps": _wrap_function("json.dumps", dumps),
        },
    )


@dataclass(slots=True)
class StandardLibrary:
    """Loads safe modules by explicit allow-list."""

    modules: dict[str, ModuleNamespace] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.modules:
            return
        self.modules.update(
            {
                "math": _build_math_module(),
                "random": _build_random_module(),
                "json": _build_json_module(),
                "pymini": ModuleNamespace(
                    "pymini",
                    {
                        "version": __version__,
                    },
                ),
            }
        )

    def load(self, name: str) -> ModuleNamespace:
        root = name.split(".", maxsplit=1)[0]
        if root not in self.modules:
            raise PyMiniNameError(f"module {name!r} is not available in PyMini stdlib")
        return self.modules[root]
