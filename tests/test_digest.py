from datetime import date

from knowledgehub.digest import daily, weekend, weekly
from knowledgehub.memory import MemoryDoc

FRIDAY = date(2026, 10, 9)
SUNDAY = date(2026, 10, 4)
PING = "123456789012345678"

DAILY_MEMORY = """## Tasks
- [ ] A 📅 2026-10-07 ^m3
- [ ] B 📅 2026-10-09 ^m5
- [ ] D ⏰ 14:30 📅 2026-10-10 ^m6
- [ ] F 📅 2026-10-20 ^m9
- [x] G 📅 2026-10-01 ✅ 2026-10-02 ^m4
- [x] Done today 📅 2026-10-09 ✅ 2026-10-08 ^m11
- [ ] H ^m10

## Events
- C ⏰ 09:00 📅 2026-10-09 ^m8
- E 📅 2026-10-13 ^m7
- Old 📅 2026-10-01 ^m2

## Facts
- Likes tea ^m1
"""


def items(text):
    return MemoryDoc.parse(text).items()


def test_daily_digest_all_sections():
    text, sections = daily(items(DAILY_MEMORY), FRIDAY)
    assert text == "\n".join([
        "# ☀️ Friday 09/10/2026",
        "",
        "## ⚠️ Overdue",
        "- A · was due Wed 07/10/2026 (m3)",
        "",
        "## 📌 Today",
        "- 09:00 C (event)",
        "- B (m5)",
        "",
        "## ⏭️ Tomorrow, Sat 10/10/2026",
        "- 14:30 D (m6)",
    ])
    assert [i["id"] for i in sections["overdue"]] == ["m3"]
    assert [i["id"] for i in sections["today"]] == ["m8", "m5"]
    assert sections["tomorrow"][0]["time"] == "14:30"


def test_daily_digest_is_empty_when_nothing_to_say():
    quiet = "## Tasks\n- [ ] H ^m10\n- [ ] F 📅 2026-10-20 ^m9\n\n## Facts\n- Likes tea ^m1\n"
    assert daily(items(quiet), FRIDAY)[0] == ""
    assert daily([], FRIDAY)[0] == ""
    assert daily([], FRIDAY, mention=PING)[0] == ""


def test_daily_digest_always_shows_today_and_tomorrow():
    text, _ = daily(items("## Tasks\n- [ ] B 📅 2026-10-09 ^m5\n"), FRIDAY)
    assert text == "# ☀️ Friday 09/10/2026\n\n## 📌 Today\n- B (m5)\n\n## ⏭️ Tomorrow, Sat 10/10/2026\n- Nothing due"
    text, _ = daily(items("## Tasks\n- [ ] D 📅 2026-10-10 ^m6\n"), FRIDAY)
    assert text == "# ☀️ Friday 09/10/2026\n\n## 📌 Today\n- Nothing due\n\n## ⏭️ Tomorrow, Sat 10/10/2026\n- D (m6)"


IDEA = {"title": "Plant-watering robot", "created": "2026-10-22", "gist": "A plant robot.",
        "path": "Ideas/Plant-watering robot.md"}


def test_daily_digest_mentions_and_ends_with_the_idea():
    text, sections = daily(items("## Tasks\n- [ ] B 📅 2026-10-09 ^m5\n"), FRIDAY, idea=IDEA, mention=PING)
    lines = text.split("\n")
    assert lines[:2] == [f"<@{PING}>", "# ☀️ Friday 09/10/2026"]
    assert lines[-5:] == ["", "## 💡 Idea", "**Plant-watering robot** · from 22/10/2026", "A plant robot.",
                          "-# Ideas/Plant-watering robot.md"]
    assert sections["idea"] == IDEA


def test_daily_digest_with_only_an_idea_still_posts():
    text, _ = daily([], FRIDAY, idea=IDEA)
    assert text.startswith("# ☀️ Friday 09/10/2026\n\n## 📌 Today\n- Nothing due")
    assert "## 💡 Idea" in text


def test_daily_digest_leads_with_health_warnings():
    text, sections = daily([], date(2026, 10, 5), ["⚠️ watcher down"])
    assert text.split("\n")[:2] == ["# ☀️ Monday 05/10/2026", "⚠️ watcher down"]
    assert sections["health"] == ["⚠️ watcher down"]


WEEKLY_MEMORY = """## Tasks
- [x] Lab 2 ➕ 2026-09-30 ✅ 2026-10-04 ^m2
- [ ] Finish lab report ⏰ 17:00 📅 2026-10-05 ➕ 2026-10-01 ^m3
- [ ] Late essay 📅 2026-10-02 ➕ 2026-09-20 ^m4
- [ ] Buy cable ➕ 2026-10-03 ^m5
- [ ] Call bank ^m11
- [ ] Far away 📅 2026-10-20 ^m12

## Events
- Lab quiz ⏰ 10:00 📅 2026-10-06 ➕ 2026-10-02 ^m7
- Party 📅 2026-10-11 ^m8
- Too late 📅 2026-10-12 ^m9
"""


def test_weekly_recap_added_this_week_and_next_week():
    text, sections = weekly(items(WEEKLY_MEMORY), SUNDAY, mention=PING)
    assert text.split("\n") == [
        f"<@{PING}>",
        "# 📅 Week of 28/09/2026 – 04/10/2026",
        "",
        "## 🆕 Added this week",
        "- task: Lab 2 (m2)",
        "- task: Finish lab report — Mon 05/10/2026 17:00 (m3)",
        "- event: Lab quiz — Tue 06/10/2026 10:00",
        "- task: Buy cable (m5)",
        "",
        "## 🗓️ Next week, 05/10/2026 – 11/10/2026",
        "**Mon 05/10/2026**",
        "- 17:00 Finish lab report (m3)",
        "**Tue 06/10/2026**",
        "- 10:00 Lab quiz (event)",
        "**Sun 11/10/2026**",
        "- Party (event)",
        "",
        "## ⚠️ Still open, due by today",
        "- Late essay · was due Fri 02/10/2026 (m4)",
        "",
        "-# 📝 2 open tasks without a date (/todo lists them)",
    ]
    assert sections["week"] == ["2026-09-28", "2026-10-04"]
    assert sections["next_week"] == ["2026-10-05", "2026-10-11"]
    assert list(sections["agenda"]) == ["2026-10-05", "2026-10-06", "2026-10-11"]
    assert sections["undated"] == 2


def test_weekly_next_week_is_the_monday_after_any_day():
    _, sections = weekly([], date(2026, 10, 7))
    assert sections["next_week"] == ["2026-10-12", "2026-10-18"]


def test_weekly_recap_nothing_added_and_empty():
    nothing_added, _ = weekly(items("## Events\n- Exam ⏰ 09:30 📅 2026-10-07 ^m2\n"), SUNDAY)
    assert nothing_added.split("\n")[1:] == ["", "## 🆕 Added this week", "Nothing new", "",
                                             "## 🗓️ Next week, 05/10/2026 – 11/10/2026",
                                             "**Wed 07/10/2026**", "- 09:30 Exam (event)"]
    assert weekly([], SUNDAY)[0] == ""
    assert weekly([], SUNDAY, mention=PING)[0] == ""


WEEKEND_MEMORY = """## Tasks
- [ ] Lab report 📅 2026-10-21 ^m7
- [ ] Pay rent 📅 2026-10-23 ^m5
- [ ] Sheet ⏰ 09:00 📅 2026-10-26 ^m2
- [ ] Finish physics lab 📅 2026-10-26 ^m1
- [ ] Last day 📅 2026-11-01 ^m3
- [ ] Too far 📅 2026-11-02 ^m4
- [x] Done 📅 2026-10-24 ✅ 2026-10-20 ^m6
- [ ] Undated one ^m8
- [ ] Undated two ^m9
- [ ] Gym 🔁 every week on Saturday 📅 2026-10-24 ^m10

## Events
- Lecture 📅 2026-10-26 ^m11
"""


def test_weekend_work_friday_runs_to_the_sunday_after_next():
    text, sections = weekend(items(WEEKEND_MEMORY), date(2026, 10, 23), mention=PING)
    assert text.split("\n") == [
        f"<@{PING}>",
        "# 🛠️ Weekend work · Fri 23/10",
        "",
        "## ⚠️ Overdue",
        "- Lab report · was due Wed 21/10 (m7)",
        "",
        "## 📅 Due by Sun 01/11",
        "**Fri 23/10**",
        "- Pay rent (m5)",
        "**Sat 24/10**",
        "- Gym (m10)",
        "**Mon 26/10**",
        "- 09:00 Sheet (m2)",
        "- Finish physics lab (m1)",
        "**Sun 01/11**",
        "- Last day (m3)",
        "",
        "-# 📝 2 open tasks with no date (/todo lists them)",
    ]
    assert sections["window"] == ["2026-10-23", "2026-11-01"]
    assert sections["undated"] == 2


def test_weekend_work_saturday_shares_the_window():
    text, sections = weekend(items(WEEKEND_MEMORY), date(2026, 10, 24))
    assert text.split("\n")[0] == "# 🛠️ Weekend work · Sat 24/10"
    assert sections["window"] == ["2026-10-24", "2026-11-01"]
    assert "- Pay rent · was due Fri 23/10 (m5)" in text


def test_weekend_work_nothing_due_and_silent_when_empty():
    text, _ = weekend(items("## Tasks\n- [ ] Undated ^m1\n"), date(2026, 10, 23))
    assert text == ("# 🛠️ Weekend work · Fri 23/10\n\n## 📅 Due by Sun 01/11\nNothing due\n\n"
                    "-# 📝 1 open task with no date (/todo lists them)")
    assert weekend(items("## Events\n- Lecture 📅 2026-10-26 ^m11\n"), date(2026, 10, 23), mention=PING)[0] == ""


def test_daily_digest_counts_down_to_events_from_three_days_out():
    memory = """## Tasks
- [ ] Task in two days 📅 2026-10-11 ^m1

## Events
- History exam ⏰ 09:30 📅 2026-10-12 ^m2
- Concert 📅 2026-10-11 ^m3
- Too far 📅 2026-10-13 ^m4
- Lab ⏰ 10:00 📅 2026-10-06 🔁 every week on Monday ^m5
"""
    text, sections = daily(items(memory), FRIDAY)
    assert "\n".join([
        "## 🔜 Coming up",
        "- Concert · Sun 11/10, in 2 days",
        "- History exam · Mon 12/10 09:30, in 3 days",
    ]) in text
    assert text.index("## ⏭️ Tomorrow") < text.index("## 🔜 Coming up")
    assert [i["id"] for i in sections["coming"]] == ["m3", "m2"]


def test_daily_digest_posts_for_a_coming_event_alone():
    text, _ = daily(items("## Events\n- Exam 📅 2026-10-12 ^m1\n"), FRIDAY)
    assert "- Exam · Mon 12/10, in 3 days" in text
