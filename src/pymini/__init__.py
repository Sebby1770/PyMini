"""PyMini: a staged mini-Python interpreter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pymini.api import evaluate, parse


def parse(*args: Any, **kwargs: Any) -> object:
    from pymini.api import parse as _parse

    return _parse(*args, **kwargs)


def evaluate(*args: Any, **kwargs: Any) -> object:
    from pymini.api import evaluate as _evaluate

    return _evaluate(*args, **kwargs)


__all__ = ["evaluate", "parse"]
