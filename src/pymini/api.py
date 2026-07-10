"""Public API for parsing, evaluating, compiling, and disassembling PyMini programs."""

from __future__ import annotations

import ast
from typing import Literal

from pymini.compiler.bytecode import (
    Chunk,
    compile_source as _compile_source,
    disassemble as _disassemble,
    disassemble_source as _disassemble_source,
)
from pymini.optimizer.ast_optimizer import optimize_module
from pymini.parser import ParserMode, parse_source
from pymini.runtime.evaluator import Evaluator
from pymini.vm.machine import VirtualMachine


def parse(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = False,
) -> ast.Module:
    """Parse source text into an ``ast.Module``.

    The returned tree is compatible with the evaluator and the compiler.
    """

    module = parse_source(source, mode=mode)
    return optimize_module(module) if optimize else module


def evaluate(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
) -> object:
    """Evaluate source text with the tree-walking evaluator."""

    evaluator = Evaluator()
    return evaluator.run(source, parser_mode=mode, optimize=optimize)


def compile_source(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
    name: str = "<module>",
) -> Chunk:
    """Compile source text into a PyMini bytecode :class:`Chunk`."""

    return _compile_source(source, mode=mode, optimize=optimize, name=name)


def disassemble(source_or_chunk: str | Chunk, *, optimize: bool = True) -> str:
    """Disassemble a source string or an already-compiled :class:`Chunk`."""

    if isinstance(source_or_chunk, Chunk):
        return _disassemble(source_or_chunk)
    return _disassemble_source(source_or_chunk, optimize=optimize)


def run_bytecode(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
) -> object:
    """Compile *source* and execute it on the bytecode VM."""

    chunk = compile_source(source, mode=mode, optimize=optimize)
    return VirtualMachine().run(chunk)
