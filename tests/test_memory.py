from datetime import date

import pytest
from pydantic import ValidationError

from fakes import FakeLLM
from knowledgehub.memory import (HEADER, Item, MemoryDoc, MemoryStore, add_from_message, clean_drafts, find_item, forget,
                            expire_tasks, list_items, mark_done)
from knowledgehub.prompts import memory_prompt
from knowledgehub.schemas import MemoryDraft, MemoryExtraction

TODAY = date(2026, 10, 4)

SAMPLE = """# Memory

What you asked the bot to remember. Edit freely: tick tasks, fix dates (📅 YYYY-MM-DD), delete lines.

## Tasks
- [ ] Finish lab report 📅 2026-10-09 ➕ 2026-10-04 ^m3
- [x] Email tutor ➕ 2026-10-01 ✅ 2026-10-03 ^m1
- [ ] Buy HDMI cable ➕ 2026-10-02 ^m5

## Events
- Physics exam 📅 2026-10-20 ➕ 2026-10-04 ^m2
- Old meetup 📅 2026-09-01 ➕ 2026-08-20 ^m6

## Facts
- Prefers short explanations ➕ 2026-10-04 ^m4
"""


def ids(items):
    return [i.id for i in items]


def test_parse_reads_kinds_and_tokens():
    doc = MemoryDoc.parse(SAMPLE)
    by_id = {i.id: i for i in doc.items()}
    assert by_id[3] == Item("task", "Finish lab report", id=3, due="2026-10-09", added="2026-10-04")
    assert by_id[1].checked and by_id[1].done == "2026-10-03" and not by_id[1].is_open
    assert by_id[2].kind == "event" and by_id[2].due == "2026-10-20"
    assert 4 not in by_id  # a Facts section from before facts were dropped is kept as plain notes


def test_canonical_file_round_trips():
    assert MemoryDoc.parse(SAMPLE).render() == SAMPLE


def test_tokens_in_any_order_are_normalised():
    doc = MemoryDoc.parse("## Tasks\n- [ ] ^m7 Pay rent ➕ 2026-10-01 📅 2026-10-05\n")
    assert doc.render() == "## Tasks\n- [ ] Pay rent 📅 2026-10-05 ➕ 2026-10-01 ^m7\n"


def test_foreign_lines_survive_add():
    text = "# Memory\n\nmy own intro\n\n## Tasks\n- [ ] A ^m1\nfree text under tasks\n\n## Notes\n- not an item\n"
    doc = MemoryDoc.parse(text)
    doc.add(Item("task", "B", added="2026-10-04"))
    doc.assign_ids()
    out = doc.render()
    assert "my own intro" in out and "free text under tasks" in out
    assert "## Notes\n- not an item" in out
    assert out.index("- [ ] B ➕ 2026-10-04 ^m2") < out.index("## Notes")
    assert [i.text for i in MemoryDoc.parse(out).items()] == ["A", "B"]


def test_hand_written_line_gets_next_id():
    doc = MemoryDoc.parse("## Tasks\n- [ ] A ^m4\n- [ ] typed in Obsidian 📅 2026-10-10\n")
    doc.assign_ids()
    assert ids(doc.items()) == [4, 5]


def test_add_creates_missing_sections_in_order():
    doc = MemoryDoc.parse("")
    doc.add(Item("event", "E", due="2026-10-20"))
    doc.add(Item("task", "T"))
    doc.assign_ids()
    out = doc.render()
    assert out.startswith(HEADER)
    assert out.index("## Events") < out.index("- E") and out.index("## Tasks") < out.index("- [ ] T")
    assert "## Facts" not in out


def test_store_load_missing_and_save(vault):
    store = MemoryStore(vault)
    assert store.path == vault.memory_root / "memory.md"
    doc = store.load()
    assert doc.items() == []
    doc.add(Item("task", "T", added="2026-10-04"))
    doc.assign_ids()
    store.save(doc)
    assert store.path.read_text(encoding="utf-8").startswith("# Memory")
    assert [i.text for i in store.load().items()] == ["T"]


def test_list_items_default_and_all():
    doc = MemoryDoc.parse(SAMPLE)
    assert ids(list_items(doc, TODAY)) == [3, 5, 2]
    assert ids(list_items(doc, TODAY, all_=True)) == [3, 5, 1, 2, 6]
    assert ids(list_items(doc, TODAY, kind="event", all_=True)) == [2, 6]


def test_find_item_by_id_text_and_errors():
    items = MemoryDoc.parse(SAMPLE).items()
    assert find_item(items, "m3").id == 3
    assert find_item(items, "3").id == 3
    assert find_item(items, "hdmi").id == 5
    with pytest.raises(ValueError, match="m3: Finish lab report"):
        find_item(items, "e")
    with pytest.raises(ValueError, match="nothing matches"):
        find_item(items, "zebra")
    with pytest.raises(ValueError, match="nothing matches"):
        find_item(items, "m99")


def test_mark_done_only_open_tasks():
    doc = MemoryDoc.parse(SAMPLE)
    item, following = mark_done(doc, "lab report", TODAY)
    assert following is None
    assert item.checked and item.done == "2026-10-04"
    assert "- [x] Finish lab report 📅 2026-10-09 ➕ 2026-10-04 ✅ 2026-10-04 ^m3" in doc.render()
    with pytest.raises(ValueError):
        mark_done(doc, "m1", TODAY)  # already done
    with pytest.raises(ValueError):
        mark_done(doc, "m2", TODAY)  # an event, not a task


def test_forget_removes_only_that_line():
    doc = MemoryDoc.parse(SAMPLE)
    item = forget(doc, "m2")
    assert item.text == "Physics exam"
    assert doc.render() == SAMPLE.replace("- Physics exam 📅 2026-10-20 ➕ 2026-10-04 ^m2\n", "")


def test_memory_prompt_has_today_a_month_calendar_and_a_worked_example():
    prompt = memory_prompt("finish the lab by friday", TODAY)
    assert "Sunday 2026-10-04" in prompt
    assert "Fri 2026-10-09" in prompt and "Wed 2026-11-04" in prompt
    assert "2026-11-05" not in prompt
    # the example's dates are real dates relative to today: tomorrow, and the next 20th
    assert '"due": "2026-10-05"' in prompt and '"due": "2026-10-20"' in prompt
    assert prompt.rstrip().endswith("finish the lab by friday")


def test_memory_prompt_example_rolls_to_next_month():
    assert '"due": "2026-11-20"' in memory_prompt("x", date(2026, 10, 25))


def test_clean_drafts_validates_dates_and_kinds():
    drafts = [
        MemoryDraft(kind="task", text="  Finish lab  ", due="2026-10-09"),
        MemoryDraft(kind="task", text="Call mum", due="next friday"),
        MemoryDraft(kind="event", text="Concert", due=""),
        MemoryDraft(kind="event", text="Exam", due="2026-10-20"),
        MemoryDraft(kind="task", text="   ", due=""),
        MemoryDraft(kind="task", text="x" * 300),
    ]
    items = clean_drafts(drafts, TODAY)
    assert [(i.kind, i.text[:12], i.due) for i in items] == [
        ("task", "Finish lab", "2026-10-09"), ("task", "Call mum", None),
        ("task", "Concert", None), ("event", "Exam", "2026-10-20"), ("task", "x" * 12, None)]
    assert all(i.added == "2026-10-04" for i in items)
    assert len(items[-1].text) == 200


def test_add_from_message_appends_and_skips_duplicates():
    doc = MemoryDoc.parse(SAMPLE)
    llm = FakeLLM(memory=MemoryExtraction(items=[
        MemoryDraft(kind="task", text="finish lab report", due="2026-10-10"),
        MemoryDraft(kind="task", text="Book dentist", due="2026-10-06"),
    ]))
    result = add_from_message(doc, llm, "qwen", "lab report and dentist", TODAY)
    assert [i.text for i in result["added"]] == ["Book dentist"]
    assert result["skipped"] == ["finish lab report"]
    assert result["question"] is False
    assert llm.calls[0][0] == "MemoryExtraction" and "lab report and dentist" in llm.calls[0][1]
    assert [i.text for i in doc.items() if i.kind == "task"][-1] == "Book dentist"


def test_add_from_message_reports_questions():
    llm = FakeLLM(memory=MemoryExtraction(items=[], is_question=True))
    result = add_from_message(MemoryDoc([]), llm, "qwen", "what's due?", TODAY)
    assert result == {"added": [], "skipped": [], "question": True, "ideas": []}


def test_question_mark_with_nothing_extracted_counts_as_a_question():
    llm = FakeLLM(memory=MemoryExtraction(items=[], is_question=False))
    assert add_from_message(MemoryDoc([]), llm, None, "what do I have this week? ", TODAY)["question"] is True
    assert add_from_message(MemoryDoc([]), llm, None, "nothing here", TODAY)["question"] is False


def test_time_round_trips_before_the_due_date():
    line = "## Events\n- Exam ⏰ 09:30 📅 2026-10-20 ➕ 2026-10-04 ^m2\n"
    doc = MemoryDoc.parse(line)
    [item] = doc.items()
    assert (item.text, item.time, item.due) == ("Exam", "09:30", "2026-10-20")
    assert doc.render() == line
    assert item.to_dict()["time"] == "09:30"
    # hand-written in another order and an unpadded hour: normalised, time kept in front of the date
    loose = MemoryDoc.parse("## Tasks\n- [ ] Lab 📅 2026-10-09 ⏰ 9:05 ^m3\n")
    assert loose.render() == "## Tasks\n- [ ] Lab ⏰ 09:05 📅 2026-10-09 ^m3\n"


@pytest.mark.parametrize("raw, expected", [
    ("14:00", "14:00"), ("9.30", "09:30"), ("2pm", "14:00"), ("2:30 pm", "14:30"), ("12am", "00:00"),
    ("12 PM", "12:00"), ("9.30am", "09:30"), ("", None), ("14", None), ("25:00", None), ("13pm", None),
    ("noon", None),
])
def test_clock_time(raw, expected):
    from knowledgehub.memory import clock_time

    assert clock_time(raw) == expected


def test_clean_drafts_keeps_a_time_only_with_a_date():
    items = clean_drafts([MemoryDraft(kind="event", text="Exam", due="2026-10-20", time="9:30am"),
                          MemoryDraft(kind="task", text="Call", due="", time="14:00"),
                          MemoryDraft(kind="task", text="Gym", due="", time="07:00")], TODAY)
    assert [(i.text, i.time) for i in items] == [("Exam", "09:30"), ("Call", None), ("Gym", None)]


def test_list_items_puts_timed_items_first_within_a_day():
    doc = MemoryDoc.parse("## Tasks\n- [ ] Late 📅 2026-10-05 ^m1\n- [ ] Early ⏰ 08:00 📅 2026-10-05 ^m2\n"
                          "- [ ] Noon ⏰ 12:00 📅 2026-10-05 ^m3\n")
    assert [i.text for i in list_items(doc, TODAY)] == ["Early", "Noon", "Late"]


def test_memory_prompt_asks_for_a_24_hour_time():
    prompt = memory_prompt("exam friday at 2pm", TODAY)
    assert '"2pm" -> "14:00"' in prompt and '"time": "09:30"' in prompt


def test_expire_tasks_drops_past_due_but_keeps_todays_timed_tasks():
    doc = MemoryDoc.parse(
        "# Memory\n\n## Tasks\n"
        "- [ ] essay 📅 2026-10-04 ^m1\n"
        "- [ ] sports ⏰ 07:00 📅 2026-10-05 ^m2\n"  # due today, its time has passed: stays all day
        "- [ ] gym ⏰ 19:00 📅 2026-10-05 ^m3\n"
        "- [x] get sim ⏰ 08:00 📅 2026-10-04 ✅ 2026-10-04 ^m4\n"  # done and past due: goes too
        "- [ ] someday 🙂 ^m5\n"  # no due date: never expires
        "- [ ] report 📅 2026-10-09 ^m6\n"
        "Notes I wrote here stay.\n"
        "\n## Events\n- dentist 📅 2026-10-01 ^m7\n")
    expired = expire_tasks(doc, date(2026, 10, 5))
    assert [i.id for i in expired] == [1, 4]
    assert [i.id for i in doc.items()] == [2, 3, 5, 6, 7]  # events are not tasks: left alone
    assert "Notes I wrote here stay." in doc.render()
    assert expire_tasks(doc, date(2026, 10, 5)) == []


def test_expire_tasks_moves_an_overdue_repeating_task_to_its_next_date():
    doc = MemoryDoc.parse(
        "## Tasks\n"
        "- [ ] sports ⏰ 18:00 🔁 every week on Tuesday 📅 2026-09-29 ^m1\n"
        "- [x] water plants 🔁 every day 📅 2026-10-04 ✅ 2026-10-04 ^m2\n"  # its next copy already exists
        "- [ ] water plants 🔁 every day 📅 2026-10-05 ^m3\n")
    expired = expire_tasks(doc, date(2026, 10, 5))  # a Monday
    assert [i.id for i in expired] == [2]
    sports, plants = doc.items()
    assert (sports.id, sports.due, sports.time) == (1, "2026-10-06", "18:00")  # next Tuesday, same line
    assert (plants.id, plants.due) == (3, "2026-10-05")


def test_store_expire_writes_only_when_something_changed(vault):
    store = MemoryStore(vault)
    assert store.expire(date(2026, 10, 5)) == [] and not store.path.exists()
    store.path.write_text("## Tasks\n- [ ] essay 📅 2026-10-04 ^m1\n- [ ] gym ⏰ 07:00 📅 2026-10-05 ^m2\n",
                          encoding="utf-8")
    assert [i.text for i in store.expire(date(2026, 10, 5))] == ["essay"]
    assert store.path.read_text(encoding="utf-8") == "## Tasks\n- [ ] gym ⏰ 07:00 📅 2026-10-05 ^m2\n"
    mtime = store.path.stat().st_mtime_ns
    assert store.expire(date(2026, 10, 5)) == [] and store.path.stat().st_mtime_ns == mtime




def test_facts_are_no_longer_a_kind():
    with pytest.raises(ValidationError):
        MemoryDraft(kind="fact", text="Likes tea")
    assert "fact" not in memory_prompt("I am vegetarian", TODAY).split("Kinds:")[1].split("Split")[0]


def test_an_impossible_date_stays_text_and_breaks_nothing():
    from knowledgehub.digest import daily

    doc = MemoryDoc.parse("## Tasks\n- [ ] Typo 📅 2026-02-30 ^m1\n- [ ] Fine 📅 2026-03-01 ^m2\n")
    typo, fine = doc.items()
    assert typo.due is None and typo.text == "Typo 📅 2026-02-30" and fine.due == "2026-03-01"
    assert "Fine (m2)" in daily(doc.items(), date(2026, 3, 1))[0]
    assert "📅 2026-02-30" in doc.render()
