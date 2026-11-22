"""Proactive digests: plain text built from memory.md and the idea of the day, no LLM.

Written for Discord: `# ` title, `## ` sections with a blank line between them, `-# ` footnotes, and an optional
`<@user id>` first line so the post pings. An empty string means "nothing worth saying"; Hermes' no-agent cron jobs
treat empty output as a silent tick.
"""

from __future__ import annotations

from datetime import date, timedelta

from .memory import Item, by_time

HEADS_UP_DAYS = 3  # one-off events show in the morning digest from this many days before


def _day(iso: str) -> str:
    """Format an ISO date as day-first display text, e.g. "Fri 09/10/2026"."""
    d = date.fromisoformat(iso)
    return f"{d:%a %d/%m/%Y}"


def _short(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def _brief(d: date) -> str:
    """"Fri 23/10", for the weekend digest that only looks a week or so ahead."""
    return f"{d:%a %d/%m}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _label(item: Item) -> str:
    return f"{item.text} (event)" if item.kind == "event" else f"{item.text} (m{item.id})"


def _on(items: list[Item], day: date) -> list[Item]:
    """Open tasks and events dated `day` (repeating events included), timed ones first (by time)."""
    hits = [i for i in items if (i.kind == "event" or i.is_open) and i.due and i.occurs_on(day)]
    return sorted(hits, key=lambda i: (i.time or "~", i.id or 0))


def _bullet(item: Item) -> str:
    return "- " + (f"{item.time} " if item.time else "") + _label(item)


def _coming(items: list[Item], today: date) -> list[tuple[Item, date]]:
    """One-off events 2..HEADS_UP_DAYS days away; tomorrow and today have their own sections. Repeating events
    (a weekly lab) are left out, or the timetable would show up every week."""
    return [(i, day) for n in range(2, HEADS_UP_DAYS + 1) for day in [today + timedelta(days=n)]
            for i in _on(items, day) if i.kind == "event" and not i.repeat]


def _coming_line(item: Item, day: date, today: date) -> str:
    when = _brief(day) + (f" {item.time}" if item.time else "")
    return f"- {item.text} · {when}, in {(day - today).days} days"


def _overdue_line(item: Item, short: bool = False) -> str:
    when = _brief(date.fromisoformat(item.due)) if short else _day(item.due)
    return f"- {item.text} · was due {when} (m{item.id})"


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", *body]


def _post(mention: str, title: str, head: list[str], sections: list[list[str]], foot: list[str] = ()) -> str:
    """The message: mention, `# title` and any lines under it, then the sections and footnotes, a blank line
    between each part."""
    parts = ["\n".join([f"# {title}", *head])] + ["\n".join(s) for s in sections] + ["\n".join(f"-# {f}" for f in foot)]
    text = "\n\n".join(part for part in parts if part)
    return f"<@{mention}>\n{text}" if mention else text


def _idea_lines(idea: dict) -> list[str]:
    try:  # Obsidian may hold a date and time, or anything typed by hand
        created = f" · from {_short(date.fromisoformat(str(idea.get('created') or '')[:10]))}"
    except ValueError:
        created = ""
    lines = [f"**{idea['title']}**{created}"]
    if idea.get("gist"):
        lines.append(idea["gist"])
    lines.append(f"-# {idea['path']}")
    return lines


def daily(items: list[Item], today: date, health: list[str] = (), idea: dict | None = None,
          mention: str = "") -> tuple[str, dict]:
    """Morning digest: `health` warnings (see health.py), anything overdue, then what is due today and tomorrow
    (with times), a countdown to one-off events up to HEADS_UP_DAYS days away, and the idea of the day (`idea`:
    title, created, gist, path). Silent when all of these are empty."""
    now = today.isoformat()
    tomorrow = today + timedelta(days=1)
    overdue = sorted((i for i in items if i.is_open and i.due and i.due < now), key=by_time)
    due_today, due_tomorrow = _on(items, today), _on(items, tomorrow)
    coming = _coming(items, today)
    sections = {"overdue": [i.to_dict() for i in overdue], "today": [i.to_dict() for i in due_today],
                "tomorrow": [i.to_dict() for i in due_tomorrow],
                "coming": [i.to_dict() for i, _ in coming], "health": list(health), "idea": idea}
    if not (health or overdue or due_today or due_tomorrow or coming or idea):
        return "", sections

    parts = []
    if overdue:
        parts.append(_section("⚠️ Overdue", [_overdue_line(i) for i in overdue]))
    parts.append(_section("📌 Today", [*map(_bullet, due_today)] or ["- Nothing due"]))
    parts.append(_section(f"⏭️ Tomorrow, {_day(tomorrow.isoformat())}", [*map(_bullet, due_tomorrow)] or ["- Nothing due"]))
    if coming:
        parts.append(_section("🔜 Coming up", [_coming_line(i, day, today) for i, day in coming]))
    if idea:
        parts.append(_section("💡 Idea", _idea_lines(idea)))
    return _post(mention, f"☀️ {today:%A %d/%m/%Y}", list(health), parts), sections


def weekly(items: list[Item], today: date, mention: str = "") -> tuple[str, dict]:
    """The Sunday recap in two parts. Added this week: everything put in memory.md. Next week: Monday to Sunday
    after `today`, day by day with times; then anything overdue and the number of open tasks without a date."""
    start = today - timedelta(days=6)
    lo, hi = start.isoformat(), today.isoformat()
    remembered = sorted((i for i in items if i.added and lo <= i.added <= hi), key=lambda i: (i.added, i.id or 0))
    monday = today + timedelta(days=7 - today.weekday())
    sunday = monday + timedelta(days=6)
    agenda = {day: _on(items, day) for day in (monday + timedelta(days=n) for n in range(7))}
    agenda = {day: hits for day, hits in agenda.items() if hits}
    overdue = sorted((i for i in items if i.is_open and i.due and i.due <= hi), key=by_time)
    undated = sum(1 for i in items if i.is_open and not i.due)
    sections = {"week": [lo, hi], "remembered": [i.to_dict() for i in remembered],
                "next_week": [monday.isoformat(), sunday.isoformat()],
                "agenda": {day.isoformat(): [i.to_dict() for i in hits] for day, hits in agenda.items()},
                "overdue": [i.to_dict() for i in overdue], "undated": undated}
    if not (remembered or agenda or overdue or undated):
        return "", sections

    new = [f"- {i.kind}: {i.text}" + (f" — {_day(i.due)}" if i.due else "")
           + (f" {i.time}" if i.time else "") + (f", 🔁 {i.repeat}" if i.repeat else "")
           + (f" (m{i.id})" if i.kind != "event" else "")
           for i in remembered]
    ahead = []
    for day, hits in agenda.items():
        ahead.append(f"**{_day(day.isoformat())}**")
        ahead += map(_bullet, hits)
    parts = [_section("🆕 Added this week", new or ["Nothing new"]),
             _section(f"🗓️ Next week, {_short(monday)} – {_short(sunday)}", ahead or ["Nothing scheduled yet"])]
    if overdue:
        parts.append(_section("⚠️ Still open, due by today", [_overdue_line(i) for i in overdue]))
    foot = [f"📝 {_plural(undated, 'open task')} without a date (/todo lists them)"] if undated else []
    return _post(mention, f"📅 Week of {_short(start)} – {_short(today)}", [], parts, foot), sections


def weekend(items: list[Item], today: date, mention: str = "") -> tuple[str, dict]:
    """Friday and Saturday: open tasks to work on. Overdue first, then everything due from today to the Sunday of
    the following week, day by day, and how many open tasks have no date. Events are left out. Silent when there is
    no open task at all."""
    end = today + timedelta(days=(6 - today.weekday()) + 7)
    now, last = today.isoformat(), end.isoformat()
    tasks = [i for i in items if i.is_open]
    overdue = sorted((i for i in tasks if i.due and i.due < now), key=by_time)
    due = sorted((i for i in tasks if i.due and now <= i.due <= last), key=by_time)
    undated = sum(1 for i in tasks if not i.due)
    sections = {"window": [now, last], "overdue": [i.to_dict() for i in overdue], "due": [i.to_dict() for i in due],
                "undated": undated}
    if not (overdue or due or undated):
        return "", sections

    days: list[str] = []
    for n, i in enumerate(due):
        if n == 0 or due[n - 1].due != i.due:
            days.append(f"**{_brief(date.fromisoformat(i.due))}**")
        days.append(_bullet(i))
    parts = []
    if overdue:
        parts.append(_section("⚠️ Overdue", [_overdue_line(i, short=True) for i in overdue]))
    parts.append(_section(f"📅 Due by {_brief(end)}", days or ["Nothing due"]))
    foot = [f"📝 {_plural(undated, 'open task')} with no date (/todo lists them)"] if undated else []
    return _post(mention, f"🛠️ Weekend work · {_brief(today)}", [], parts, foot), sections
