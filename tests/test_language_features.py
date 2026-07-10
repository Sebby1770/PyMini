from __future__ import annotations

import pytest

from pymini.runtime.errors import PyMiniError, format_exception
from pymini.runtime.evaluator import Evaluator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_try_except_catches_exception() -> None:
    source = """
result = "ok"
try:
    raise Exception("boom")
except Exception:
    result = "caught"
result
"""
    assert run(source) == "caught"


def test_try_except_binds_exception() -> None:
    source = """
msg = ""
try:
    raise Exception("hello")
except Exception as exc:
    msg = str(exc)
msg
"""
    assert run(source) == "hello"


def test_try_finally_runs() -> None:
    source = """
flag = 0
try:
    flag = 1
finally:
    flag = flag + 10
flag
"""
    assert run(source) == 11


def test_try_except_finally() -> None:
    source = """
steps = []
try:
    steps = steps + ["try"]
    raise Exception("x")
except Exception:
    steps = steps + ["except"]
finally:
    steps = steps + ["finally"]
steps
"""
    assert run(source) == ["try", "except", "finally"]


def test_function_default_args() -> None:
    source = """
def greet(name, suffix="!"):
    return name + suffix
greet("hi") + greet("hi", "?")
"""
    assert run(source) == "hi!hi?"


def test_function_varargs() -> None:
    source = """
def sum_all(first, *rest):
    total = first
    for value in rest:
        total = total + value
    return total
sum_all(1, 2, 3, 4)
"""
    assert run(source) == 10


def test_starred_call_args() -> None:
    source = """
def add(a, b, c):
    return a + b + c
values = [1, 2, 3]
add(*values)
"""
    assert run(source) == 6


def test_with_statement_context_manager() -> None:
    source = """
class CM:
    def __init__(self):
        self.events = []
    def __enter__(self):
        self.events = self.events + ["enter"]
        return 42
    def __exit__(self, exc_type, exc, tb):
        self.events = self.events + ["exit"]
        return False

cm = CM()
value = 0
with cm as x:
    value = x
cm.events + [value]
"""
    assert run(source) == ["enter", "exit", 42]


def test_list_comprehension() -> None:
    assert run("[x * 2 for x in [1, 2, 3]]") == [2, 4, 6]


def test_list_comprehension_with_filter() -> None:
    assert run("[x for x in range(5) if x % 2 == 0]") == [0, 2, 4]


def test_dict_comprehension() -> None:
    assert run("{x: x * x for x in [1, 2, 3]}") == {1: 1, 2: 4, 3: 9}


def test_set_comprehension() -> None:
    assert run("{x % 2 for x in [1, 2, 3, 4]}") == {0, 1}


def test_f_string_basic() -> None:
    source = """
name = "Ada"
f"hello {name}"
"""
    assert run(source) == "hello Ada"


def test_f_string_expression() -> None:
    assert run('f"{1 + 2} items"') == "3 items"


def test_traceback_includes_line_number() -> None:
    evaluator = Evaluator(filename="sample.pymi")
    with pytest.raises(PyMiniError) as info:
        evaluator.run(
            """
def boom():
    return missing

boom()
"""
        )
    formatted = format_exception(info.value)
    assert "sample.pymi" in formatted
    assert "boom" in formatted
    assert "line" in formatted
    assert info.value.frames
    assert any(frame.name == "boom" for frame in info.value.frames)


def test_name_error_message_is_clear() -> None:
    with pytest.raises(PyMiniError) as info:
        run("not_defined")
    assert "not_defined" in str(info.value)
