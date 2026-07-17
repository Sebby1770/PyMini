from __future__ import annotations

import pytest

from pymini.runtime.errors import PyMiniError
from pymini.runtime.evaluator import Evaluator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_keyword_args_call() -> None:
    source = """
def greet(name, punct):
    return name + punct
greet(name="hi", punct="!")
"""
    assert run(source) == "hi!"


def test_mixed_positional_and_keyword() -> None:
    source = """
def f(a, b, c):
    return a * 100 + b * 10 + c
f(1, c=3, b=2)
"""
    assert run(source) == 123


def test_kwargs_param() -> None:
    source = """
def f(**kwargs):
    return kwargs["x"] + kwargs["y"]
f(x=10, y=5)
"""
    assert run(source) == 15


def test_kwargs_with_positional() -> None:
    source = """
def f(a, **kwargs):
    return a + kwargs["b"]
f(1, b=2)
"""
    assert run(source) == 3


def test_keyword_only_after_star() -> None:
    source = """
def f(a, *, b, c=3):
    return a + b + c
f(1, b=2)
"""
    assert run(source) == 6


def test_keyword_only_required() -> None:
    with pytest.raises(PyMiniError):
        run(
            """
def f(*, b):
    return b
f()
"""
        )


def test_double_star_call() -> None:
    source = """
def f(a, b):
    return a + b
opts = {"a": 10, "b": 20}
f(**opts)
"""
    assert run(source) == 30


def test_unexpected_keyword() -> None:
    with pytest.raises(PyMiniError):
        run(
            """
def f(a):
    return a
f(a=1, b=2)
"""
        )
