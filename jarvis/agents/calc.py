"""Exact computation (#21) — never let the LLM do arithmetic; evaluate it deterministically.

A small, SAFE expression evaluator (AST whitelist — no `eval`, no names, no calls except a handful
of math funcs) plus conservative detection of "this is just a calculation" questions. Routing a pure
arithmetic ask here gives an exact, instant, inference-free answer and removes a whole class of
model errors. Detection is intentionally strict: it only fires when the utterance is essentially an
arithmetic expression, so word problems and code questions still go to the model.
"""

from __future__ import annotations

import ast
import math
import operator
import re

# Allowed binary/unary operators → their implementations. Everything else is rejected.
_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "log": math.log, "log2": math.log2, "log10": math.log10, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "factorial": math.factorial,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}

# A query is "math" only if, after stripping polite lead-ins, it's essentially an expression.
_LEAD_RE = re.compile(
    r"^(?:what(?:'s| is)|whats|calculate|compute|evaluate|how much is|what does|tell me)\b"
    r"\s*", re.I,
)
_EXPR_CHARS_RE = re.compile(r"^[\d\s+\-*/%^().,]+(?:=\s*)?\??$")
_PERCENT_OF_RE = re.compile(r"^\s*([\d.]+)\s*%\s*of\s*([\d.]+)\s*\??$", re.I)


class _UnsafeExpression(Exception):
    """The expression used a construct outside the whitelist."""


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise _UnsafeExpression("non-numeric constant")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise _UnsafeExpression("keyword args not allowed")
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise _UnsafeExpression(f"disallowed node {type(node).__name__}")


def evaluate(expr: str) -> float:
    """Safely evaluate an arithmetic expression. Raises on unsafe/invalid input."""
    expr = expr.strip().rstrip("=?").strip().replace("^", "**")
    tree = ast.parse(expr, mode="eval")
    return _eval(tree)


def _extract_expression(text: str) -> str | None:
    """Pull a pure-arithmetic expression from the utterance, or None if it isn't one."""
    stripped = _LEAD_RE.sub("", text.strip()).strip()
    pct = _PERCENT_OF_RE.match(stripped)
    if pct:
        return f"{pct.group(1)}/100*{pct.group(2)}"
    if stripped and _EXPR_CHARS_RE.match(stripped) and any(c.isdigit() for c in stripped):
        # require an actual operator so a bare number ("what is 5") isn't treated as a calc
        if re.search(r"[+\-*/%^]", stripped):
            return stripped
    return None


def looks_like_math(text: str) -> bool:
    return _extract_expression(text) is not None


def _format(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.6g}"


def compute(text: str) -> str | None:
    """Deterministic answer for a pure calculation, or None if it isn't one / can't be evaluated."""
    expr = _extract_expression(text)
    if expr is None:
        return None
    try:
        return _format(evaluate(expr))
    except (_UnsafeExpression, SyntaxError, ValueError, ZeroDivisionError,
            OverflowError, TypeError):
        return None
