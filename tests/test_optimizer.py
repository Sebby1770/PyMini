from __future__ import annotations

import ast

from pymini.api import parse


def test_constant_folding() -> None:
    module = parse("x = 2 + 3 * 4", optimize=True)
    assign = module.body[0]
    assert isinstance(assign, ast.Assign)
    assert isinstance(assign.value, ast.Constant)
    assert assign.value.value == 14


def test_dead_code_after_return_is_removed() -> None:
    module = parse(
        """
def f():
    return 1
    x = 2
""",
        optimize=True,
    )
    func = module.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert len(func.body) == 1

