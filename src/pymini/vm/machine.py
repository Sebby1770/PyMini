"""Stack-based virtual machine for PyMini bytecode."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass, field

from pymini.compiler.bytecode import Chunk, Instruction, OpCode
from pymini.runtime.errors import (
    PyMiniNameError,
    PyMiniRuntimeError,
    PyMiniTypeError,
)


COMPARE_FUNCS: dict[str, Callable[[object, object], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "is": operator.is_,
    "is not": operator.is_not,
    "in": lambda item, container: item in container,  # type: ignore[operator]
    "not in": lambda item, container: item not in container,  # type: ignore[operator]
}


@dataclass(slots=True)
class CodeFunction:
    """A function whose body is a compiled bytecode chunk."""

    code: Chunk
    globals: dict[str, object]
    defaults: tuple[object, ...] = ()

    @property
    def name(self) -> str:
        return self.code.name

    def __repr__(self) -> str:
        return f"<code fn {self.name}>"


@dataclass(slots=True)
class Frame:
    chunk: Chunk
    globals: dict[str, object]
    locals: dict[str, object] = field(default_factory=dict)
    stack: list[object] = field(default_factory=list)
    ip: int = 0


class VirtualMachine:
    """Execute PyMini bytecode chunks on a value stack."""

    def __init__(self, *, builtins: dict[str, object] | None = None) -> None:
        self.builtins: dict[str, object] = builtins or {
            "print": print,
            "len": len,
            "range": range,
            "list": list,
            "dict": dict,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "Exception": Exception,
        }
        self.frames: list[Frame] = []

    def run(self, chunk: Chunk, *, globals_dict: dict[str, object] | None = None) -> object:
        env = globals_dict if globals_dict is not None else {}
        # Seed builtins into the module namespace for LOAD_NAME.
        for name, value in self.builtins.items():
            env.setdefault(name, value)
        frame = Frame(chunk=chunk, globals=env, locals=env)
        self.frames.append(frame)
        try:
            return self._eval_frame(frame)
        finally:
            self.frames.clear()

    def _eval_frame(self, frame: Frame) -> object:
        while frame.ip < len(frame.chunk.instructions):
            instr = frame.chunk.instructions[frame.ip]
            frame.ip += 1
            result = self._step(frame, instr)
            if result is not _CONTINUE:
                return result
        return None

    def _step(self, frame: Frame, instr: Instruction) -> object:
        op = instr.opcode
        stack = frame.stack

        if op is OpCode.LOAD_CONST:
            assert isinstance(instr.operand, int)
            stack.append(frame.chunk.constants[instr.operand])
            return _CONTINUE

        if op is OpCode.LOAD_NAME:
            name = str(instr.operand)
            if name in frame.locals:
                stack.append(frame.locals[name])
            elif name in frame.globals:
                stack.append(frame.globals[name])
            elif name in self.builtins:
                stack.append(self.builtins[name])
            else:
                raise PyMiniNameError(f"name {name!r} is not defined")
            return _CONTINUE

        if op is OpCode.STORE_NAME:
            name = str(instr.operand)
            frame.locals[name] = stack.pop()
            return _CONTINUE

        if op is OpCode.POP_TOP:
            stack.pop()
            return _CONTINUE

        if op is OpCode.BINARY_ADD:
            right, left = stack.pop(), stack.pop()
            stack.append(left + right)  # type: ignore[operator]
            return _CONTINUE

        if op is OpCode.BINARY_SUB:
            right, left = stack.pop(), stack.pop()
            stack.append(left - right)  # type: ignore[operator]
            return _CONTINUE

        if op is OpCode.BINARY_MUL:
            right, left = stack.pop(), stack.pop()
            stack.append(left * right)  # type: ignore[operator]
            return _CONTINUE

        if op is OpCode.BINARY_DIV:
            right, left = stack.pop(), stack.pop()
            stack.append(left / right)  # type: ignore[operator]
            return _CONTINUE

        if op is OpCode.COMPARE_OP:
            right, left = stack.pop(), stack.pop()
            func = COMPARE_FUNCS.get(str(instr.operand))
            if func is None:
                raise PyMiniRuntimeError(f"unknown compare op {instr.operand!r}")
            stack.append(func(left, right))
            return _CONTINUE

        if op is OpCode.JUMP:
            assert isinstance(instr.operand, int)
            frame.ip = instr.operand
            return _CONTINUE

        if op is OpCode.JUMP_IF_FALSE:
            assert isinstance(instr.operand, int)
            value = stack.pop()
            if not value:
                frame.ip = instr.operand
            return _CONTINUE

        if op is OpCode.RETURN_VALUE:
            return stack.pop() if stack else None

        if op is OpCode.MAKE_FUNCTION:
            code = stack.pop()
            if not isinstance(code, Chunk):
                raise PyMiniTypeError("MAKE_FUNCTION expects a code chunk")
            stack.append(CodeFunction(code=code, globals=frame.globals))
            return _CONTINUE

        if op is OpCode.CALL:
            assert isinstance(instr.operand, int)
            argc = instr.operand
            args = [stack.pop() for _ in range(argc)][::-1]
            callee = stack.pop()
            stack.append(self._call(callee, args))
            return _CONTINUE

        if op is OpCode.BUILD_LIST:
            assert isinstance(instr.operand, int)
            count = instr.operand
            items = [stack.pop() for _ in range(count)][::-1]
            stack.append(items)
            return _CONTINUE

        if op is OpCode.BUILD_TUPLE:
            assert isinstance(instr.operand, int)
            count = instr.operand
            items = [stack.pop() for _ in range(count)][::-1]
            stack.append(tuple(items))
            return _CONTINUE

        if op is OpCode.BUILD_DICT:
            assert isinstance(instr.operand, int)
            count = instr.operand
            mapping: dict[object, object] = {}
            pairs = [stack.pop() for _ in range(count * 2)][::-1]
            for i in range(0, len(pairs), 2):
                mapping[pairs[i]] = pairs[i + 1]
            stack.append(mapping)
            return _CONTINUE

        raise PyMiniRuntimeError(f"unknown opcode {op}")

    def _call(self, callee: object, args: list[object]) -> object:
        if isinstance(callee, CodeFunction):
            return self._call_code_function(callee, args)
        if callable(callee):
            return callee(*args)
        raise PyMiniTypeError(f"object {callee!r} is not callable")

    def _call_code_function(self, fn: CodeFunction, args: list[object]) -> object:
        code = fn.code
        params = list(code.arg_names)
        if code.vararg is None:
            if len(args) != len(params):
                raise PyMiniTypeError(
                    f"{fn.name}() expected {len(params)} arguments, got {len(args)}"
                )
            local_map = dict(zip(params, args, strict=True))
        else:
            if len(args) < len(params):
                raise PyMiniTypeError(
                    f"{fn.name}() expected at least {len(params)} arguments, got {len(args)}"
                )
            local_map = dict(zip(params, args[: len(params)], strict=True))
            local_map[code.vararg] = tuple(args[len(params) :])

        child = Frame(chunk=code, globals=fn.globals, locals=local_map)
        self.frames.append(child)
        try:
            return self._eval_frame(child)
        finally:
            self.frames.pop()


class _Continue:
    """Sentinel meaning 'keep executing the current frame'."""


_CONTINUE = _Continue()
