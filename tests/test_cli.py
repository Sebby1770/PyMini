from __future__ import annotations

import argparse

import pytest

from pymini import __main__ as cli


def test_cli_runs_commands_and_vm_disassembly(capsys) -> None:
    assert cli.main(["-c", "1 + 2"]) == 0
    assert capsys.readouterr().out.strip() == "3"

    assert cli.main(["--engine", "vm", "--disassemble", "-c", "x = 2\nx"]) == 0
    output = capsys.readouterr().out
    assert "STORE_NAME" in output
    assert output.rstrip().endswith("2")


def test_cli_formats_runtime_and_file_errors(capsys, tmp_path) -> None:
    assert cli.main(["-c", "missing"]) == 1
    assert "PyMiniNameError" in capsys.readouterr().out

    missing_path = tmp_path / "missing.pymi"
    assert cli.main([str(missing_path)]) == 1
    assert "could not read" in capsys.readouterr().out


def test_cli_rejects_disassembly_for_evaluator(capsys) -> None:
    assert cli.main(["--disassemble", "-c", "1"]) == 1
    assert "requires --engine vm" in capsys.readouterr().out


def test_cli_uses_evaluator_for_repl(monkeypatch, capsys) -> None:
    calls: list[tuple[object, bool]] = []

    def fake_repl(*, parser_mode, optimize) -> None:
        calls.append((parser_mode, optimize))

    monkeypatch.setattr(cli, "run_repl", fake_repl)

    assert cli.main(["--vm", "--no-optimize"]) == 0
    assert calls and calls[0][1] is False
    assert "using the evaluator" in capsys.readouterr().out


def test_positive_integer_validation() -> None:
    assert cli.positive_integer("3") == 3
    with pytest.raises(argparse.ArgumentTypeError):
        cli.positive_integer("0")
