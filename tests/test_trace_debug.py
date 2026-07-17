from __future__ import annotations

from pymini.debug.debugger import Debugger, TraceHooks, run_with_trace
from pymini.runtime.evaluator import Evaluator
from pymini.__main__ import main


def test_trace_prints_lines(capsys) -> None:
    source = "x = 1\ny = 2\nx + y\n"
    result = run_with_trace(source, filename="sample.py")
    captured = capsys.readouterr()
    assert "sample.py:1" in captured.out
    assert "sample.py:2" in captured.out
    assert result == 3


def test_on_line_hook() -> None:
    hooks = TraceHooks()
    ev = Evaluator(filename="t.py", on_line=hooks.on_line)
    ev.run("a = 1\nb = 2\na + b\n")
    assert hooks.lines_seen
    assert 1 in hooks.lines_seen


def test_debugger_with_scripted_input() -> None:
    commands = iter(["l", "c"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(commands)
        except StopIteration:
            return "c"

    outputs: list[str] = []

    dbg = Debugger(
        input_fn=fake_input,
        output_fn=lambda s: outputs.append(s),
    )
    dbg.set_breakpoint(2)
    result = dbg.run_source("x = 10\ny = x + 1\ny\n", filename="dbg.py")
    assert result == 11
    assert any("break at line 2" in line for line in outputs)
    assert any("x = 10" in line for line in outputs)


def test_cli_version() -> None:
    assert main(["version"]) == 0


def test_cli_eval(capsys) -> None:
    code = main(["eval", "-c", "1 + 2"])
    assert code == 0
    assert "3" in capsys.readouterr().out


def test_cli_disasm(capsys) -> None:
    code = main(["disasm", "-c", "x = 1 + 2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "LOAD_CONST" in out or "BINARY_ADD" in out or "STORE_NAME" in out
