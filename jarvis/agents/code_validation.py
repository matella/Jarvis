"""Syntax-validate code the model generates — execute-to-verify's risk-free sibling.

Parsing a fenced ```python / ```json block (ast.parse / json.loads) catches a big class of coding
mistakes — unbalanced brackets, bad indentation, invalid literals, typos — with ZERO execution, so
no sandbox and no security surface. The conversation agent uses it to re-ask the coder once when the
first answer's code doesn't parse. Pure functions, fully unit-testable, no I/O.
"""

from __future__ import annotations

import ast
import json
import re

_FENCE_RE = re.compile(r"```([a-zA-Z0-9_+-]*)[ \t]*\n(.*?)```", re.DOTALL)
_PY_LANGS = {"py", "python", "python3"}
_JSON_LANGS = {"json", "json5", "jsonc"}


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Every fenced code block as (lang_lowercased, source). Unlabelled fences → lang ''."""
    return [(m.group(1).lower(), m.group(2)) for m in _FENCE_RE.finditer(text)]


def validate_blocks(blocks: list[tuple[str, str]]) -> list[str]:
    """Human-readable syntax issues across the blocks we can statically check (Python, JSON).

    Blocks in other languages (or unlabelled) are skipped — we only flag what we can prove wrong,
    never guess. Empty result = nothing provably broken.
    """
    issues: list[str] = []
    for lang, code in blocks:
        if lang in _PY_LANGS:
            try:
                ast.parse(code)
            except SyntaxError as exc:
                issues.append(f"Python block: {exc.msg} (line {exc.lineno})")
        elif lang in _JSON_LANGS:
            try:
                json.loads(code)
            except json.JSONDecodeError as exc:
                issues.append(f"JSON block: {exc.msg} (line {exc.lineno})")
    return issues


def syntax_issues(markdown: str) -> list[str]:
    """Convenience: extract + validate in one call."""
    return validate_blocks(extract_code_blocks(markdown))
