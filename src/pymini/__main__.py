"""Command-line entry point for PyMini."""

from __future__ import annotations

import argparse
from pathlib import Path

from pymini.api import ExecutionEngine, compile_source, evaluate
from pymini.parser import ParserMode
from pymini.repl.console import run_repl
from pymini.runtime.errors import PyMiniError, format_error
from pymini.vm import VirtualMachine


def positive_integer(value: str) -> int:
    """Parse a positive command-line integer."""

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pymini", description="Run PyMini programs.")
    parser.add_argument("file", nargs="?", help="A .pymi or .py source file to run.")
    parser.add_argument("-c", "--command", help="Source code to run.")
    parser.add_argument(
        "--parser",
        choices=[mode.value for mode in ParserMode],
        default=ParserMode.AST.value,
        help="Parser frontend to use.",
    )
    parser.add_argument("--no-optimize", action="store_true", help="Disable AST optimizations.")
    parser.add_argument(
        "--engine",
        choices=[engine.value for engine in ExecutionEngine],
        default=ExecutionEngine.EVALUATOR.value,
        help="Execution backend. The VM currently supports a documented subset.",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Compatibility alias for --engine vm.",
    )
    parser.add_argument("--max-steps", type=positive_integer, default=100_000)
    parser.add_argument(
        "--disassemble",
        action="store_true",
        help="Print VM bytecode before execution; requires --engine vm.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    parser_mode = ParserMode(args.parser)
    engine = ExecutionEngine.VM if args.vm else ExecutionEngine(args.engine)
    optimize = not args.no_optimize
    filename = "<string>"
    source: str | None = None

    try:
        if args.command is not None:
            source = args.command
        elif args.file:
            path = Path(args.file)
            filename = str(path)
            source = path.read_text(encoding="utf-8")
        else:
            if engine is ExecutionEngine.VM:
                print("VM mode is unavailable in the stateful REPL; using the evaluator.")
            run_repl(parser_mode=parser_mode, optimize=optimize)
            return 0

        if args.disassemble and engine is not ExecutionEngine.VM:
            raise PyMiniError("--disassemble requires --engine vm")

        if args.disassemble:
            chunk = compile_source(
                source,
                mode=parser_mode,
                optimize=optimize,
                filename=filename,
            )
            print(chunk.disassemble())
            result = VirtualMachine(
                max_steps=args.max_steps,
                filename=filename,
            ).run(chunk)
        else:
            result = evaluate(
                source,
                mode=parser_mode,
                optimize=optimize,
                engine=engine,
                filename=filename,
                max_steps=args.max_steps,
            )
        if result is not None:
            print(result)
        return 0
    except PyMiniError as exc:
        print(format_error(exc, source=source, filename=filename))
        return 1
    except OSError as exc:
        print(f"could not read {filename}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
