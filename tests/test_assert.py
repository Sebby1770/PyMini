from __future__ import annotations

import pytest

from pymini.runtime.evaluator import Evaluator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_assert_true_passes() -> None:
    assert run("assert True\n1") == 1


def test_assert_expression_passes() -> None:
    assert run("x = 2\nassert x == 2\nx") == 2


def test_assert_false_raises() -> None:
    with pytest.raises(AssertionError):
        run("assert False")


def test_assert_with_message() -> None:
    with pytest.raises(AssertionError) as info:
        run('assert 1 == 0, "nope"')
    assert "nope" in str(info.value)


def test_assert_in_function() -> None:
    source = """
def check(x):
    assert x > 0, "positive required"
    return x
check(5)
"""
    assert run(source) == 5
