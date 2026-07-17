# PyMini Architecture

```mermaid
flowchart LR
    subgraph Frontend
        Source["Source text"]
        Lexer["Lexer"]
        RD["Recursive descent parser"]
        ASTFacade["ast parser facade"]
        AST["ast.Module"]
    end

    subgraph Analysis
        Opt["Optimizer"]
        Symbols["Future symbol table"]
    end

    subgraph Execution
        Eval["Tree evaluator"]
        Compile["Compiler"]
        BC["Bytecode"]
        VM["VM"]
    end

    subgraph Runtime
        Env["Lexical environments"]
        Obj["Runtime objects"]
        Std["Standard library"]
        Mem["GC simulator"]
    end

    subgraph Tooling
        Repl["REPL"]
        Bench["Benchmarks"]
        Debug["Debugger + line trace"]
        Targets["JIT + WASM roadmap"]
    end

    Source --> Lexer --> RD --> AST
    Source --> ASTFacade --> AST
    AST --> Opt --> Eval
    Opt --> Symbols --> Compile --> BC --> VM
    Eval --> Env
    Eval --> Obj
    VM --> Env
    VM --> Obj
    Obj --> Std
    Obj --> Mem
    Repl --> Source
    Bench --> Eval
    Bench --> VM
    Debug --> Eval
    Targets --> BC
```

The milestone implementation uses `ast.Module` as the interchange format. That
lets the `ast` parser and the hand-written parser share the evaluator, optimizer,
and compiler pipeline.

### Runtime highlights (0.3)

- **Evaluator**: lambda, assert, kwargs/`**kwargs`, keyword-only params, basic
  `yield` generators (`MiniGenerator` + generator-style statement evaluation).
- **Builtins**: enumerate, zip, map, filter, sorted, reversed, sum, min, max,
  any, all, abs, round, isinstance, type, hasattr/getattr/setattr.
- **Stdlib**: expanded `math`, `random`, `json`, and `pymini.version`.
- **VM**: MOD/POW, unary ops, BUILD_SET, GET_ITER/FOR_ITER, JUMP_IF_TRUE.
- **Debugger**: breakpoints, step/continue, locals inspection; `--trace` mode.

