"""prompt_toolkit-powered REPL with Python syntax highlighting."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from pymini.parser import ParserMode
from pymini.runtime.errors import PyMiniError, format_error
from pymini.runtime.evaluator import Evaluator
from pymini.version import VERSION


def _terminal_prompt() -> Callable[[str], str]:
    """Create the richest available terminal prompt implementation."""

    try:
        from prompt_toolkit import PromptSession  # type: ignore[import-not-found]
        from prompt_toolkit.lexers import PygmentsLexer  # type: ignore[import-not-found]
        from pygments.lexers.python import PythonLexer  # type: ignore[import-untyped]

        session = PromptSession(lexer=PygmentsLexer(PythonLexer))

        def read_prompt(text: str) -> str:
            return cast(str, session.prompt(text))

    except ImportError:

        def read_prompt(text: str) -> str:
            return input(text)

    return read_prompt


def run_repl(
    *,
    parser_mode: ParserMode = ParserMode.AST,
    optimize: bool = True,
    prompt: Callable[[str], str] | None = None,
    stdout: Callable[[str], None] | None = None,
) -> None:
    """Run a stateful REPL with injectable I/O for embedding and tests."""

    write = stdout or print
    read = prompt or _terminal_prompt()
    evaluator = Evaluator(stdout=write)
    buffer: list[str] = []

    write(f"PyMini {VERSION}. Type Ctrl-D to exit.")
    while True:
        try:
            line = read("... " if buffer else ">>> ")
        except (EOFError, KeyboardInterrupt):
            write("")
            break

        if not line.strip() and buffer:
            source = "\n".join(buffer)
            buffer.clear()
        elif line.rstrip().endswith(":") or buffer:
            buffer.append(line)
            continue
        else:
            source = line

        if not source.strip():
            continue
        try:
            result = evaluator.run(source, parser_mode=parser_mode, optimize=optimize)
            if result is not None:
                write(str(result))
        except PyMiniError as exc:
            write(format_error(exc, source=source))
