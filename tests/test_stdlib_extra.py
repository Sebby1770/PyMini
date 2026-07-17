from __future__ import annotations

from pymini import __version__
from pymini.runtime.evaluator import Evaluator


def run(source: str) -> object:
    return Evaluator().run(source)


def test_math_extra_functions() -> None:
    source = """
import math
[
    math.fabs(-3.5),
    math.floor(math.log(math.exp(2))),
    math.degrees(math.radians(90)),
    math.pow(2, 3),
    math.factorial(5),
]
"""
    result = run(source)
    assert result[0] == 3.5
    assert result[1] == 2
    assert abs(result[2] - 90.0) < 1e-9
    assert result[3] == 8.0
    assert result[4] == 120


def test_random_module() -> None:
    source = """
import random
random.seed(42)
a = random.randint(1, 10)
b = random.random()
c = random.choice([10, 20, 30])
[isinstance(a, int), 0.0 <= b < 1.0, c in [10, 20, 30]]
"""
    assert run(source) == [True, True, True]


def test_json_module() -> None:
    source = """
import json
data = json.loads('{"a": 1, "b": [2, 3]}')
text = json.dumps({"x": 1})
[data["a"], data["b"], text]
"""
    result = run(source)
    assert result[0] == 1
    assert result[1] == [2, 3]
    assert '"x"' in result[2]


def test_pymini_version_matches_package() -> None:
    source = """
import pymini
pymini.version
"""
    assert run(source) == __version__
    assert __version__ == "0.3.0"
