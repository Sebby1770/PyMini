from __future__ import annotations

import ast

from pymini.parser import ParserMode, parse_source


def test_ast_parser_returns_module() -> None:
    module = parse_source("x = 1 + 2", mode=ParserMode.AST)
    assert isinstance(module, ast.Module)
    assert isinstance(module.body[0], ast.Assign)


def test_handwritten_parser_parses_assignment_and_precedence() -> None:
    module = parse_source("x = 1 + 2 * 3", mode=ParserMode.HANDWRITTEN)
    assign = module.body[0]
    assert isinstance(assign, ast.Assign)
    assert ast.dump(assign.value) == ast.dump(
        ast.BinOp(
            left=ast.Constant(1),
            op=ast.Add(),
            right=ast.BinOp(left=ast.Constant(2), op=ast.Mult(), right=ast.Constant(3)),
        )
    )


def test_handwritten_parser_parses_blocks() -> None:
    source = """
def add(x, y):
    if x > y:
        return x
    else:
        return y
"""
    module = parse_source(source, mode="handwritten")
    assert isinstance(module.body[0], ast.FunctionDef)
    assert isinstance(module.body[0].body[0], ast.If)

