"""Lecture notes: one `Lecture N.md` per lecture folder, linking that lecture's sheets and its neighbours.

`<school dir>/<Course>/.../Lecture N/Lecture N.md` gets: the previous and next lecture, a line of links to every
other note in the folder (study guide, visual notes, practical first), and the lecture PDF embedded. Links use
full vault paths with a short label, because every course has its own "Lecture 1". Whatever is under
`## My Notes` is kept; the rest is regenerated, and a file is only written when its text would change.

The sheets next to it (study guide, visual notes, practical) get the same treatment for their own links: a bare
`[[Lecture 1]]` or `![[Lecture1.pdf]]` that names exactly one file of the course is given its full path, so it
keeps pointing at this course once another course has a "Lecture 1" too. Lecture and course notes carry
`cssclasses: [study]` for the vault's `study.css` snippet.

Only notes directly inside a `Lecture N` folder are written: the hub itself and the generated sheets
(`*_notes`, `*_study`, `*_visual`, `*_practical`). The user's own notes, `*_mynotes.md` included, are never touched.

A lecture folder is any `Lecture N` or `LectureN` folder under the course, at any depth (`Week1/Lecture1`);
lectures chain by number across those subfolders.

Each course with lectures also gets a course note, `<Course>/<Course name>.md` (e.g. "Intro to Physics.md"):
the subject's node in the graph, listing every lecture; each lecture note links back up to it. A note of the
user's with that name, without `type: course`, is left alone.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .config import Config
from .names import course_name, course_note_name


FOLDER = re.compile(r"^Lecture ?(\d+)$", re.IGNORECASE)
SHEETS = (("_notes", "Lecture notes"), ("_study", "Study guide"), ("_visual", "Visual notes"), ("_practical", "Practical"),
          ("_mynotes", "My notes"))
# The user's own notes per lecture: linked from the hub, never rewritten.
MY_NOTES_SUFFIX = "_mynotes"
_MY_NOTES = "## My Notes"
CSS_CLASS = "study"


def _frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 3)
        if end != -1:
            try:
                loaded = yaml.safe_load(text[4:end])
            except yaml.YAMLError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded, text[end + 5:]
    return {}, text


def _link(cfg: Config, path: Path, label: str) -> str:
    target = path.relative_to(cfg.vault).with_suffix("").as_posix() if path.suffix == ".md" \
        else path.relative_to(cfg.vault).as_posix()
    return f"[[{target}|{label}]]"


def _sheet_order(path: Path) -> tuple[int, str]:
    stem = path.stem.casefold()
    for rank, (suffix, _) in enumerate(SHEETS):
        if stem.endswith(suffix):
            return rank, stem
    return len(SHEETS), stem


def _label(path: Path) -> str:
    stem = path.stem.casefold()
    for suffix, name in SHEETS:
        if stem.endswith(suffix):
            return name
    return path.stem


def _sheet_meta(sheets: list[Path]) -> dict:
    """course and topic from the lecture's own sheets (the practical, study guide and visual notes carry them)."""
    found: dict = {}
    for sheet in sheets:
        try:
            meta, _ = _frontmatter(sheet.read_text(encoding="utf-8").replace("\r\n", "\n"))
        except OSError:
            continue
        for key in ("course", "topic"):
            if meta.get(key) and key not in found:
                found[key] = meta[key]
    return found


def render(cfg: Config, course: Path, folder: Path, number: int, prev: Path | None, nxt: Path | None,
           existing: str) -> str:
    hub = folder / f"Lecture {number}.md"
    meta, body = _frontmatter(existing.replace("\r\n", "\n"))
    files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name.casefold())
    sheets = sorted((p for p in files if p.suffix.lower() == ".md" and p.name != hub.name), key=_sheet_order)
    pdfs = [p for p in files if p.suffix.lower() == ".pdf"]
    from_sheets = _sheet_meta(sheets)
    # The folder name is only a stand-in until a sheet names the course; any other name is the user's and stays.
    own_course = meta.get("course") if meta.get("course") != course_name(course.name) else None
    meta = {"course": own_course or from_sheets.get("course") or course_name(course.name),
            "lecture": number, **({"topic": meta.get("topic") or from_sheets["topic"]}
                                  if meta.get("topic") or from_sheets.get("topic") else {}),
            "type": "lecture", "tags": meta.get("tags") or ["lecture-hub"],
            "cssclasses": meta.get("cssclasses") or [CSS_CLASS],
            **{k: v for k, v in meta.items() if k not in ("course", "lecture", "topic", "type", "tags", "cssclasses")}}
    notes = body[body.index(_MY_NOTES) + len(_MY_NOTES):].strip("\n") if _MY_NOTES in body else ""

    title = f"# Lecture {number}" + (f": {meta['topic']}" if meta.get("topic") else "")
    up = f"↑ {_link(cfg, course / course_note_name(course.name), course_name(course.name))}"
    nav = " · ".join(part for part in (
        f"← {_link(cfg, prev, prev.stem)}" if prev else "",
        f"{_link(cfg, nxt, nxt.stem)} →" if nxt else "") if part)
    links = " · ".join(_link(cfg, sheet, _label(sheet)) for sheet in sheets) or "No study notes yet."
    # An embed takes no label: after "|" Obsidian reads a display size, not text.
    parts = [title, up, nav, links, *(f"![[{pdf.relative_to(cfg.vault).as_posix()}]]" for pdf in pdfs)]
    return _note(meta, parts, notes)


def _note(meta: dict, parts: list[str], notes: str) -> str:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, default_flow_style=None)
    text = f"---\n{front}---\n\n" + "\n\n".join(p for p in parts if p) + f"\n\n{_MY_NOTES}\n"
    return text + (f"\n{notes}\n" if notes else "")


def render_course(cfg: Config, course: Path, lectures: list[tuple[Path, dict]], existing: str) -> str | None:
    """The course note: one line per lecture note (with its topic). None when a note of the user's already has
    the name (it has no `type: course`), so it is never overwritten."""
    meta, body = _frontmatter(existing.replace("\r\n", "\n"))
    if existing.strip() and meta.get("type") != "course":
        return None
    name = course_name(course.name)
    # The full module name from the lecture notes ("PHYS101 Intro to Physics"), else the folder's.
    full = next((str(m["course"]) for _, m in lectures if m.get("course") and m["course"] != name), name)
    meta = {"course": meta.get("course") or full, "type": "course", "tags": meta.get("tags") or ["course-hub"],
            "cssclasses": meta.get("cssclasses") or [CSS_CLASS],
            **{k: v for k, v in meta.items() if k not in ("course", "type", "tags", "cssclasses")}}
    notes = body[body.index(_MY_NOTES) + len(_MY_NOTES):].strip("\n") if _MY_NOTES in body else ""
    items = "\n".join(f"- {_link(cfg, hub, hub.stem)}" + (f" — {m['topic']}" if m.get("topic") else "")
                      for hub, m in lectures)
    return _note(meta, [f"# {meta['course']}", items], notes)


def _generated_sheet(path: Path) -> bool:
    stem = path.stem.casefold()
    return path.suffix.lower() == ".md" and any(stem.endswith(suffix) for suffix, _ in SHEETS
                                                 if suffix != MY_NOTES_SUFFIX)


def _write(cfg: Config, path: Path, text: str, *, sheet: bool = False) -> None:
    """Atomic write, refused anywhere but a note directly in a `Lecture N` folder under a school dir:
    `Lecture N.md` itself, or (with `sheet`) a generated sheet, e.g. `Lecture6_study.md`; or a course note,
    `<Course>/<Course name>.md` right below a school dir."""
    roots = [(cfg.vault / school).resolve() for school in cfg.school_dirs]
    resolved = path.resolve()
    course_note = resolved.parent.parent in roots and resolved.name == course_note_name(resolved.parent.name)
    match = FOLDER.match(resolved.parent.name)
    allowed = sheet and _generated_sheet(resolved) or match and resolved.name == f"Lecture {match.group(1)}.md"
    lecture_note = any(resolved.is_relative_to(root) for root in roots) and match and allowed
    if not (course_note or lecture_note):
        raise PermissionError(f"not a lecture note this tool may write: {path}")
    tmp = resolved.with_name(resolved.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, resolved)


_WIKILINK = re.compile(r"(!?)\[\[([^\]|#]+)(#[^\]|]*)?(\|[^\]]*)?\]\]")


def course_files(course: Path) -> dict[str, list[Path]]:
    """Every file under a course folder by lower-case name, notes also by name without `.md`."""
    names: dict[str, list[Path]] = {}
    for path in course.rglob("*"):
        if path.is_file() and not path.name.endswith(".tmp"):
            names.setdefault(path.name.casefold(), []).append(path)
            if path.suffix.lower() == ".md":
                names.setdefault(path.stem.casefold(), []).append(path)
    return names


def qualify_links(cfg: Config, text: str, files: dict[str, list[Path]]) -> str:
    """Bare links and embeds that name exactly one file of this course get its full vault path, so a second
    course with its own "Lecture 1" cannot capture them. A link keeps showing what it showed before (the old
    name becomes its label); an embed keeps any `|size`. Paths, unknown and ambiguous names are left alone."""
    def fix(match: re.Match) -> str:
        bang, target, heading, tail = match.group(1), match.group(2).strip(), match.group(3) or "", match.group(4) or ""
        hits = files.get(target.casefold(), []) if "/" not in target else []
        if len(hits) != 1:
            return match.group(0)
        rel = hits[0].relative_to(cfg.vault).as_posix()
        rel = rel[:-3] if hits[0].suffix.lower() == ".md" else rel
        if bang:
            return f"![[{rel}{heading}{tail}]]"
        return f"[[{rel}{heading}{tail or '|' + target + heading}]]"

    return _WIKILINK.sub(fix, text)


def lecture_folders(course: Path) -> list[tuple[int, Path]]:
    """Every lecture folder under a course, at any depth, by lecture number. Hidden folders and asset folders
    (`_slides/Lecture3`, `_figures/Lecture3`) are skipped."""
    found = [(int(m.group(1)), path) for path in course.rglob("*")
             if path.is_dir() and (m := FOLDER.match(path.name))
             and not any(part.startswith((".", "_")) for part in path.relative_to(course).parts)]
    return sorted(found, key=lambda item: (item[0], item[1].as_posix().casefold()))


def refresh(cfg: Config) -> list[Path]:
    """Create or update every lecture note and course note, and give bare links in the lecture's sheets full
    paths; returns the files written."""
    written: list[Path] = []
    for school in cfg.school_dirs:
        root = cfg.vault / school
        courses = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        for course in courses:
            lectures = lecture_folders(course)
            hubs = [folder / f"Lecture {number}.md" for number, folder in lectures]
            rendered: list[tuple[Path, dict]] = []
            for index, (number, folder) in enumerate(lectures):
                hub = hubs[index]
                existing = hub.read_text(encoding="utf-8") if hub.exists() else ""
                text = render(cfg, course, folder, number, hubs[index - 1] if index else None,
                              hubs[index + 1] if index + 1 < len(hubs) else None, existing)
                rendered.append((hub, _frontmatter(text)[0]))
                if text != existing.replace("\r\n", "\n"):
                    _write(cfg, hub, text)
                    written.append(hub)
            if lectures:
                note = course / course_note_name(course.name)
                existing = note.read_text(encoding="utf-8") if note.exists() else ""
                text = render_course(cfg, course, rendered, existing)
                if text is not None and text != existing.replace("\r\n", "\n"):
                    _write(cfg, note, text)
                    written.append(note)
            files = course_files(course) if lectures else {}
            for _, folder in lectures:
                for sheet in sorted(folder.glob("*.md")):
                    if not _generated_sheet(sheet):
                        continue  # the lecture note itself, or a note of the user's
                    old = sheet.read_text(encoding="utf-8").replace("\r\n", "\n")
                    new = qualify_links(cfg, old, files)
                    if new != old:
                        _write(cfg, sheet, new, sheet=True)
                        written.append(sheet)
    return written
