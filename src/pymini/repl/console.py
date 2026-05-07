"""prompt_toolkit-powered REPL with Python syntax highlighting."""

from __future__ import annotations

from pymini.parser import ParserMode
from pymini.runtime.evaluator import Evaluator


def run_repl(*, parser_mode: ParserMode = ParserMode.AST, optimize: bool = True) -> None:
    evaluator = Evaluator()
    buffer: list[str] = []

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.lexers import PygmentsLexer
        from pygments.lexers.python import PythonLexer

        session = PromptSession(lexer=PygmentsLexer(PythonLexer))

        def prompt(text: str) -> str:
            return session.prompt(text)

    except Exception:

        def prompt(text: str) -> str:
            return input(text)

    print("PyMini 0.1.0. Type Ctrl-D to exit.")
    while True:
        try:
            line = prompt("... " if buffer else ">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
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
                print(result)
        except Exception as exc:
            print(f"{exc.__class__.__name__}: {exc}")

