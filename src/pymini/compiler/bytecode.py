"""Bytecode model for the upcoming PyMini VM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class OpCode(Enum):
    LOAD_CONST = auto()
    LOAD_NAME = auto()
    STORE_NAME = auto()
    POP_TOP = auto()
    BINARY_ADD = auto()
    RETURN_VALUE = auto()


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: OpCode
    operand: object = None
    line: int | None = None


@dataclass(slots=True)
class Chunk:
    name: str = "<module>"
    instructions: list[Instruction] = field(default_factory=list)
    constants: list[object] = field(default_factory=list)

    def add_constant(self, value: object) -> int:
        self.constants.append(value)
        return len(self.constants) - 1

    def emit(self, opcode: OpCode, operand: object = None, line: int | None = None) -> None:
        self.instructions.append(Instruction(opcode, operand, line))

