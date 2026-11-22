from datetime import date

import pytest

from knowledgehub.digest import daily, weekly
from knowledgehub.memory import MemoryDoc, clean_drafts, list_items, mark_done
from knowledgehub.recur import Rule, parse_rule
from knowledgehub.schemas import MemoryDraft

SUNDAY = date(2026, 10, 4)


@pytest.mark.parametrize("text, rule, rendered", [
    ("every day", Rule("day"), "every day"),
    ("every 3 days", Rule("day", 3), "every 3 days"),
    ("every weekday", Rule("weekday"), "every weekday"),
    ("Every week", Rule("week"), "every week"),
    ("every 2 weeks", Rule("week", 2), "every 2 weeks"),
    ("every week on Tuesday", Rule("week", 1, (1,)), "every week on Tuesday"),
    ("every week on thursday, monday", Rule("week", 1, (0, 3)), "every week on Monday, Thursday"),
    ("every Tuesday", Rule("week", 1, (1,)), "every week on Tuesday"),
    ("every mon and wed", Rule("week", 1, (0, 2)), "every week on Monday, Wednesday"),
    ("🔁 every month", Rule("month"), "every month"),
])
def test_parse_and_render(text, rule, rendered):
    assert parse_rule(text) == rule
    assert rule.render() == rendered


@pytest.mark.parametrize("text", ["", None, "every other tuesday", "sometimes", "every 0 days",
                                  "every day on monday", "every funday"])
def test_unknown_rules_are_none(text):
    assert parse_rule(text) is None


def test_occurrences():
    start = date(2026, 10, 6)  # a Tuesday
    weekly_tue = parse_rule("every week on Tuesday")
    assert [weekly_tue.occurs(start, date(2026, 10, d)) for d in (5, 6, 13, 14)] == [False, True, True, False]
    fortnight = parse_rule("every 2 weeks")
    assert fortnight.occurs(start, date(2026, 10, 20)) and not fortnight.occurs(start, date(2026, 10, 13))
    assert parse_rule("every weekday").occurs(start, date(2026, 10, 9))
    assert not parse_rule("every weekday").occurs(start, date(2026, 10, 10))
    assert parse_rule("every month").first_on_or_after(date(2026, 1, 31), date(2026, 2, 1)) == date(2026, 3, 31)
    assert weekly_tue.first_on_or_after(start, date(2026, 10, 7)) == date(2026, 10, 13)


def test_repeat_round_trips_in_tasks_order():
    line = "## Events\n- Physics lab ⏰ 10:00 🔁 every week on Tuesday 📅 2026-10-06 ➕ 2026-10-04 ^m4\n"
    doc = MemoryDoc.parse(line)
    [lab] = doc.items()
    assert (lab.text, lab.time, lab.repeat, lab.due) == ("Physics lab", "10:00", "every week on Tuesday",
                                                         "2026-10-06")
    assert doc.render() == line
    odd = MemoryDoc.parse("## Events\n- Club 🔁 every other friday 📅 2026-10-09 ^m5\n")
    assert odd.items()[0].repeat == "every other friday" and odd.items()[0].rule is None  # kept, not guessed


def test_ticking_a_repeating_task_writes_the_next_copy_above_it():
    doc = MemoryDoc.parse("## Tasks\n- [ ] Problem sheet ⏰ 17:00 🔁 every week 📅 2026-10-05 ➕ 2026-09-28 ^m1\n"
                          "- [ ] Other ^m2\n")
    ticked, following = mark_done(doc, "m1", SUNDAY)
    assert ticked.checked and following.due == "2026-10-12" and following.id == 3
    assert doc.render() == ("## Tasks\n"
                            "- [ ] Problem sheet ⏰ 17:00 🔁 every week 📅 2026-10-12 ➕ 2026-10-04 ^m3\n"
                            "- [x] Problem sheet ⏰ 17:00 🔁 every week 📅 2026-10-05 ➕ 2026-09-28 ✅ 2026-10-04 ^m1\n"
                            "- [ ] Other ^m2\n")


def test_drafts_keep_valid_rules_and_find_the_first_date():
    items = clean_drafts([
        MemoryDraft(kind="event", text="Lab", due="", time="10:00", repeat="every Tuesday"),
        MemoryDraft(kind="task", text="Gym", due="2026-10-05", repeat="every other day"),
    ], SUNDAY)
    assert [(i.kind, i.due, i.time, i.repeat) for i in items] == [
        ("event", "2026-10-06", "10:00", "every week on Tuesday"),
        ("task", "2026-10-05", None, None)]


TIMETABLE = """## Events
- Physics lab ⏰ 10:00 🔁 every week on Tuesday 📅 2026-09-15 ^m4
- Lecture ⏰ 09:00 🔁 every week on Monday, Thursday 📅 2026-09-14 ^m5
"""


def test_repeating_events_show_up_in_digests_and_lists():
    items = MemoryDoc.parse(TIMETABLE).items()
    text, _ = daily(items, date(2026, 10, 5))  # a Monday
    assert text.split("\n")[1:] == ["", "## 📌 Today", "- 09:00 Lecture (event)", "",
                                    "## ⏭️ Tomorrow, Tue 06/10/2026", "- 10:00 Physics lab (event)"]
    week, sections = weekly(items, SUNDAY)
    assert list(sections["agenda"]) == ["2026-10-05", "2026-10-06", "2026-10-08"]
    listed = list_items(MemoryDoc.parse(TIMETABLE), SUNDAY)
    assert [i.text for i in listed] == ["Lecture", "Physics lab"]  # by next date: Mon 5, Tue 6
