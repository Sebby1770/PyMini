"""PyMini exceptions, control-flow signals, and traceback formatting."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TracebackFrame:
    """One stack frame for runtime diagnostics."""

    name: str
    filename: str = "<string>"
    lineno: int | None = None

    def format(self) -> str:
        line = self.lineno if self.lineno is not None else "?"
        return f'  File "{self.filename}", line {line}, in {self.name}'


class PyMiniError(Exception):
    """Base class for all user-facing PyMini errors."""

    def __init__(self, message: str = "", *, frames: list[TracebackFrame] | None = None) -> None:
        super().__init__(message)
        self.frames: list[TracebackFrame] = list(frames or [])

    @property
    def message(self) -> str:
        return str(self.args[0]) if self.args else ""

    def with_frames(self, frames: list[TracebackFrame]) -> PyMiniError:
        if not self.frames:
            self.frames = list(frames)
        return self


class PyMiniSyntaxError(PyMiniError):
    """Raised when source cannot be parsed."""


class PyMiniNameError(PyMiniError):
    """Raised when a name is not bound in lexical scope."""


class PyMiniTypeError(PyMiniError):
    """Raised when a runtime operation receives an unsupported value."""


class PyMiniRuntimeError(PyMiniError):
    """Raised for general runtime failures."""


class PyMiniNotImplementedError(PyMiniError):
    """Raised for syntax that PyMini has not implemented yet."""


class PyMiniException(PyMiniError):
    """Raised by user-level ``raise`` when the payload is not a BaseException."""


@dataclass(slots=True)
class ReturnSignal(Exception):
    value: object


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


def format_exception(exc: BaseException) -> str:
    """Format a PyMini (or wrapped) exception with a CPython-like traceback."""

    lines: list[str] = ["Traceback (most recent call last):"]
    frames: list[TracebackFrame] = []
    if isinstance(exc, PyMiniError) and exc.frames:
        frames = exc.frames
    if frames:
        for frame in frames:
            lines.append(frame.format())
    else:
        lines.append('  File "<string>", line ?, in <module>')
    if isinstance(exc, PyMiniError):
        lines.append(f"{exc.__class__.__name__}: {exc.message}")
    else:
        lines.append(f"{exc.__class__.__name__}: {exc}")
    return "\n".join(lines)
