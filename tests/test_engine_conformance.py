from __future__ import annotations

import pytest

from pymini.api import ExecutionEngine, evaluate


@pytest.mark.parametrize(
    "source",
    [
        "x = 2 + 3 * 4\nx",
        "0 and missing",
        "1 or missing",
        "10 if 2 < 3 else 20",
        "items = [1, 2, 3]\nitems[0] + items[2]",
        'mapping = {"answer": int("4")}\nmapping["answer"]',
        "total = 0\nfor value in range(5):\n    total += value\ntotal",
        "i = 0\nwhile i < 4:\n    i += 1\ni",
        "x = 0\nfor value in []:\n    x = 1\nelse:\n    x = 2\nx",
    ],
)
def test_vm_matches_evaluator_for_compiled_subset(source: str) -> None:
    evaluator_result = evaluate(source, engine=ExecutionEngine.EVALUATOR)
    vm_result = evaluate(source, engine=ExecutionEngine.VM)

    assert vm_result == evaluator_result
