from __future__ import annotations

from pymini.runtime.evaluator import Evaluator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_enumerate() -> None:
    assert run("enumerate(['a', 'b'], 1)") == [(1, "a"), (2, "b")]


def test_zip() -> None:
    assert run("zip([1, 2], ['a', 'b'])") == [(1, "a"), (2, "b")]


def test_map_filter() -> None:
    source = """
squares = map(lambda x: x * x, [1, 2, 3, 4])
evens = filter(lambda x: x % 2 == 0, squares)
evens
"""
    assert run(source) == [4, 16]


def test_sorted_reversed() -> None:
    assert run("sorted([3, 1, 2])") == [1, 2, 3]
    assert run("reversed([1, 2, 3])") == [3, 2, 1]


def test_sorted_key_reverse() -> None:
    source = """
sorted([3, 1, 2], key=lambda x: -x)
"""
    assert run(source) == [3, 2, 1]
    assert run("sorted([1, 2, 3], reverse=True)") == [3, 2, 1]


def test_sum_min_max() -> None:
    assert run("sum([1, 2, 3])") == 6
    assert run("sum([1, 2, 3], 10)") == 16
    assert run("min(3, 1, 2)") == 1
    assert run("max([3, 1, 2])") == 3


def test_any_all() -> None:
    assert run("any([0, 0, 1])") is True
    assert run("all([1, 2, 3])") is True
    assert run("all([1, 0, 3])") is False


def test_abs_round() -> None:
    assert run("abs(-5)") == 5
    assert run("round(3.6)") == 4
    assert run("round(3.14159, 2)") == 3.14


def test_isinstance_type() -> None:
    assert run("isinstance(1, int)") is True
    assert run("isinstance('a', str)") is True
    assert run("type(1) is int") is True


def test_hasattr_getattr_setattr() -> None:
    source = """
class Box:
    def __init__(self):
        self.value = 1

b = Box()
ok = hasattr(b, "value")
v = getattr(b, "value")
setattr(b, "value", 9)
[ok, v, b.value, getattr(b, "missing", 42)]
"""
    assert run(source) == [True, 1, 9, 42]
