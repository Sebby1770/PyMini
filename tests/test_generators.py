from __future__ import annotations

from pymini.runtime.evaluator import Evaluator
from pymini.runtime.objects import MiniGenerator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_simple_generator() -> None:
    source = """
def count():
    yield 1
    yield 2
    yield 3

list(count())
"""
    assert run(source) == [1, 2, 3]


def test_generator_in_for_loop() -> None:
    source = """
def gen():
    yield 10
    yield 20

total = 0
for x in gen():
    total = total + x
total
"""
    assert run(source) == 30


def test_generator_with_loop() -> None:
    source = """
def count_to(n):
    i = 0
    while i < n:
        yield i
        i = i + 1

list(count_to(4))
"""
    assert run(source) == [0, 1, 2, 3]


def test_generator_object_type() -> None:
    evaluator = Evaluator()
    result = evaluator.run(
        """
def g():
    yield 1
g()
"""
    )
    assert isinstance(result, MiniGenerator)


def test_generator_next() -> None:
    source = """
def g():
    yield "a"
    yield "b"

it = g()
first = it.__next__()
second = it.__next__()
[first, second]
"""
    assert run(source) == ["a", "b"]


def test_generator_with_for_yield() -> None:
    source = """
def from_list(items):
    for item in items:
        yield item * 2

list(from_list([1, 2, 3]))
"""
    assert run(source) == [2, 4, 6]
