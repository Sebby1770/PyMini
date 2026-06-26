"""AST-to-bytecode compiler for the supported PyMini VM subset."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import NoReturn

from pymini.compiler.bytecode import Chunk, CompareOp, OpCode
from pymini.runtime.errors import PyMiniNotImplementedError, location_from_node


@dataclass(slots=True)
class _LoopContext:
    continue_target: int
    cleanup_items: int = 0
    break_jumps: list[int] = field(default_factory=list)


class Compiler:
    """Compile a deliberately explicit subset of PyMini into bytecode."""

    def __init__(self, *, filename: str = "<string>") -> None:
        self.filename = filename
        self.chunk = Chunk()
        self._loops: list[_LoopContext] = []

    def compile(self, tree: ast.Module) -> Chunk:
        """Compile a module, preserving its final expression as the result."""

        self.chunk = Chunk(name="<module>")
        self._loops = []
        leaves_result = False
        for index, statement in enumerate(tree.body):
            leaves_result = self._compile_stmt(
                statement,
                keep_result=index == len(tree.body) - 1,
            )
        if not leaves_result:
            self._emit_constant(None)
        self.chunk.emit(OpCode.RETURN_VALUE)
        return self.chunk

    def _compile_stmt(self, node: ast.stmt, *, keep_result: bool = False) -> bool:
        if isinstance(node, ast.Expr):
            self._compile_expr(node.value)
            if not keep_result:
                self.chunk.emit(OpCode.POP_TOP, line=node.lineno)
            return keep_result

        if isinstance(node, ast.Assign):
            self._compile_expr(node.value)
            for target in node.targets[:-1]:
                self.chunk.emit(OpCode.DUP_TOP, line=node.lineno)
                self._compile_store(target)
            self._compile_store(node.targets[-1])
            return False

        if isinstance(node, ast.AugAssign):
            self._compile_load(node.target)
            self._compile_expr(node.value)
            self._emit_binop(node.op, line=node.lineno)
            self._compile_store(node.target)
            return False

        if isinstance(node, ast.If):
            self._compile_if(node)
            return False

        if isinstance(node, ast.While):
            self._compile_while(node)
            return False

        if isinstance(node, ast.For):
            self._compile_for(node)
            return False

        if isinstance(node, ast.Break):
            if not self._loops:
                self._unsupported(node, "break outside a VM loop")
            loop = self._loops[-1]
            for _ in range(loop.cleanup_items):
                self.chunk.emit(OpCode.POP_TOP, line=node.lineno)
            loop.break_jumps.append(self.chunk.emit(OpCode.JUMP, line=node.lineno))
            return False

        if isinstance(node, ast.Continue):
            if not self._loops:
                self._unsupported(node, "continue outside a VM loop")
            self.chunk.emit(OpCode.JUMP, self._loops[-1].continue_target, line=node.lineno)
            return False

        if isinstance(node, ast.Pass):
            return False

        self._unsupported(node, f"{type(node).__name__} statements")

    def _compile_if(self, node: ast.If) -> None:
        self._compile_expr(node.test)
        false_jump = self.chunk.emit(OpCode.JUMP_IF_FALSE, line=node.lineno)
        self._compile_block(node.body)
        end_jump = self.chunk.emit(OpCode.JUMP, line=node.lineno)
        self.chunk.patch_jump(false_jump, len(self.chunk.instructions))
        self._compile_block(node.orelse)
        self.chunk.patch_jump(end_jump, len(self.chunk.instructions))

    def _compile_while(self, node: ast.While) -> None:
        loop_start = len(self.chunk.instructions)
        self._compile_expr(node.test)
        exit_jump = self.chunk.emit(OpCode.JUMP_IF_FALSE, line=node.lineno)
        context = _LoopContext(continue_target=loop_start)
        self._loops.append(context)
        self._compile_block(node.body)
        self._loops.pop()
        self.chunk.emit(OpCode.JUMP, loop_start, line=node.lineno)
        self.chunk.patch_jump(exit_jump, len(self.chunk.instructions))
        self._compile_block(node.orelse)
        loop_end = len(self.chunk.instructions)
        for jump in context.break_jumps:
            self.chunk.patch_jump(jump, loop_end)

    def _compile_for(self, node: ast.For) -> None:
        self._compile_expr(node.iter)
        self.chunk.emit(OpCode.GET_ITER, line=node.lineno)
        loop_start = len(self.chunk.instructions)
        exit_jump = self.chunk.emit(OpCode.FOR_ITER, line=node.lineno)
        self._compile_store(node.target)
        context = _LoopContext(continue_target=loop_start, cleanup_items=1)
        self._loops.append(context)
        self._compile_block(node.body)
        self._loops.pop()
        self.chunk.emit(OpCode.JUMP, loop_start, line=node.lineno)
        self.chunk.patch_jump(exit_jump, len(self.chunk.instructions))
        self._compile_block(node.orelse)
        loop_end = len(self.chunk.instructions)
        for jump in context.break_jumps:
            self.chunk.patch_jump(jump, loop_end)

    def _compile_block(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self._compile_stmt(statement)

    def _compile_expr(self, node: ast.expr) -> None:
        if isinstance(node, ast.Constant):
            self._emit_constant(node.value, line=node.lineno)
            return

        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            self._compile_load(node)
            return

        if isinstance(node, ast.BinOp):
            self._compile_expr(node.left)
            self._compile_expr(node.right)
            self._emit_binop(node.op, line=node.lineno)
            return

        if isinstance(node, ast.UnaryOp):
            self._compile_expr(node.operand)
            if isinstance(node.op, ast.UAdd):
                opcode = OpCode.UNARY_POS
            elif isinstance(node.op, ast.USub):
                opcode = OpCode.UNARY_NEG
            elif isinstance(node.op, ast.Not):
                opcode = OpCode.UNARY_NOT
            else:
                self._unsupported(node, f"{type(node.op).__name__} unary operators")
            self.chunk.emit(opcode, line=node.lineno)
            return

        if isinstance(node, ast.BoolOp):
            self._compile_bool_op(node)
            return

        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                self._unsupported(node, "chained comparisons")
            self._compile_expr(node.left)
            self._compile_expr(node.comparators[0])
            self._emit_compare(node.ops[0], line=node.lineno)
            return

        if isinstance(node, ast.IfExp):
            self._compile_expr(node.test)
            false_jump = self.chunk.emit(OpCode.JUMP_IF_FALSE, line=node.lineno)
            self._compile_expr(node.body)
            end_jump = self.chunk.emit(OpCode.JUMP, line=node.lineno)
            self.chunk.patch_jump(false_jump, len(self.chunk.instructions))
            self._compile_expr(node.orelse)
            self.chunk.patch_jump(end_jump, len(self.chunk.instructions))
            return

        if isinstance(node, ast.List):
            for element in node.elts:
                self._compile_expr(element)
            self.chunk.emit(OpCode.BUILD_LIST, len(node.elts), line=node.lineno)
            return

        if isinstance(node, ast.Tuple):
            for element in node.elts:
                self._compile_expr(element)
            self.chunk.emit(OpCode.BUILD_TUPLE, len(node.elts), line=node.lineno)
            return

        if isinstance(node, ast.Dict):
            if any(key is None for key in node.keys):
                self._unsupported(node, "dictionary unpacking")
            for key, value in zip(node.keys, node.values, strict=True):
                assert key is not None
                self._compile_expr(key)
                self._compile_expr(value)
            self.chunk.emit(OpCode.BUILD_MAP, len(node.values), line=node.lineno)
            return

        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                self._unsupported(node, "slice expressions")
            self._compile_expr(node.value)
            self._compile_expr(node.slice)
            self.chunk.emit(OpCode.BINARY_SUBSCR, line=node.lineno)
            return

        if isinstance(node, ast.Call):
            if node.keywords:
                self._unsupported(node, "keyword arguments")
            self._compile_expr(node.func)
            for argument in node.args:
                self._compile_expr(argument)
            self.chunk.emit(OpCode.CALL_FUNCTION, len(node.args), line=node.lineno)
            return

        self._unsupported(node, f"{type(node).__name__} expressions")

    def _compile_bool_op(self, node: ast.BoolOp) -> None:
        jump_opcode = (
            OpCode.JUMP_IF_FALSE if isinstance(node.op, ast.And) else OpCode.JUMP_IF_TRUE
        )
        jumps: list[int] = []
        for value in node.values[:-1]:
            self._compile_expr(value)
            self.chunk.emit(OpCode.DUP_TOP, line=node.lineno)
            jumps.append(self.chunk.emit(jump_opcode, line=node.lineno))
            self.chunk.emit(OpCode.POP_TOP, line=node.lineno)
        self._compile_expr(node.values[-1])
        end = len(self.chunk.instructions)
        for jump in jumps:
            self.chunk.patch_jump(jump, end)

    def _compile_load(self, node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            self.chunk.emit(OpCode.LOAD_NAME, node.id, line=node.lineno)
            return
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                self._unsupported(node, "slice load targets")
            self._compile_expr(node.value)
            self._compile_expr(node.slice)
            self.chunk.emit(OpCode.BINARY_SUBSCR, line=node.lineno)
            return
        self._unsupported(node, "complex load targets")

    def _compile_store(self, node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            self.chunk.emit(OpCode.STORE_NAME, node.id, line=node.lineno)
            return
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                self._unsupported(node, "slice assignment targets")
            self._compile_expr(node.value)
            self._compile_expr(node.slice)
            self.chunk.emit(OpCode.STORE_SUBSCR, line=node.lineno)
            return
        if isinstance(node, ast.Tuple | ast.List):
            self.chunk.emit(OpCode.UNPACK_SEQUENCE, len(node.elts), line=node.lineno)
            for element in node.elts:
                self._compile_store(element)
            return
        self._unsupported(node, "complex assignment targets")

    def _emit_constant(self, value: object, *, line: int | None = None) -> None:
        self.chunk.emit(OpCode.LOAD_CONST, self.chunk.add_constant(value), line=line)

    def _emit_binop(self, op: ast.operator, *, line: int | None = None) -> None:
        mapping = {
            ast.Add: OpCode.BINARY_ADD,
            ast.Sub: OpCode.BINARY_SUB,
            ast.Mult: OpCode.BINARY_MUL,
            ast.Div: OpCode.BINARY_DIV,
            ast.FloorDiv: OpCode.BINARY_FLOOR_DIV,
            ast.Mod: OpCode.BINARY_MOD,
            ast.Pow: OpCode.BINARY_POW,
        }
        opcode = mapping.get(type(op))
        if opcode is None:
            self._unsupported(op, f"{type(op).__name__} binary operators")
        self.chunk.emit(opcode, line=line)

    def _emit_compare(self, op: ast.cmpop, *, line: int | None = None) -> None:
        mapping = {
            ast.Eq: CompareOp.EQ,
            ast.NotEq: CompareOp.NOT_EQ,
            ast.Lt: CompareOp.LT,
            ast.LtE: CompareOp.LT_E,
            ast.Gt: CompareOp.GT,
            ast.GtE: CompareOp.GT_E,
            ast.Is: CompareOp.IS,
            ast.IsNot: CompareOp.IS_NOT,
            ast.In: CompareOp.IN,
            ast.NotIn: CompareOp.NOT_IN,
        }
        comparison = mapping.get(type(op))
        if comparison is None:
            self._unsupported(op, f"{type(op).__name__} comparisons")
        self.chunk.emit(OpCode.COMPARE_OP, comparison, line=line)

    def _unsupported(self, node: object, feature: str) -> NoReturn:
        raise PyMiniNotImplementedError(
            f"the VM does not support {feature} yet",
            location=location_from_node(node, filename=self.filename),
        )
