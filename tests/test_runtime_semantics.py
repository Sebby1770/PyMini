from __future__ import annotations

import pytest

from pymini.runtime.errors import PyMiniNameError, format_error
from pymini.runtime.evaluator import Evaluator


@pytest.mark.parametrize("optimize", [False, True])
def test_loop_else_runs_only_without_break(optimize: bool) -> None:
    while_source = """
x = 0
while False:
    x = 1
else:
    x = 2
x
"""
    for_source = """
x = 0
for value in []:
    x = 1
else:
    x = 2
x
"""
    break_source = """
x = 0
while True:
    x = 1
    break
else:
    x = 2
x
"""

    assert Evaluator().run(while_source, optimize=optimize) == 2
    assert Evaluator().run(for_source, optimize=optimize) == 2
    assert Evaluator().run(break_source, optimize=optimize) == 1


def test_reused_evaluator_resets_budget_but_preserves_globals() -> None:
    evaluator = Evaluator(max_steps=4)

    assert evaluator.run("x = 1", optimize=False) == 1
    assert evaluator.run("x", optimize=False) == 1
    assert evaluator.steps <= evaluator.max_steps


def test_runtime_error_contains_source_location() -> None:
    source = "x = 1\nmissing"
    with pytest.raises(PyMiniNameError) as captured:
        Evaluator(filename="example.pymi").run(source)

    rendered = format_error(captured.value)
    assert "example.pymi:2:1" in rendered
    assert ">    2 | missing" in rendered
    assert "^" in rendered


def test_native_function_internals_are_not_reflectable() -> None:
    with pytest.raises(PyMiniNameError, match="no accessible attribute"):
        Evaluator().run("len.func")
