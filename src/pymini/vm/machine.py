"""Typed stack machine for PyMini bytecode."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from pymini.compiler.bytecode import Chunk, CompareOp, Instruction, OpCode
from pymini.runtime.builtins import default_builtin_functions
from pymini.runtime.errors import (
    Location,
    PyMiniNameError,
    PyMiniRuntimeError,
    PyMiniTypeError,
)


@dataclass(slots=True)
class Frame:
    """Instruction pointer and operand stack for one bytecode chunk."""

    chunk: Chunk
    ip: int = 0
    stack: list[object] = field(default_factory=list)


class VirtualMachine:
    """Execute the intentionally small bytecode subset emitted by ``Compiler``."""

    def __init__(
        self,
        *,
        max_steps: int = 100_000,
        filename: str = "<string>",
        builtins: Mapping[str, object] | None = None,
        stdout: Callable[[str], None] | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        self.max_steps = max_steps
        self.filename = filename
        self.steps = 0
        self.globals: dict[str, object] = {}
        self._builtins = (
            dict(builtins)
            if builtins is not None
            else default_builtin_functions(stdout)
        )
        self._frame: Frame | None = None

    @property
    def stack(self) -> list[object]:
        """Expose the active operand stack for debugging and tests."""

        return self._frame.stack if self._frame is not None else []

    def run(self, chunk: Chunk) -> object:
        """Execute a chunk with fresh globals and return its result."""

        self.steps = 0
        self.globals = dict(self._builtins)
        self._frame = Frame(chunk=chunk)
        return self._execute(self._frame)

    def _execute(self, frame: Frame) -> object:
        while frame.ip < len(frame.chunk.instructions):
            self._tick(frame)
            instruction = frame.chunk.instructions[frame.ip]
            frame.ip += 1
            try:
                result, returned = self._execute_instruction(frame, instruction)
            except (PyMiniNameError, PyMiniRuntimeError, PyMiniTypeError):
                raise
            except (ArithmeticError, IndexError, KeyError, TypeError, ValueError) as exc:
                raise self._runtime_error(instruction, str(exc)) from exc
            if returned:
                return result
        return None

    def _execute_instruction(
        self, frame: Frame, instruction: Instruction
    ) -> tuple[object, bool]:
        opcode = instruction.opcode

        if opcode is OpCode.LOAD_CONST:
            index = self._int_operand(instruction)
            try:
                frame.stack.append(frame.chunk.constants[index])
            except IndexError as exc:
                raise self._runtime_error(
                    instruction, f"constant index out of range: {index}"
                ) from exc
        elif opcode is OpCode.LOAD_NAME:
            name = self._str_operand(instruction)
            if name not in self.globals:
                raise PyMiniNameError(
                    f"name {name!r} is not defined",
                    location=self._location(instruction),
                )
            frame.stack.append(self.globals[name])
        elif opcode is OpCode.STORE_NAME:
            self.globals[self._str_operand(instruction)] = self._pop(frame, instruction)
        elif opcode is OpCode.POP_TOP:
            self._pop(frame, instruction)
        elif opcode is OpCode.DUP_TOP:
            frame.stack.append(self._peek(frame, instruction))
        elif opcode is OpCode.BUILD_LIST:
            frame.stack.append(self._pop_many(frame, instruction))
        elif opcode is OpCode.BUILD_TUPLE:
            frame.stack.append(tuple(self._pop_many(frame, instruction)))
        elif opcode is OpCode.BUILD_MAP:
            items = self._pop_many(frame, instruction, multiplier=2)
            mapping: dict[object, object] = {}
            for mapping_index in range(0, len(items), 2):
                mapping[items[mapping_index]] = items[mapping_index + 1]
            frame.stack.append(mapping)
        elif opcode is OpCode.BINARY_SUBSCR:
            subscript_index = self._pop(frame, instruction)
            container = cast(Any, self._pop(frame, instruction))
            frame.stack.append(container[subscript_index])
        elif opcode is OpCode.GET_ITER:
            frame.stack.append(iter(cast(Any, self._pop(frame, instruction))))
        elif opcode is OpCode.FOR_ITER:
            iterator = cast(Any, self._peek(frame, instruction))
            try:
                frame.stack.append(next(iterator))
            except StopIteration:
                self._pop(frame, instruction)
                frame.ip = self._jump_target(frame, instruction)
        elif opcode in _BINARY_OPCODES:
            right = self._pop(frame, instruction)
            left = self._pop(frame, instruction)
            frame.stack.append(self._binary(opcode, left, right, instruction))
        elif opcode is OpCode.UNARY_POS:
            frame.stack.append(+cast(Any, self._pop(frame, instruction)))
        elif opcode is OpCode.UNARY_NEG:
            frame.stack.append(-cast(Any, self._pop(frame, instruction)))
        elif opcode is OpCode.UNARY_NOT:
            frame.stack.append(not self._pop(frame, instruction))
        elif opcode is OpCode.COMPARE_OP:
            right = self._pop(frame, instruction)
            left = self._pop(frame, instruction)
            frame.stack.append(
                self._compare(self._compare_operand(instruction), left, right, instruction)
            )
        elif opcode is OpCode.JUMP:
            frame.ip = self._jump_target(frame, instruction)
        elif opcode is OpCode.JUMP_IF_FALSE:
            if not self._pop(frame, instruction):
                frame.ip = self._jump_target(frame, instruction)
        elif opcode is OpCode.JUMP_IF_TRUE:
            if self._pop(frame, instruction):
                frame.ip = self._jump_target(frame, instruction)
        elif opcode is OpCode.CALL_FUNCTION:
            argument_count = self._int_operand(instruction)
            if argument_count < 0:
                raise self._runtime_error(instruction, "argument count cannot be negative")
            arguments = [self._pop(frame, instruction) for _ in range(argument_count)]
            arguments.reverse()
            function = self._pop(frame, instruction)
            if not callable(function):
                raise PyMiniTypeError(
                    f"object {function!r} is not callable",
                    location=self._location(instruction),
                )
            callable_value = cast(Callable[..., object], function)
            frame.stack.append(callable_value(*arguments))
        elif opcode is OpCode.RETURN_VALUE:
            return self._pop(frame, instruction), True
        else:
            raise self._runtime_error(instruction, f"unknown opcode: {opcode}")
        return None, False

    def _binary(
        self,
        opcode: OpCode,
        left: object,
        right: object,
        instruction: Instruction,
    ) -> object:
        lhs = cast(Any, left)
        rhs = cast(Any, right)
        try:
            result: object
            if opcode is OpCode.BINARY_ADD:
                result = lhs + rhs
            elif opcode is OpCode.BINARY_SUB:
                result = lhs - rhs
            elif opcode is OpCode.BINARY_MUL:
                result = lhs * rhs
            elif opcode is OpCode.BINARY_DIV:
                result = lhs / rhs
            elif opcode is OpCode.BINARY_FLOOR_DIV:
                result = lhs // rhs
            elif opcode is OpCode.BINARY_MOD:
                result = lhs % rhs
            elif opcode is OpCode.BINARY_POW:
                result = lhs**rhs
            else:
                raise self._runtime_error(instruction, f"unknown binary opcode: {opcode}")
            return result
        except PyMiniRuntimeError:
            raise
        except TypeError as exc:
            raise PyMiniTypeError(
                str(exc), location=self._location(instruction)
            ) from exc
        except ArithmeticError as exc:
            raise self._runtime_error(instruction, str(exc)) from exc

    def _compare(
        self,
        comparison: CompareOp,
        left: object,
        right: object,
        instruction: Instruction,
    ) -> bool:
        lhs = cast(Any, left)
        rhs = cast(Any, right)
        try:
            if comparison is CompareOp.EQ:
                return bool(lhs == rhs)
            if comparison is CompareOp.NOT_EQ:
                return bool(lhs != rhs)
            if comparison is CompareOp.LT:
                return bool(lhs < rhs)
            if comparison is CompareOp.LT_E:
                return bool(lhs <= rhs)
            if comparison is CompareOp.GT:
                return bool(lhs > rhs)
            if comparison is CompareOp.GT_E:
                return bool(lhs >= rhs)
        except TypeError as exc:
            raise PyMiniTypeError(
                str(exc), location=self._location(instruction)
            ) from exc
        raise self._runtime_error(instruction, f"unknown comparison: {comparison}")

    def _tick(self, frame: Frame) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            instruction = (
                frame.chunk.instructions[frame.ip]
                if frame.ip < len(frame.chunk.instructions)
                else Instruction(OpCode.RETURN_VALUE)
            )
            raise self._runtime_error(instruction, "execution step limit exceeded")

    def _pop(self, frame: Frame, instruction: Instruction) -> object:
        if not frame.stack:
            raise self._runtime_error(instruction, "operand stack underflow")
        return frame.stack.pop()

    def _peek(self, frame: Frame, instruction: Instruction) -> object:
        if not frame.stack:
            raise self._runtime_error(instruction, "operand stack underflow")
        return frame.stack[-1]

    def _pop_many(
        self,
        frame: Frame,
        instruction: Instruction,
        *,
        multiplier: int = 1,
    ) -> list[object]:
        count = self._int_operand(instruction) * multiplier
        if count < 0:
            raise self._runtime_error(instruction, "item count cannot be negative")
        if count > len(frame.stack):
            raise self._runtime_error(instruction, "operand stack underflow")
        if count == 0:
            return []
        items = frame.stack[-count:]
        del frame.stack[-count:]
        return items

    def _jump_target(self, frame: Frame, instruction: Instruction) -> int:
        target = self._int_operand(instruction)
        if not 0 <= target <= len(frame.chunk.instructions):
            raise self._runtime_error(instruction, f"invalid jump target: {target}")
        return target

    def _int_operand(self, instruction: Instruction) -> int:
        if isinstance(instruction.operand, bool) or not isinstance(instruction.operand, int):
            raise self._runtime_error(instruction, "instruction requires an integer operand")
        return instruction.operand

    def _str_operand(self, instruction: Instruction) -> str:
        if not isinstance(instruction.operand, str):
            raise self._runtime_error(instruction, "instruction requires a string operand")
        return instruction.operand

    def _compare_operand(self, instruction: Instruction) -> CompareOp:
        try:
            return CompareOp(self._int_operand(instruction))
        except ValueError as exc:
            raise self._runtime_error(
                instruction, f"invalid comparison operand: {instruction.operand}"
            ) from exc

    def _location(self, instruction: Instruction) -> Location | None:
        if instruction.line is None:
            return None
        return Location(filename=self.filename, lineno=instruction.line)

    def _runtime_error(
        self, instruction: Instruction, message: str
    ) -> PyMiniRuntimeError:
        return PyMiniRuntimeError(message, location=self._location(instruction))

_BINARY_OPCODES = {
    OpCode.BINARY_ADD,
    OpCode.BINARY_SUB,
    OpCode.BINARY_MUL,
    OpCode.BINARY_DIV,
    OpCode.BINARY_FLOOR_DIV,
    OpCode.BINARY_MOD,
    OpCode.BINARY_POW,
}
