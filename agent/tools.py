"""Custom tools exposed to the agent through an in-process MCP server.

Add a new tool by writing an async function decorated with ``@tool`` and
appending it to ``ALL_TOOLS``. Claude sees each one as ``mcp__assistant__<name>``.
"""

from __future__ import annotations

import ast
import math
import operator
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from claude_agent_sdk import create_sdk_mcp_server, tool

SERVER_NAME = "assistant"
NOTES_DIR = Path(os.environ.get("AGENT_NOTES_DIR", "notes"))


def _text(text: str, *, error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if error:
        result["is_error"] = True
    return result


# --- current time -----------------------------------------------------------

@tool(
    "get_current_time",
    "Get the current date and time. Optionally pass an IANA timezone "
    "such as 'Europe/London' or 'America/New_York' (defaults to UTC).",
    {"timezone": str},
)
async def get_current_time(args: dict[str, Any]) -> dict[str, Any]:
    tz_name = args.get("timezone") or "UTC"
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except (ZoneInfoNotFoundError, ValueError):
        return _text(f"Unknown timezone: {tz_name!r}", error=True)
    return _text(now.strftime(f"%A %Y-%m-%d %H:%M:%S ({tz_name}, UTC%z)"))


# --- calculator -------------------------------------------------------------

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    name: getattr(math, name)
    for name in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "floor", "ceil")
} | {"abs": abs, "round": round}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expression: str) -> float | int:
    """Evaluate an arithmetic expression without using ``eval``."""

    def ev(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("exponent too large")
            return _BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS
            and not node.keywords
        ):
            return _FUNCS[node.func.id](*(ev(a) for a in node.args))
        raise ValueError(f"unsupported expression: {ast.dump(node)[:60]}")

    return ev(ast.parse(expression, mode="eval"))


@tool(
    "calculator",
    "Evaluate an arithmetic expression exactly, e.g. '(3.5 * 2) ** 3 / sqrt(16)'. "
    "Supports + - * / // % **, parentheses, pi, e, and sqrt/log/log10/exp/"
    "sin/cos/tan/floor/ceil/abs/round. Use this instead of mental math.",
    {"expression": str},
)
async def calculator(args: dict[str, Any]) -> dict[str, Any]:
    expr = args["expression"]
    try:
        return _text(f"{expr} = {safe_eval(expr)}")
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError) as exc:
        return _text(f"Could not evaluate {expr!r}: {exc}", error=True)


# --- notes ------------------------------------------------------------------

def _note_path(title: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        raise ValueError("title must contain letters or digits")
    return NOTES_DIR / f"{slug[:80]}.md"


@tool(
    "save_note",
    "Save a markdown note the user can come back to later. "
    "Saving with an existing title overwrites that note.",
    {"title": str, "content": str},
)
async def save_note(args: dict[str, Any]) -> dict[str, Any]:
    try:
        path = _note_path(args["title"])
    except ValueError as exc:
        return _text(str(exc), error=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {args['title']}\n\n{args['content']}\n", encoding="utf-8")
    return _text(f"Saved note to {path}")


@tool("list_notes", "List the titles of all saved notes.", {})
async def list_notes(args: dict[str, Any]) -> dict[str, Any]:
    paths = sorted(NOTES_DIR.glob("*.md")) if NOTES_DIR.exists() else []
    if not paths:
        return _text("No notes saved yet.")
    return _text("\n".join(f"- {p.stem}" for p in paths))


@tool("read_note", "Read a saved note by its title.", {"title": str})
async def read_note(args: dict[str, Any]) -> dict[str, Any]:
    try:
        path = _note_path(args["title"])
    except ValueError as exc:
        return _text(str(exc), error=True)
    if not path.exists():
        return _text(f"No note titled {args['title']!r}. Try list_notes.", error=True)
    return _text(path.read_text(encoding="utf-8"))


ALL_TOOLS = [get_current_time, calculator, save_note, list_notes, read_note]
TOOL_NAMES = [f"mcp__{SERVER_NAME}__{t.name}" for t in ALL_TOOLS]

server = create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=ALL_TOOLS)
