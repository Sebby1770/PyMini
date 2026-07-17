"""Command-line entry point for PyMini."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymini import __version__
from pymini.api import disassemble, run_bytecode
from pymini.debug.debugger import Debugger, run_with_trace
from pymini.parser import ParserMode
from pymini.repl.console import run_repl
from pymini.runtime.errors import PyMiniError, format_exception
from pymini.runtime.evaluator import Evaluator

SUBCOMMANDS = {"run", "eval", "disasm", "repl", "version", "debug"}


def build_parser(*, with_subcommand: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymini",
        description="Run, disassemble, debug, or interactively explore PyMini programs.",
    )
    if with_subcommand:
        parser.add_argument(
            "subcommand",
            choices=sorted(SUBCOMMANDS),
            help="Action to perform.",
        )
        parser.add_argument(
            "target",
            nargs="?",
            help="File path, or inline source for eval/disasm.",
        )
    else:
        parser.add_argument("file", nargs="?", help="A .pymi or .py source file to run.")
        parser.add_argument(
            "source",
            nargs="?",
            help="Legacy second positional (rarely used).",
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
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print each source line before executing it.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run with the interactive line debugger.",
    )
    parser.add_argument(
        "--break",
        dest="breakpoints",
        action="append",
        type=int,
        default=[],
        help="Breakpoint line number (repeatable). Used with --debug.",
    )
    parser.add_argument("--version", action="version", version=f"PyMini {__version__}")
    return parser


def _print_error(exc: BaseException) -> None:
    if isinstance(exc, PyMiniError):
        print(format_exception(exc), file=sys.stderr)
    else:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)


def _execute(
    source: str,
    *,
    filename: str,
    mode: ParserMode,
    optimize: bool,
    use_vm: bool,
    trace: bool,
    debug: bool,
    breakpoints: list[int],
) -> object:
    if debug:
        dbg = Debugger()
        for line in breakpoints:
            dbg.set_breakpoint(line)
        return dbg.run_source(
            source,
            filename=filename,
            parser_mode=mode,
            optimize=optimize,
            step_first=not breakpoints,
        )
    if trace:
        return run_with_trace(
            source, filename=filename, parser_mode=mode, optimize=optimize
        )
    if use_vm:
        return run_bytecode(source, mode=mode, optimize=optimize)
    return Evaluator(filename=filename).run(
        source, parser_mode=mode, optimize=optimize
    )


def _run_disasm(source: str, *, optimize: bool) -> int:
    print(disassemble(source, optimize=optimize))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Fast path: pymini version
    if argv == ["version"] or (len(argv) == 1 and argv[0] in {"-V"}):
        print(f"PyMini {__version__}")
        return 0

    # Detect explicit subcommand vs legacy bare invocation.
    has_sub = bool(argv) and not argv[0].startswith("-") and argv[0] in SUBCOMMANDS
    # Also treat legacy `pymini disasm ...` which is a subcommand.
    if has_sub:
        args = build_parser(with_subcommand=True).parse_args(argv)
        sub = args.subcommand
        mode = ParserMode(args.parser)
        optimize = not args.no_optimize
        return _dispatch_sub(sub, args, mode=mode, optimize=optimize)

    # Legacy: rewrite `disasm` already handled; support bare flags/files.
    # Support: pymini disasm "x = 1 + 2" was historically rewritten — covered by sub.
    args = build_parser(with_subcommand=False).parse_args(argv)
    mode = ParserMode(args.parser)
    optimize = not args.no_optimize

    source: str | None = args.command
    if source is None and args.file and args.disasm and not Path(args.file).is_file():
        source = args.file
        args.file = None
    if source is None and args.source is not None:
        source = args.source

    try:
        if args.disasm:
            if source is not None:
                return _run_disasm(source, optimize=optimize)
            if args.file:
                text = Path(args.file).read_text(encoding="utf-8")
                return _run_disasm(text, optimize=optimize)
            print("error: --disasm requires -c SOURCE or a file", file=sys.stderr)
            return 2

        if source is not None:
            result = _execute(
                source,
                filename="<string>",
                mode=mode,
                optimize=optimize,
                use_vm=args.vm,
                trace=args.trace,
                debug=args.debug,
                breakpoints=args.breakpoints,
            )
            if result is not None:
                print(result)
            return 0

        if args.file:
            path = Path(args.file)
            text = path.read_text(encoding="utf-8")
            result = _execute(
                text,
                filename=str(path),
                mode=mode,
                optimize=optimize,
                use_vm=args.vm,
                trace=args.trace,
                debug=args.debug,
                breakpoints=args.breakpoints,
            )
            if result is not None:
                print(result)
            return 0

        run_repl(parser_mode=mode, optimize=optimize)
        return 0
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except PyMiniError as exc:
        _print_error(exc)
        return 1
    except Exception as exc:
        _print_error(exc)
        return 1


def _dispatch_sub(
    sub: str,
    args: argparse.Namespace,
    *,
    mode: ParserMode,
    optimize: bool,
) -> int:
    try:
        if sub == "version":
            print(f"PyMini {__version__}")
            return 0

        if sub == "repl":
            run_repl(parser_mode=mode, optimize=optimize)
            return 0

        if sub == "disasm":
            source = args.command
            if source is None and args.target is not None:
                if Path(args.target).is_file():
                    source = Path(args.target).read_text(encoding="utf-8")
                else:
                    source = args.target
            if source is None:
                print("error: disasm requires -c SOURCE or a file/source argument", file=sys.stderr)
                return 2
            return _run_disasm(source, optimize=optimize)

        if sub == "eval":
            source = args.command
            if source is None and args.target is not None:
                source = args.target
            if source is None:
                print("error: eval requires -c CODE or a source argument", file=sys.stderr)
                return 2
            result = _execute(
                source,
                filename="<string>",
                mode=mode,
                optimize=optimize,
                use_vm=args.vm,
                trace=args.trace,
                debug=args.debug,
                breakpoints=args.breakpoints,
            )
            if result is not None:
                print(result)
            return 0

        if sub in {"run", "debug"}:
            source = args.command
            filename = "<string>"
            if source is None:
                if args.target is None:
                    print(f"error: {sub} requires a file path or -c CODE", file=sys.stderr)
                    return 2
                path = Path(args.target)
                source = path.read_text(encoding="utf-8")
                filename = str(path)
            result = _execute(
                source,
                filename=filename,
                mode=mode,
                optimize=optimize,
                use_vm=args.vm and sub != "debug",
                trace=args.trace and sub != "debug",
                debug=args.debug or sub == "debug",
                breakpoints=args.breakpoints,
            )
            if result is not None:
                print(result)
            return 0

        print(f"error: unknown subcommand {sub!r}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except PyMiniError as exc:
        _print_error(exc)
        return 1
    except Exception as exc:
        _print_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
