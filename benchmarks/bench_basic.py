"""Repeatable benchmark comparing PyMini's evaluator with CPython."""

from __future__ import annotations

import argparse
import json
import statistics
import timeit
from dataclasses import asdict, dataclass

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


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    repeat: int
    number: int
    pymini_seconds: float
    cpython_seconds: float
    ratio: float


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def benchmark(*, repeat: int = 7, number: int = 100) -> BenchmarkResult:
    """Warm both runtimes and report medians to reduce one-shot timing noise."""

    run_pymini()
    run_cpython()
    pymini_samples = timeit.repeat(run_pymini, repeat=repeat, number=number)
    cpython_samples = timeit.repeat(run_cpython, repeat=repeat, number=number)
    pymini_seconds = statistics.median(pymini_samples)
    cpython_seconds = statistics.median(cpython_samples)
    return BenchmarkResult(
        repeat=repeat,
        number=number,
        pymini_seconds=pymini_seconds,
        cpython_seconds=cpython_seconds,
        ratio=pymini_seconds / cpython_seconds,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=positive_integer, default=7)
    parser.add_argument("--number", type=positive_integer, default=100)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = benchmark(repeat=args.repeat, number=args.number)
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(f"Median of {result.repeat} runs ({result.number} executions each)")
        print(f"PyMini evaluator: {result.pymini_seconds:.4f}s")
        print(f"CPython exec:      {result.cpython_seconds:.4f}s")
        print(f"Ratio:             {result.ratio:.1f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
