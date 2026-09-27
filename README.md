# Agent

A general-purpose command-line assistant built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk). It chats in your terminal, searches the web, reads files, does exact math, and keeps notes. It asks for your OK before it writes files or runs shell commands.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export ANTHROPIC_API_KEY=sk-ant-...   # see .env.example
```

## Usage

```bash
agent                                  # interactive chat (/clear resets, /exit quits)
agent "what's 18% tip on $86.40?"      # one-shot prompt
agent -v                               # show tool inputs and cost per turn
agent --yes                            # auto-approve Write/Edit/Bash (use with care)
agent --model claude-sonnet-5          # or set AGENT_MODEL
```

## Tools

| Tool | Source | Approval |
|---|---|---|
| `Read`, `Glob`, `Grep` | built-in | automatic |
| `WebSearch`, `WebFetch` | built-in | automatic |
| `Write`, `Edit`, `Bash` | built-in | asks each time (unless `--yes`) |
| `get_current_time`, `calculator` | `agent/tools.py` | automatic |
| `save_note`, `list_notes`, `read_note` | `agent/tools.py` (saved in `./notes/`) | automatic |

## Extending it

- **Add a tool:** write an `async` function with `@tool(name, description, schema)` in `agent/tools.py` and add it to `ALL_TOOLS`. It returns `{"content": [{"type": "text", "text": ...}]}`, plus `"is_error": True` on failure.
- **Change its behavior:** edit `SYSTEM_PROMPT` in `agent/cli.py`.
- **Change which built-ins it gets:** edit `SAFE_BUILTINS` / `GATED_BUILTINS` in `agent/cli.py`.

## Tests

```bash
pytest
```
