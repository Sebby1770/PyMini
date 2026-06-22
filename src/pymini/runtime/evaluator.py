"""Tree-walking evaluator for the milestone PyMini runtime."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal, cast

from pymini.parser import ParserMode
from pymini.pipeline import prepare_module
from pymini.runtime.builtins import default_builtin_functions
from pymini.runtime.errors import (
    BreakSignal,
    ContinueSignal,
    Location,
    PyMiniError,
    PyMiniNameError,
    PyMiniNotImplementedError,
    PyMiniRuntimeError,
    PyMiniTypeError,
    ReturnSignal,
    location_from_node,
)
from pymini.runtime.objects import (
    BoundMethod,
    MiniClass,
    MiniFunction,
    MiniInstance,
    ModuleNamespace,
    NativeFunction,
    SupportsCall,
)
from pymini.runtime.scope import Environment
from pymini.stdlib.modules import StandardLibrary

EvalHandler = Callable[[ast.AST, Environment], object]


class Evaluator:
    """Execute PyMini programs from AST nodes."""

    def __init__(
        self,
        *,
        stdlib: StandardLibrary | None = None,
        stdout: Callable[[str], None] | None = None,
        max_steps: int = 100_000,
        filename: str = "<string>",
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        self.stdlib = stdlib or StandardLibrary()
        self.stdout = stdout or print
        self.max_steps = max_steps
        self.steps = 0
        self.global_env = Environment(name="global")
        self._filename = filename
        self._source: str | None = None
        self._current_node: ast.AST | None = None
        self._handlers: dict[type[ast.AST], EvalHandler] = {}
        self._install_builtins()

    def run(
        self,
        source: str,
        *,
        parser_mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
        optimize: bool = True,
        filename: str | None = None,
    ) -> object:
        selected_filename = filename or self._filename
        module = prepare_module(source, mode=parser_mode, optimize=optimize)
        return self.execute(module, source=source, filename=selected_filename)

    def execute(
        self,
        module: ast.Module,
        *,
        source: str | None = None,
        filename: str | None = None,
    ) -> object:
        """Execute a prepared module while preserving the evaluator's global scope."""

        self.steps = 0
        self._current_node = None
        self._source = source
        if filename is not None:
            self._filename = filename
        return self.eval(module, self.global_env)

    @property
    def current_location(self) -> Location | None:
        """Location of the node currently being evaluated."""

        if self._current_node is None:
            return None
        return location_from_node(self._current_node, filename=self._filename)

    def eval(self, node: ast.AST, env: Environment | None = None) -> object:
        self._tick()
        scope = env or self.global_env

        previous_node = self._current_node
        if isinstance(node, (ast.expr, ast.stmt)):
            self._current_node = node

        node_type = type(node)
        method = self._handlers.get(node_type)
        if method is None:
            resolved = getattr(self, f"eval_{node_type.__name__}", None)
            if resolved is None:
                raise self._error(
                    PyMiniNotImplementedError,
                    f"{node_type.__name__} is not supported yet",
                )
            method = cast(EvalHandler, resolved)
            self._handlers[node_type] = method

        try:
            return method(node, scope)
        except PyMiniError as exc:
            if exc.location is None:
                exc.location = self.current_location
            if exc.source is None:
                exc.source = self._source
            raise
        finally:
            self._current_node = previous_node

    def eval_block(self, statements: Sequence[ast.stmt], env: Environment) -> object:
        result: object = None
        for statement in statements:
            result = self.eval(statement, env)
        return result

    def eval_Module(self, node: ast.Module, env: Environment) -> object:
        return self.eval_block(node.body, env)

    def eval_Expr(self, node: ast.Expr, env: Environment) -> object:
        return self.eval(node.value, env)

    def eval_Constant(self, node: ast.Constant, env: Environment) -> object:
        return node.value

    def eval_Name(self, node: ast.Name, env: Environment) -> object:
        if isinstance(node.ctx, ast.Load):
            try:
                return env.get(node.id)
            except PyMiniNameError as e:
                # Attach location from this Name node
                if self.current_location is not None:
                    e.location = self.current_location
                raise
        raise self._error(PyMiniTypeError, f"name {node.id!r} cannot be evaluated in this context")

    def eval_Assign(self, node: ast.Assign, env: Environment) -> object:
        value = self.eval(node.value, env)
        for target in node.targets:
            self.assign_target(target, value, env)
        return value

    def eval_AugAssign(self, node: ast.AugAssign, env: Environment) -> object:
        current = self.load_target(node.target, env)
        value = self._binary_op(node.op, current, self.eval(node.value, env))
        self.assign_target(node.target, value, env)
        return value

    def eval_Pass(self, node: ast.Pass, env: Environment) -> object:
        return None

    def eval_Return(self, node: ast.Return, env: Environment) -> object:
        value = None if node.value is None else self.eval(node.value, env)
        raise ReturnSignal(value)

    def eval_Break(self, node: ast.Break, env: Environment) -> object:
        raise BreakSignal

    def eval_Continue(self, node: ast.Continue, env: Environment) -> object:
        raise ContinueSignal

    def eval_If(self, node: ast.If, env: Environment) -> object:
        branch = node.body if self._truthy(self.eval(node.test, env)) else node.orelse
        return self.eval_block(branch, env)

    def eval_While(self, node: ast.While, env: Environment) -> object:
        result: object = None
        broke = False
        while self._truthy(self.eval(node.test, env)):
            try:
                result = self.eval_block(node.body, env)
            except ContinueSignal:
                continue
            except BreakSignal:
                broke = True
                break
        if not broke and node.orelse:
            result = self.eval_block(node.orelse, env)
        return result

    def eval_For(self, node: ast.For, env: Environment) -> object:
        iterable = self.eval(node.iter, env)
        if not isinstance(iterable, Iterable):
            raise self._error(PyMiniTypeError, f"object {iterable!r} is not iterable")
        result: object = None
        broke = False
        for item in iterable:
            self.assign_target(node.target, item, env)
            try:
                result = self.eval_block(node.body, env)
            except ContinueSignal:
                continue
            except BreakSignal:
                broke = True
                break
        if not broke and node.orelse:
            result = self.eval_block(node.orelse, env)
        return result

    def eval_FunctionDef(self, node: ast.FunctionDef, env: Environment) -> object:
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.posonlyargs:
            raise self._error(
                PyMiniNotImplementedError,
                "only simple positional parameters are supported",
            )
        defaults = tuple(self.eval(default, env) for default in node.args.defaults)
        function = MiniFunction(node.name, node, env, defaults)
        return env.define(node.name, function)

    def eval_ClassDef(self, node: ast.ClassDef, env: Environment) -> object:
        if node.keywords:
            raise self._error(PyMiniNotImplementedError, "class keywords are not supported")

        bases: list[MiniClass] = []
        for base_node in node.bases:
            base = self.eval(base_node, env)
            if not isinstance(base, MiniClass):
                raise self._error(PyMiniTypeError, "base classes must be PyMini classes")
            bases.append(base)

        class_env = Environment(name=f"class {node.name}", parent=env)
        self.eval_block(node.body, class_env)
        attrs = class_env.snapshot()
        klass = MiniClass(node.name, bases, attrs)
        return env.define(node.name, klass)

    def eval_Import(self, node: ast.Import, env: Environment) -> object:
        last: object = None
        for alias in node.names:
            module = self.stdlib.load(alias.name)
            bind_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
            last = env.define(bind_name, module)
        return last

    def eval_ImportFrom(self, node: ast.ImportFrom, env: Environment) -> object:
        if node.level:
            raise self._error(PyMiniNotImplementedError, "relative imports are not supported")
        if node.module is None:
            raise self._error(PyMiniTypeError, "from-import requires a module name")
        module = self.stdlib.load(node.module)
        last: object = None
        for alias in node.names:
            if alias.name == "*":
                for name, value in module.members.items():
                    env.define(name, value)
                    last = value
                continue
            value = module.get_attr(alias.name)
            last = env.define(alias.asname or alias.name, value)
        return last

    def eval_BinOp(self, node: ast.BinOp, env: Environment) -> object:
        return self._binary_op(node.op, self.eval(node.left, env), self.eval(node.right, env))

    def eval_UnaryOp(self, node: ast.UnaryOp, env: Environment) -> object:
        value = self.eval(node.operand, env)
        try:
            if isinstance(node.op, ast.UAdd):
                return +cast(Any, value)
            if isinstance(node.op, ast.USub):
                return -cast(Any, value)
            if isinstance(node.op, ast.Not):
                return not self._truthy(value)
        except TypeError as exc:
            raise self._error(PyMiniTypeError, str(exc)) from exc
        raise self._error(
            PyMiniNotImplementedError,
            f"unary operator {node.op.__class__.__name__} is unsupported",
        )

    def eval_BoolOp(self, node: ast.BoolOp, env: Environment) -> object:
        if isinstance(node.op, ast.And):
            and_result: object = True
            for value_node in node.values:
                and_result = self.eval(value_node, env)
                if not self._truthy(and_result):
                    return and_result
            return and_result
        if isinstance(node.op, ast.Or):
            or_result: object = False
            for value_node in node.values:
                or_result = self.eval(value_node, env)
                if self._truthy(or_result):
                    return or_result
            return or_result
        raise self._error(
            PyMiniNotImplementedError,
            f"boolean operator {node.op.__class__.__name__} is unsupported",
        )

    def eval_Compare(self, node: ast.Compare, env: Environment) -> object:
        left = self.eval(node.left, env)
        for op_node, comparator in zip(node.ops, node.comparators, strict=True):
            right = self.eval(comparator, env)
            if not self._compare(op_node, left, right):
                return False
            left = right
        return True

    def eval_IfExp(self, node: ast.IfExp, env: Environment) -> object:
        return self.eval(node.body if self._truthy(self.eval(node.test, env)) else node.orelse, env)

    def eval_List(self, node: ast.List, env: Environment) -> object:
        return [self.eval(item, env) for item in node.elts]

    def eval_Tuple(self, node: ast.Tuple, env: Environment) -> object:
        return tuple(self.eval(item, env) for item in node.elts)

    def eval_Dict(self, node: ast.Dict, env: Environment) -> object:
        result: dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if key_node is None:
                raise self._error(PyMiniNotImplementedError, "dict unpacking is not supported")
            result[self.eval(key_node, env)] = self.eval(value_node, env)
        return result

    def eval_Subscript(self, node: ast.Subscript, env: Environment) -> object:
        value = self.eval(node.value, env)
        index = self.eval_slice(node.slice, env)
        try:
            return cast(Any, value)[index]
        except (TypeError, KeyError, IndexError) as exc:
            raise self._error(PyMiniTypeError, str(exc)) from exc

    def eval_Attribute(self, node: ast.Attribute, env: Environment) -> object:
        return self.get_attribute(self.eval(node.value, env), node.attr)

    def eval_Call(self, node: ast.Call, env: Environment) -> object:
        if node.keywords:
            raise self._error(PyMiniNotImplementedError, "keyword arguments are not supported yet")
        callee = self.eval(node.func, env)
        args = [self.eval(arg, env) for arg in node.args]
        return self.call_value(callee, args)

    def eval_slice(self, node: ast.AST, env: Environment) -> object:
        if isinstance(node, ast.Slice):
            lower = None if node.lower is None else self.eval(node.lower, env)
            upper = None if node.upper is None else self.eval(node.upper, env)
            step = None if node.step is None else self.eval(node.step, env)
            return slice(lower, upper, step)
        return self.eval(node, env)

    def assign_target(self, target: ast.expr, value: object, env: Environment) -> object:
        if isinstance(target, ast.Name):
            return env.set_local(target.id, value)
        if isinstance(target, ast.Attribute):
            receiver = self.eval(target.value, env)
            return self.set_attribute(receiver, target.attr, value)
        if isinstance(target, ast.Subscript):
            receiver = self.eval(target.value, env)
            index = self.eval_slice(target.slice, env)
            cast(Any, receiver)[index] = value
            return value
        if isinstance(target, ast.Tuple | ast.List):
            if not isinstance(value, Sequence):
                raise self._error(PyMiniTypeError, "cannot unpack non-sequence value")
            if len(target.elts) != len(value):
                raise self._error(
                    PyMiniTypeError,
                    "unpack target length does not match value length",
                )
            for child, child_value in zip(target.elts, value, strict=True):
                self.assign_target(child, child_value, env)
            return value
        raise self._error(PyMiniTypeError, "invalid assignment target")

    def load_target(self, target: ast.expr, env: Environment) -> object:
        if isinstance(target, ast.Name):
            return env.get(target.id)
        if isinstance(target, ast.Attribute):
            return self.get_attribute(self.eval(target.value, env), target.attr)
        if isinstance(target, ast.Subscript):
            receiver = self.eval(target.value, env)
            index = self.eval_slice(target.slice, env)
            return cast(Any, receiver)[index]
        raise self._error(PyMiniTypeError, "invalid augmented assignment target")

    def get_attribute(self, value: object, name: str) -> object:
        if isinstance(value, MiniInstance | MiniClass | ModuleNamespace):
            try:
                return value.get_attr(name)
            except (AttributeError, PyMiniNameError) as exc:
                raise self._error(
                    PyMiniNameError, f"{value!r} has no attribute {name!r}"
                ) from exc
        if isinstance(value, NativeFunction) or name.startswith("_"):
            raise self._error(
                PyMiniNameError, f"{value!r} has no accessible attribute {name!r}"
            )
        try:
            return getattr(value, name)
        except AttributeError:
            raise self._error(PyMiniNameError, f"{value!r} has no attribute {name!r}")

    def set_attribute(self, value: object, name: str, assigned: object) -> object:
        if isinstance(value, MiniInstance | MiniClass):
            try:
                return value.set_attr(name, assigned)
            except PyMiniTypeError as exc:
                if self.current_location is not None:
                    exc.location = self.current_location
                raise
        raise self._error(PyMiniTypeError, f"cannot set attribute {name!r} on {value!r}")

    def call_value(self, callee: object, args: Sequence[object]) -> object:
        if isinstance(callee, MiniFunction | BoundMethod | MiniClass | NativeFunction):
            return callee.call(args, self)
        if isinstance(callee, SupportsCall):
            return callee.call(args, self)
        raise self._error(PyMiniTypeError, f"object {callee!r} is not callable")

    def _install_builtins(self) -> None:
        for name, function in default_builtin_functions(self.stdout).items():
            self.global_env.define(name, NativeFunction(name, function))

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise self._error(PyMiniRuntimeError, "execution step limit exceeded")

    def _error(self, error_cls: type[PyMiniError], message: str) -> PyMiniError:
        """Create an error with the current source location attached."""
        return error_cls(
            message,
            location=self.current_location,
            source=self._source,
        )

    def _binary_op(self, op: ast.operator, left: object, right: object) -> object:
        lhs = cast(Any, left)
        rhs = cast(Any, right)
        try:
            result: object
            if isinstance(op, ast.Add):
                result = lhs + rhs
            elif isinstance(op, ast.Sub):
                result = lhs - rhs
            elif isinstance(op, ast.Mult):
                result = lhs * rhs
            elif isinstance(op, ast.Div):
                result = lhs / rhs
            elif isinstance(op, ast.FloorDiv):
                result = lhs // rhs
            elif isinstance(op, ast.Mod):
                result = lhs % rhs
            elif isinstance(op, ast.Pow):
                result = lhs**rhs
            else:
                raise self._error(
                    PyMiniNotImplementedError,
                    f"binary operator {op.__class__.__name__} is unsupported",
                )
            return result
        except PyMiniError:
            raise
        except TypeError as exc:
            raise self._error(PyMiniTypeError, str(exc)) from exc
        except (ArithmeticError, OverflowError) as exc:
            raise self._error(PyMiniRuntimeError, str(exc)) from exc

    def _compare(self, op: ast.cmpop, left: object, right: object) -> bool:
        lhs = cast(Any, left)
        rhs = cast(Any, right)
        try:
            if isinstance(op, ast.Eq):
                return bool(lhs == rhs)
            if isinstance(op, ast.NotEq):
                return bool(lhs != rhs)
            if isinstance(op, ast.Lt):
                return bool(lhs < rhs)
            if isinstance(op, ast.LtE):
                return bool(lhs <= rhs)
            if isinstance(op, ast.Gt):
                return bool(lhs > rhs)
            if isinstance(op, ast.GtE):
                return bool(lhs >= rhs)
            if isinstance(op, ast.Is):
                return left is right
            if isinstance(op, ast.IsNot):
                return left is not right
            if isinstance(op, ast.In):
                return bool(lhs in rhs)
            if isinstance(op, ast.NotIn):
                return bool(lhs not in rhs)
        except TypeError as exc:
            raise self._error(PyMiniTypeError, str(exc)) from exc
        raise self._error(
            PyMiniNotImplementedError,
            f"comparison {op.__class__.__name__} is unsupported",
        )

    @staticmethod
    def _truthy(value: object) -> bool:
        return bool(value)
