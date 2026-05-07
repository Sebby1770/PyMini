"""PyMini exceptions and internal control-flow signals."""

from __future__ import annotations

from dataclasses import dataclass


class PyMiniError(Exception):
    """Base class for all user-facing PyMini errors."""


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

