"""A small hand-written lexer for the recursive descent parser."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final

from pymini.runtime.errors import PyMiniSyntaxError


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


class TokenKind:
    NAME: Final = "NAME"
    NUMBER: Final = "NUMBER"
    STRING: Final = "STRING"
    OP: Final = "OP"
    NEWLINE: Final = "NEWLINE"
    INDENT: Final = "INDENT"
    DEDENT: Final = "DEDENT"
    EOF: Final = "EOF"


KEYWORDS: Final = {
    "and",
    "as",
    "break",
    "class",
    "continue",
    "def",
    "else",
    "False",
    "for",
    "from",
    "if",
    "import",
    "in",
    "is",
    "None",
    "not",
    "or",
    "pass",
    "return",
    "True",
    "while",
}

TWO_CHAR_OPS: Final = {
    "==",
    "!=",
    "<=",
    ">=",
    "//",
    "**",
    "+=",
    "-=",
    "*=",
    "/=",
    "%=",
}

ONE_CHAR_OPS: Final = set("()[]{}:,.+-*/%=<>")


class Lexer:
    """Lex enough Python syntax for the milestone parser.

    The lexer intentionally keeps keyword tokens as ``NAME`` with keyword values.
    The parser decides when a name is acting as a keyword.
    """

    def tokenize(self, source: str) -> list[Token]:
        tokens: list[Token] = []
        indent_stack = [0]

        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            line = raw_line.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue

            indent = self._indent_width(line)
            stripped = line[indent:]
            if stripped and indent > indent_stack[-1]:
                indent_stack.append(indent)
                tokens.append(Token(TokenKind.INDENT, "", line_number, 1))
            while indent < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token(TokenKind.DEDENT, "", line_number, indent + 1))
            if indent != indent_stack[-1]:
                raise PyMiniSyntaxError(f"inconsistent indentation at line {line_number}")

            self._lex_line(line, line_number, indent, tokens)
            tokens.append(Token(TokenKind.NEWLINE, "", line_number, len(line) + 1))

        final_line = max(source.count("\n") + 1, 1)
        while len(indent_stack) > 1:
            indent_stack.pop()
            tokens.append(Token(TokenKind.DEDENT, "", final_line, 1))
        tokens.append(Token(TokenKind.EOF, "", final_line, 1))
        return tokens

    @staticmethod
    def literal_value(token: Token) -> str | bytes | int | float:
        if token.kind == TokenKind.STRING:
            value = ast.literal_eval(token.value)
            if isinstance(value, (str, bytes)):
                return value
            raise PyMiniSyntaxError("string token did not produce a string literal")
        if token.kind == TokenKind.NUMBER:
            return float(token.value) if "." in token.value else int(token.value)
        raise PyMiniSyntaxError(f"token {token.kind} has no literal value")

    def _lex_line(self, line: str, line_number: int, start: int, tokens: list[Token]) -> None:
        index = start
        while index < len(line):
            char = line[index]
            column = index + 1
            if char in " \t":
                index += 1
                continue
            if char == "#":
                break
            if char.isalpha() or char == "_":
                end = index + 1
                while end < len(line) and (line[end].isalnum() or line[end] == "_"):
                    end += 1
                tokens.append(Token(TokenKind.NAME, line[index:end], line_number, column))
                index = end
                continue
            if char.isdigit():
                end = index + 1
                seen_dot = False
                while end < len(line):
                    nxt = line[end]
                    if nxt == "." and not seen_dot:
                        seen_dot = True
                        end += 1
                    elif nxt.isdigit():
                        end += 1
                    else:
                        break
                tokens.append(Token(TokenKind.NUMBER, line[index:end], line_number, column))
                index = end
                continue
            if char in {"'", '"'}:
                end = self._string_end(line, index, line_number)
                tokens.append(Token(TokenKind.STRING, line[index:end], line_number, column))
                index = end
                continue
            two = line[index : index + 2]
            if two in TWO_CHAR_OPS:
                tokens.append(Token(TokenKind.OP, two, line_number, column))
                index += 2
                continue
            if char in ONE_CHAR_OPS:
                tokens.append(Token(TokenKind.OP, char, line_number, column))
                index += 1
                continue
            raise PyMiniSyntaxError(f"unexpected character {char!r} at line {line_number}")

    @staticmethod
    def _indent_width(line: str) -> int:
        count = 0
        for char in line:
            if char == " ":
                count += 1
            elif char == "\t":
                raise PyMiniSyntaxError("tabs are not supported for indentation")
            else:
                break
        return count

    @staticmethod
    def _string_end(line: str, start: int, line_number: int) -> int:
        quote = line[start]
        index = start + 1
        escaped = False
        while index < len(line):
            char = line[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                return index + 1
            index += 1
        raise PyMiniSyntaxError(f"unterminated string literal at line {line_number}")
