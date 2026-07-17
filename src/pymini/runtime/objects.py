"""Runtime object model for functions, classes, instances, modules, and generators."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pymini.runtime.errors import (
    PyMiniRuntimeError,
    PyMiniTypeError,
    ReturnSignal,
    YieldSignal,
)
from pymini.runtime.scope import Environment


@runtime_checkable
class SupportsCall(Protocol):
    def call(
        self,
        args: Sequence[object],
        evaluator: object,
        kwargs: Mapping[str, object] | None = None,
    ) -> object:
        """Call the object with positional and keyword arguments."""


def _contains_yield(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, (ast.Yield, ast.YieldFrom)):
            return True
    return False


@dataclass(slots=True)
class NativeFunction:
    name: str
    func: Callable[..., object]

    def call(
        self,
        args: Sequence[object],
        evaluator: object,
        kwargs: Mapping[str, object] | None = None,
    ) -> object:
        if kwargs:
            return self.func(*args, **dict(kwargs))
        return self.func(*args)

    def __repr__(self) -> str:
        return f"<native fn {self.name}>"


@dataclass(slots=True)
class MiniFunction:
    name: str
    declaration: ast.FunctionDef
    closure: Environment
    defaults: tuple[object, ...] = ()
    kw_defaults: tuple[object | None, ...] = ()
    is_generator: bool = False

    @classmethod
    def from_function_def(
        cls,
        node: ast.FunctionDef,
        closure: Environment,
        defaults: tuple[object, ...],
        kw_defaults: tuple[object | None, ...] = (),
    ) -> MiniFunction:
        return cls(
            name=node.name,
            declaration=node,
            closure=closure,
            defaults=defaults,
            kw_defaults=kw_defaults,
            is_generator=_contains_yield(node),
        )

    def call(
        self,
        args: Sequence[object],
        evaluator: object,
        kwargs: Mapping[str, object] | None = None,
    ) -> object:
        from pymini.runtime.evaluator import Evaluator

        if not isinstance(evaluator, Evaluator):
            raise PyMiniRuntimeError("MiniFunction requires an Evaluator")

        local = self._bind_arguments(args, kwargs or {})
        if self.is_generator:
            return MiniGenerator(
                name=self.name,
                body=self.declaration.body,
                env=local,
                evaluator=evaluator,
                lineno=getattr(self.declaration, "lineno", None),
            )

        lineno = getattr(self.declaration, "lineno", None)
        evaluator.push_frame(self.name, lineno=lineno)
        try:
            evaluator.eval_block(self.declaration.body, local)
        except ReturnSignal as signal:
            return signal.value
        finally:
            evaluator.pop_frame()
        return None

    def _bind_arguments(
        self,
        args: Sequence[object],
        kwargs: Mapping[str, object],
    ) -> Environment:
        parameters = self.declaration.args.args
        kwonly = self.declaration.args.kwonlyargs
        vararg = self.declaration.args.vararg
        kwarg_param = self.declaration.args.kwarg
        kw_remaining = dict(kwargs)

        max_positional = len(parameters)
        required = max_positional - len(self.defaults)

        if vararg is None and len(args) > max_positional:
            raise PyMiniTypeError(
                f"{self.name}() expected at most {max_positional} arguments, got {len(args)}"
            )

        bound: dict[str, object] = {}

        # Bind positional parameters.
        for index, parameter in enumerate(parameters):
            name = parameter.arg
            if index < len(args):
                if name in kw_remaining:
                    raise PyMiniTypeError(
                        f"{self.name}() got multiple values for argument {name!r}"
                    )
                bound[name] = args[index]
            elif name in kw_remaining:
                bound[name] = kw_remaining.pop(name)
            elif index >= required:
                default_index = index - required
                bound[name] = self.defaults[default_index]
            else:
                raise PyMiniTypeError(
                    f"{self.name}() missing required positional argument: {name!r}"
                )

        if vararg is not None:
            bound[vararg.arg] = tuple(args[max_positional:])
        elif len(args) > max_positional:
            raise PyMiniTypeError(
                f"{self.name}() expected at most {max_positional} arguments, got {len(args)}"
            )

        # Keyword-only parameters.
        for index, parameter in enumerate(kwonly):
            name = parameter.arg
            if name in kw_remaining:
                bound[name] = kw_remaining.pop(name)
            elif index < len(self.kw_defaults) and self.kw_defaults[index] is not None:
                bound[name] = self.kw_defaults[index]
            else:
                # AST stores None for missing kw defaults; also treat missing slot as required.
                has_default = (
                    index < len(self.declaration.args.kw_defaults)
                    and self.declaration.args.kw_defaults[index] is not None
                )
                if has_default and index < len(self.kw_defaults):
                    bound[name] = self.kw_defaults[index]
                else:
                    raise PyMiniTypeError(
                        f"{self.name}() missing required keyword-only argument: {name!r}"
                    )

        if kwarg_param is not None:
            bound[kwarg_param.arg] = dict(kw_remaining)
        elif kw_remaining:
            unexpected = next(iter(kw_remaining))
            raise PyMiniTypeError(
                f"{self.name}() got an unexpected keyword argument {unexpected!r}"
            )

        local = Environment(name=f"fn {self.name}", parent=self.closure)
        for name, value in bound.items():
            local.define(name, value)
        return local

    def bind(self, receiver: object) -> BoundMethod:
        return BoundMethod(self, receiver)

    def __repr__(self) -> str:
        return f"<fn {self.name}>"


@dataclass(slots=True)
class BoundMethod:
    function: MiniFunction
    receiver: object

    def call(
        self,
        args: Sequence[object],
        evaluator: object,
        kwargs: Mapping[str, object] | None = None,
    ) -> object:
        return self.function.call([self.receiver, *args], evaluator, kwargs)

    def __repr__(self) -> str:
        return f"<bound method {self.function.name}>"


@dataclass(slots=True)
class MiniGenerator:
    """A simple generator object produced by functions that contain ``yield``."""

    name: str
    body: list[ast.stmt]
    env: Environment
    evaluator: object
    lineno: int | None = None
    _iterator: Iterator[object] | None = field(default=None, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _exhausted: bool = field(default=False, init=False, repr=False)

    def __iter__(self) -> MiniGenerator:
        return self

    def __next__(self) -> object:
        return self.send(None)

    def send(self, value: object) -> object:
        from pymini.runtime.evaluator import Evaluator

        if not isinstance(self.evaluator, Evaluator):
            raise PyMiniRuntimeError("MiniGenerator requires an Evaluator")
        if self._exhausted:
            raise StopIteration
        if self._iterator is None:
            if value is not None:
                raise TypeError("can't send non-None value to a just-started generator")
            self._iterator = self.evaluator.gen_eval_block(self.body, self.env)
            self._started = True

        self.evaluator.push_frame(self.name, lineno=self.lineno)
        try:
            if not self._started:
                return next(self._iterator)
            # After the first yield, send is not fully wired into AST yields;
            # educational subset advances via next().
            return next(self._iterator)
        except StopIteration as stop:
            self._exhausted = True
            raise stop
        except ReturnSignal as signal:
            self._exhausted = True
            if signal.value is None:
                raise StopIteration from signal
            raise StopIteration(signal.value) from signal
        except YieldSignal as signal:
            # Should not surface; gen_eval yields values directly.
            return signal.value
        finally:
            self.evaluator.pop_frame()

    def close(self) -> None:
        self._exhausted = True
        self._iterator = None

    def __repr__(self) -> str:
        return f"<generator {self.name}>"


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

    def call(
        self,
        args: Sequence[object],
        evaluator: object,
        kwargs: Mapping[str, object] | None = None,
    ) -> MiniInstance:
        instance = MiniInstance(self)
        try:
            initializer = instance.get_attr("__init__")
        except AttributeError:
            initializer = None
        if initializer is not None:
            if not isinstance(initializer, BoundMethod):
                raise PyMiniTypeError("__init__ must be a method")
            initializer.call(args, evaluator, kwargs)
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
