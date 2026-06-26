"""Shared source-to-AST pipeline used by every execution engine."""

from __future__ import annotations

import ast
from typing import Literal

from pymini.optimizer.ast_optimizer import optimize_module
from pymini.parser import ParserMode, parse_source


def prepare_module(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
) -> ast.Module:
    """Parse source once and optionally apply the canonical optimizer."""

    module = parse_source(source, mode=mode)
    return optimize_module(module) if optimize else module
