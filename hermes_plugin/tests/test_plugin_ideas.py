import asyncio

from knowledge_hub.runner import RunResult
from knowledge_hub.texts import IDEA_USAGE, format_ideas, format_memory_added
from test_plugin_handlers import FakeRunner, make_plugin

NEW = {"action": "new", "id": "i3", "title": "Plant-watering robot", "path": "Ideas/Plant-watering robot.md",
       "entry": 1}
ADDED = {**NEW, "action": "added", "entry": 2}
IDEA_ADDED = RunResult(0, {"ok": True, "added": [], "skipped": [], "question": False, "idea": NEW}, "")
TASK = {"id": "m5", "kind": "task", "text": "Pay rent", "due": "2026-10-23", "status": "open"}


def test_format_new_idea_with_and_without_tasks():
    assert format_memory_added({"added": [], "idea": NEW}) == \
        "💡 New idea: Plant-watering robot\n→ Ideas/Plant-watering robot.md"
    assert format_memory_added({"added": [TASK], "idea": ADDED}) == \
        "➕ Added to: Plant-watering robot\n🧠 Got it:\n• task: Pay rent — due Fri 23/10/2026 (m5)"
    assert format_memory_added({"added": [TASK], "idea": None}).startswith("🧠 Got it:")


def test_format_ideas():
    assert format_ideas({"remind": True, "count": 2, "total": 3}) == \
        "💡 Idea of the day: on (2 of 3 ideas take turns). /ideas off stops it."
    assert format_ideas({"remind": False, "count": 2, "total": 3}) == \
        "💡 Idea of the day: off. /ideas on starts it again."


def test_idea_and_ideas_commands(tmp_path):
    runner = FakeRunner([IDEA_ADDED, RunResult(0, {"ok": True, "remind": False, "count": 1, "total": 1}, "")])
    plugin = make_plugin(tmp_path, runner)
    assert asyncio.run(plugin.cmd_idea("  ")) == IDEA_USAGE
    assert asyncio.run(plugin.cmd_idea("a plant robot")).startswith("💡 New idea:")
    assert asyncio.run(plugin.cmd_ideas(" OFF ")).startswith("💡 Idea of the day: off")
    assert runner.calls == [("memory-add", "--kind", "idea", "--via", "cli", "--", "a plant robot"), ("ideas", "off")]
    assert asyncio.run(plugin.cmd_ideas("maybe")) == "Usage: /ideas, /ideas on or /ideas off"
