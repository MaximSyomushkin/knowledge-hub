"""Health checks: watcher heartbeat freshness and model server reachability."""

from __future__ import annotations

from datetime import datetime, timedelta

from .llm import LLM, LLMError
from .vault import Vault

HEARTBEAT = "watch.heartbeat"
STALE = timedelta(minutes=15)
WATCHER_HINT = "restart 'khub watch' (or your background service) to resume syncing"


def beat(vault: Vault, now: datetime | None = None) -> None:
    vault.write_text(vault.state_root / HEARTBEAT, (now or datetime.now()).isoformat(timespec="seconds") + "\n")


def watcher_problem(vault: Vault, now: datetime) -> str | None:
    path = vault.state_root / HEARTBEAT
    try:
        last = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return f"⚠️ The hub watcher isn't running, so lecture notes and expired tasks aren't updated; {WATCHER_HINT}."
    if now - last <= STALE:
        return None
    return (f"⚠️ The hub watcher stopped (last seen {last:%a %d/%m/%Y %H:%M}), so lecture notes and expired tasks "
            f"aren't updated; {WATCHER_HINT}.")


def server_problem(llm: LLM, model: str) -> str | None:
    if model.startswith("claude-"):
        return None
    try:
        llm.list_models()
    except LLMError:
        return "⚠️ The local model server isn't running, so #memory, /remember and ideas won't work until it starts."
    return None
