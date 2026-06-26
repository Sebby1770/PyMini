"""Single source of truth for safe PyMini builtin functions."""

from __future__ import annotations

from collections.abc import Callable


def default_builtin_functions(
    stdout: Callable[[str], None] | None = None,
) -> dict[str, Callable[..., object]]:
    """Return a fresh builtin registry with an injectable output sink."""

    write = stdout or print

    def print_values(*values: object) -> None:
        write(" ".join(str(value) for value in values))

    return {
        "bool": bool,
        "dict": dict,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "print": print_values,
        "range": range,
        "str": str,
    }
