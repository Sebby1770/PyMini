"""Parser frontend backed by Python's ``ast`` module."""

from __future__ import annotations

import ast

from pymini.runtime.errors import PyMiniSyntaxError


class AstParser:
    """Parse source using CPython's parser and expose an AST-only contract."""

    def parse(self, source: str) -> ast.Module:
        try:
            return ast.parse(source)
        except SyntaxError as exc:
            location = f" at line {exc.lineno}, column {exc.offset}" if exc.lineno else ""
            raise PyMiniSyntaxError(f"{exc.msg}{location}") from exc

