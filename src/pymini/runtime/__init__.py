"""Runtime support for PyMini."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pymini.runtime.evaluator import Evaluator


def __getattr__(name: str) -> Any:
    if name == "Evaluator":
        from pymini.runtime.evaluator import Evaluator

        return Evaluator
    raise AttributeError(name)


__all__ = ["Evaluator"]
