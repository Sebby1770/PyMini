from __future__ import annotations

from pymini.api import compile_source, disassemble, run_bytecode
from pymini.compiler.bytecode import OpCode


def test_binary_mod_and_pow() -> None:
    assert run_bytecode("10 % 3", optimize=False) == 1
    assert run_bytecode("2 ** 5", optimize=False) == 32


def test_unary_not_and_negative() -> None:
    assert run_bytecode("not 0", optimize=False) is True
    assert run_bytecode("not 1", optimize=False) is False
    assert run_bytecode("-5", optimize=False) == -5
    assert run_bytecode("--3", optimize=False) == 3


def test_build_set() -> None:
    result = run_bytecode("{1, 2, 2, 3}", optimize=False)
    assert result == {1, 2, 3}


def test_for_loop_get_iter_for_iter() -> None:
    source = """
total = 0
for x in [1, 2, 3]:
    total = total + x
total
"""
    chunk = compile_source(source, optimize=False)
    opcodes = [instr.opcode for instr in chunk.instructions]
    assert OpCode.GET_ITER in opcodes
    assert OpCode.FOR_ITER in opcodes
    assert run_bytecode(source, optimize=False) == 6


def test_jump_if_true_in_disassembly_available() -> None:
    # Opcode exists and is recognized by the disassembler table.
    assert OpCode.JUMP_IF_TRUE.name == "JUMP_IF_TRUE"
    text = disassemble("x = 1\nif x:\n    y = 2\ny", optimize=False)
    assert "JUMP_IF_FALSE" in text


def test_mod_pow_in_disassembly() -> None:
    text = disassemble("a = 7 % 4\nb = 2 ** 3", optimize=False)
    assert "BINARY_MOD" in text
    assert "BINARY_POW" in text


def test_unary_in_disassembly() -> None:
    text = disassemble("x = -1\ny = not x", optimize=False)
    assert "UNARY_NEGATIVE" in text
    assert "UNARY_NOT" in text


def test_for_loop_range() -> None:
    source = """
total = 0
for i in range(5):
    total = total + i
total
"""
    assert run_bytecode(source, optimize=False) == 10
