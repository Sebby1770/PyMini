"""Parser frontends for PyMini."""

from __future__ import annotations

import ast
from enum import StrEnum

from pymini.parser.ast_parser import AstParser
from pymini.parser.handwritten import HandwrittenParser


class ParserMode(StrEnum):
    AST = "ast"
    HANDWRITTEN = "handwritten"


def parse_source(source: str, *, mode: ParserMode | str = ParserMode.AST) -> ast.Module:
    parser_mode = ParserMode(mode)
    if parser_mode is ParserMode.AST:
        return AstParser().parse(source)
    return HandwrittenParser().parse(source)


__all__ = ["AstParser", "HandwrittenParser", "ParserMode", "parse_source"]
