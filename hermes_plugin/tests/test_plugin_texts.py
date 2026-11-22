from knowledge_hub.texts import (MEMORY_NOTHING, MEMORY_QUESTION, TODO_EMPTY, fmt_day, format_done, format_forgot,
                            format_memory_added, format_todo, heard, split_message)


def test_messages_split_at_discord_limit():
    assert [len(part) for part in split_message("x" * 4500)] == [2000, 2000, 500]




def test_heard_echo():
    assert heard("what is a graph") == "🎙️ heard: what is a graph"




def test_split_message_prefers_paragraphs():
    text = ("a" * 50 + "\n\n") * 3
    parts = split_message(text, limit=110)
    assert all(len(p) <= 110 for p in parts)
    assert "".join(parts).replace("\n", "") == "a" * 150


def test_split_message_hard_splits_long_line():
    parts = split_message("x" * 250, limit=100)
    assert [len(p) for p in parts] == [100, 100, 50]


def test_split_message_short_text_unchanged():
    assert split_message("hi") == ["hi"]












TASK = {"id": "m3", "kind": "task", "text": "Finish lab report", "due": "2026-10-09", "status": "open"}
EVENT = {"id": "m2", "kind": "event", "text": "Physics exam", "due": "2026-10-20"}
FACT = {"id": "m4", "kind": "fact", "text": "Likes tea", "due": None}


def test_fmt_day():
    assert fmt_day("2026-10-09") == "Fri 09/10/2026"


def test_format_memory_added_variants():
    added = format_memory_added({"added": [TASK, EVENT, FACT], "skipped": [], "question": False})
    assert added == ("🧠 Got it:\n• task: Finish lab report — due Fri 09/10/2026 (m3)\n"
                     "• event: Physics exam — Tue 20/10/2026 (m2)\n• fact: Likes tea (m4)")
    both = format_memory_added({"added": [FACT], "skipped": ["Finish lab report"], "question": False})
    assert both.endswith("\n(already had: Finish lab report)")
    assert format_memory_added({"added": [], "skipped": ["X"], "question": False}) == "👍 I already have that: X"
    assert format_memory_added({"added": [], "skipped": [], "question": True}) == MEMORY_QUESTION
    assert format_memory_added({"added": [], "skipped": [], "question": False}) == MEMORY_NOTHING


def test_format_todo():
    undated = {"id": "m5", "kind": "task", "text": "Buy cable", "due": None, "status": "open"}
    text = format_todo({"items": [TASK, undated, EVENT, FACT]})
    assert text == ("📝 To do:\nm3 Finish lab report — due Fri 09/10/2026\nm5 Buy cable\n"
                    "🗓️ Coming up:\nm2 Physics exam — Tue 20/10/2026")
    assert format_todo({"items": [FACT]}) == TODO_EMPTY


def test_format_done_and_forgot():
    assert format_done(TASK) == "✅ Done: Finish lab report (m3)"
    assert format_forgot(EVENT) == "🗑️ Forgot: Physics exam (m2)"


def test_memory_replies_show_the_time():
    added = {"added": [{"id": "m4", "kind": "event", "text": "Exam", "due": "2026-10-20", "time": "09:30"}]}
    assert format_memory_added(added) == "🧠 Got it:\n• event: Exam — Tue 20/10/2026, 09:30 (m4)"
    todo = {"items": [{"id": "m1", "kind": "task", "text": "Lab", "due": "2026-10-09", "time": "14:00"}]}
    assert format_todo(todo) == "📝 To do:\nm1 Lab — due Fri 09/10/2026, 14:00"


def test_repeats_show_in_replies_and_done_names_the_next_copy():
    lab = {"id": "m4", "kind": "event", "text": "Lab", "due": "2026-10-06", "time": "10:00",
           "repeat": "every week on Tuesday"}
    assert format_todo({"items": [lab]}) == "🗓️ Coming up:\nm4 Lab — Tue 06/10/2026, 10:00, 🔁 every week on Tuesday"
    done = {"id": "m1", "kind": "task", "text": "Sheet", "next": {"id": "m3", "kind": "task", "text": "Sheet",
                                                                 "due": "2026-10-12", "repeat": "every week"}}
    assert format_done(done) == "✅ Done: Sheet (m1)\n🔁 Next: Sheet — due Mon 12/10/2026, 🔁 every week (m3)"
