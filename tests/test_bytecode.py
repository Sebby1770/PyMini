from __future__ import annotations

from pymini.api import compile_source, disassemble, run_bytecode
from pymini.compiler.bytecode import OpCode
from pymini.vm.machine import VirtualMachine


def test_compile_simple_assignment_and_add() -> None:
    chunk = compile_source("x = 1 + 2\nx", optimize=False)
    opcodes = [instr.opcode for instr in chunk.instructions]
    assert OpCode.LOAD_CONST in opcodes
    assert OpCode.BINARY_ADD in opcodes
    assert OpCode.STORE_NAME in opcodes
    assert OpCode.LOAD_NAME in opcodes
    assert OpCode.RETURN_VALUE in opcodes


def test_disassemble_contains_readable_instructions() -> None:
    # Disable optimizer so BINARY_ADD is preserved (folding would collapse 1+2).
    text = disassemble("x = 1 + 2", optimize=False)
    assert "BINARY_ADD" in text
    assert "STORE_NAME" in text
    assert "LOAD_CONST" in text


def test_vm_runs_arithmetic() -> None:
    assert run_bytecode("1 + 2 * 3", optimize=False) == 7


def test_vm_runs_assignment_and_name_load() -> None:
    assert run_bytecode("x = 10\ny = 5\nx + y") == 15


def test_vm_runs_compare_and_if() -> None:
    source = """
x = 3
if x > 2:
    y = 1
else:
    y = 0
y
"""
    assert run_bytecode(source) == 1


def test_vm_runs_while_loop() -> None:
    source = """
i = 0
total = 0
while i < 4:
    total = total + i
    i = i + 1
total
"""
    assert run_bytecode(source) == 6


def test_vm_calls_simple_function() -> None:
    source = """
def add(a, b):
    return a + b
add(2, 3)
"""
    assert run_bytecode(source) == 5


def test_vm_function_disassembly_nested() -> None:
    text = disassemble(
        """
def f(x):
    return x + 1
f(1)
"""
    )
    assert "MAKE_FUNCTION" in text
    assert "disassembly of 'f'" in text
    assert "RETURN_VALUE" in text


def test_virtual_machine_direct() -> None:
    chunk = compile_source("2 + 2")
    assert VirtualMachine().run(chunk) == 4
