# Implementation Plan

## Milestone 1: Parser + Basic Evaluator

- [x] Provide a parser facade over Python's `ast` module.
- [x] Provide a hand-written recursive descent parser for a useful Python subset.
- [x] Implement lexical environments and runtime objects.
- [x] Execute variables, arithmetic, functions, closures, classes, inheritance,
  control flow, lists, dicts, calls, attributes, subscripts, and safe imports.
- [x] Add constant folding and dead code elimination.
- [x] Add tests around the supported subset.
- [x] try/except/finally, with, *args/defaults, comprehensions, f-strings
- [x] lambda, assert, keyword args / `**kwargs`, keyword-only parameters
- [x] Basic generators (`yield`, MiniGenerator, for-loop iteration)

## Milestone 2: Compiler + Bytecode VM

- [x] Design bytecode instructions and a disassembler.
- [x] Compile AST nodes into chunks with constants and name tables.
- [x] Implement stack frames, call protocol, and simple functions.
- [x] Add VM tests that mirror evaluator tests (subset).
- [x] Expanded opcodes: `BINARY_MOD`, `BINARY_POW`, `UNARY_NOT`, `UNARY_NEGATIVE`,
  `BUILD_SET`, `GET_ITER`, `FOR_ITER`, `JUMP_IF_TRUE`
- [x] Compile for-loops to `GET_ITER` / `FOR_ITER`
- [ ] Full closure cells, class opcodes, import opcodes (roadmap)

## Milestone 3: Memory Model

- [x] Reference counting / cycle detection *simulator* scaffolding
- [ ] Track object references in a simulated heap end-to-end
- [ ] Expose memory statistics in the debugger and REPL

## Milestone 4: Tooling

- [x] Polish the `prompt_toolkit` REPL.
- [x] Rich diagnostics / tracebacks with line numbers.
- [x] Bytecode disassembly (`pymini disasm` / `--disasm`)
- [x] Line tracing (`pymini run --trace`)
- [x] Lightweight debugger (breakpoints, step, continue, locals)
- [x] CLI subcommands: `run`, `eval`, `disasm`, `repl`, `version`, `debug`

## Milestone 5: Performance + Targets

- [ ] Benchmark evaluator and VM against CPython (scaffolding present).
- [ ] Add `llvmlite` JIT experiments for hot loops.
- [ ] Add a WebAssembly backend for a small numeric subset.

## Version history

| Version | Highlights |
|---------|------------|
| 0.1.x   | Parser + tree-walking evaluator foundation |
| 0.2.0   | Bytecode VM, try/with, *args, comprehensions, f-strings |
| 0.3.0   | lambda, assert, kwargs, generators, richer builtins/stdlib, VM ops, debugger |
