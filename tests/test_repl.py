from __future__ import annotations

from pymini.repl.console import run_repl


def scripted_prompt(lines: list[str]):
    responses = iter(lines)

    def prompt(_: str) -> str:
        try:
            return next(responses)
        except StopIteration as exc:
            raise EOFError from exc

    return prompt


def test_repl_preserves_state_and_supports_multiline_input() -> None:
    output: list[str] = []

    run_repl(
        prompt=scripted_prompt(["x = 2", "x + 3", "if True:", "    x = 9", "", "x"]),
        stdout=output.append,
    )

    assert output[0].startswith("PyMini 0.1.0")
    assert output[1:] == ["2", "5", "9", "9", ""]


def test_repl_formats_errors_and_handles_keyboard_interrupt() -> None:
    output: list[str] = []
    calls = 0

    def prompt(_: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "missing"
        raise KeyboardInterrupt

    run_repl(prompt=prompt, stdout=output.append)

    assert any("PyMiniNameError" in line for line in output)
    assert output[-1] == ""
