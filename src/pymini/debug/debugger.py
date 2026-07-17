"""Lightweight line debugger and trace hooks for PyMini."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal

from pymini.parser import ParserMode
from pymini.runtime.evaluator import Evaluator
from pymini.runtime.scope import Environment


class DebugCommand(Enum):
    CONTINUE = auto()
    STEP = auto()
    QUIT = auto()


@dataclass
class TraceHooks:
    """Simple hooks invoked before each new source line executes."""

    lines_seen: list[int] = field(default_factory=list)
    callback: Callable[[int, str | None], None] | None = None

    def on_line(self, lineno: int, frame_name: str | None) -> None:
        self.lines_seen.append(lineno)
        if self.callback is not None:
            self.callback(lineno, frame_name)


@dataclass
class Debugger:
    """Minimal debugger: breakpoints by line, step, continue, inspect locals.

    Designed for interactive CLI use and for scripted smoke tests.
    """

    breakpoints: set[int] = field(default_factory=set)
    mode: Literal["run", "step", "quit"] = "run"
    last_line: int | None = None
    input_fn: Callable[[str], str] = input
    output_fn: Callable[[str], None] = print
    _paused: bool = False
    _source_lines: list[str] = field(default_factory=list)
    _evaluator: Evaluator | None = None

    def set_breakpoint(self, line: int) -> None:
        self.breakpoints.add(line)

    def clear_breakpoint(self, line: int) -> None:
        self.breakpoints.discard(line)

    def clear_all_breakpoints(self) -> None:
        self.breakpoints.clear()

    def _format_locals(self, env: Environment) -> str:
        items = sorted(env.values.items())
        if not items:
            return "  (empty)"
        lines = []
        for name, value in items:
            if name.startswith("_"):
                continue
            lines.append(f"  {name} = {value!r}")
        return "\n".join(lines) if lines else "  (empty)"

    def _show_context(self, lineno: int, frame_name: str | None) -> None:
        self.output_fn(f"-- break at line {lineno} in {frame_name or '<module>'} --")
        if 1 <= lineno <= len(self._source_lines):
            start = max(1, lineno - 2)
            end = min(len(self._source_lines), lineno + 2)
            for n in range(start, end + 1):
                marker = "->" if n == lineno else "  "
                self.output_fn(f"{marker} {n:4d} | {self._source_lines[n - 1]}")
        if self._evaluator is not None:
            self.output_fn("locals:")
            self.output_fn(self._format_locals(self._evaluator.current_env))

    def _handle_pause(self, lineno: int, frame_name: str | None) -> None:
        self._show_context(lineno, frame_name)
        while True:
            try:
                raw = self.input_fn("(pymini-debug) ").strip()
            except EOFError:
                self.mode = "quit"
                raise SystemExit(0)
            if not raw:
                raw = "s" if self.mode == "step" else "c"
            cmd, *rest = raw.split(maxsplit=1)
            cmd = cmd.lower()
            if cmd in {"c", "continue"}:
                self.mode = "run"
                return
            if cmd in {"s", "step", "n", "next"}:
                self.mode = "step"
                return
            if cmd in {"l", "locals"}:
                if self._evaluator is not None:
                    self.output_fn(self._format_locals(self._evaluator.current_env))
                continue
            if cmd in {"p", "print"} and rest:
                if self._evaluator is not None:
                    name = rest[0]
                    try:
                        value = self._evaluator.current_env.get(name)
                        self.output_fn(repr(value))
                    except Exception as exc:
                        self.output_fn(f"error: {exc}")
                continue
            if cmd in {"b", "break"} and rest:
                try:
                    self.set_breakpoint(int(rest[0]))
                    self.output_fn(f"breakpoint set at line {rest[0]}")
                except ValueError:
                    self.output_fn("usage: b <lineno>")
                continue
            if cmd in {"q", "quit"}:
                self.mode = "quit"
                raise SystemExit(0)
            if cmd in {"h", "help"}:
                self.output_fn(
                    "commands: c(ontinue), s(tep), l(ocals), p <name>, b <line>, q(uit), h(elp)"
                )
                continue
            self.output_fn(f"unknown command {cmd!r}; type h for help")

    def on_line(self, lineno: int, frame_name: str | None) -> None:
        if self.mode == "quit":
            raise SystemExit(0)
        should_pause = self.mode == "step" or lineno in self.breakpoints
        if should_pause and lineno != self.last_line:
            self.last_line = lineno
            self._handle_pause(lineno, frame_name)
        else:
            self.last_line = lineno

    def run_source(
        self,
        source: str,
        *,
        filename: str = "<string>",
        parser_mode: ParserMode | str = ParserMode.AST,
        optimize: bool = True,
        step_first: bool = False,
    ) -> object:
        self._source_lines = source.splitlines() or [""]
        if step_first:
            self.mode = "step"
        evaluator = Evaluator(
            filename=filename,
            on_line=self.on_line,
        )
        self._evaluator = evaluator
        return evaluator.run(source, parser_mode=parser_mode, optimize=optimize)


def run_with_trace(
    source: str,
    *,
    filename: str = "<string>",
    stdout: Callable[[str], None] | None = None,
    parser_mode: ParserMode | str = ParserMode.AST,
    optimize: bool = True,
) -> object:
    """Execute *source* while printing each line before it runs."""

    out = stdout or print
    return Evaluator(filename=filename, stdout=out, trace=True).run(
        source, parser_mode=parser_mode, optimize=optimize
    )
