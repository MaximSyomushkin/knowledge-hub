"""Repeat rules for memory items, in the Obsidian Tasks wording (`🔁 every week on Tuesday`).

Only the forms people actually say are understood: every day / N days, every weekday, every week / N weeks,
every week on <days>, every <day>(s), every month / N months. Anything else is not a rule (None), so a
model's odd answer is dropped instead of guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_SHORT = {name[:3]: i for i, name in enumerate(DAYS)}
_EVERY = re.compile(r"^every\s+(?:(\d+)\s+)?(day|days|weekday|week|weeks|month|months)(?:\s+on\s+(.+))?$")
_DAY_LIST = re.compile(r"^every\s+(.+)$")
_SEPARATORS = re.compile(r"\s*(?:,|\band\b|&)\s*")
LOOKAHEAD_DAYS = 800  # longer than any gap these rules allow (every N months with a small N)


@dataclass(frozen=True)
class Rule:
    unit: str  # "day", "weekday", "week" or "month"
    n: int = 1
    days: tuple[int, ...] = ()  # weekdays (Monday = 0) for "every week on ..."

    def render(self) -> str:
        if self.unit == "weekday":
            return "every weekday"
        head = f"every {self.unit}" if self.n == 1 else f"every {self.n} {self.unit}s"
        if self.days:
            head += " on " + ", ".join(DAYS[d].capitalize() for d in self.days)
        return head

    def occurs(self, start: date, day: date) -> bool:
        """True when a series starting on `start` falls on `day`."""
        if day < start:
            return False
        if self.unit == "day":
            return (day - start).days % self.n == 0
        if self.unit == "weekday":
            return day.weekday() < 5
        if self.unit == "week":
            weeks = ((day - timedelta(days=day.weekday())) - (start - timedelta(days=start.weekday()))).days // 7
            if weeks % self.n:
                return False
            return day.weekday() in self.days if self.days else day.weekday() == start.weekday()
        months = (day.year - start.year) * 12 + day.month - start.month
        return day.day == start.day and months % self.n == 0

    def first_on_or_after(self, start: date, day: date) -> date | None:
        probe = max(start, day)
        for _ in range(LOOKAHEAD_DAYS):
            if self.occurs(start, probe):
                return probe
            probe += timedelta(days=1)
        return None


def _weekdays(text: str) -> tuple[int, ...] | None:
    found = []
    for part in _SEPARATORS.split(text.strip()):
        key = part.strip().removesuffix("s")[:3]
        if key not in _SHORT:
            return None
        found.append(_SHORT[key])
    return tuple(sorted(set(found))) or None


def parse_rule(text: str | None) -> Rule | None:
    if not text:
        return None
    clean = " ".join(text.strip().casefold().replace("🔁", "").split())
    match = _EVERY.match(clean)
    if match:
        n = int(match.group(1) or 1)
        unit = match.group(2).removesuffix("s")
        if n < 1 or (unit == "weekday" and (n != 1 or match.group(3))):
            return None
        days: tuple[int, ...] = ()
        if match.group(3):
            if unit != "week":
                return None
            days = _weekdays(match.group(3)) or ()
            if not days:
                return None
        return Rule(unit, n, days)
    match = _DAY_LIST.match(clean)  # "every tuesday", "every monday and thursday"
    days = _weekdays(match.group(1)) if match else None
    return Rule("week", 1, days) if days else None
