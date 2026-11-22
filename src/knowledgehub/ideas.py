"""Ideas: one note per idea in the ideas folder (`ideas_dir`), apart from memory.md.

A note is front matter (`type: idea`, `id`, `created`, `status`, `remind`), a `# Title`, a Meta Bind status dropdown,
then `## Summary` (the bot's, written when a message arrives), `## What I said` (dated entries, only ever appended)
and `## My Notes` (the user's, never written). Notes are edited as text, section by section; the
front matter is never re-dumped, so what Obsidian wrote stays as it was.

`.ideas.json` in the same folder keeps what notes cannot: the highest id ever given (ids are never reused), the day
each idea was last shown in the digest, and the on/off switch for the digest's idea section. A missing or broken
file starts empty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from .llm import LLMError
from .prompts import IDEA_SYSTEM, idea_summary_prompt
from .schemas import IdeaSummary, MemoryDraft
from .vault import Vault

STATE_FILE = ".ideas.json"
STATUSES = ("New", "Exploring", "Building", "Done", "Dropped")
RESTING = {"done", "dropped"}  # left out of the daily rotation
SUMMARY, SAID, NOTES = "Summary", "What I said", "My Notes"
SUMMARY_NOTE = "<!-- Rewritten by the bot from everything below. Put your own thoughts in My Notes. -->"
STATUS_LINE = ("Status: `INPUT[inlineSelect(" + ", ".join(f"option({s})" for s in STATUSES) + "):status]`")
GIST_CHARS = 140
VIA = {"telegram": "Telegram", "discord": "Discord", "cli": "CLI"}

_ID = re.compile(r"i(\d+)")
_BAD_NAME = re.compile(r'[<>:"/\\|?*\[\]#^\x00-\x1f]')
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_SECTION = re.compile(r"^## (.+?)\s*$")


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _id_number(value: str) -> int:
    match = _ID.fullmatch(value or "")
    return int(match.group(1)) if match else 0


def file_stem(title: str) -> str:
    stem = " ".join(_BAD_NAME.sub(" ", title).split()).strip(" .")
    return stem[:80].rstrip(" .") or "Idea"


def _quote(message: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in _norm(message).strip().split("\n"))


def entry_block(message: str, when: datetime, via: str) -> str:
    return f"### {when:%d/%m/%Y %H:%M} · {VIA.get(via, via.title())}\n{_quote(message)}\n"


def note_text(idea_id: str, title: str, created: date, message: str, when: datetime, via: str) -> str:
    front = f"---\ntype: idea\nid: {idea_id}\ncreated: {created.isoformat()}\nstatus: New\nremind: true\n---\n"
    return (f"{front}# {title}\n\n{STATUS_LINE}\n\n## {SUMMARY}\n{SUMMARY_NOTE}\n\n## {SAID}\n\n"
            f"{entry_block(message, when, via)}\n## {NOTES}\n")


@dataclass
class _Parsed:
    meta: dict
    lines: list[str]  # the whole note, LF, without line ends
    spans: dict[str, tuple[int, int]]  # section -> (heading line, end line exclusive)
    title: str


def _parse(text: str) -> _Parsed | None:
    lines = _norm(text).split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except (StopIteration, yaml.YAMLError):
        return None
    if not isinstance(meta, dict) or meta.get("type") != "idea":
        return None
    # Only the three known headings bound sections; any other "## " line belongs to the section above it, and
    # everything after "## My Notes" is the user's.
    starts: list[tuple[int, str]] = []
    for i in range(end + 1, len(lines)):
        match = _SECTION.match(lines[i])
        name = match.group(1) if match else None
        if name in (SUMMARY, SAID, NOTES) and name not in {n for _, n in starts}:
            starts.append((i, name))
            if name == NOTES:
                break
    spans = {name: (start, starts[k + 1][0] if k + 1 < len(starts) else len(lines))
             for k, (start, name) in enumerate(starts)}
    if SUMMARY in spans:  # the bot rewrites the Summary whole, so it stops at any heading the user added below it
        start, end_ = spans[SUMMARY]
        spans[SUMMARY] = (start, next((i for i in range(start + 1, end_) if lines[i].startswith("## ")), end_))
    first = starts[0][0] if starts else len(lines)
    title = next((line[2:].strip() for line in lines[end + 1:first] if line.startswith("# ")), "")
    return _Parsed(meta, lines, spans, title)


def _body(parsed: _Parsed, name: str) -> list[str]:
    if name not in parsed.spans:
        return []
    start, end = parsed.spans[name]
    return parsed.lines[start + 1:end]


def _entries(said: list[str]) -> list[tuple[int, int]]:
    """(first line, end line) of each `### ` entry inside the What I said body."""
    heads = [i for i, line in enumerate(said) if line.startswith("### ")]
    return [(h, heads[k + 1] if k + 1 < len(heads) else len(said)) for k, h in enumerate(heads)]


def _entry_text(lines: list[str]) -> str:
    out = []
    for line in lines:
        if line.startswith("> "):
            out.append(line[2:])
        elif line.startswith(">"):
            out.append(line[1:])
        else:
            out.append(line)
    return "\n".join(out).strip()


@dataclass
class Idea:
    path: Path
    id: str
    title: str
    created: str
    status: str
    remind: bool
    summary: str
    said: str
    notes: str
    entries: list[str] = field(default_factory=list)
    loose: str = ""  # text under What I said above its first entry, typed in Obsidian

    @property
    def resting(self) -> bool:
        return self.status.casefold() in RESTING

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "created": self.created, "status": self.status,
                "remind": self.remind, "summary": self.summary, "entries": len(self.entries)}


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in ("false", "no", "off", "0")


def _from(path: Path, parsed: _Parsed) -> Idea | None:
    meta = parsed.meta
    idea_id = str(meta.get("id") or "")
    if not _id_number(idea_id):
        return None
    said = _body(parsed, SAID)
    summary = [line for line in _body(parsed, SUMMARY) if line.strip() != SUMMARY_NOTE]
    spans = _entries(said)
    entries = [_entry_text(said[start + 1:end]) for start, end in spans]
    loose = "\n".join(said[:spans[0][0]] if spans else said).strip()
    return Idea(path=path, id=idea_id, title=parsed.title or str(meta.get("title") or path.stem),
                created=str(meta.get("created") or ""), status=str(meta.get("status") or "New"),
                remind=_flag(meta.get("remind", True)), summary="\n".join(summary).strip(),
                said="\n".join(said), notes="\n".join(_body(parsed, NOTES)), entries=entries, loose=loose)


class IdeaStore:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.root = vault.ideas_root
        self.state_path = self.root / STATE_FILE

    # --- state -----------------------------------------------------------------

    def state(self) -> dict:
        data: dict = {}
        if self.state_path.exists():
            try:
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                data = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                data = {}
        for key, default in (("high", 0), ("shown", {}), ("remind", True)):
            if not isinstance(data.get(key), type(default)):
                data[key] = default
        return data

    def _save_state(self, data: dict) -> None:
        self.vault.write_text(self.state_path, json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")

    def set_reminders(self, on: bool) -> None:
        data = self.state()
        data["remind"] = on
        self._save_state(data)

    # --- notes -----------------------------------------------------------------

    def _read(self, path: Path) -> tuple[Idea, _Parsed] | None:
        try:
            parsed = _parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return None
        if parsed is None:
            return None
        idea = _from(path, parsed)
        return (idea, parsed) if idea is not None else None

    def all(self) -> list[Idea]:
        if not self.root.is_dir():
            return []
        found = [self._read(path) for path in sorted(self.root.glob("*.md"))]
        ideas = [hit[0] for hit in found if hit is not None]
        return sorted(ideas, key=lambda i: _id_number(i.id))

    def get(self, idea_id: str) -> Idea | None:
        return next((i for i in self.all() if i.id == idea_id), None)

    def next_id(self) -> str:
        top = max([self.state()["high"], *(_id_number(i.id) for i in self.all())])
        return f"i{top + 1}"

    def display_path(self, idea: Idea) -> str:
        return f"{self.root.name}/{idea.path.name}"

    def create(self, title: str, message: str, when: datetime, via: str) -> Idea:
        idea_id = self.next_id()
        title = " ".join(title.split()) or "Idea"
        stem = file_stem(title)
        path, n = self.root / f"{stem}.md", 2
        while path.exists():
            path, n = self.root / f"{stem} ({n}).md", n + 1
        self.vault.write_text(path, note_text(idea_id, title, when.date(), message, when, via))
        data = self.state()
        data["high"] = max(data["high"], _id_number(idea_id))
        self._save_state(data)
        return self.get(idea_id)

    def _write_lines(self, idea: Idea, lines: list[str]) -> None:
        self.vault.write_text(idea.path, "\n".join(lines))

    def _fresh(self, idea: Idea) -> tuple[Idea, _Parsed]:
        hit = self._read(idea.path)
        if hit is None or hit[0].id != idea.id:
            raise ValueError(f"idea {idea.id} has changed or is gone")
        return hit

    def append(self, idea: Idea, message: str, when: datetime, via: str) -> int:
        """Add a dated entry at the end of What I said; returns its number (1 = first entry)."""
        idea, parsed = self._fresh(idea)
        block = entry_block(message, when, via).rstrip("\n").split("\n")
        lines = parsed.lines
        if SAID in parsed.spans:
            start, end = parsed.spans[SAID]
            last = end
            while last > start + 1 and not lines[last - 1].strip():
                last -= 1
            new = lines[:last] + [""] + block + [""] + lines[end:]
        else:
            notes = parsed.spans.get(NOTES, (len(lines), len(lines)))[0]
            new = lines[:notes] + [f"## {SAID}", ""] + block + [""] + lines[notes:]
        self._write_lines(idea, new)
        return len(idea.entries) + 1

    def set_summary(self, idea: Idea, text: str) -> Idea:
        """Rewrite the Summary section only."""
        idea, parsed = self._fresh(idea)
        body = [SUMMARY_NOTE, *([line.rstrip() for line in _norm(text).strip().split("\n")] if text.strip() else []), ""]
        lines = parsed.lines
        if SUMMARY in parsed.spans:
            start, end = parsed.spans[SUMMARY]
            new = lines[:start + 1] + body + lines[end:]
        else:
            first = min((s for s, _ in parsed.spans.values()), default=len(lines))
            new = lines[:first] + [f"## {SUMMARY}", *body] + lines[first:]
        self._write_lines(idea, new)
        return self.get(idea.id)


def summarize(llm, model: str | None, idea: Idea) -> str:
    notes = "\n\n".join(part for part in (idea.loose, idea.notes.strip()) if part)
    result = llm.generate_json(idea_summary_prompt(idea.title, idea.entries, notes), IdeaSummary,
                               system=IDEA_SYSTEM, model=model)
    return result.summary.strip()


def try_summary(store: IdeaStore, llm, model: str | None, idea: Idea) -> Idea:
    """Write the Summary now if the model answers; otherwise the note keeps its old one."""
    try:
        return store.set_summary(idea, summarize(llm, model, idea))
    except (LLMError, ValueError):
        return idea


def open_ideas(store: IdeaStore) -> list[tuple[str, str, str]]:
    """(id, title, gist) of every idea not Done or Dropped, for the memory prompt."""
    return [(i.id, i.title, gist(i.summary, i.entries)) for i in store.all() if not i.resting]


def capture(store: IdeaStore, llm, model: str | None, drafts: list[MemoryDraft], message: str, now: datetime,
            via: str) -> dict | None:
    """The message as an idea: added to the idea the first draft names (`idea_ref`), else a new note titled by it.
    Several idea drafts are one train of thought, so only the first counts."""
    if not drafts:
        return None
    draft = drafts[0]
    existing = store.get(draft.idea_ref.strip()) if draft.idea_ref.strip() else None
    if existing is not None:
        entry, action = store.append(existing, message, now, via), "added"
        idea = store.get(existing.id)
    else:
        idea, entry, action = store.create(draft.title or draft.text or "Idea", message, now, via), 1, "new"
    idea = try_summary(store, llm, model, idea)
    return {"action": action, "id": idea.id, "title": idea.title, "path": store.display_path(idea), "entry": entry}


def pick_of_the_day(store: IdeaStore, today: date) -> Idea | None:
    """The idea for today's digest: in the rotation (remind on, not Done/Dropped), shown longest ago (never shown
    first, then oldest). The same idea all day; records today as its last-shown day."""
    state = store.state()
    if not state["remind"]:
        return None
    pool = [i for i in store.all() if i.remind and not i.resting]
    if not pool:
        return None
    shown, day = state["shown"], today.isoformat()
    pick = next((i for i in pool if shown.get(i.id) == day), None)
    if pick is None:
        pick = min(pool, key=lambda i: (shown.get(i.id, ""), i.created, _id_number(i.id)))
        shown[pick.id] = day
        store._save_state(state)
    return pick


def gist(summary: str, entries: list[str]) -> str:
    """First sentence of the Summary; without one, the start of what was said."""
    text = " ".join(summary.split())
    if text:
        return _SENTENCE.split(text, maxsplit=1)[0]
    said = " ".join(entries[0].split()) if entries else ""
    return said if len(said) <= GIST_CHARS else said[:GIST_CHARS - 1] + "…"
