import pytest

from agent import tools
from agent.cli import build_options


@pytest.fixture(autouse=True)
def notes_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "NOTES_DIR", tmp_path / "notes")


def text_of(result):
    return result["content"][0]["text"]


@pytest.mark.parametrize(
    "expr, expected",
    [("2 + 3 * 4", 14), ("(3.5 * 2) ** 2", 49.0), ("sqrt(16) + abs(-2)", 6.0), ("-pi", -3.141592653589793)],
)
def test_safe_eval(expr, expected):
    assert tools.safe_eval(expr) == pytest.approx(expected)


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "2 ** 100000", "x + 1"])
def test_safe_eval_rejects(expr):
    with pytest.raises(ValueError):
        tools.safe_eval(expr)


async def test_calculator_tool():
    assert text_of(await tools.calculator.handler({"expression": "10 / 4"})) == "10 / 4 = 2.5"
    bad = await tools.calculator.handler({"expression": "1 / 0"})
    assert bad["is_error"] is True


async def test_current_time():
    assert "UTC" in text_of(await tools.get_current_time.handler({}))
    assert (await tools.get_current_time.handler({"timezone": "Not/AZone"}))["is_error"]


async def test_notes_roundtrip():
    assert text_of(await tools.list_notes.handler({})) == "No notes saved yet."
    await tools.save_note.handler({"title": "Shopping List!", "content": "- eggs"})
    assert text_of(await tools.list_notes.handler({})) == "- shopping-list"
    note = text_of(await tools.read_note.handler({"title": "shopping list"}))
    assert "- eggs" in note
    assert (await tools.read_note.handler({"title": "missing"}))["is_error"]
    assert (await tools.save_note.handler({"title": "../..", "content": "x"}))["is_error"]


def test_options_gate_risky_tools():
    gated = build_options("claude-opus-5", allow_all=False)
    assert "Bash" not in gated.allowed_tools
    assert gated.can_use_tool is not None
    assert "mcp__assistant__calculator" in gated.allowed_tools

    open_ = build_options("claude-opus-5", allow_all=True)
    assert "Bash" in open_.allowed_tools
    assert open_.can_use_tool is None
