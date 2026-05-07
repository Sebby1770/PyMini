"""Simple benchmark runner comparing PyMini's evaluator with CPython."""

from __future__ import annotations

import timeit

from pymini.runtime.evaluator import Evaluator

PROGRAM = """
total = 0
for value in range(1000):
    total = total + value
total
"""


def run_pymini() -> object:
    return Evaluator().run(PROGRAM)


def run_cpython() -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(PROGRAM, {}, namespace)
    return namespace


def main() -> None:
    pymini = timeit.timeit(run_pymini, number=100)
    cpython = timeit.timeit(run_cpython, number=100)
    print(f"PyMini evaluator: {pymini:.4f}s")
    print(f"CPython exec:      {cpython:.4f}s")
    print(f"Ratio:            {pymini / cpython:.1f}x")


if __name__ == "__main__":
    main()

