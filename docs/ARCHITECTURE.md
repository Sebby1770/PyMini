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
        Debug["Debugger roadmap"]
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
    Debug --> VM
    Targets --> BC
```

The milestone implementation uses `ast.Module` as the interchange format. That
lets the `ast` parser and the hand-written parser share the evaluator, optimizer,
and future compiler pipeline.

