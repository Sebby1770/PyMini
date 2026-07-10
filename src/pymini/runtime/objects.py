"""Runtime object model for functions, classes, instances, and modules."""

from __future__ import annotations

import ast
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pymini.runtime.errors import (
    PyMiniRuntimeError,
    PyMiniTypeError,
    ReturnSignal,
)
from pymini.runtime.scope import Environment


@runtime_checkable
class SupportsCall(Protocol):
    def call(self, args: Sequence[object], evaluator: object) -> object:
        """Call the object with positional arguments."""


@dataclass(slots=True)
class NativeFunction:
    name: str
    func: Callable[..., object]

    def call(self, args: Sequence[object], evaluator: object) -> object:
        return self.func(*args)

    def __repr__(self) -> str:
        return f"<native fn {self.name}>"


@dataclass(slots=True)
class MiniFunction:
    name: str
    declaration: ast.FunctionDef
    closure: Environment
    defaults: tuple[object, ...] = ()

    def call(self, args: Sequence[object], evaluator: object) -> object:
        from pymini.runtime.evaluator import Evaluator

        if not isinstance(evaluator, Evaluator):
            raise PyMiniRuntimeError("MiniFunction requires an Evaluator")

        parameters = self.declaration.args.args
        vararg = self.declaration.args.vararg
        max_positional = len(parameters)
        required = max_positional - len(self.defaults)

        if vararg is None and len(args) > max_positional:
            raise PyMiniTypeError(
                f"{self.name}() expected at most {max_positional} arguments, got {len(args)}"
            )
        if len(args) < required:
            raise PyMiniTypeError(
                f"{self.name}() expected at least {required} arguments, got {len(args)}"
            )

        bound: list[object] = list(args[:max_positional])
        missing = max_positional - len(bound)
        if missing:
            bound.extend(self.defaults[-missing:])

        local = Environment(name=f"fn {self.name}", parent=self.closure)
        for parameter, value in zip(parameters, bound, strict=True):
            local.define(parameter.arg, value)
        if vararg is not None:
            local.define(vararg.arg, tuple(args[max_positional:]))

        lineno = getattr(self.declaration, "lineno", None)
        evaluator.push_frame(self.name, lineno=lineno)
        try:
            evaluator.eval_block(self.declaration.body, local)
        except ReturnSignal as signal:
            return signal.value
        finally:
            evaluator.pop_frame()
        return None

    def bind(self, receiver: object) -> BoundMethod:
        return BoundMethod(self, receiver)

    def __repr__(self) -> str:
        return f"<fn {self.name}>"


@dataclass(slots=True)
class BoundMethod:
    function: MiniFunction
    receiver: object

    def call(self, args: Sequence[object], evaluator: object) -> object:
        return self.function.call([self.receiver, *args], evaluator)

    def __repr__(self) -> str:
        return f"<bound method {self.function.name}>"


@dataclass(slots=True)
class MiniClass:
    name: str
    bases: list[MiniClass]
    attrs: dict[str, object] = field(default_factory=dict)

    def find_attr(self, name: str) -> object:
        if name in self.attrs:
            return self.attrs[name]
        for base in self.bases:
            try:
                return base.find_attr(name)
            except AttributeError:
                continue
        raise AttributeError(name)

    def get_attr(self, name: str) -> object:
        return self.find_attr(name)

    def set_attr(self, name: str, value: object) -> object:
        self.attrs[name] = value
        return value

    def call(self, args: Sequence[object], evaluator: object) -> MiniInstance:
        instance = MiniInstance(self)
        try:
            initializer = instance.get_attr("__init__")
        except AttributeError:
            initializer = None
        if initializer is not None:
            if not isinstance(initializer, BoundMethod):
                raise PyMiniTypeError("__init__ must be a method")
            initializer.call(args, evaluator)
        return instance

    def __repr__(self) -> str:
        return f"<class {self.name}>"


@dataclass(slots=True)
class MiniInstance:
    klass: MiniClass
    attrs: dict[str, object] = field(default_factory=dict)

    def get_attr(self, name: str) -> object:
        if name in self.attrs:
            return self.attrs[name]
        attr = self.klass.find_attr(name)
        if isinstance(attr, MiniFunction):
            return attr.bind(self)
        return attr

    def set_attr(self, name: str, value: object) -> object:
        self.attrs[name] = value
        return value

    def __repr__(self) -> str:
        return f"<{self.klass.name} instance>"


@dataclass(slots=True)
class ModuleNamespace:
    name: str
    members: dict[str, object]

    def get_attr(self, name: str) -> object:
        if name not in self.members:
            raise AttributeError(name)
        return self.members[name]

    def __repr__(self) -> str:
        return f"<module {self.name}>"
