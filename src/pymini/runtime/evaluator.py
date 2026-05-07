"""Tree-walking evaluator for the milestone PyMini runtime."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Iterable, Sequence
from typing import Literal

from pymini.optimizer.ast_optimizer import optimize_module
from pymini.parser import ParserMode, parse_source
from pymini.runtime.errors import (
    BreakSignal,
    ContinueSignal,
    PyMiniNameError,
    PyMiniNotImplementedError,
    PyMiniRuntimeError,
    PyMiniTypeError,
    ReturnSignal,
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


class Evaluator:
    """Execute PyMini programs from AST nodes."""

    def __init__(
        self,
        *,
        stdlib: StandardLibrary | None = None,
        stdout: Callable[[str], None] | None = None,
        max_steps: int = 100_000,
    ) -> None:
        self.stdlib = stdlib or StandardLibrary()
        self.stdout = stdout or print
        self.max_steps = max_steps
        self.steps = 0
        self.global_env = Environment(name="global")
        self._install_builtins()

    def run(
        self,
        source: str,
        *,
        parser_mode: ParserMode | Literal["ast", "handwritten"] = ParserMode.AST,
        optimize: bool = True,
    ) -> object:
        module = parse_source(source, mode=parser_mode)
        if optimize:
            module = optimize_module(module)
        return self.eval(module, self.global_env)

    def eval(self, node: ast.AST, env: Environment | None = None) -> object:
        self._tick()
        scope = env or self.global_env
        method_name = f"eval_{node.__class__.__name__}"
        method = getattr(self, method_name, None)
        if method is None:
            raise PyMiniNotImplementedError(f"{node.__class__.__name__} is not supported yet")
        return method(node, scope)

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
            return env.get(node.id)
        raise PyMiniTypeError(f"name {node.id!r} cannot be evaluated in this context")

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
        while self._truthy(self.eval(node.test, env)):
            try:
                result = self.eval_block(node.body, env)
            except ContinueSignal:
                continue
            except BreakSignal:
                break
        return result

    def eval_For(self, node: ast.For, env: Environment) -> object:
        iterable = self.eval(node.iter, env)
        if not isinstance(iterable, Iterable):
            raise PyMiniTypeError(f"object {iterable!r} is not iterable")
        result: object = None
        for item in iterable:
            self.assign_target(node.target, item, env)
            try:
                result = self.eval_block(node.body, env)
            except ContinueSignal:
                continue
            except BreakSignal:
                break
        return result

    def eval_FunctionDef(self, node: ast.FunctionDef, env: Environment) -> object:
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.posonlyargs:
            raise PyMiniNotImplementedError("only simple positional parameters are supported")
        defaults = tuple(self.eval(default, env) for default in node.args.defaults)
        function = MiniFunction(node.name, node, env, defaults)
        return env.define(node.name, function)

    def eval_ClassDef(self, node: ast.ClassDef, env: Environment) -> object:
        if node.keywords:
            raise PyMiniNotImplementedError("class keywords are not supported")

        bases: list[MiniClass] = []
        for base_node in node.bases:
            base = self.eval(base_node, env)
            if not isinstance(base, MiniClass):
                raise PyMiniTypeError("base classes must be PyMini classes")
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
            raise PyMiniNotImplementedError("relative imports are not supported")
        if node.module is None:
            raise PyMiniTypeError("from-import requires a module name")
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
        unary_ops: dict[type[ast.unaryop], Callable[[object], object]] = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Not: lambda item: not self._truthy(item),
        }
        for op_type, func in unary_ops.items():
            if isinstance(node.op, op_type):
                return func(value)
        raise PyMiniNotImplementedError(
            f"unary operator {node.op.__class__.__name__} is unsupported"
        )

    def eval_BoolOp(self, node: ast.BoolOp, env: Environment) -> object:
        if isinstance(node.op, ast.And):
            result: object = True
            for value_node in node.values:
                result = self.eval(value_node, env)
                if not self._truthy(result):
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result: object = False
            for value_node in node.values:
                result = self.eval(value_node, env)
                if self._truthy(result):
                    return result
            return result
        raise PyMiniNotImplementedError(
            f"boolean operator {node.op.__class__.__name__} is unsupported"
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
                raise PyMiniNotImplementedError("dict unpacking is not supported")
            result[self.eval(key_node, env)] = self.eval(value_node, env)
        return result

    def eval_Subscript(self, node: ast.Subscript, env: Environment) -> object:
        value = self.eval(node.value, env)
        index = self.eval_slice(node.slice, env)
        return value[index]  # type: ignore[index]

    def eval_Attribute(self, node: ast.Attribute, env: Environment) -> object:
        return self.get_attribute(self.eval(node.value, env), node.attr)

    def eval_Call(self, node: ast.Call, env: Environment) -> object:
        if node.keywords:
            raise PyMiniNotImplementedError("keyword arguments are not supported yet")
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
            receiver[index] = value  # type: ignore[index]
            return value
        if isinstance(target, ast.Tuple | ast.List):
            if not isinstance(value, Sequence):
                raise PyMiniTypeError("cannot unpack non-sequence value")
            if len(target.elts) != len(value):
                raise PyMiniTypeError("unpack target length does not match value length")
            for child, child_value in zip(target.elts, value, strict=True):
                self.assign_target(child, child_value, env)
            return value
        raise PyMiniTypeError("invalid assignment target")

    def load_target(self, target: ast.expr, env: Environment) -> object:
        if isinstance(target, ast.Name):
            return env.get(target.id)
        if isinstance(target, ast.Attribute):
            return self.get_attribute(self.eval(target.value, env), target.attr)
        if isinstance(target, ast.Subscript):
            receiver = self.eval(target.value, env)
            index = self.eval_slice(target.slice, env)
            return receiver[index]  # type: ignore[index]
        raise PyMiniTypeError("invalid augmented assignment target")

    def get_attribute(self, value: object, name: str) -> object:
        if isinstance(value, MiniInstance | MiniClass | ModuleNamespace):
            return value.get_attr(name)
        try:
            return getattr(value, name)
        except AttributeError:
            raise PyMiniNameError(f"{value!r} has no attribute {name!r}")

    def set_attribute(self, value: object, name: str, assigned: object) -> object:
        if isinstance(value, MiniInstance | MiniClass):
            return value.set_attr(name, assigned)
        raise PyMiniTypeError(f"cannot set attribute {name!r} on {value!r}")

    def call_value(self, callee: object, args: Sequence[object]) -> object:
        if isinstance(callee, MiniFunction | BoundMethod | MiniClass | NativeFunction):
            return callee.call(args, self)
        if isinstance(callee, SupportsCall):
            return callee.call(args, self)
        raise PyMiniTypeError(f"object {callee!r} is not callable")

    def _install_builtins(self) -> None:
        self.global_env.define("print", NativeFunction("print", self._print))
        self.global_env.define("len", NativeFunction("len", len))
        self.global_env.define("range", NativeFunction("range", range))
        self.global_env.define("list", NativeFunction("list", list))
        self.global_env.define("dict", NativeFunction("dict", dict))
        self.global_env.define("str", NativeFunction("str", str))
        self.global_env.define("int", NativeFunction("int", int))
        self.global_env.define("float", NativeFunction("float", float))
        self.global_env.define("bool", NativeFunction("bool", bool))

    def _print(self, *values: object) -> None:
        self.stdout(" ".join(str(value) for value in values))
        return None

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise PyMiniRuntimeError("execution step limit exceeded")

    def _binary_op(self, op: ast.operator, left: object, right: object) -> object:
        binary_ops: dict[type[ast.operator], Callable[[object, object], object]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        for op_type, func in binary_ops.items():
            if isinstance(op, op_type):
                return func(left, right)
        raise PyMiniNotImplementedError(f"binary operator {op.__class__.__name__} is unsupported")

    def _compare(self, op: ast.cmpop, left: object, right: object) -> bool:
        compare_ops: dict[type[ast.cmpop], Callable[[object, object], bool]] = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.Is: operator.is_,
            ast.IsNot: operator.is_not,
            ast.In: lambda item, container: item in container,
            ast.NotIn: lambda item, container: item not in container,
        }
        for op_type, func in compare_ops.items():
            if isinstance(op, op_type):
                return func(left, right)
        raise PyMiniNotImplementedError(f"comparison {op.__class__.__name__} is unsupported")

    @staticmethod
    def _truthy(value: object) -> bool:
        return bool(value)
