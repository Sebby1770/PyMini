"""Parser frontend backed by Python's ``ast`` module."""

from __future__ import annotations

import ast

from pymini.runtime.errors import Location, PyMiniSyntaxError


class AstParser:
    """Parse source using CPython's parser and expose an AST-only contract."""

    def parse(self, source: str) -> ast.Module:
        try:
            return ast.parse(source)
        except SyntaxError as exc:
            location = None
            if exc.lineno is not None:
                location = Location(
                    lineno=exc.lineno,
                    col_offset=max(0, (exc.offset or 1) - 1),
                    end_lineno=exc.end_lineno,
                    end_col_offset=exc.end_offset,
                )
            raise PyMiniSyntaxError(exc.msg, location=location, source=source) from exc
