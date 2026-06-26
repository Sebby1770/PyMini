from __future__ import annotations

import pytest

from pymini.api import ExecutionEngine, evaluate
from pymini.runtime.builtins import default_builtin_functions
from pymini.runtime.errors import PyMiniNameError


def test_engines_share_the_same_builtin_registry_and_output_contract() -> None:
    evaluator_output: list[str] = []
    vm_output: list[str] = []

    evaluator_result = evaluate(
        'print("value", int("3"))\nlen([1, 2])',
        stdout=evaluator_output.append,
    )
    vm_result = evaluate(
        'print("value", int("3"))\nlen([1, 2])',
        engine=ExecutionEngine.VM,
        stdout=vm_output.append,
    )

    assert evaluator_result == vm_result == 2
    assert evaluator_output == vm_output == ["value 3"]


def test_builtin_registry_is_fresh_and_explicitly_bounded() -> None:
    first = default_builtin_functions()
    second = default_builtin_functions()

    assert first is not second
    assert set(first) == {
        "bool",
        "dict",
        "float",
        "int",
        "len",
        "list",
        "print",
        "range",
        "str",
    }
    with pytest.raises(PyMiniNameError, match="sum"):
        evaluate("sum([1, 2])", engine=ExecutionEngine.VM)
