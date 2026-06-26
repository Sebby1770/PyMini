# Changelog

All notable changes to this project will be documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A shared parse-and-optimize pipeline and selectable evaluator/VM execution engines.
- A typed bytecode compiler, human-readable disassembler, and bounded stack VM with
  control flow, collections, subscripting, iteration, loop control, built-in calls,
  and source-aware errors.
- VM support for subscript assignment, sequence unpacking, augmented subscript assignment,
  identity comparisons, and membership comparisons.
- Detailed CLI/REPL diagnostics, bytecode tests, runtime semantic tests, and GC tests.
- Centralized runtime version metadata and GitHub Actions verification.
- `@Sebby1770` code ownership and grouped Dependabot updates.
- Contribution, security, pull-request, and structured bug-report guidance.
- Coverage, package-build, metadata-consistency, and artifact validation gates.
- A shared bounded builtin registry and injectable evaluator, VM, and REPL output paths.
- Repeatable median-based benchmarks with human-readable and JSON output.
- Differential evaluator/VM conformance tests for the compiled language subset.
- Isolated built-wheel installation and published-CLI smoke verification.

### Changed

- The VM now uses one frame-owned operand stack and validates every instruction operand.
- The compiler and VM now cover more of the evaluator's collection and comparison semantics
  under differential conformance tests.
- The GC simulator now enforces refcount invariants, cascading release, and rooted tracing.
- Architecture and milestones now distinguish implemented engines from roadmap work.
- Evaluator diagnostics materialize source locations lazily to protect the hot path.
- The enforced test coverage floor increased from 65% to 75%.
- Evaluator AST dispatch now caches resolved node handlers, reducing end-to-end benchmark
  time by roughly 8% in the documented local median workload.

### Fixed

- Kept strict typing portable between minimal local environments and CI environments with
  installed prompt-toolkit/Pygments type information.
- Corrected `for`/`while ... else`, `break`, and `continue` semantics.
- Reset execution budgets between runs while preserving stateful REPL globals.
- Corrected duplicate-edge refcounts, zero-refcount cascades, and cycle collection.
- Eliminated all strict mypy and Ruff failures in the expanded implementation.

### Security

- Prevented interpreted programs from reflecting into native-function internals.
- Added consistent evaluator and VM execution-step limits.

[Unreleased]: https://github.com/Sebby1770/PyMini/compare/v0.1.0...HEAD
