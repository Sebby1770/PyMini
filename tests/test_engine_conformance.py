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
        "items = [1, 2, 3]\nitems[1] = 5\nitems[0] + items[1]",
        "first, second = (4, 9)\nfirst * 10 + second",
        "nested = [0]\nnested[0] += 7\nnested[0]",
        'mapping = {"answer": int("4")}\nmapping["answer"]',
        "None is None",
        "1 is not None",
        "2 in [1, 2, 3]",
        '"x" not in {"answer": 42}',
        "total = 0\nfor value in range(5):\n    total += value\ntotal",
        "i = 0\nwhile i < 4:\n    i += 1\ni",
        "x = 0\nfor value in []:\n    x = 1\nelse:\n    x = 2\nx",
    ],
)
def test_vm_matches_evaluator_for_compiled_subset(source: str) -> None:
    evaluator_result = evaluate(source, engine=ExecutionEngine.EVALUATOR)
    vm_result = evaluate(source, engine=ExecutionEngine.VM)

    assert vm_result == evaluator_result
