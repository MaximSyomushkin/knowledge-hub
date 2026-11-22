import json
from datetime import date, datetime

import pytest

from knowledgehub.ideas import IdeaStore, gist, note_text, pick_of_the_day, try_summary

from fakes import FakeLLM

WHEN = datetime(2026, 10, 22, 14, 5)
ROBOT = "What if there was a little desk robot that checks soil moisture and waters plants"

EXPECTED_NOTE = """---
type: idea
id: i1
created: 2026-10-22
status: New
remind: true
---
# Plant-watering robot

Status: `INPUT[inlineSelect(option(New), option(Exploring), option(Building), option(Done), option(Dropped)):status]`

## Summary
<!-- Rewritten by the bot from everything below. Put your own thoughts in My Notes. -->

## What I said

### 22/10/2026 14:05 · Telegram
> What if there was a little desk robot that checks soil moisture and waters plants

## My Notes
"""


@pytest.fixture
def store(vault):
    return IdeaStore(vault)


def test_new_note_has_the_spec_layout():
    assert note_text("i1", "Plant-watering robot", date(2026, 10, 22), ROBOT, WHEN, "telegram") == EXPECTED_NOTE


def test_create_writes_note_named_after_title(store, cfg):
    idea = store.create("Plant-watering robot", ROBOT, WHEN, "telegram")
    path = cfg.vault / "ReadWrite" / "Ideas" / "Plant-watering robot.md"
    assert idea.path == path.resolve()
    assert path.read_text(encoding="utf-8") == EXPECTED_NOTE
    assert (idea.id, idea.title, idea.status, idea.remind) == ("i1", "Plant-watering robot", "New", True)
    assert store.display_path(idea) == "Ideas/Plant-watering robot.md"


def test_file_name_is_cleaned_and_collisions_numbered(store):
    first = store.create('Robot: "bot" / v2?', "a", WHEN, "telegram")
    second = store.create('Robot: "bot" / v2?', "b", WHEN, "discord")
    assert first.path.name == "Robot bot v2.md"
    assert second.path.name == "Robot bot v2 (2).md"
    assert second.id == "i2"


def test_ids_are_never_reused_after_delete(store):
    store.create("One", "a", WHEN, "telegram")
    two = store.create("Two", "b", WHEN, "telegram")
    two.path.unlink()
    assert store.create("Three", "c", WHEN, "telegram").id == "i3"


def test_append_keeps_earlier_text_byte_for_byte(store):
    idea = store.create("Plant-watering robot", ROBOT, WHEN, "telegram")
    before = idea.path.read_text(encoding="utf-8")
    n = store.append(idea, "Add a light sensor too.\nIt moves toward the window.", datetime(2026, 10, 24, 9, 0), "discord")
    after = idea.path.read_text(encoding="utf-8")
    assert n == 2
    head, _, tail = before.partition("## My Notes")
    assert after.startswith(head.rstrip("\n"))
    assert ("### 24/10/2026 09:00 · Discord\n> Add a light sensor too.\n> It moves toward the window.\n\n## My Notes"
            in after)
    assert store.get("i1").entries == [ROBOT, "Add a light sensor too.\nIt moves toward the window."]




def test_set_summary_only_touches_summary(store):
    idea = store.create("Plant-watering robot", ROBOT, WHEN, "telegram")
    text = idea.path.read_text(encoding="utf-8").replace("## My Notes\n", "## My Notes\nMine.\n## Not a section\nkeep\n")
    idea.path.write_text(text, encoding="utf-8", newline="\n")
    store.set_summary(store.get("i1"), "A plant robot.\nWith sensors.")
    after = idea.path.read_text(encoding="utf-8")
    assert after == text.replace("in My Notes. -->\n", "in My Notes. -->\nA plant robot.\nWith sensors.\n")
    assert store.get("i1").summary == "A plant robot.\nWith sensors."
    assert store.get("i1").notes.strip() == "Mine.\n## Not a section\nkeep"




def test_crlf_note_and_renamed_file_are_found_by_id(store):
    idea = store.create("Plant-watering robot", ROBOT, WHEN, "telegram")
    moved = idea.path.with_name("Robots.md")
    text = idea.path.read_text(encoding="utf-8").replace("# Plant-watering robot", "# Plant bot")
    moved.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    idea.path.unlink()
    found = store.get("i1")
    assert (found.path.name, found.title, found.entries) == ("Robots.md", "Plant bot", [ROBOT])
    store.set_summary(found, "Waters plants.")
    assert "## Summary\n<!-- Rewritten by the bot from everything below. Put your own thoughts in My Notes. -->\nWaters plants.\n" \
        in moved.read_text(encoding="utf-8")


def test_notes_without_idea_front_matter_are_ignored(store, cfg):
    folder = cfg.vault / "ReadWrite" / "Ideas"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scratch.md").write_text("# Just a note\n", encoding="utf-8")
    (folder / "broken.md").write_text("---\ntype: idea\n: [\n---\n# x\n", encoding="utf-8")
    assert store.all() == []


def test_corrupt_state_file_is_rebuilt(store, cfg):
    store.create("One", "a", WHEN, "telegram")
    (cfg.vault / "ReadWrite" / "Ideas" / ".ideas.json").write_text("{not json", encoding="utf-8")
    assert store.state()["remind"] is True
    assert store.create("Two", "b", WHEN, "telegram").id == "i2"


def test_reminders_switch(store, cfg):
    store.set_reminders(False)
    assert json.loads((cfg.vault / "ReadWrite" / "Ideas" / ".ideas.json").read_text(encoding="utf-8"))["remind"] is False
    assert store.state()["remind"] is False




def test_set_summary_keeps_a_section_added_under_the_summary(store):
    idea = store.create("Plant-watering robot", ROBOT, WHEN, "telegram")
    text = idea.path.read_text(encoding="utf-8").replace("## What I said", "## Links\nhttps://example.com\n\n## What I said")
    idea.path.write_text(text, encoding="utf-8", newline="\n")
    store.set_summary(store.get("i1"), "Waters plants.")
    after = idea.path.read_text(encoding="utf-8")
    assert "## Links\nhttps://example.com\n\n## What I said" in after and "-->\nWaters plants.\n" in after


def test_text_above_the_first_entry_feeds_the_summary(store):
    idea = store.create("Plant-watering robot", ROBOT, WHEN, "telegram")
    text = idea.path.read_text(encoding="utf-8").replace("## What I said\n", "## What I said\nLoose thought.\n")
    idea.path.write_text(text, encoding="utf-8", newline="\n")
    llm = FakeLLM()
    try_summary(store, llm, None, store.get("i1"))
    assert "Loose thought." in llm.calls[0][1]




def _set_front(idea, key, value):
    text = idea.path.read_text(encoding="utf-8")
    lines = [f"{key}: {value}" if line.startswith(f"{key}:") else line for line in text.split("\n")]
    idea.path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def test_pick_of_the_day_rotates_longest_unseen_first(store):
    one = store.create("One", "a", datetime(2026, 10, 1, 9, 0), "telegram")
    two = store.create("Two", "b", datetime(2026, 10, 2, 9, 0), "telegram")
    _set_front(one, "created", "2026-10-01")
    _set_front(two, "created", "2026-10-02")
    assert pick_of_the_day(store, date(2026, 10, 22)).id == "i1"
    assert pick_of_the_day(store, date(2026, 10, 22)).id == "i1"  # same day, same idea
    assert pick_of_the_day(store, date(2026, 10, 23)).id == "i2"
    assert pick_of_the_day(store, date(2026, 10, 24)).id == "i1"


def test_pick_skips_remind_false_done_dropped_and_switched_off(store):
    a = store.create("A", "a", WHEN, "telegram")
    b = store.create("B", "b", WHEN, "telegram")
    c = store.create("C", "c", WHEN, "telegram")
    _set_front(a, "remind", "false")
    _set_front(b, "status", "Done")
    _set_front(c, "status", "Dropped")
    assert pick_of_the_day(store, date(2026, 10, 22)) is None
    d = store.create("D", "d", WHEN, "telegram")
    assert pick_of_the_day(store, date(2026, 10, 22)).id == d.id
    store.set_reminders(False)
    assert pick_of_the_day(store, date(2026, 10, 23)) is None


def test_gist_is_first_sentence_or_start_of_what_was_said(store):
    assert gist("A plant robot. Sensors check soil moisture.", []) == "A plant robot."
    assert gist("", ["x" * 200]) == "x" * 139 + "…"
    assert gist("", []) == ""
