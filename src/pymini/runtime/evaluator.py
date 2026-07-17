"""Tree-walking evaluator for the PyMini runtime."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Literal

from pymini.optimizer.ast_optimizer import optimize_module
from pymini.parser import ParserMode, parse_source
from pymini.runtime.errors import (
    BreakSignal,
    ContinueSignal,
    PyMiniError,
    PyMiniNameError,
    PyMiniNotImplementedError,
    PyMiniRuntimeError,
    PyMiniTypeError,
    ReturnSignal,
    TracebackFrame,
)
from pymini.runtime.objects import (
    BoundMethod,
    MiniClass,
    MiniFunction,
    MiniGenerator,
    MiniInstance,
    ModuleNamespace,
    NativeFunction,
    SupportsCall,
)
from pymini.runtime.scope import Environment
from pymini.stdlib.modules import StandardLibrary

_CONTROL_FLOW = (ReturnSignal, BreakSignal, ContinueSignal)


def _node_contains_yield(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, (ast.Yield, ast.YieldFrom)):
            return True
    return False


class Evaluator:
    """Execute PyMini programs from AST nodes."""

    def __init__(
        self,
        *,
        stdlib: StandardLibrary | None = None,
        stdout: Callable[[str], None] | None = None,
        max_steps: int = 100_000,
        filename: str = "<string>",
        trace: bool = False,
        on_line: Callable[[int, str | None], None] | None = None,
    ) -> None:
        self.stdlib = stdlib or StandardLibrary()
        self.stdout = stdout or print
        self.max_steps = max_steps
        self.steps = 0
        self.filename = filename
        self.trace = trace
        self.on_line = on_line
        self._last_traced_line: int | None = None
        self.global_env = Environment(name="global")
        self.frames: list[TracebackFrame] = [
            TracebackFrame(name="<module>", filename=filename, lineno=1)
        ]
        # Current environment for debugger inspection.
        self.current_env: Environment = self.global_env
        self._install_builtins()

    def push_frame(self, name: str, lineno: int | None = None) -> None:
        self.frames.append(TracebackFrame(name=name, filename=self.filename, lineno=lineno))

    def pop_frame(self) -> None:
        if len(self.frames) > 1:
            self.frames.pop()

    def snapshot_frames(self) -> list[TracebackFrame]:
        return [
            TracebackFrame(name=f.name, filename=f.filename, lineno=f.lineno)
            for f in self.frames
        ]

    def _set_lineno(self, node: ast.AST) -> None:
        lineno = getattr(node, "lineno", None)
        if lineno is not None and self.frames:
            self.frames[-1].lineno = lineno
        if lineno is not None and (self.trace or self.on_line is not None):
            if lineno != self._last_traced_line:
                self._last_traced_line = lineno
                if self.trace:
                    self.stdout(f"  --> {self.filename}:{lineno}")
                if self.on_line is not None:
                    self.on_line(lineno, self.frames[-1].name if self.frames else None)

    def _attach_frames(self, exc: BaseException) -> BaseException:
        if isinstance(exc, PyMiniError):
            exc.with_frames(self.snapshot_frames())
            return exc
        wrapped = PyMiniRuntimeError(str(exc), frames=self.snapshot_frames())
        wrapped.__cause__ = exc
        return wrapped

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
        self._set_lineno(node)
        scope = env or self.global_env
        self.current_env = scope
        method_name = f"eval_{node.__class__.__name__}"
        method = getattr(self, method_name, None)
        if method is None:
            raise PyMiniNotImplementedError(
                f"{node.__class__.__name__} is not supported yet",
                frames=self.snapshot_frames(),
            )
        try:
            return method(node, scope)
        except _CONTROL_FLOW:
            raise
        except PyMiniError as exc:
            # Attach frames once; leave user-raised Exception subclasses alone so
            # try/except Exception in PyMini programs can match them.
            exc.with_frames(self.snapshot_frames())
            raise

    def eval_block(self, statements: Sequence[ast.stmt], env: Environment) -> object:
        result: object = None
        for statement in statements:
            result = self.eval(statement, env)
        return result

    # --- Generator evaluation path -------------------------------------------------

    def gen_eval_block(
        self, statements: Sequence[ast.stmt], env: Environment
    ) -> Iterator[object]:
        for statement in statements:
            yield from self.gen_eval_stmt(statement, env)

    def gen_eval_stmt(self, node: ast.stmt, env: Environment) -> Iterator[object]:
        """Yield values from ``yield`` expressions inside a generator body."""

        self._tick()
        self._set_lineno(node)
        self.current_env = env

        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Yield):
                value = None if node.value.value is None else self.eval(node.value.value, env)
                yield value
                return
            if isinstance(node.value, ast.YieldFrom):
                iterable = self.eval(node.value.value, env)
                if not isinstance(iterable, Iterable):
                    raise PyMiniTypeError(f"object {iterable!r} is not iterable")
                yield from iterable  # type: ignore[misc]
                return
            self.eval(node.value, env)
            return

        if isinstance(node, ast.Assign):
            value = self.eval(node.value, env)
            for target in node.targets:
                self.assign_target(target, value, env)
            return

        if isinstance(node, ast.AugAssign):
            self.eval(node, env)
            return

        if isinstance(node, ast.Return):
            value = None if node.value is None else self.eval(node.value, env)
            raise ReturnSignal(value)

        if isinstance(node, ast.Break):
            raise BreakSignal
        if isinstance(node, ast.Continue):
            raise ContinueSignal
        if isinstance(node, ast.Pass):
            return

        if isinstance(node, ast.If):
            branch = node.body if self._truthy(self.eval(node.test, env)) else node.orelse
            yield from self.gen_eval_block(branch, env)
            return

        if isinstance(node, ast.While):
            while self._truthy(self.eval(node.test, env)):
                try:
                    yield from self.gen_eval_block(node.body, env)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return

        if isinstance(node, ast.For):
            iterable = self.eval(node.iter, env)
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"object {iterable!r} is not iterable")
            for item in iterable:
                self.assign_target(node.target, item, env)
                try:
                    yield from self.gen_eval_block(node.body, env)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return

        if isinstance(node, ast.Try):
            # Minimal try support inside generators.
            pending: BaseException | None = None
            try:
                try:
                    yield from self.gen_eval_block(node.body, env)
                except _CONTROL_FLOW:
                    raise
                except Exception as exc:
                    handled = False
                    for handler in node.handlers:
                        if self._exception_matches(handler, exc, env):
                            if handler.name:
                                env.define(handler.name, exc)
                            try:
                                yield from self.gen_eval_block(handler.body, env)
                            finally:
                                if handler.name:
                                    env.values.pop(handler.name, None)
                            handled = True
                            break
                    if not handled:
                        pending = exc
                else:
                    if pending is None and node.orelse:
                        yield from self.gen_eval_block(node.orelse, env)
            finally:
                if node.finalbody:
                    yield from self.gen_eval_block(node.finalbody, env)
            if pending is not None:
                raise pending
            return

        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            self.eval(node, env)
            return

        if isinstance(node, ast.Assert):
            self.eval(node, env)
            return

        if isinstance(node, ast.Raise):
            self.eval(node, env)
            return

        if isinstance(node, ast.With):
            # Fall back to non-generator with for simplicity.
            self.eval(node, env)
            return

        # Default: evaluate as a normal statement (no yields expected).
        if _node_contains_yield(node):
            raise PyMiniNotImplementedError(
                f"yield inside {node.__class__.__name__} is not supported yet"
            )
        self.eval(node, env)

    # --- Statements ----------------------------------------------------------------

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

    def eval_AnnAssign(self, node: ast.AnnAssign, env: Environment) -> object:
        if node.value is None:
            return None
        value = self.eval(node.value, env)
        if node.target is not None:
            self.assign_target(node.target, value, env)
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

    def eval_Yield(self, node: ast.Yield, env: Environment) -> object:
        # Bare yield expressions outside the generator driver are not supported.
        raise PyMiniRuntimeError(
            "'yield' outside function",
            frames=self.snapshot_frames(),
        )

    def eval_YieldFrom(self, node: ast.YieldFrom, env: Environment) -> object:
        raise PyMiniRuntimeError(
            "'yield from' outside function",
            frames=self.snapshot_frames(),
        )

    def eval_Break(self, node: ast.Break, env: Environment) -> object:
        raise BreakSignal

    def eval_Continue(self, node: ast.Continue, env: Environment) -> object:
        raise ContinueSignal

    def eval_Assert(self, node: ast.Assert, env: Environment) -> object:
        if not self._truthy(self.eval(node.test, env)):
            if node.msg is not None:
                msg = self.eval(node.msg, env)
                raise AssertionError(msg)
            raise AssertionError
        return None

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
        if node.args.posonlyargs:
            raise PyMiniNotImplementedError("positional-only parameters are not supported yet")
        defaults = tuple(self.eval(default, env) for default in node.args.defaults)
        kw_defaults: list[object | None] = []
        for default in node.args.kw_defaults:
            if default is None:
                kw_defaults.append(None)
            else:
                kw_defaults.append(self.eval(default, env))
        function = MiniFunction.from_function_def(
            node, env, defaults, tuple(kw_defaults)
        )
        return env.define(node.name, function)

    def eval_Lambda(self, node: ast.Lambda, env: Environment) -> object:
        if node.args.posonlyargs:
            raise PyMiniNotImplementedError("positional-only parameters are not supported yet")
        defaults = tuple(self.eval(default, env) for default in node.args.defaults)
        kw_defaults: list[object | None] = []
        for default in node.args.kw_defaults:
            if default is None:
                kw_defaults.append(None)
            else:
                kw_defaults.append(self.eval(default, env))
        # Synthesize a FunctionDef so MiniFunction can evaluate a return body.
        ret = ast.Return(value=node.body)
        ast.copy_location(ret, node)
        func_def = ast.FunctionDef(
            name="<lambda>",
            args=node.args,
            body=[ret],
            decorator_list=[],
            returns=None,
            type_comment=None,
        )
        ast.copy_location(func_def, node)
        return MiniFunction.from_function_def(
            func_def, env, defaults, tuple(kw_defaults)
        )

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

    def eval_Raise(self, node: ast.Raise, env: Environment) -> object:
        if node.exc is None:
            raise PyMiniRuntimeError("No active exception to re-raise")
        exc = self.eval(node.exc, env)
        if isinstance(exc, BaseException):
            raise exc
        if isinstance(exc, type) and issubclass(exc, BaseException):
            raise exc()
        raise PyMiniTypeError(f"exceptions must derive from BaseException, got {exc!r}")

    def eval_Try(self, node: ast.Try, env: Environment) -> object:
        result: object = None
        pending: BaseException | None = None
        try:
            try:
                result = self.eval_block(node.body, env)
            except _CONTROL_FLOW as signal:
                pending = signal
            except Exception as exc:
                handled = False
                for handler in node.handlers:
                    if self._exception_matches(handler, exc, env):
                        if handler.name:
                            env.define(handler.name, exc)
                        try:
                            result = self.eval_block(handler.body, env)
                        except _CONTROL_FLOW as signal:
                            pending = signal
                        except Exception as handler_exc:
                            pending = handler_exc
                        finally:
                            if handler.name:
                                env.values.pop(handler.name, None)
                        handled = True
                        break
                if not handled:
                    pending = exc
            else:
                if pending is None and node.orelse:
                    try:
                        result = self.eval_block(node.orelse, env)
                    except _CONTROL_FLOW as signal:
                        pending = signal
                    except Exception as exc:
                        pending = exc
        finally:
            if node.finalbody:
                try:
                    finally_result = self.eval_block(node.finalbody, env)
                    if result is None and pending is None:
                        result = finally_result
                except _CONTROL_FLOW as signal:
                    pending = signal
                except Exception as exc:
                    pending = exc
        if pending is not None:
            raise pending
        return result

    def _exception_matches(
        self, handler: ast.ExceptHandler, exc: BaseException, env: Environment
    ) -> bool:
        if handler.type is None:
            return True
        expected = self.eval(handler.type, env)
        if isinstance(expected, tuple):
            return isinstance(exc, expected)
        if isinstance(expected, type) and issubclass(expected, BaseException):
            return isinstance(exc, expected)
        return False

    def eval_With(self, node: ast.With, env: Environment) -> object:
        if not node.items:
            return self.eval_block(node.body, env)

        managers: list[tuple[object, object]] = []
        result: object = None
        try:
            for item in node.items:
                manager = self.eval(item.context_expr, env)
                enter = self.get_attribute(manager, "__enter__")
                value = self.call_value(enter, [])
                if item.optional_vars is not None:
                    self.assign_target(item.optional_vars, value, env)
                managers.append((manager, value))
            result = self.eval_block(node.body, env)
        except _CONTROL_FLOW as signal:
            self._exit_managers(managers, None)
            raise signal
        except Exception as exc:
            suppressed = self._exit_managers(managers, exc)
            if not suppressed:
                raise
            return result
        else:
            self._exit_managers(managers, None)
            return result

    def _exit_managers(
        self,
        managers: list[tuple[object, object]],
        exc: BaseException | None,
    ) -> bool:
        """Call ``__exit__`` on managers in reverse order. Return True if suppressed."""

        suppressed = False
        exc_type: object = None if exc is None else type(exc)
        exc_val: object = exc
        exc_tb: object = None
        for manager, _value in reversed(managers):
            exit_method = self.get_attribute(manager, "__exit__")
            exit_result = self.call_value(exit_method, [exc_type, exc_val, exc_tb])
            if exc is not None and self._truthy(exit_result):
                suppressed = True
                # Subsequent exits see a suppressed exception.
                exc = None
                exc_type = None
                exc_val = None
        return suppressed

    def eval_BinOp(self, node: ast.BinOp, env: Environment) -> object:
        return self._binary_op(node.op, self.eval(node.left, env), self.eval(node.right, env))

    def eval_UnaryOp(self, node: ast.UnaryOp, env: Environment) -> object:
        value = self.eval(node.operand, env)
        unary_ops: dict[type[ast.unaryop], Callable[[object], object]] = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Not: lambda item: not self._truthy(item),
            ast.Invert: operator.invert,
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
            result = False
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

    def eval_Set(self, node: ast.Set, env: Environment) -> object:
        return {self.eval(item, env) for item in node.elts}

    def eval_Dict(self, node: ast.Dict, env: Environment) -> object:
        result: dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if key_node is None:
                raise PyMiniNotImplementedError("dict unpacking is not supported")
            result[self.eval(key_node, env)] = self.eval(value_node, env)
        return result

    def eval_ListComp(self, node: ast.ListComp, env: Environment) -> object:
        result: list[object] = []
        self._run_comprehension(node.generators, env, lambda local: result.append(self.eval(node.elt, local)))
        return result

    def eval_SetComp(self, node: ast.SetComp, env: Environment) -> object:
        result: set[object] = set()
        self._run_comprehension(node.generators, env, lambda local: result.add(self.eval(node.elt, local)))
        return result

    def eval_DictComp(self, node: ast.DictComp, env: Environment) -> object:
        result: dict[object, object] = {}

        def collect(local: Environment) -> None:
            key = self.eval(node.key, local)
            value = self.eval(node.value, local)
            result[key] = value

        self._run_comprehension(node.generators, env, collect)
        return result

    def eval_GeneratorExp(self, node: ast.GeneratorExp, env: Environment) -> object:
        # Materialize as a list for simplicity (educational subset).
        result: list[object] = []
        self._run_comprehension(
            node.generators, env, lambda local: result.append(self.eval(node.elt, local))
        )
        return iter(result)

    def _run_comprehension(
        self,
        generators: list[ast.comprehension],
        env: Environment,
        collect: Callable[[Environment], None],
    ) -> None:
        comp_env = Environment(name="comprehension", parent=env)

        def rec(index: int) -> None:
            if index == len(generators):
                collect(comp_env)
                return
            gen = generators[index]
            iter_env = env if index == 0 else comp_env
            iterable = self.eval(gen.iter, iter_env)
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"object {iterable!r} is not iterable")
            for item in iterable:
                self.assign_target(gen.target, item, comp_env)
                if all(self._truthy(self.eval(if_clause, comp_env)) for if_clause in gen.ifs):
                    rec(index + 1)

        rec(0)

    def eval_JoinedStr(self, node: ast.JoinedStr, env: Environment) -> object:
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append("" if value.value is None else str(value.value))
            elif isinstance(value, ast.FormattedValue):
                parts.append(self._format_value(value, env))
            else:
                parts.append(str(self.eval(value, env)))
        return "".join(parts)

    def eval_FormattedValue(self, node: ast.FormattedValue, env: Environment) -> object:
        return self._format_value(node, env)

    def _format_value(self, node: ast.FormattedValue, env: Environment) -> str:
        value = self.eval(node.value, env)
        conversion = node.conversion
        if conversion == ord("s"):
            value = str(value)
        elif conversion == ord("r"):
            value = repr(value)
        elif conversion == ord("a"):
            value = ascii(value)
        if node.format_spec is not None:
            spec = self.eval(node.format_spec, env)
            return format(value, str(spec))
        return format(value)

    def eval_Subscript(self, node: ast.Subscript, env: Environment) -> object:
        value = self.eval(node.value, env)
        index = self.eval_slice(node.slice, env)
        return value[index]  # type: ignore[index]

    def eval_Attribute(self, node: ast.Attribute, env: Environment) -> object:
        return self.get_attribute(self.eval(node.value, env), node.attr)

    def eval_Call(self, node: ast.Call, env: Environment) -> object:
        callee = self.eval(node.func, env)
        args: list[object] = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                starred = self.eval(arg.value, env)
                if not isinstance(starred, Iterable):
                    raise PyMiniTypeError(f"{starred!r} is not iterable")
                args.extend(list(starred))
            else:
                args.append(self.eval(arg, env))

        kwargs: dict[str, object] = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                # **mapping
                mapping = self.eval(keyword.value, env)
                if not isinstance(mapping, Mapping):
                    raise PyMiniTypeError(f"{mapping!r} is not a mapping")
                for key, value in mapping.items():
                    if not isinstance(key, str):
                        raise PyMiniTypeError("keywords must be strings")
                    if key in kwargs:
                        raise PyMiniTypeError(f"got multiple values for keyword argument {key!r}")
                    kwargs[key] = value
            else:
                if keyword.arg in kwargs:
                    raise PyMiniTypeError(
                        f"got multiple values for keyword argument {keyword.arg!r}"
                    )
                kwargs[keyword.arg] = self.eval(keyword.value, env)

        return self.call_value(callee, args, kwargs)

    def eval_Starred(self, node: ast.Starred, env: Environment) -> object:
        raise PyMiniTypeError("starred expression is not allowed here")

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
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
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
            try:
                return value.get_attr(name)
            except AttributeError:
                raise PyMiniNameError(f"{value!r} has no attribute {name!r}")
        try:
            return getattr(value, name)
        except AttributeError:
            raise PyMiniNameError(f"{value!r} has no attribute {name!r}")

    def set_attribute(self, value: object, name: str, assigned: object) -> object:
        if isinstance(value, MiniInstance | MiniClass):
            return value.set_attr(name, assigned)
        try:
            setattr(value, name, assigned)
            return assigned
        except Exception as exc:
            raise PyMiniTypeError(f"cannot set attribute {name!r} on {value!r}") from exc

    def call_value(
        self,
        callee: object,
        args: Sequence[object],
        kwargs: Mapping[str, object] | None = None,
    ) -> object:
        kwargs = kwargs or {}
        if isinstance(callee, MiniFunction | BoundMethod | MiniClass | NativeFunction):
            return callee.call(args, self, kwargs)
        if isinstance(callee, SupportsCall):
            return callee.call(args, self, kwargs)
        if callable(callee):
            if kwargs:
                return callee(*args, **dict(kwargs))
            return callee(*args)
        raise PyMiniTypeError(f"object {callee!r} is not callable")

    def _install_builtins(self) -> None:
        def _print(*values: object) -> None:
            self.stdout(" ".join(str(value) for value in values))
            return None

        def _map(func: object, *iterables: object) -> list[object]:
            # Eager map for simplicity / predictability in educational subset.
            if not iterables:
                raise PyMiniTypeError("map() must have at least two arguments")
            iterators = [iter(it) for it in iterables]  # type: ignore[arg-type]
            result: list[object] = []
            while True:
                try:
                    items = [next(it) for it in iterators]
                except StopIteration:
                    break
                result.append(self.call_value(func, items))
            return result

        def _filter(func: object, iterable: object) -> list[object]:
            result: list[object] = []
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"{iterable!r} is not iterable")
            for item in iterable:
                if func is None:
                    if self._truthy(item):
                        result.append(item)
                elif self._truthy(self.call_value(func, [item])):
                    result.append(item)
            return result

        def _sorted_fn(iterable: object, *, key: object = None, reverse: bool = False) -> list[object]:
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"{iterable!r} is not iterable")
            items = list(iterable)
            if key is None:
                return sorted(items, reverse=bool(reverse))  # type: ignore[type-var]
            return sorted(
                items,
                key=lambda item: self.call_value(key, [item]),  # type: ignore[arg-type]
                reverse=bool(reverse),
            )

        def _min_fn(*args: object, **kwargs: object) -> object:
            if len(args) == 1 and isinstance(args[0], Iterable) and not isinstance(args[0], (str, bytes)):
                return min(args[0], **kwargs)  # type: ignore[call-overload]
            return min(args, **kwargs)  # type: ignore[type-var]

        def _max_fn(*args: object, **kwargs: object) -> object:
            if len(args) == 1 and isinstance(args[0], Iterable) and not isinstance(args[0], (str, bytes)):
                return max(args[0], **kwargs)  # type: ignore[call-overload]
            return max(args, **kwargs)  # type: ignore[type-var]

        def _sum_fn(iterable: object, start: object = 0) -> object:
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"{iterable!r} is not iterable")
            return sum(iterable, start)  # type: ignore[call-overload]

        def _any_fn(iterable: object) -> bool:
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"{iterable!r} is not iterable")
            return any(self._truthy(item) for item in iterable)

        def _all_fn(iterable: object) -> bool:
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"{iterable!r} is not iterable")
            return all(self._truthy(item) for item in iterable)

        def _reversed_fn(seq: object) -> list[object]:
            return list(reversed(seq))  # type: ignore[call-overload]

        def _enumerate_fn(iterable: object, start: int = 0) -> list[tuple[int, object]]:
            if not isinstance(iterable, Iterable):
                raise PyMiniTypeError(f"{iterable!r} is not iterable")
            return list(enumerate(iterable, start=start))

        def _zip_fn(*iterables: object) -> list[tuple[object, ...]]:
            return list(zip(*iterables, strict=False))  # type: ignore[arg-type]

        def _isinstance_fn(obj: object, classinfo: object) -> bool:
            if isinstance(classinfo, tuple):
                return any(_isinstance_fn(obj, item) for item in classinfo)
            if isinstance(classinfo, MiniClass):
                if isinstance(obj, MiniInstance):
                    current: MiniClass | None = obj.klass
                    while current is not None:
                        if current is classinfo:
                            return True
                        current = current.bases[0] if current.bases else None
                    return False
                return False
            if isinstance(classinfo, type):
                return isinstance(obj, classinfo)
            raise PyMiniTypeError("isinstance() arg 2 must be a type or tuple of types")

        def _type_fn(obj: object) -> object:
            if isinstance(obj, MiniInstance):
                return obj.klass
            if isinstance(obj, MiniClass):
                return type
            return type(obj)

        def _hasattr_fn(obj: object, name: object) -> bool:
            if not isinstance(name, str):
                raise PyMiniTypeError("hasattr(): attribute name must be string")
            try:
                self.get_attribute(obj, name)
                return True
            except Exception:
                return False

        def _getattr_fn(obj: object, name: object, default: object = _MISSING) -> object:
            if not isinstance(name, str):
                raise PyMiniTypeError("getattr(): attribute name must be string")
            try:
                return self.get_attribute(obj, name)
            except Exception:
                if default is not _MISSING:
                    return default
                raise

        def _setattr_fn(obj: object, name: object, value: object) -> None:
            if not isinstance(name, str):
                raise PyMiniTypeError("setattr(): attribute name must be string")
            self.set_attribute(obj, name, value)
            return None

        def _abs_fn(x: object) -> object:
            return abs(x)  # type: ignore[arg-type]

        def _round_fn(number: object, ndigits: object | None = None) -> object:
            if ndigits is None:
                return round(number)  # type: ignore[call-overload]
            return round(number, ndigits)  # type: ignore[call-overload]

        # Use real types for int/str/... so isinstance/type work naturally.
        builtins: dict[str, object] = {
            "print": NativeFunction("print", _print),
            "len": NativeFunction("len", len),
            "range": NativeFunction("range", range),
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "enumerate": NativeFunction("enumerate", _enumerate_fn),
            "zip": NativeFunction("zip", _zip_fn),
            "map": NativeFunction("map", _map),
            "filter": NativeFunction("filter", _filter),
            "sorted": NativeFunction("sorted", _sorted_fn),
            "reversed": NativeFunction("reversed", _reversed_fn),
            "sum": NativeFunction("sum", _sum_fn),
            "min": NativeFunction("min", _min_fn),
            "max": NativeFunction("max", _max_fn),
            "any": NativeFunction("any", _any_fn),
            "all": NativeFunction("all", _all_fn),
            "abs": NativeFunction("abs", _abs_fn),
            "round": NativeFunction("round", _round_fn),
            "isinstance": NativeFunction("isinstance", _isinstance_fn),
            "type": NativeFunction("type", _type_fn),
            "hasattr": NativeFunction("hasattr", _hasattr_fn),
            "getattr": NativeFunction("getattr", _getattr_fn),
            "setattr": NativeFunction("setattr", _setattr_fn),
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "RuntimeError": RuntimeError,
            "ZeroDivisionError": ZeroDivisionError,
            "AssertionError": AssertionError,
            "StopIteration": StopIteration,
            "help": NativeFunction("help", self._help),
            "dis": NativeFunction("dis", self._dis),
        }
        for name, value in builtins.items():
            self.global_env.define(name, value)

    def _help(self, *values: object) -> None:
        if not values:
            self.stdout(
                "PyMini help\n"
                "  evaluate expressions, define functions/classes, use control flow.\n"
                "  Builtins: print, len, range, list/dict/set/tuple, str/int/float/bool,\n"
                "            enumerate, zip, map, filter, sorted, reversed, sum, min, max,\n"
                "            any, all, abs, round, isinstance, type, hasattr/getattr/setattr,\n"
                "            Exception, AssertionError, help, dis\n"
                "  Features: lambda, assert, kwargs/**kwargs, yield/generators,\n"
                "            try/except/finally, with, *args, defaults, comprehensions,\n"
                "            f-strings (AST parser), bytecode disassembler.\n"
                "  REPL: dis(\"code\") shows bytecode; help() shows this message.\n"
                "  CLI:  pymini run file.py | eval -c '...' | disasm | repl | version | debug"
            )
            return None
        target = values[0]
        self.stdout(f"Help on {target!r}: {type(target).__name__} object")
        return None

    def _dis(self, *values: object) -> str:
        if not values:
            raise PyMiniTypeError("dis() takes exactly one string argument")
        source = values[0]
        if not isinstance(source, str):
            raise PyMiniTypeError("dis() argument must be a string of PyMini source")
        from pymini.compiler.bytecode import disassemble_source

        text = disassemble_source(source)
        self.stdout(text)
        return text

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise PyMiniRuntimeError(
                "execution step limit exceeded", frames=self.snapshot_frames()
            )

    def _binary_op(self, op: ast.operator, left: object, right: object) -> object:
        binary_ops: dict[type[ast.operator], Callable[[object, object], object]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.BitAnd: operator.and_,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
        }
        for op_type, func in binary_ops.items():
            if isinstance(op, op_type):
                try:
                    return func(left, right)
                except Exception as exc:
                    raise PyMiniTypeError(
                        str(exc) or f"unsupported operand types for {op_type.__name__}",
                        frames=self.snapshot_frames(),
                    ) from exc
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


class _Missing:
    """Sentinel for getattr default."""


_MISSING = _Missing()
