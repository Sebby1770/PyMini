"""Command-line entry point for PyMini."""

from __future__ import annotations

import argparse
from pathlib import Path

from pymini.parser import ParserMode
from pymini.repl.console import run_repl
from pymini.runtime.evaluator import Evaluator


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    evaluator = Evaluator()
    mode = ParserMode(args.parser)
    optimize = not args.no_optimize

    if args.command is not None:
        result = evaluator.run(args.command, parser_mode=mode, optimize=optimize)
        if result is not None:
            print(result)
        return 0

    if args.file:
        source = Path(args.file).read_text(encoding="utf-8")
        result = evaluator.run(source, parser_mode=mode, optimize=optimize)
        if result is not None:
            print(result)
        return 0

    run_repl(parser_mode=mode, optimize=optimize)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

