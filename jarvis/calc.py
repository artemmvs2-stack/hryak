"""Безопасный калькулятор для голосовых команд."""
from __future__ import annotations

import ast
import operator
import re

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _to_expression(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(
        r"^\s*(?:посчитай|вычисли|сколько\s+будет|чему\s+равно|"
        r"сколько\s+это|посчитай-ка)\s*",
        "",
        text,
    )
    text = re.sub(r"\bв\s+квадрате\b", "**2", text)
    text = re.sub(r"\bв\s+кубе\b", "**3", text)
    text = re.sub(r"\bв\s+степени\b", "**", text)
    text = re.sub(
        r"\b(?:умножить|умножь|помножить|помножь)\s+на\b",
        "*",
        text,
    )
    text = re.sub(
        r"\b(?:разделить|раздели|поделить|подели|делить)\s+на\b",
        "/",
        text,
    )
    text = re.sub(r"\b(?:прибавить|плюс)\b", "+", text)
    text = re.sub(r"\b(?:отнять|минус)\b", "-", text)
    text = re.sub(r"\b(?:умножить|умножь|помножить|помножь)\b", "*", text)
    text = re.sub(r"\b(?:разделить|раздели|поделить|подели|делить)\b", "/", text)
    text = re.sub(r"(\d)\s*[хx]\s*(\d)", r"\1*\2", text)
    text = text.replace(",", ".")
    text = re.sub(r"[^0-9+\-*/().%\s]", "", text)
    return re.sub(r"\s+", "", text)


def evaluate(text: str) -> float | int | None:
    """Вычисляет арифметическое выражение. None — это не выражение."""
    expression = _to_expression(text)
    if not expression or not re.search(r"\d", expression):
        return None
    if len(expression) > 120:
        return None

    def _eval(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("bad constant")
        if isinstance(node, ast.UnaryOp):
            value = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
            raise ValueError("bad unary")
        if isinstance(node, ast.BinOp):
            op = _OPS.get(type(node.op))
            if op is None:
                raise ValueError("bad operator")
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("too big")
            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
                raise ValueError("division by zero")
            return op(left, right)
        raise ValueError("bad expression")

    try:
        return _eval(ast.parse(expression, mode="eval"))
    except Exception:  # noqa: BLE001
        return None


def format_result(value: float | int) -> str:
    if isinstance(value, float):
        if abs(value) < 1e15 and float(value).is_integer():
            value = int(value)
        else:
            value = round(value, 6)
    text = f"{value}"
    return text.replace(".", ",")
