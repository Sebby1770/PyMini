"""AST optimizer: constant folding and simple dead code elimination."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable


def optimize_module(module: ast.Module) -> ast.Module:
    optimizer = AstOptimizer()
    optimized = optimizer.visit(module)
    assert isinstance(optimized, ast.Module)
    return ast.fix_missing_locations(optimized)


class AstOptimizer(ast.NodeTransformer):
    """Small, conservative optimizer for the milestone interpreter."""

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._prune_dead_statements([self.visit(stmt) for stmt in node.body])
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.args = self.visit(node.args)
        node.body = self._prune_dead_statements([self.visit(stmt) for stmt in node.body])
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.returns = None if node.returns is None else self.visit(node.returns)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.bases = [self.visit(base) for base in node.bases]
        node.keywords = [self.visit(keyword) for keyword in node.keywords]
        node.body = self._prune_dead_statements([self.visit(stmt) for stmt in node.body])
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        return node

    def visit_If(self, node: ast.If) -> ast.stmt | list[ast.stmt]:
        node.test = self.visit(node.test)
        node.body = self._prune_dead_statements([self.visit(stmt) for stmt in node.body])
        node.orelse = self._prune_dead_statements([self.visit(stmt) for stmt in node.orelse])
        if isinstance(node.test, ast.Constant):
            if bool(node.test.value):
                return node.body
            return node.orelse or ast.copy_location(ast.Pass(), node)
        return node

    def visit_While(self, node: ast.While) -> ast.stmt:
        node.test = self.visit(node.test)
        node.body = self._prune_dead_statements([self.visit(stmt) for stmt in node.body])
        node.orelse = self._prune_dead_statements([self.visit(stmt) for stmt in node.orelse])
        if isinstance(node.test, ast.Constant) and not bool(node.test.value):
            return ast.copy_location(ast.Pass(), node)
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        if isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant):
            result = self._fold_binary(node.op, node.left.value, node.right.value)
            if result is not _NO_FOLD:
                return ast.copy_location(ast.Constant(result), node)
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.expr:
        node.operand = self.visit(node.operand)
        if isinstance(node.operand, ast.Constant):
            result = self._fold_unary(node.op, node.operand.value)
            if result is not _NO_FOLD:
                return ast.copy_location(ast.Constant(result), node)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.expr:
        node.values = [self.visit(value) for value in node.values]
        if all(isinstance(value, ast.Constant) for value in node.values):
            values = [value.value for value in node.values if isinstance(value, ast.Constant)]
            if isinstance(node.op, ast.And):
                result = values[-1]
                for value in values:
                    result = value
                    if not value:
                        break
                return ast.copy_location(ast.Constant(result), node)
            if isinstance(node.op, ast.Or):
                result = values[-1]
                for value in values:
                    result = value
                    if value:
                        break
                return ast.copy_location(ast.Constant(result), node)
        return node

    @staticmethod
    def _prune_dead_statements(statements: list[ast.AST | None]) -> list[ast.stmt]:
        result: list[ast.stmt] = []
        terminated = False
        for statement in statements:
            if statement is None or terminated:
                continue
            if isinstance(statement, list):
                result.extend(item for item in statement if isinstance(item, ast.stmt))
                continue
            assert isinstance(statement, ast.stmt)
            result.append(statement)
            terminated = isinstance(statement, ast.Return | ast.Break | ast.Continue)
        return result

    @staticmethod
    def _fold_binary(op: ast.operator, left: object, right: object) -> object:
        funcs: dict[type[ast.operator], Callable[[object, object], object]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        for op_type, func in funcs.items():
            if isinstance(op, op_type):
                try:
                    return func(left, right)
                except Exception:
                    return _NO_FOLD
        return _NO_FOLD

    @staticmethod
    def _fold_unary(op: ast.unaryop, value: object) -> object:
        funcs: dict[type[ast.unaryop], Callable[[object], object]] = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Not: operator.not_,
        }
        for op_type, func in funcs.items():
            if isinstance(op, op_type):
                try:
                    return func(value)
                except Exception:
                    return _NO_FOLD
        return _NO_FOLD


class _NoFold:
    pass


_NO_FOLD = _NoFold()
