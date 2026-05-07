"""Recursive descent parser for a compact Python subset."""

from __future__ import annotations

import ast
from collections.abc import Callable

from pymini.parser.lexer import Lexer, Token, TokenKind
from pymini.runtime.errors import PyMiniSyntaxError


class HandwrittenParser:
    """Parse a useful Python subset into CPython-compatible AST nodes."""

    def __init__(self) -> None:
        self.tokens: list[Token] = []
        self.current = 0
        self.lexer = Lexer()

    def parse(self, source: str) -> ast.Module:
        self.tokens = self.lexer.tokenize(source)
        self.current = 0
        body: list[ast.stmt] = []
        self._skip_newlines()
        while not self._check(TokenKind.EOF):
            body.append(self._statement())
            self._skip_newlines()
        module = ast.Module(body=body, type_ignores=[])
        return ast.fix_missing_locations(module)

    def _statement(self) -> ast.stmt:
        if self._match_keyword("if"):
            return self._if_statement()
        if self._match_keyword("while"):
            return self._while_statement()
        if self._match_keyword("for"):
            return self._for_statement()
        if self._match_keyword("def"):
            return self._function_definition()
        if self._match_keyword("class"):
            return self._class_definition()
        if self._match_keyword("return"):
            value = None if self._at_line_end() else self._expression()
            return ast.Return(value=value)
        if self._match_keyword("break"):
            return ast.Break()
        if self._match_keyword("continue"):
            return ast.Continue()
        if self._match_keyword("pass"):
            return ast.Pass()
        if self._match_keyword("import"):
            return self._import_statement()
        if self._match_keyword("from"):
            return self._from_import_statement()
        return self._assignment_or_expression()

    def _if_statement(self) -> ast.If:
        test = self._expression()
        body = self._suite()
        orelse: list[ast.stmt] = []
        if self._match_keyword("elif"):
            nested = self._if_statement()
            orelse = [nested]
        elif self._match_keyword("else"):
            orelse = self._suite()
        return ast.If(test=test, body=body, orelse=orelse)

    def _while_statement(self) -> ast.While:
        test = self._expression()
        body = self._suite()
        return ast.While(test=test, body=body, orelse=[])

    def _for_statement(self) -> ast.For:
        target = self._store_context(self._expression())
        self._consume_keyword("in", "expected 'in' in for statement")
        iterable = self._expression()
        body = self._suite()
        return ast.For(target=target, iter=iterable, body=body, orelse=[], type_comment=None)

    def _function_definition(self) -> ast.FunctionDef:
        name = self._consume(TokenKind.NAME, "expected function name").value
        self._consume_op("(", "expected '(' after function name")
        parameters: list[ast.arg] = []
        if not self._check_op(")"):
            while True:
                token = self._consume(TokenKind.NAME, "expected parameter name")
                parameters.append(ast.arg(arg=token.value))
                if not self._match_op(","):
                    break
        self._consume_op(")", "expected ')' after parameters")
        body = self._suite()
        args = ast.arguments(
            posonlyargs=[],
            args=parameters,
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        )
        return ast.FunctionDef(
            name=name,
            args=args,
            body=body,
            decorator_list=[],
            returns=None,
            type_comment=None,
        )

    def _class_definition(self) -> ast.ClassDef:
        name = self._consume(TokenKind.NAME, "expected class name").value
        bases: list[ast.expr] = []
        if self._match_op("("):
            if not self._check_op(")"):
                while True:
                    bases.append(self._expression())
                    if not self._match_op(","):
                        break
            self._consume_op(")", "expected ')' after base classes")
        body = self._suite()
        return ast.ClassDef(
            name=name,
            bases=bases,
            keywords=[],
            body=body,
            decorator_list=[],
        )

    def _import_statement(self) -> ast.Import:
        return ast.Import(names=self._aliases())

    def _from_import_statement(self) -> ast.ImportFrom:
        module = self._dotted_name()
        self._consume_keyword("import", "expected 'import' in from-import statement")
        return ast.ImportFrom(module=module, names=self._aliases(), level=0)

    def _aliases(self) -> list[ast.alias]:
        aliases: list[ast.alias] = []
        while True:
            name = self._dotted_name()
            asname = None
            if self._match_keyword("as"):
                asname = self._consume(TokenKind.NAME, "expected alias name").value
            aliases.append(ast.alias(name=name, asname=asname))
            if not self._match_op(","):
                break
        return aliases

    def _assignment_or_expression(self) -> ast.stmt:
        expr = self._expression()
        if self._match_op("="):
            value = self._expression()
            return ast.Assign(targets=[self._store_context(expr)], value=value)
        aug_ops: dict[str, ast.operator] = {
            "+=": ast.Add(),
            "-=": ast.Sub(),
            "*=": ast.Mult(),
            "/=": ast.Div(),
            "%=": ast.Mod(),
        }
        for token, op in aug_ops.items():
            if self._match_op(token):
                return ast.AugAssign(
                    target=self._store_context(expr),
                    op=op,
                    value=self._expression(),
                )
        return ast.Expr(value=expr)

    def _suite(self) -> list[ast.stmt]:
        self._consume_op(":", "expected ':' before block")
        if self._match(TokenKind.NEWLINE):
            self._consume(TokenKind.INDENT, "expected indented block")
            body: list[ast.stmt] = []
            self._skip_newlines()
            while not self._check(TokenKind.DEDENT) and not self._check(TokenKind.EOF):
                body.append(self._statement())
                self._skip_newlines()
            self._consume(TokenKind.DEDENT, "expected end of indented block")
            if not body:
                raise PyMiniSyntaxError("empty blocks are not supported; use pass")
            return body
        return [self._statement()]

    def _expression(self) -> ast.expr:
        return self._or()

    def _or(self) -> ast.expr:
        values = [self._and()]
        while self._match_keyword("or"):
            values.append(self._and())
        if len(values) == 1:
            return values[0]
        return ast.BoolOp(op=ast.Or(), values=values)

    def _and(self) -> ast.expr:
        values = [self._not()]
        while self._match_keyword("and"):
            values.append(self._not())
        if len(values) == 1:
            return values[0]
        return ast.BoolOp(op=ast.And(), values=values)

    def _not(self) -> ast.expr:
        if self._match_keyword("not"):
            return ast.UnaryOp(op=ast.Not(), operand=self._not())
        return self._comparison()

    def _comparison(self) -> ast.expr:
        left = self._sum()
        ops: list[ast.cmpop] = []
        comparators: list[ast.expr] = []
        while True:
            operator = self._comparison_operator()
            if operator is None:
                break
            ops.append(operator)
            comparators.append(self._sum())
        if not ops:
            return left
        return ast.Compare(left=left, ops=ops, comparators=comparators)

    def _comparison_operator(self) -> ast.cmpop | None:
        op_map: dict[str, ast.cmpop] = {
            "==": ast.Eq(),
            "!=": ast.NotEq(),
            "<": ast.Lt(),
            "<=": ast.LtE(),
            ">": ast.Gt(),
            ">=": ast.GtE(),
        }
        for text, op in op_map.items():
            if self._match_op(text):
                return op
        if self._match_keyword("is"):
            if self._match_keyword("not"):
                return ast.IsNot()
            return ast.Is()
        if self._match_keyword("not"):
            self._consume_keyword("in", "expected 'in' after 'not'")
            return ast.NotIn()
        if self._match_keyword("in"):
            return ast.In()
        return None

    def _sum(self) -> ast.expr:
        return self._binary(self._term, {"+": ast.Add, "-": ast.Sub})

    def _term(self) -> ast.expr:
        return self._binary(
            self._factor,
            {"*": ast.Mult, "/": ast.Div, "//": ast.FloorDiv, "%": ast.Mod},
        )

    def _factor(self) -> ast.expr:
        if self._match_op("+"):
            return ast.UnaryOp(op=ast.UAdd(), operand=self._factor())
        if self._match_op("-"):
            return ast.UnaryOp(op=ast.USub(), operand=self._factor())
        return self._power()

    def _power(self) -> ast.expr:
        left = self._postfix()
        if self._match_op("**"):
            return ast.BinOp(left=left, op=ast.Pow(), right=self._factor())
        return left

    def _postfix(self) -> ast.expr:
        node = self._atom()
        while True:
            if self._match_op("("):
                args: list[ast.expr] = []
                if not self._check_op(")"):
                    while True:
                        args.append(self._expression())
                        if not self._match_op(","):
                            break
                self._consume_op(")", "expected ')' after arguments")
                node = ast.Call(func=node, args=args, keywords=[])
                continue
            if self._match_op("["):
                index = self._expression()
                self._consume_op("]", "expected ']' after subscript")
                node = ast.Subscript(value=node, slice=index, ctx=ast.Load())
                continue
            if self._match_op("."):
                attr = self._consume(TokenKind.NAME, "expected attribute name").value
                node = ast.Attribute(value=node, attr=attr, ctx=ast.Load())
                continue
            break
        return node

    def _atom(self) -> ast.expr:
        if self._match(TokenKind.NUMBER):
            return ast.Constant(value=Lexer.literal_value(self._previous()))
        if self._match(TokenKind.STRING):
            return ast.Constant(value=Lexer.literal_value(self._previous()))
        if self._match_keyword("True"):
            return ast.Constant(value=True)
        if self._match_keyword("False"):
            return ast.Constant(value=False)
        if self._match_keyword("None"):
            return ast.Constant(value=None)
        if self._match(TokenKind.NAME):
            return ast.Name(id=self._previous().value, ctx=ast.Load())
        if self._match_op("("):
            if self._match_op(")"):
                return ast.Tuple(elts=[], ctx=ast.Load())
            expr = self._expression()
            if self._match_op(","):
                items = [expr]
                if not self._check_op(")"):
                    while True:
                        items.append(self._expression())
                        if not self._match_op(","):
                            break
                self._consume_op(")", "expected ')' after tuple")
                return ast.Tuple(elts=items, ctx=ast.Load())
            self._consume_op(")", "expected ')' after grouped expression")
            return expr
        if self._match_op("["):
            items: list[ast.expr] = []
            if not self._check_op("]"):
                while True:
                    items.append(self._expression())
                    if not self._match_op(","):
                        break
            self._consume_op("]", "expected ']' after list")
            return ast.List(elts=items, ctx=ast.Load())
        if self._match_op("{"):
            keys: list[ast.expr | None] = []
            values: list[ast.expr] = []
            if not self._check_op("}"):
                while True:
                    keys.append(self._expression())
                    self._consume_op(":", "expected ':' in dict literal")
                    values.append(self._expression())
                    if not self._match_op(","):
                        break
            self._consume_op("}", "expected '}' after dict")
            return ast.Dict(keys=keys, values=values)
        token = self._peek()
        raise PyMiniSyntaxError(f"expected expression at line {token.line}, column {token.column}")

    def _binary(
        self,
        operand: Callable[[], ast.expr],
        operators: dict[str, type[ast.operator]],
    ) -> ast.expr:
        expr = operand()
        while self._check(TokenKind.OP) and self._peek().value in operators:
            op_token = self._advance()
            right = operand()
            expr = ast.BinOp(left=expr, op=operators[op_token.value](), right=right)
        return expr

    def _store_context(self, node: ast.expr) -> ast.expr:
        if isinstance(node, ast.Name):
            node.ctx = ast.Store()
            return node
        if isinstance(node, ast.Attribute):
            node.ctx = ast.Store()
            return node
        if isinstance(node, ast.Subscript):
            node.ctx = ast.Store()
            return node
        if isinstance(node, ast.Tuple):
            node.ctx = ast.Store()
            node.elts = [self._store_context(item) for item in node.elts]
            return node
        if isinstance(node, ast.List):
            node.ctx = ast.Store()
            node.elts = [self._store_context(item) for item in node.elts]
            return node
        raise PyMiniSyntaxError("invalid assignment target")

    def _dotted_name(self) -> str:
        parts = [self._consume(TokenKind.NAME, "expected name").value]
        while self._match_op("."):
            parts.append(self._consume(TokenKind.NAME, "expected name after '.'").value)
        return ".".join(parts)

    def _skip_newlines(self) -> None:
        while self._match(TokenKind.NEWLINE):
            pass

    def _at_line_end(self) -> bool:
        return (
            self._check(TokenKind.NEWLINE)
            or self._check(TokenKind.DEDENT)
            or self._check(TokenKind.EOF)
        )

    def _match_keyword(self, value: str) -> bool:
        if self._check(TokenKind.NAME) and self._peek().value == value:
            self._advance()
            return True
        return False

    def _consume_keyword(self, value: str, message: str) -> Token:
        if self._match_keyword(value):
            return self._previous()
        raise self._error(message)

    def _match_op(self, value: str) -> bool:
        if self._check_op(value):
            self._advance()
            return True
        return False

    def _consume_op(self, value: str, message: str) -> Token:
        if self._match_op(value):
            return self._previous()
        raise self._error(message)

    def _check_op(self, value: str) -> bool:
        return self._check(TokenKind.OP) and self._peek().value == value

    def _match(self, kind: str) -> bool:
        if self._check(kind):
            self._advance()
            return True
        return False

    def _consume(self, kind: str, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        raise self._error(message)

    def _check(self, kind: str) -> bool:
        if self._is_at_end():
            return kind == TokenKind.EOF
        return self._peek().kind == kind

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.current += 1
        return self._previous()

    def _is_at_end(self) -> bool:
        return self._peek().kind == TokenKind.EOF

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    def _error(self, message: str) -> PyMiniSyntaxError:
        token = self._peek()
        return PyMiniSyntaxError(f"{message} at line {token.line}, column {token.column}")
