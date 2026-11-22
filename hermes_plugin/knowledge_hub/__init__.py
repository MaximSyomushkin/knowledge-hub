"""knowledge-hub: Hermes plugin for the school hub.

Hooks: pre_gateway_dispatch (every message or voice note in Discord #memory, or in the Telegram chats of
KHUB_TELEGRAM_MEMORY, goes to `khub memory-add`), pre_llm_call (where school files live, which tools to use).
Commands: /remember, /todo, /done, /forget, /idea, /ideas, /browse.
Tools: khub_memory (read the task list), pick_folder (Discord button folder picker).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .handlers import HubPlugin
from .runner import HubRunner

logger = logging.getLogger("knowledge-hub")

DEFAULT_BIN = Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "khub.exe"  # in-repo; installed copies set KHUB_BIN
DEFAULT_VAULT = Path.home() / "vault"  # override via KHUB_VAULT

TOOL_SCHEMAS = {
    "khub_memory": {
        "name": "khub_memory",
        "description": "List what the user asked you to remember: open tasks (with due dates), upcoming events, "
                       "each with an id like m3. Use it for questions such as 'what do I have to do this "
                       "week?' or 'when is my exam?'. Read-only: the user adds and ticks items with /remember, "
                       "/done and /forget or in the #memory channel.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["task", "event"],
                         "description": "Only this kind (default: all kinds)"},
                "all": {"type": "boolean", "description": "Include done tasks and past events (default false)"},
            },
        },
    },
    "pick_folder": {
        "name": "pick_folder",
        "description": "Ask the user to choose a vault folder by clicking through it with buttons in Discord. Use it "
                       "whenever a task needs a folder the user hasn't named exactly, instead of guessing paths. "
                       "Waits for their click and returns the exact path with the folder's subfolders and files "
                       "(or that they cancelled).",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string",
                             "description": "One short line shown above the picker, e.g. 'Which lecture?'"},
                "start": {"type": "string",
                          "description": "Folder to open first, e.g. /vault/readwrite/Year-1/Intro-to-Physics. "
                                         "Omit to start at the top of the vault."},
            },
        },
    },
}


def build_plugin() -> HubPlugin:
    runner = HubRunner([os.environ.get("KHUB_BIN") or str(DEFAULT_BIN)], os.environ.get("KHUB_CONFIG") or None)
    discord_memory = os.environ.get("KHUB_DISCORD_MEMORY", "").strip() or None
    # Telegram chats (comma-separated ids) that work like #memory: every message is a task, date or idea.
    telegram_memory = {c.strip() for c in os.environ.get("KHUB_TELEGRAM_MEMORY", "").split(",") if c.strip()}
    logger.info("knowledge-hub: discord memory=%s; telegram memory=%d chat(s)",
                "set" if discord_memory else "off", len(telegram_memory))
    return HubPlugin(runner, discord_memory=discord_memory, telegram_memory=telegram_memory,
                      vault=Path(os.environ.get("KHUB_VAULT") or DEFAULT_VAULT))


def register(ctx) -> None:
    plugin = build_plugin()
    ctx.register_hook("pre_gateway_dispatch", plugin.pre_gateway_dispatch)
    ctx.register_hook("pre_llm_call", plugin.pre_llm_call)
    # "[what]" not "<what>": Hermes drops commands with a required argument from its slash-command menus.
    ctx.register_command("remember", plugin.cmd_remember, description="Remember a task or a date",
                         args_hint="[what to remember]")
    ctx.register_command("todo", plugin.cmd_todo, description="Open tasks and upcoming events")
    ctx.register_command("done", plugin.cmd_done, description="Tick off a task (id like m3, or some of its words)",
                         args_hint="[id or words]")
    ctx.register_command("forget", plugin.cmd_forget, description="Delete something I remember",
                         args_hint="[id or words]")
    ctx.register_command("browse", plugin.cmd_browse, description="Pick a vault folder with buttons, then say what to do",
                         args_hint="[start folder]")
    ctx.register_command("idea", plugin.cmd_idea, description="Save an idea as its own note in Ideas/",
                         args_hint="[your idea]")
    ctx.register_command("ideas", plugin.cmd_ideas, description="Idea of the day in the morning digest: on or off",
                         args_hint="[on|off]")
    for name, schema in TOOL_SCHEMAS.items():
        ctx.register_tool(name=name, toolset="knowledge-hub", schema=schema, handler=getattr(plugin, f"tool_{name}"),
                          is_async=True, emoji="📚")
