"""Interactive command-line chat loop for the agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import warnings
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    CanUseToolShadowedWarning,
    ClaudeSDKClient,
    CLINotFoundError,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolPermissionContext,
    ToolUseBlock,
)

from agent.tools import SERVER_NAME, TOOL_NAMES, server

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You are a helpful general-purpose assistant running in the user's terminal.

- Answer directly and concisely; use markdown sparingly since output is shown in a terminal.
- Use the calculator tool for any non-trivial arithmetic rather than computing in your head.
- Use web search / web fetch for anything time-sensitive or that you are unsure about, and cite the URLs you used.
- You can read files in the working directory. Writing files or running shell commands requires the user's approval, so explain briefly what you are about to do first.
- When the user asks you to remember something, save it with the notes tools.
"""

# Built-in tools that run without asking.
SAFE_BUILTINS = ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]
# Built-in tools that are available but need a y/n from the user each time.
GATED_BUILTINS = ["Write", "Edit", "Bash"]

# We auto-allow safe tools on purpose, so the SDK's "callback is shadowed" notice is expected.
warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning)

DIM, BOLD, CYAN, YELLOW, RESET = "\033[2m", "\033[1m", "\033[36m", "\033[33m", "\033[0m"


def _summarize_input(tool_input: dict[str, Any], limit: int = 200) -> str:
    text = json.dumps(tool_input, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def ask_permission(
    tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Prompt the user before a gated tool runs."""
    prompt = context.title or f"Claude wants to use {tool_name}"
    print(f"\n{YELLOW}{prompt}{RESET}")
    if tool_name == "Bash":
        print(f"  $ {tool_input.get('command', '')}")
    else:
        print(f"  {_summarize_input(tool_input)}")
    answer = await asyncio.to_thread(input, "  Allow? [y/N] ")
    if answer.strip().lower() in {"y", "yes"}:
        return PermissionResultAllow()
    return PermissionResultDeny(message="The user declined this action.")


def build_options(model: str, allow_all: bool) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=SAFE_BUILTINS + GATED_BUILTINS,
        mcp_servers={SERVER_NAME: server},
        allowed_tools=SAFE_BUILTINS + TOOL_NAMES + (GATED_BUILTINS if allow_all else []),
        can_use_tool=None if allow_all else ask_permission,
        # Don't pick up the user's ~/.claude or project settings; keep the agent self-contained.
        setting_sources=[],
        cwd=os.getcwd(),
    )


async def run_turn(client: ClaudeSDKClient, prompt: str, verbose: bool) -> None:
    await client.query(prompt)
    printed_text = False
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text, end="", flush=True)
                    printed_text = True
                elif isinstance(block, ToolUseBlock):
                    name = block.name.removeprefix(f"mcp__{SERVER_NAME}__")
                    detail = f" {_summarize_input(block.input, 80)}" if verbose else ""
                    print(f"\n{DIM}→ {name}{detail}{RESET}", flush=True)
        elif isinstance(message, ResultMessage):
            if printed_text:
                print()
            if message.is_error:
                print(f"{YELLOW}[error: {message.subtype}] {message.result or ''}{RESET}")
            if verbose and message.total_cost_usd is not None:
                print(f"{DIM}[{message.num_turns} turns, ${message.total_cost_usd:.4f}]{RESET}")


async def chat(model: str, allow_all: bool, verbose: bool, once: str | None) -> None:
    options = build_options(model, allow_all)
    if once is not None:
        async with ClaudeSDKClient(options=options) as client:
            await run_turn(client, once, verbose)
        return

    print(f"{BOLD}Agent{RESET} ({model}) — type /exit to quit, /clear to reset.\n")
    while True:
        # Each pass through this loop is one conversation; /clear starts a new one.
        async with ClaudeSDKClient(options=options) as client:
            while True:
                try:
                    prompt = (await asyncio.to_thread(input, f"{CYAN}you ›{RESET} ")).strip()
                except EOFError:
                    print()
                    return
                if not prompt:
                    continue
                if prompt in {"/exit", "/quit"}:
                    return
                if prompt == "/clear":
                    print(f"{DIM}(conversation cleared){RESET}\n")
                    break
                print(f"{BOLD}agent ›{RESET} ", end="", flush=True)
                await run_turn(client, prompt, verbose)
                print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Chat with a tool-using Claude agent.")
    parser.add_argument("prompt", nargs="*", help="Run a single prompt and exit.")
    parser.add_argument(
        "--model", default=os.environ.get("AGENT_MODEL", DEFAULT_MODEL), help="Claude model ID."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Auto-approve Write/Edit/Bash without prompting."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show tool inputs and cost.")
    args = parser.parse_args(argv)

    once = " ".join(args.prompt) if args.prompt else None
    try:
        asyncio.run(chat(args.model, args.yes, args.verbose, once))
    except CLINotFoundError:
        sys.exit("Claude Code CLI not found. Reinstall with: pip install -U claude-agent-sdk")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
