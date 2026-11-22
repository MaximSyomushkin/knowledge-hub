"""Structured memory: tasks and events the user asked the bot to remember.

Kept in <memory folder>/memory.md (`memory_dir`) in Obsidian Tasks format
(`- [ ] text ⏰ 14:00 📅 date ➕ date ✅ date ^m3`), so the records stay readable and editable in Obsidian.
The time sits before 📅: Tasks reads its fields from the end of
the line, so it shows the time as part of the text and still finds the dates. `🔁 every week on Tuesday` repeats an
item (see recur.py): a repeating task gets its next copy when ticked, as Tasks does; a repeating event is never
copied, the digests work out its dates. Tasks expire by the day (`expire_tasks`, run by the watcher): deleted
once their due date is past, kept all of their due day whatever the time. Lines the parser does not own (intro, notes, other sections) are kept
verbatim; only item lines are re-rendered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from .prompts import MEMORY_SYSTEM, memory_prompt
from .recur import Rule, parse_rule
from .schemas import MemoryDraft, MemoryExtraction
from .vault import Vault

MEMORY_FILE = "memory.md"
KINDS = ("task", "event")
MAX_TEXT = 200
SECTIONS = {"task": "## Tasks", "event": "## Events"}
_HEADING_KIND = {heading.casefold(): kind for kind, heading in SECTIONS.items()}
HEADER = ("# Memory\n\nWhat you asked the bot to remember. Edit freely: tick tasks, fix dates (📅 YYYY-MM-DD), "
          "delete lines.\n")

_ITEM = re.compile(r"^\s*- (.*)$")
_CHECK = re.compile(r"^\[( |x|X)\]\s*")
_DATE = r"(\d{4}-\d{2}-\d{2})"
_TOKENS = (("time", re.compile(r"⏰\s*(\d{1,2}:\d{2})")), ("due", re.compile(r"📅\s*" + _DATE)),
           ("repeat", re.compile(r"🔁\s*(.+?)\s*(?=📅|➕|✅|⏰|\^m\d|$)")),
           ("added", re.compile(r"➕\s*" + _DATE)), ("done", re.compile(r"✅\s*" + _DATE)),
           ("id", re.compile(r"\^m(\d+)(?!\S)")))
_ID_REF = re.compile(r"[mM]?(\d+)")
_CLOCK = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*([ap])?\.?\s*m?\.?", re.IGNORECASE)


@dataclass
class Item:
    kind: str
    text: str
    id: int | None = None
    due: str | None = None
    added: str | None = None
    done: str | None = None  # tasks: the day it was ticked
    checked: bool = False
    time: str | None = None  # HH:MM, only with a due date
    repeat: str | None = None  # Tasks wording, e.g. "every week on Tuesday"; kept as written

    @property
    def is_open(self) -> bool:
        return self.kind == "task" and not self.checked

    @property
    def rule(self) -> Rule | None:
        return parse_rule(self.repeat) if self.due else None

    def occurs_on(self, day: date) -> bool:
        """Dated on `day`. A repeating event is dated on every day of its series; a repeating task only on its
        current due date (its next copy is written when it is ticked)."""
        rule = self.rule
        if rule is not None and self.kind == "event":
            return rule.occurs(date.fromisoformat(self.due), day)
        return self.due == day.isoformat()

    def next_date(self, day: date) -> str | None:
        """The first date on or after `day` (for a repeating event), else the due date."""
        rule = self.rule
        if rule is not None and self.kind == "event":
            found = rule.first_on_or_after(date.fromisoformat(self.due), day)
            return found.isoformat() if found else None
        return self.due

    def to_dict(self) -> dict:
        data = {"id": f"m{self.id}" if self.id is not None else None, "kind": self.kind, "text": self.text,
                "due": self.due, "time": self.time, "repeat": self.repeat, "added": self.added}
        if self.kind == "task":
            data["status"] = "done" if self.checked else "open"
            data["done"] = self.done
        return data

    def render(self) -> str:
        parts = []
        if self.kind == "task":
            parts.append("[x]" if self.checked else "[ ]")
        parts.append(self.text)
        if self.time:
            parts.append(f"⏰ {self.time}")
        if self.repeat:
            parts.append(f"🔁 {self.repeat}")
        if self.due:
            parts.append(f"📅 {self.due}")
        if self.added:
            parts.append(f"➕ {self.added}")
        if self.checked and self.done:
            parts.append(f"✅ {self.done}")
        if self.id is not None:
            parts.append(f"^m{self.id}")
        return "- " + " ".join(parts)


def _real_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parse_item(kind: str, body: str) -> Item | None:
    checked = False
    if kind == "task":
        box = _CHECK.match(body)
        if box:
            checked = box.group(1) != " "
            body = body[box.end():]
    fields: dict[str, str] = {}
    for name, pattern in _TOKENS:
        found = pattern.search(body)
        if found and name in ("due", "added", "done") and not _real_date(found.group(1)):
            continue  # a hand-typed 2026-02-30 stays in the text instead of breaking every command
        if found:
            fields[name] = found.group(1)
            body = pattern.sub(" ", body, count=1)
    text = " ".join(body.split())
    if not text:
        return None
    return Item(kind, text, id=int(fields["id"]) if "id" in fields else None, due=fields.get("due"),
                added=fields.get("added"), done=fields.get("done") if checked else None, checked=checked,
                time=clock_time(fields.get("time", "")), repeat=fields.get("repeat"))


class MemoryDoc:
    """The file as a list of blocks: an `Item` for each item line, the raw string for every other line."""

    def __init__(self, blocks: list[str | Item]):
        self.blocks = blocks

    @classmethod
    def parse(cls, text: str) -> MemoryDoc:
        blocks: list[str | Item] = []
        kind: str | None = None
        for line in text.lstrip("﻿").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                kind = _HEADING_KIND.get(stripped.casefold())
                blocks.append(line)
                continue
            match = _ITEM.match(line) if kind else None
            item = _parse_item(kind, match.group(1)) if match else None
            blocks.append(item if item is not None else line)
        return cls(blocks)

    def items(self) -> list[Item]:
        return [block for block in self.blocks if isinstance(block, Item)]

    def _section(self, kind: str) -> int | None:
        heading = SECTIONS[kind].casefold()
        for index, block in enumerate(self.blocks):
            if isinstance(block, str) and block.strip().casefold() == heading:
                return index
        return None

    def add(self, item: Item) -> None:
        """Append to the item's section (after its last non-blank line), creating the section if needed."""
        start = self._section(item.kind)
        if start is None:
            if not self.blocks:
                self.blocks.extend(HEADER.rstrip("\n").split("\n"))
            if self.blocks and self.blocks[-1] != "":
                self.blocks.append("")
            self.blocks.extend([SECTIONS[item.kind], item])
            return
        end = next((i for i in range(start + 1, len(self.blocks))
                    if isinstance(self.blocks[i], str) and self.blocks[i].strip().startswith("#")), len(self.blocks))
        last = start
        for i in range(start + 1, end):
            block = self.blocks[i]
            if isinstance(block, Item) or block.strip():
                last = i
        self.blocks.insert(last + 1, item)

    def remove(self, item: Item) -> None:
        self.blocks = [block for block in self.blocks if block is not item]

    def assign_ids(self) -> None:
        items = self.items()
        next_id = max((i.id for i in items if i.id is not None), default=0) + 1
        for item in items:
            if item.id is None:
                item.id = next_id
                next_id += 1

    def render(self) -> str:
        if not self.blocks:
            return ""
        return "\n".join(b.render() if isinstance(b, Item) else b for b in self.blocks) + "\n"


class MemoryStore:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.path = vault.memory_root / MEMORY_FILE

    def load(self) -> MemoryDoc:
        if not self.path.exists():
            return MemoryDoc([])
        return MemoryDoc.parse(self.vault.read_text(self.path))

    def save(self, doc: MemoryDoc) -> None:
        self.vault.write_text(self.path, doc.render())

    def expire(self, today: date) -> list[Item]:
        """`expire_tasks` on memory.md; the file is written only when something changed (once a day at most), so
        the watcher's minute tick rarely touches it."""
        doc = self.load()
        before = doc.render()
        expired = expire_tasks(doc, today)
        if doc.render() != before:
            self.save(doc)
        return expired


def clock_time(value: str) -> str | None:
    """'14:00', '9.30', '2pm', '2:30 pm' -> 'HH:MM' (24-hour); None for anything else, e.g. a bare '14'."""
    match = _CLOCK.fullmatch(value.strip())
    if not match or (match.group(2) is None and match.group(3) is None):
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if match.group(3):
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if match.group(3).lower() == "p" else 0)
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def by_time(item: Item) -> tuple[str, str, int]:
    """Date, then timed before untimed, then id."""
    return item.due or "", item.time or "~", item.id or 0


def _by_date(item: Item) -> tuple[str, str, int]:
    return by_time(item)


def list_items(doc: MemoryDoc, today: date, kind: str | None = None, all_: bool = False) -> list[Item]:
    """Open tasks (dated by due date, then undated), then events from today on; `all_` adds done tasks and
    past events. Each group keeps that order."""
    now = today.isoformat()
    items = doc.items()
    tasks = [i for i in items if i.kind == "task"]
    open_tasks = ([i for i in sorted(tasks, key=_by_date) if i.is_open and i.due]
                  + [i for i in sorted(tasks, key=_by_date) if i.is_open and not i.due])
    done_tasks = sorted((i for i in tasks if i.checked), key=lambda i: (i.done or "", i.id or 0))
    events = [i for i in items if i.kind == "event"]
    nexts = {id(e): e.next_date(today) for e in events if e.due}  # a repeating event: its next date
    upcoming = (sorted((e for e in events if e.due and (nexts[id(e)] or "") >= now),
                       key=lambda e: (nexts[id(e)], e.time or "~", e.id or 0))
                + [e for e in events if not e.due])
    past = sorted((e for e in events if e.due and (nexts[id(e)] or "") < now), key=_by_date)
    groups = {
        "task": open_tasks + (done_tasks if all_ else []),
        "event": upcoming + (past if all_ else []),
    }
    if kind is not None:
        return groups[kind]
    return groups["task"] + groups["event"]


def find_item(candidates: list[Item], ref: str) -> Item:
    """One item by id (`m3` or `3`) or by a case-insensitive piece of its text."""
    ref = ref.strip()
    by_id = _ID_REF.fullmatch(ref)
    if by_id:
        hits = [i for i in candidates if i.id == int(by_id.group(1))]
    else:
        hits = [i for i in candidates if ref.casefold() in i.text.casefold()] if ref else []
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"nothing matches {ref!r}")
    listed = "; ".join(f"m{i.id}: {i.text}" for i in hits[:5])
    raise ValueError(f"{ref!r} matches {len(hits)} items, say which: {listed}")


def mark_done(doc: MemoryDoc, ref: str, today: date) -> tuple[Item, Item | None]:
    """Tick an open task. A repeating one also gets its next copy, dated by its rule from the old due date and
    written above it, as the Obsidian Tasks plugin does; returns (ticked, next copy or None)."""
    item = find_item([i for i in doc.items() if i.is_open], ref)
    item.checked = True
    item.done = today.isoformat()
    rule = item.rule
    if rule is None:
        return item, None
    due = date.fromisoformat(item.due)
    following = rule.first_on_or_after(due, due + timedelta(days=1))
    if following is None:
        return item, None
    copy = Item("task", item.text, due=following.isoformat(), added=today.isoformat(), time=item.time,
                repeat=item.repeat)
    doc.blocks.insert(doc.blocks.index(item), copy)
    doc.assign_ids()
    return item, copy


def forget(doc: MemoryDoc, ref: str) -> Item:
    item = find_item(doc.items(), ref)
    doc.remove(item)
    return item


def expire_tasks(doc: MemoryDoc, today: date) -> list[Item]:
    """Delete tasks whose due date is before `today`, open or ticked; returns them. Expiry goes by the day, not
    the time: a task due today stays all day even after its ⏰ time. An open repeating task moves on to its next
    date on or after today instead (same line, same id), and is deleted only when its series has ended. Undated
    tasks and events are never touched."""
    now = today.isoformat()
    expired: list[Item] = []
    for item in doc.items():
        if item.kind != "task" or not item.due or item.due >= now:
            continue
        rule = item.rule
        following = rule.first_on_or_after(date.fromisoformat(item.due), today) if rule and item.is_open else None
        if following is not None:
            item.due = following.isoformat()
            continue
        doc.remove(item)
        expired.append(item)
    return expired


def _iso(value: str) -> str | None:
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def clean_drafts(drafts: list[MemoryDraft], today: date) -> list[Item]:
    """LLM drafts -> items: trimmed and capped text, only real ISO dates, an event without a
    valid date kept as a task (a dateless event is just something to do). A repeat rule is kept only when it
    parses (canonical Tasks wording); without a date it starts on its first day from today."""
    items = []
    for draft in drafts:
        if draft.kind not in KINDS:
            continue
        text = " ".join(draft.text.split())[:MAX_TEXT].strip()
        if not text:
            continue
        due = _iso(draft.due)
        rule = parse_rule(draft.repeat)
        if rule is not None and due is None:
            first = rule.first_on_or_after(today, today)
            due = first.isoformat() if first else None
        kind = "task" if draft.kind == "event" and due is None else draft.kind
        time = clock_time(draft.time) if due else None  # a time without a date is too vague to keep
        items.append(Item(kind, text, due=due, added=today.isoformat(), time=time,
                          repeat=rule.render() if rule and due else None))
    return items


_WEEKDAYS = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "weds": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4,
             "sat": 5, "sun": 6}
_WEEKDAY = re.compile(r"\b(next\s+)?(mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)(?:day|nesday|urday|sday)?"
                      r"\b(\s+after\s+next)?", re.IGNORECASE)
_OTHER_DATE = re.compile(r"\b(today|tonight|tomorrow|every|weekend|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|"
                         r"nov|dec|january|february|march|april|june|july|august|september|october|november|"
                         r"december|\d{1,2}(st|nd|rd|th))\b|\d{1,2}[/.]\d{1,2}", re.IGNORECASE)


def weekday_due(message: str, today: date) -> tuple[date, bool] | None:
    """The date a message means when it names exactly one weekday and nothing else date-like, plus whether
    the same day a week later also fits ("next Thursday" is said both ways). Small models count weekdays
    wrongly even with a calendar in the prompt, so this is worked out here instead. A day named on that
    same day means the next one."""
    hits = _WEEKDAY.findall(message)
    if len(hits) != 1 or _OTHER_DATE.search(message):
        return None
    next_word, name, after_next = hits[0]
    ahead = (_WEEKDAYS[name.lower()] - today.weekday() - 1) % 7 + 1
    if after_next:
        ahead += 7
    return today + timedelta(days=ahead), bool(next_word) and not after_next


def _fix_weekday(items: list[Item], message: str, today: date) -> None:
    found = weekday_due(message, today)
    if found is None:
        return
    day, week_later_ok = found
    allowed = {day.isoformat(), (day + timedelta(days=7)).isoformat()} if week_later_ok else {day.isoformat()}
    for item in items:
        if item.due and not item.repeat and item.due not in allowed:
            item.due = day.isoformat()


def first_words(message: str) -> str:
    """A title for an idea the model gave none: the message's first sentence, cut to a few words."""
    first = re.split(r"(?<=[.!?])\s|\n", message.strip(), maxsplit=1)[0].rstrip(".!? ")
    words = first.split()
    return " ".join(words[:8]) if words else "Idea"


def add_from_message(doc: MemoryDoc, llm, model: str | None, message: str, today: date, *, ideas=(),
                     allow_ideas: bool = True, only_idea: bool = False) -> dict:
    """One schema-constrained LLM call; new items are added to `doc` (not saved). Items whose text matches a
    not-yet-done item of the same kind are skipped. Idea drafts never go into `doc`: they come back under "ideas"
    (see ideas.capture). Without `allow_ideas` an idea draft is kept as a task; with `only_idea` everything else is
    dropped and there is always one idea."""
    extraction = llm.generate_json(memory_prompt(message, today, ideas, allow_ideas, only_idea), MemoryExtraction,
                                   system=MEMORY_SYSTEM, model=model)
    drafts, idea_drafts = [], []
    for draft in extraction.items:
        if draft.kind != "idea":
            drafts.append(draft)
        elif allow_ideas or only_idea:
            idea_drafts.append(draft)
        else:
            drafts.append(draft.model_copy(update={"kind": "task", "text": draft.text or draft.title}))
    if only_idea:
        title = next((d.title or d.text for d in idea_drafts + drafts if (d.title or d.text).strip()), "")
        ref = idea_drafts[0].idea_ref if idea_drafts else ""
        return {"added": [], "skipped": [], "question": False,
                "ideas": [MemoryDraft(kind="idea", text="", title=title or first_words(message), idea_ref=ref)]}
    existing = {(i.kind, i.text.casefold()) for i in doc.items() if not i.checked}
    added, skipped = [], []
    items = clean_drafts(drafts, today)
    _fix_weekday(items, message, today)
    for item in items:
        key = (item.kind, item.text.casefold())
        if key in existing:
            skipped.append(item.text)
            continue
        existing.add(key)
        doc.add(item)
        added.append(item)
    # Small models miss some questions; a "?" message that yielded nothing is one too.
    question = not idea_drafts and (extraction.is_question
                                    or (not added and not skipped and message.rstrip().endswith("?")))
    return {"added": added, "skipped": skipped, "question": question, "ideas": idea_drafts}
