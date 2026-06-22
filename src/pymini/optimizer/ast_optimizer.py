"""AST optimizer: constant folding and simple dead code elimination."""

from __future__ import annotations

import ast
from typing import Any, cast


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
            if node.orelse:
                replacement = ast.If(
                    test=ast.Constant(value=True),
                    body=node.orelse,
                    orelse=[],
                )
                return ast.copy_location(replacement, node)
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
    def _fold_binary(op: ast.operator, left: object, right: object) -> Any:
        lhs = cast(Any, left)
        rhs = cast(Any, right)
        try:
            if isinstance(op, ast.Add):
                return lhs + rhs
            if isinstance(op, ast.Sub):
                return lhs - rhs
            if isinstance(op, ast.Mult):
                return lhs * rhs
            if isinstance(op, ast.Div):
                return lhs / rhs
            if isinstance(op, ast.FloorDiv):
                return lhs // rhs
            if isinstance(op, ast.Mod):
                return lhs % rhs
            if isinstance(op, ast.Pow):
                return lhs**rhs
        except Exception:
            return _NO_FOLD
        return _NO_FOLD

    @staticmethod
    def _fold_unary(op: ast.unaryop, value: object) -> Any:
        operand = cast(Any, value)
        try:
            if isinstance(op, ast.UAdd):
                return +operand
            if isinstance(op, ast.USub):
                return -operand
            if isinstance(op, ast.Not):
                return not operand
        except Exception:
            return _NO_FOLD
        return _NO_FOLD


class _NoFold:
    pass


_NO_FOLD = _NoFold()
