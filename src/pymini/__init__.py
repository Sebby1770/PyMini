"""PyMini: a staged mini-Python interpreter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.2.0"

if TYPE_CHECKING:
    from pymini.api import compile_source, disassemble, evaluate, parse, run_bytecode


def parse(*args: Any, **kwargs: Any) -> object:
    from pymini.api import parse as _parse

    return _parse(*args, **kwargs)


def evaluate(*args: Any, **kwargs: Any) -> object:
    from pymini.api import evaluate as _evaluate

    return _evaluate(*args, **kwargs)


def compile_source(*args: Any, **kwargs: Any) -> object:
    from pymini.api import compile_source as _compile_source

    return _compile_source(*args, **kwargs)


def disassemble(*args: Any, **kwargs: Any) -> str:
    from pymini.api import disassemble as _disassemble

    return _disassemble(*args, **kwargs)


def run_bytecode(*args: Any, **kwargs: Any) -> object:
    from pymini.api import run_bytecode as _run_bytecode

    return _run_bytecode(*args, **kwargs)


__all__ = [
    "__version__",
    "compile_source",
    "disassemble",
    "evaluate",
    "parse",
    "run_bytecode",
]
