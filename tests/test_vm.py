from __future__ import annotations

import pytest

from pymini.api import ExecutionEngine, compile_source, evaluate
from pymini.runtime.errors import PyMiniNotImplementedError, PyMiniRuntimeError


def run_vm(source: str, *, max_steps: int = 100_000) -> object:
    return evaluate(source, engine=ExecutionEngine.VM, max_steps=max_steps)


def test_vm_executes_arithmetic_names_and_last_expression() -> None:
    assert run_vm("x = 2 + 3 * 4\nx") == 14
    assert run_vm("x = y = 7\nx + y") == 14


def test_vm_executes_control_flow_and_short_circuiting() -> None:
    source = """
total = 0
i = 0
while i < 4:
    total += i
    i += 1
if total == 6:
    total += 10
total
"""

    assert run_vm(source) == 16
    assert run_vm("0 and missing") == 0
    assert run_vm("1 or missing") == 1
    assert run_vm("10 if 2 < 3 else 20") == 10


def test_vm_exposes_bounded_builtins() -> None:
    assert run_vm('int("3") + len("ab")') == 5


def test_vm_executes_collections_iteration_and_subscripts() -> None:
    source = """
total = 0
for value in [1, 2, 3]:
    if value == 2:
        continue
    total += value
else:
    total += 10
mapping = {"answer": total}
mapping["answer"]
"""
    break_source = """
total = 0
for value in (1, 2, 3):
    if value == 2:
        break
    total += value
else:
    total = 99
total
"""

    assert run_vm(source) == 14
    assert run_vm(break_source) == 1


def test_vm_executes_subscript_assignment_and_unpacking() -> None:
    source = """
items = [1, 2, 3]
items[1] = 20
first, second, third = items
nested = [0]
nested[0] += second
first + nested[0] + third
"""

    assert run_vm(source) == 24


def test_vm_executes_identity_and_membership_comparisons() -> None:
    source = """
is_none = None is None
not_none = 1 is not None
contains = 2 in [1, 2, 3]
missing = "x" not in {"answer": 42}
is_none and not_none and contains and missing
"""

    assert run_vm(source) is True


def test_vm_rejects_unsupported_syntax_before_execution() -> None:
    with pytest.raises(PyMiniNotImplementedError, match="FunctionDef statements"):
        run_vm("x = 1\ndef f():\n    return x")


def test_vm_enforces_execution_budget() -> None:
    with pytest.raises(PyMiniRuntimeError, match="step limit"):
        run_vm("while True:\n    x = 1", max_steps=10)


def test_bytecode_disassembly_is_stable_and_readable() -> None:
    disassembly = compile_source("x = 2 + 3\nx", optimize=False).disassemble()

    assert "chunk '<module>'" in disassembly
    assert "BINARY_ADD" in disassembly
    assert "STORE_NAME" in disassembly
    assert "RETURN_VALUE" in disassembly
