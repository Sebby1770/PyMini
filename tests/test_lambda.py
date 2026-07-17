from __future__ import annotations

from pymini.runtime.evaluator import Evaluator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_lambda_basic() -> None:
    assert run("f = lambda x: x + 1\nf(41)") == 42


def test_lambda_two_args() -> None:
    assert run("add = lambda a, b: a + b\nadd(2, 3)") == 5


def test_lambda_closure() -> None:
    source = """
def make(n):
    return lambda x: x + n
make(10)(5)
"""
    assert run(source) == 15


def test_lambda_default() -> None:
    assert run("f = lambda x, y=2: x * y\nf(3)") == 6


def test_lambda_in_map() -> None:
    assert run("map(lambda x: x * x, [1, 2, 3])") == [1, 4, 9]
