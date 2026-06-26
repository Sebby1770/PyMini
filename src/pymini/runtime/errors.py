"""PyMini exceptions, source locations, and internal control-flow signals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Location:
    """Source location for a user-facing diagnostic."""

    filename: str = "<string>"
    lineno: int = 1
    col_offset: int = 0
    end_lineno: int | None = None
    end_col_offset: int | None = None

    def __str__(self) -> str:
        start = f"{self.filename}:{self.lineno}:{self.col_offset + 1}"
        if self.end_lineno is None:
            return start
        end_column = self.end_col_offset if self.end_col_offset is not None else 0
        if self.end_lineno != self.lineno:
            return f"{start}-{self.end_lineno}:{end_column + 1}"
        if end_column > self.col_offset + 1:
            return f"{start}-{end_column}"
        return start


class PyMiniError(Exception):
    """Base class for all user-facing PyMini errors."""

    def __init__(
        self,
        message: str,
        *,
        location: Location | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.location = location
        self.source = source

    def __str__(self) -> str:
        return self.message


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


@dataclass(slots=True)
class ReturnSignal(Exception):
    value: object


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


def location_from_node(node: object, *, filename: str = "<string>") -> Location | None:
    """Create a location from an AST-like object when line metadata exists."""

    lineno = getattr(node, "lineno", None)
    if not isinstance(lineno, int):
        return None
    col_offset = getattr(node, "col_offset", 0)
    return Location(
        filename=filename,
        lineno=lineno,
        col_offset=col_offset if isinstance(col_offset, int) else 0,
        end_lineno=getattr(node, "end_lineno", None),
        end_col_offset=getattr(node, "end_col_offset", None),
    )


def format_error(
    exc: PyMiniError,
    *,
    source: str | None = None,
    filename: str = "<string>",
    show_context: bool = True,
) -> str:
    """Format a PyMini error with optional source context and a caret."""

    location = exc.location
    header = f"{exc.__class__.__name__}: {exc.message}"
    if location is not None:
        header = f"{header} ({location})"
    elif filename != "<string>":
        header = f"{header} ({filename})"

    lines = [header]
    source_text = exc.source or source
    if not show_context or source_text is None or location is None:
        return "\n".join(lines)

    source_lines = source_text.splitlines()
    line_index = location.lineno - 1
    if not 0 <= line_index < len(source_lines):
        return "\n".join(lines)

    if line_index > 0:
        lines.append(f"   {line_index:4d} | {source_lines[line_index - 1]}")
    lines.append(f" > {location.lineno:4d} | {source_lines[line_index]}")

    column = max(0, location.col_offset)
    caret = " " * (10 + column) + "^"
    if (
        location.end_lineno == location.lineno
        and location.end_col_offset is not None
        and location.end_col_offset > location.col_offset + 1
    ):
        caret += "~" * (location.end_col_offset - location.col_offset - 1)
    lines.append(caret)
    return "\n".join(lines)
