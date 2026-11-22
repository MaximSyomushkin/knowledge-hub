"""Chat replies for the school hub (Discord messages are at most 2000 characters)."""

from __future__ import annotations

import re
from datetime import date

DISCORD_LIMIT = 2000
TRANSCRIBE_FAILED = "❌ Couldn't transcribe that voice note."
BROWSE_DISCORD_ONLY = "📂 The folder picker works in Discord. Here, just type the folder path."
BROWSE_FAILED = "❌ Couldn't open the folder picker. Type the folder path instead."
BROWSE_PICK_HINT = "Now tell me what to do there."


def heard(transcript: str) -> str:
    return f"🎙️ heard: {transcript}"


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for piece in re.split(r"(?<=\n\n)", text):
        while len(piece) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(piece[:limit])
            piece = piece[limit:]
        if len(current) + len(piece) > limit:
            parts.append(current)
            current = piece
        else:
            current += piece
    if current:
        parts.append(current)
    return [p for p in parts if p.strip()]


# --- memory -------------------------------------------------------------------

MEMORY_QUESTION = "🤔 That sounds like a question. /todo lists what I remember; ask anything else in #chat."
MEMORY_NOTHING = "🤷 I didn't find anything to remember in that."
FILE_HINT = "📎 This chat only takes tasks, dates and ideas (text or voice), not files."
TODO_EMPTY = "📭 Nothing on your list. Tell me in #memory or with /remember."
REMEMBER_USAGE = "Usage: /remember <what to remember>, e.g. /remember lab report due Friday"
DONE_USAGE = "Usage: /done <id or words>, e.g. /done m3 or /done lab report"
FORGET_USAGE = "Usage: /forget <id or words>, e.g. /forget m3"


def fmt_day(iso: str) -> str:
    """Format an ISO date as day-first display text, e.g. "Fri 09/10/2026"."""
    d = date.fromisoformat(iso)
    return f"{d:%a %d/%m/%Y}"


def _when(item: dict) -> str:
    if not item.get("due"):
        return ""
    day = fmt_day(item["due"]) + (f", {item['time']}" if item.get("time") else "")
    day += f", 🔁 {item['repeat']}" if item.get("repeat") else ""
    return f" — due {day}" if item.get("kind") == "task" else f" — {day}"


def _idea_lines(idea: dict) -> list[str]:
    if idea.get("action") == "added":
        return [f"➕ Added to: {idea.get('title', '?')}"]
    return [f"💡 New idea: {idea.get('title', '?')}", f"→ {idea.get('path', '?')}"]


def format_memory_added(data: dict) -> str:
    added, skipped = data.get("added") or [], data.get("skipped") or []
    idea = data.get("idea")
    lines = _idea_lines(idea) if idea else []
    if added:
        lines += ["🧠 Got it:"] + [f"• {i['kind']}: {i['text']}{_when(i)} ({i['id']})" for i in added]
        if skipped:
            lines.append(f"(already had: {', '.join(skipped)})")
        return "\n".join(lines)
    if skipped:
        lines.append(f"👍 I already have that: {', '.join(skipped)}")
    if lines:
        return "\n".join(lines)
    return MEMORY_QUESTION if data.get("question") else MEMORY_NOTHING


# --- ideas ----------------------------------------------------------------------

IDEA_USAGE = "Usage: /idea <your idea>, e.g. /idea a little robot that waters houseplants"
IDEAS_USAGE = "Usage: /ideas, /ideas on or /ideas off"


def format_ideas(data: dict) -> str:
    if not data.get("remind"):
        return "💡 Idea of the day: off. /ideas on starts it again."
    return (f"💡 Idea of the day: on ({data.get('count', 0)} of {data.get('total', 0)} ideas take turns). "
            "/ideas off stops it.")


def format_todo(data: dict) -> str:
    items = data.get("items") or []
    tasks = [i for i in items if i.get("kind") == "task"]
    events = [i for i in items if i.get("kind") == "event"]
    if not tasks and not events:
        return TODO_EMPTY
    lines = []
    if tasks:
        lines += ["📝 To do:"] + [f"{i['id']} {i['text']}{_when(i)}" for i in tasks]
    if events:
        lines += ["🗓️ Coming up:"] + [f"{i['id']} {i['text']}{_when(i)}" for i in events]
    return "\n".join(lines)


def format_done(item: dict) -> str:
    text = f"✅ Done: {item.get('text', '?')} ({item.get('id', '?')})"
    following = item.get("next")
    if following:
        text += f"\n🔁 Next: {following.get('text', '?')}{_when(following)} ({following.get('id', '?')})"
    return text


def format_forgot(item: dict) -> str:
    return f"🗑️ Forgot: {item.get('text', '?')} ({item.get('id', '?')})"
