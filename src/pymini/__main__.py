"""Command-line entry point for PyMini."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymini import __version__
from pymini.api import disassemble, run_bytecode
from pymini.parser import ParserMode
from pymini.repl.console import run_repl
from pymini.runtime.errors import PyMiniError, format_exception
from pymini.runtime.evaluator import Evaluator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymini",
        description="Run, disassemble, or interactively explore PyMini programs.",
    )
    parser.add_argument("file", nargs="?", help="A .pymi or .py source file to run.")
    parser.add_argument(
        "source",
        nargs="?",
        help="Source for the 'disasm' subcommand (also accepts -c).",
    )
    parser.add_argument("-c", "--command", help="Source code to run or disassemble.")
    parser.add_argument(
        "--parser",
        choices=[mode.value for mode in ParserMode],
        default=ParserMode.AST.value,
        help="Parser frontend to use.",
    )
    parser.add_argument("--no-optimize", action="store_true", help="Disable AST optimizations.")
    parser.add_argument(
        "--disasm",
        action="store_true",
        help="Disassemble source instead of executing it.",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Execute with the bytecode VM instead of the tree-walking evaluator.",
    )
    parser.add_argument("--version", action="version", version=f"PyMini {__version__}")
    return parser


def _print_error(exc: BaseException) -> None:
    if isinstance(exc, PyMiniError):
        print(format_exception(exc), file=sys.stderr)
    else:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Support: pymini disasm "x = 1 + 2"
    if argv and argv[0] == "disasm":
        argv = ["--disasm", *argv[1:]]
        # Treat bare source as -c when not a path flag.
        if (
            len(argv) >= 2
            and not argv[1].startswith("-")
            and argv[1] not in {"--disasm"}
            and "-c" not in argv
            and "--command" not in argv
        ):
            # If it doesn't look like a file path we still accept it as source.
            maybe = argv[1]
            if not Path(maybe).is_file():
                argv = [argv[0], "-c", maybe, *argv[2:]]

    args = build_parser().parse_args(argv)
    mode = ParserMode(args.parser)
    optimize = not args.no_optimize

    source: str | None = args.command
    if source is None and args.file and args.disasm and not Path(args.file).is_file():
        # `pymini --disasm "x = 1"` style
        source = args.file
        args.file = None
    if source is None and args.source is not None:
        source = args.source

    try:
        if args.disasm:
            if source is not None:
                print(disassemble(source, optimize=optimize))
                return 0
            if args.file:
                text = Path(args.file).read_text(encoding="utf-8")
                print(disassemble(text, optimize=optimize))
                return 0
            print("error: --disasm requires -c SOURCE or a file", file=sys.stderr)
            return 2

        if source is not None:
            if args.vm:
                result = run_bytecode(source, mode=mode, optimize=optimize)
            else:
                result = Evaluator(filename="<string>").run(
                    source, parser_mode=mode, optimize=optimize
                )
            if result is not None:
                print(result)
            return 0

        if args.file:
            path = Path(args.file)
            text = path.read_text(encoding="utf-8")
            if args.vm:
                result = run_bytecode(text, mode=mode, optimize=optimize)
            else:
                result = Evaluator(filename=str(path)).run(
                    text, parser_mode=mode, optimize=optimize
                )
            if result is not None:
                print(result)
            return 0

        run_repl(parser_mode=mode, optimize=optimize)
        return 0
    except PyMiniError as exc:
        _print_error(exc)
        return 1
    except Exception as exc:
        _print_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
