"""Bytecode model, disassembler, and AST-to-bytecode compiler for PyMini."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum, auto

from pymini.optimizer.ast_optimizer import optimize_module
from pymini.parser import ParserMode, parse_source
from pymini.runtime.errors import PyMiniNotImplementedError, PyMiniSyntaxError


class OpCode(Enum):
    """Minimal educational instruction set."""

    LOAD_CONST = auto()
    LOAD_NAME = auto()
    STORE_NAME = auto()
    POP_TOP = auto()
    BINARY_ADD = auto()
    BINARY_SUB = auto()
    BINARY_MUL = auto()
    BINARY_DIV = auto()
    COMPARE_OP = auto()
    JUMP = auto()
    JUMP_IF_FALSE = auto()
    RETURN_VALUE = auto()
    CALL = auto()
    MAKE_FUNCTION = auto()
    BUILD_LIST = auto()
    BUILD_TUPLE = auto()
    BUILD_DICT = auto()


# Compare operator names used as COMPARE_OP operands.
COMPARE_OPS = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
}

BINARY_OPS = {
    ast.Add: OpCode.BINARY_ADD,
    ast.Sub: OpCode.BINARY_SUB,
    ast.Mult: OpCode.BINARY_MUL,
    ast.Div: OpCode.BINARY_DIV,
}


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: OpCode
    operand: object = None
    line: int | None = None


@dataclass(slots=True)
class Chunk:
    """A sequence of instructions with a constants table."""

    name: str = "<module>"
    instructions: list[Instruction] = field(default_factory=list)
    constants: list[object] = field(default_factory=list)
    arg_names: tuple[str, ...] = ()
    vararg: str | None = None

    def add_constant(self, value: object) -> int:
        for index, existing in enumerate(self.constants):
            if type(existing) is type(value) and existing == value:
                return index
        self.constants.append(value)
        return len(self.constants) - 1

    def emit(self, opcode: OpCode, operand: object = None, line: int | None = None) -> int:
        self.instructions.append(Instruction(opcode, operand, line))
        return len(self.instructions) - 1

    def patch_jump(self, offset: int, target: int | None = None) -> None:
        instr = self.instructions[offset]
        dest = len(self.instructions) if target is None else target
        self.instructions[offset] = Instruction(instr.opcode, dest, instr.line)


def disassemble(chunk: Chunk) -> str:
    """Return a human-readable disassembly of *chunk*."""

    lines: list[str] = [f"-- disassembly of {chunk.name!r} --"]
    if chunk.arg_names or chunk.vararg:
        params = list(chunk.arg_names)
        if chunk.vararg:
            params.append(f"*{chunk.vararg}")
        lines.append(f"  args: ({', '.join(params)})")
    if chunk.constants:
        const_repr = ", ".join(repr(c) if not isinstance(c, Chunk) else f"<chunk {c.name!r}>"
                               for c in chunk.constants)
        lines.append(f"  constants: [{const_repr}]")
    width = max(len(str(len(chunk.instructions) - 1)), 1) if chunk.instructions else 1
    for index, instr in enumerate(chunk.instructions):
        line_col = f"L{instr.line}" if instr.line is not None else "   "
        op_name = instr.opcode.name
        if instr.opcode is OpCode.LOAD_CONST:
            const = chunk.constants[instr.operand] if isinstance(instr.operand, int) else instr.operand
            if isinstance(const, Chunk):
                detail = f"{instr.operand} ({const.name!r} code)"
            else:
                detail = f"{instr.operand} ({const!r})"
        elif instr.opcode in (OpCode.JUMP, OpCode.JUMP_IF_FALSE):
            detail = f"-> {instr.operand}"
        elif instr.operand is None:
            detail = ""
        else:
            detail = repr(instr.operand) if not isinstance(instr.operand, str) else instr.operand
            if instr.opcode is OpCode.COMPARE_OP:
                detail = str(instr.operand)
            elif instr.opcode is OpCode.CALL:
                detail = str(instr.operand)
        operand_text = f" {detail}" if detail != "" else ""
        lines.append(f"{index:>{width}}  {line_col:>4}  {op_name}{operand_text}")
    # Nested function chunks
    for const in chunk.constants:
        if isinstance(const, Chunk):
            lines.append("")
            lines.append(disassemble(const))
    return "\n".join(lines)


class Compiler:
    """Compile a restricted AST subset into a :class:`Chunk`."""

    def __init__(self, name: str = "<module>") -> None:
        self.chunk = Chunk(name=name)

    def compile_module(self, module: ast.Module) -> Chunk:
        body = module.body
        for index, statement in enumerate(body):
            is_last = index == len(body) - 1
            if is_last and isinstance(statement, ast.Expr):
                self.compile_expr(statement.value)
                self.emit(OpCode.RETURN_VALUE, line=getattr(statement, "lineno", None))
                return self.chunk
            self.compile_stmt(statement)
        self.emit_const(None)
        self.emit(OpCode.RETURN_VALUE)
        return self.chunk

    def compile_function(self, node: ast.FunctionDef) -> Chunk:
        nested = Compiler(name=node.name)
        nested.chunk.arg_names = tuple(arg.arg for arg in node.args.args)
        nested.chunk.vararg = node.args.vararg.arg if node.args.vararg else None
        for statement in node.body:
            nested.compile_stmt(statement)
        if (
            not nested.chunk.instructions
            or nested.chunk.instructions[-1].opcode is not OpCode.RETURN_VALUE
        ):
            nested.emit_const(None)
            nested.emit(OpCode.RETURN_VALUE)
        return nested.chunk

    def compile_stmt(self, node: ast.stmt) -> None:
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise PyMiniNotImplementedError(
                    "bytecode compiler only supports simple name assignment"
                )
            self.compile_expr(node.value)
            self.emit(OpCode.STORE_NAME, node.targets[0].id, line=line)
            return
        if isinstance(node, ast.Expr):
            self.compile_expr(node.value)
            self.emit(OpCode.POP_TOP, line=line)
            return
        if isinstance(node, ast.Return):
            if node.value is None:
                self.emit_const(None, line=line)
            else:
                self.compile_expr(node.value)
            self.emit(OpCode.RETURN_VALUE, line=line)
            return
        if isinstance(node, ast.Pass):
            return
        if isinstance(node, ast.If):
            self.compile_expr(node.test)
            jump_else = self.emit(OpCode.JUMP_IF_FALSE, 0, line=line)
            for stmt in node.body:
                self.compile_stmt(stmt)
            if node.orelse:
                jump_end = self.emit(OpCode.JUMP, 0, line=line)
                self.chunk.patch_jump(jump_else)
                for stmt in node.orelse:
                    self.compile_stmt(stmt)
                self.chunk.patch_jump(jump_end)
            else:
                self.chunk.patch_jump(jump_else)
            return
        if isinstance(node, ast.While):
            loop_start = len(self.chunk.instructions)
            self.compile_expr(node.test)
            jump_exit = self.emit(OpCode.JUMP_IF_FALSE, 0, line=line)
            for stmt in node.body:
                self.compile_stmt(stmt)
            self.emit(OpCode.JUMP, loop_start, line=line)
            self.chunk.patch_jump(jump_exit)
            return
        if isinstance(node, ast.FunctionDef):
            if node.args.kwonlyargs or node.args.kwarg or node.args.posonlyargs:
                raise PyMiniNotImplementedError(
                    "bytecode compiler supports only positional/*args parameters"
                )
            if node.args.defaults:
                raise PyMiniNotImplementedError(
                    "bytecode compiler does not support default arguments yet"
                )
            code = self.compile_function(node)
            index = self.chunk.add_constant(code)
            self.emit(OpCode.LOAD_CONST, index, line=line)
            self.emit(OpCode.MAKE_FUNCTION, line=line)
            self.emit(OpCode.STORE_NAME, node.name, line=line)
            return
        raise PyMiniNotImplementedError(
            f"bytecode compiler does not support {node.__class__.__name__} yet"
        )

    def compile_expr(self, node: ast.expr) -> None:
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Constant):
            self.emit_const(node.value, line=line)
            return
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                raise PyMiniNotImplementedError("name store/delete not valid as expression")
            self.emit(OpCode.LOAD_NAME, node.id, line=line)
            return
        if isinstance(node, ast.BinOp):
            opcode = BINARY_OPS.get(type(node.op))
            if opcode is None:
                raise PyMiniNotImplementedError(
                    f"bytecode compiler does not support binary {node.op.__class__.__name__}"
                )
            self.compile_expr(node.left)
            self.compile_expr(node.right)
            self.emit(opcode, line=line)
            return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            self.emit_const(0, line=line)
            self.compile_expr(node.operand)
            self.emit(OpCode.BINARY_SUB, line=line)
            return
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise PyMiniNotImplementedError(
                    "bytecode compiler supports only single comparisons"
                )
            op_name = COMPARE_OPS.get(type(node.ops[0]))
            if op_name is None:
                raise PyMiniNotImplementedError(
                    f"bytecode compiler does not support {node.ops[0].__class__.__name__}"
                )
            self.compile_expr(node.left)
            self.compile_expr(node.comparators[0])
            self.emit(OpCode.COMPARE_OP, op_name, line=line)
            return
        if isinstance(node, ast.Call):
            if node.keywords:
                raise PyMiniNotImplementedError("bytecode CALL does not support keywords")
            self.compile_expr(node.func)
            for arg in node.args:
                self.compile_expr(arg)
            self.emit(OpCode.CALL, len(node.args), line=line)
            return
        if isinstance(node, ast.List):
            for elt in node.elts:
                self.compile_expr(elt)
            self.emit(OpCode.BUILD_LIST, len(node.elts), line=line)
            return
        if isinstance(node, ast.Tuple):
            for elt in node.elts:
                self.compile_expr(elt)
            self.emit(OpCode.BUILD_TUPLE, len(node.elts), line=line)
            return
        if isinstance(node, ast.Dict):
            count = 0
            for key_node, value_node in zip(node.keys, node.values, strict=True):
                if key_node is None:
                    raise PyMiniNotImplementedError("dict unpacking not supported in compiler")
                self.compile_expr(key_node)
                self.compile_expr(value_node)
                count += 1
            self.emit(OpCode.BUILD_DICT, count, line=line)
            return
        if isinstance(node, ast.IfExp):
            self.compile_expr(node.test)
            jump_else = self.emit(OpCode.JUMP_IF_FALSE, 0, line=line)
            self.compile_expr(node.body)
            jump_end = self.emit(OpCode.JUMP, 0, line=line)
            self.chunk.patch_jump(jump_else)
            self.compile_expr(node.orelse)
            self.chunk.patch_jump(jump_end)
            return
        raise PyMiniNotImplementedError(
            f"bytecode compiler does not support expression {node.__class__.__name__} yet"
        )

    def emit(self, opcode: OpCode, operand: object = None, line: int | None = None) -> int:
        return self.chunk.emit(opcode, operand, line)

    def emit_const(self, value: object, line: int | None = None) -> int:
        index = self.chunk.add_constant(value)
        return self.emit(OpCode.LOAD_CONST, index, line=line)


def compile_source(
    source: str,
    *,
    mode: ParserMode | str = ParserMode.AST,
    optimize: bool = True,
    name: str = "<module>",
) -> Chunk:
    """Parse *source* and compile it to a bytecode chunk."""

    try:
        module = parse_source(source, mode=mode)
    except PyMiniSyntaxError:
        raise
    if optimize:
        module = optimize_module(module)
    return Compiler(name=name).compile_module(module)


def disassemble_source(
    source: str,
    *,
    mode: ParserMode | str = ParserMode.AST,
    optimize: bool = True,
) -> str:
    """Compile *source* and return its disassembly text."""

    chunk = compile_source(source, mode=mode, optimize=optimize)
    return disassemble(chunk)
