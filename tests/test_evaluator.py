from __future__ import annotations

from pymini.parser import ParserMode
from pymini.runtime.evaluator import Evaluator


def run(source: str, mode: ParserMode | str = ParserMode.AST) -> object:
    return Evaluator().run(source, parser_mode=mode)


def test_arithmetic_variables_and_last_expression() -> None:
    assert run("x = 2 + 3 * 4\nx") == 14


def test_lists_dicts_and_subscripts() -> None:
    source = """
items = [1, 2, 3]
mapping = {"answer": items[0] + items[2]}
mapping["answer"]
"""
    assert run(source) == 4


def test_if_while_and_for_control_flow() -> None:
    source = """
total = 0
i = 0
while i < 3:
    total = total + i
    i = i + 1
for value in [10, 20]:
    total = total + value
total
"""
    assert run(source) == 33


def test_functions_capture_lexical_scope() -> None:
    source = """
def make_adder(x):
    def add(y):
        return x + y
    return add
add10 = make_adder(10)
add10(5)
"""
    assert run(source) == 15


def test_classes_methods_and_inheritance() -> None:
    source = """
class Animal:
    def speak(self):
        return "sound"

class Dog(Animal):
    def name(self):
        return "Ada"

dog = Dog()
dog.speak() + ":" + dog.name()
"""
    assert run(source) == "sound:Ada"


def test_imports_from_safe_stdlib() -> None:
    source = """
import math
from math import sqrt
math.floor(math.pi) + sqrt(9)
"""
    assert run(source) == 6.0


def test_handwritten_parser_runs_basic_program() -> None:
    source = """
def choose(x):
    if x > 3:
        return x * 2
    return x + 1
choose(5)
"""
    assert run(source, ParserMode.HANDWRITTEN) == 10

