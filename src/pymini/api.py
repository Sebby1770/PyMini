"""Public API for parsing and evaluating PyMini programs."""

from __future__ import annotations

import ast
from collections.abc import Callable
from enum import StrEnum
from typing import Literal

from pymini.compiler.bytecode import Chunk
from pymini.compiler.compiler import Compiler
from pymini.parser import ParserMode
from pymini.pipeline import prepare_module
from pymini.runtime.evaluator import Evaluator
from pymini.vm.machine import VirtualMachine


class ExecutionEngine(StrEnum):
    """Supported execution backends."""

    EVALUATOR = "evaluator"
    VM = "vm"


def compile_source(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
    filename: str = "<string>",
) -> Chunk:
    """Compile source into a VM bytecode chunk without executing it."""

    module = prepare_module(source, mode=mode, optimize=optimize)
    return Compiler(filename=filename).compile(module)


def parse(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = False,
) -> ast.Module:
    """Parse source text into an ``ast.Module``.

    The returned tree is compatible with the evaluator and the future compiler.
    """

    return prepare_module(source, mode=mode, optimize=optimize)


def evaluate(
    source: str,
    *,
    mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
    optimize: bool = True,
    engine: ExecutionEngine | Literal["evaluator", "vm"] = ExecutionEngine.EVALUATOR,
    filename: str = "<string>",
    max_steps: int = 100_000,
    stdout: Callable[[str], None] | None = None,
) -> object:
    """Evaluate source text with the selected execution engine."""

    selected_engine = ExecutionEngine(engine)
    if selected_engine is ExecutionEngine.EVALUATOR:
        module = prepare_module(source, mode=mode, optimize=optimize)
        evaluator = Evaluator(max_steps=max_steps, filename=filename, stdout=stdout)
        return evaluator.execute(module, source=source, filename=filename)

    chunk = compile_source(
        source,
        mode=mode,
        optimize=optimize,
        filename=filename,
    )
    return VirtualMachine(max_steps=max_steps, filename=filename, stdout=stdout).run(chunk)
