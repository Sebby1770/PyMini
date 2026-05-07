"""Skeleton stack VM that will execute PyMini bytecode in Milestone 2."""

from __future__ import annotations

from pymini.compiler.bytecode import Chunk
from pymini.runtime.errors import PyMiniNotImplementedError


class VirtualMachine:
    """Future bytecode VM entry point."""

    def run(self, chunk: Chunk) -> object:
        raise PyMiniNotImplementedError(
            f"bytecode execution for chunk {chunk.name!r} arrives in Milestone 2"
        )

