"""Public API for parsing and evaluating PyMini programs."""

from __future__ import annotations

import ast
from typing import Literal

from pymini.optimizer.ast_optimizer import optimize_module
from pymini.parser import ParserMode, parse_source
from pymini.runtime.evaluator import Evaluator


def parse(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = False,
) -> ast.Module:
    """Parse source text into an ``ast.Module``.

    The returned tree is compatible with the evaluator and the future compiler.
    """

    module = parse_source(source, mode=mode)
    return optimize_module(module) if optimize else module


def evaluate(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
) -> object:
    """Evaluate source text with the milestone tree-walking evaluator."""

    evaluator = Evaluator()
    return evaluator.run(source, parser_mode=mode, optimize=optimize)

