"""Typed bytecode model for the experimental PyMini VM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto


class OpCode(Enum):
    """Instructions understood by :class:`pymini.vm.VirtualMachine`."""

    LOAD_CONST = auto()
    LOAD_NAME = auto()
    STORE_NAME = auto()
    POP_TOP = auto()
    DUP_TOP = auto()
    BUILD_LIST = auto()
    BUILD_TUPLE = auto()
    BUILD_MAP = auto()
    BINARY_SUBSCR = auto()
    GET_ITER = auto()
    FOR_ITER = auto()

    BINARY_ADD = auto()
    BINARY_SUB = auto()
    BINARY_MUL = auto()
    BINARY_DIV = auto()
    BINARY_FLOOR_DIV = auto()
    BINARY_MOD = auto()
    BINARY_POW = auto()

    UNARY_POS = auto()
    UNARY_NEG = auto()
    UNARY_NOT = auto()

    COMPARE_OP = auto()
    JUMP = auto()
    JUMP_IF_FALSE = auto()
    JUMP_IF_TRUE = auto()
    CALL_FUNCTION = auto()
    RETURN_VALUE = auto()


class CompareOp(IntEnum):
    """Operands accepted by ``COMPARE_OP``."""

    EQ = 0
    NOT_EQ = 1
    LT = 2
    LT_E = 3
    GT = 4
    GT_E = 5


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: OpCode
    operand: object = None
    line: int | None = None


@dataclass(slots=True)
class Chunk:
    """Constants and instructions for one module or function body."""

    name: str = "<module>"
    instructions: list[Instruction] = field(default_factory=list)
    constants: list[object] = field(default_factory=list)

    def add_constant(self, value: object) -> int:
        self.constants.append(value)
        return len(self.constants) - 1

    def emit(self, opcode: OpCode, operand: object = None, line: int | None = None) -> int:
        """Append an instruction and return its index for optional backpatching."""

        index = len(self.instructions)
        self.instructions.append(Instruction(opcode, operand, line))
        return index

    def patch_jump(self, jump_index: int, target: int) -> None:
        """Set the target of a previously emitted jump instruction."""

        if not 0 <= jump_index < len(self.instructions):
            raise IndexError(f"invalid jump instruction index: {jump_index}")
        instruction = self.instructions[jump_index]
        if instruction.opcode not in {
            OpCode.JUMP,
            OpCode.JUMP_IF_FALSE,
            OpCode.JUMP_IF_TRUE,
            OpCode.FOR_ITER,
        }:
            raise ValueError(f"instruction {jump_index} is not a jump")
        self.instructions[jump_index] = Instruction(
            instruction.opcode,
            target,
            instruction.line,
        )

    def disassemble(self) -> str:
        """Render deterministic, human-readable bytecode for debugging."""

        lines = [f"chunk {self.name!r}"]
        for offset, instruction in enumerate(self.instructions):
            source_line = "-" if instruction.line is None else str(instruction.line)
            operand = "" if instruction.operand is None else repr(instruction.operand)
            lines.append(
                f"{offset:04d}  line {source_line:>4}  "
                f"{instruction.opcode.name:<20} {operand}".rstrip()
            )
        return "\n".join(lines)
