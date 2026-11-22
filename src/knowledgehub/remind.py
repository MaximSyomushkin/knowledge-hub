"""Reminders shortly before timed tasks and events (`khub remind`, run by a Hermes job every 15 minutes).

Each occurrence is announced once: what was sent is kept in `<memory>/.state/reminded.json` (pruned after a week), so
overlapping runs and repeating events never repeat a reminder.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, time, timedelta

from .memory import Item, MemoryStore
from .vault import Vault

STATE = "reminded.json"
WINDOW_MINUTES = 60
KEEP_DAYS = 7


def upcoming(items: list[Item], now: datetime, window: timedelta) -> list[tuple[Item, datetime]]:
    """(item, start) for open timed tasks and timed events starting in (now, now + window]."""
    hits = []
    for item in items:
        if not (item.time and item.due and (item.kind == "event" or item.is_open)):
            continue
        for day in (now.date(), now.date() + timedelta(days=1)):  # the window can pass midnight
            start = datetime.combine(day, time.fromisoformat(item.time))
            if now < start <= now + window and item.occurs_on(day):
                hits.append((item, start))
    return sorted(hits, key=lambda hit: (hit[1], hit[0].id or 0))


def _key(item: Item, start: datetime) -> str:
    return f"{item.id if item.id is not None else item.text}|{start:%Y-%m-%d %H:%M}"


def _line(item: Item, start: datetime, now: datetime) -> str:
    minutes = math.ceil((start - now).total_seconds() / 60)
    when = f"{start:%H:%M}" + (" tomorrow" if start.date() != now.date() else "")
    label = f"{item.text} (event)" if item.kind == "event" else f"{item.text} (m{item.id})"
    return f"⏰ {when}, in {minutes} min: {label}"


def remind(vault: Vault, now: datetime, window_minutes: int = WINDOW_MINUTES) -> list[str]:
    """Lines for occurrences not announced yet; records them so the next run stays quiet."""
    path = vault.state_root / STATE
    try:
        sent: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sent = {}
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="minutes")
    kept = {key: when for key, when in sent.items() if when >= cutoff}
    lines = []
    for item, start in upcoming(MemoryStore(vault).load().items(), now, timedelta(minutes=window_minutes)):
        key = _key(item, start)
        if key in kept:
            continue
        kept[key] = start.isoformat(timespec="minutes")
        lines.append(_line(item, start, now))
    if kept != sent:
        vault.write_text(path, json.dumps(kept, indent=1, sort_keys=True) + "\n")
    return lines
