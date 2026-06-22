# Implementation Plan

## Milestone 1: Parser + Basic Evaluator

- Provide a parser facade over Python's `ast` module.
- Provide a hand-written recursive descent parser for a useful Python subset.
- Implement lexical environments and runtime objects.
- Execute variables, arithmetic, functions, closures, classes, inheritance,
  control flow, lists, dicts, calls, attributes, subscripts, and safe imports.
- Add constant folding and dead code elimination.
- Add tests around the supported subset.

## Milestone 2: Compiler + Bytecode VM

- [x] Define typed bytecode instructions, constants, jumps, and comparisons.
- [x] Compile expressions, collections, subscripts, assignments, `if`, `while`, `for`,
  loop control, short-circuit boolean operations, and bounded built-in calls.
- [x] Implement one authoritative frame stack, runtime checks, and execution budgets.
- [x] Add collections and human-readable disassembly.
- [x] Add differential evaluator/VM tests for the currently compiled subset.
- [ ] Add user functions, closures, method binding, and imports.
- [ ] Expand differential tests as the VM subset grows.

## Milestone 3: Memory Model

- Track object references in a simulated heap.
- Add reference counting operations to runtime allocation sites.
- Detect cycles with graph traversal and collect unreachable strongly connected
  components.
- Expose memory statistics in the debugger and REPL.

## Milestone 4: Tooling

- Polish the `prompt_toolkit` REPL.
- Add rich diagnostics and source spans.
- Add bytecode disassembly, tracing, stepping, and breakpoints.

## Milestone 5: Performance + Targets

- Benchmark evaluator and VM against CPython.
- Add `llvmlite` JIT experiments for hot loops.
- Add a WebAssembly backend for a small numeric subset.
