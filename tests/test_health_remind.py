import json
from datetime import datetime

from fakes import FakeLLM
from knowledgehub.health import beat, server_problem, watcher_problem
from knowledgehub.remind import STATE, remind

NOW = datetime(2026, 10, 5, 9, 0)


def test_watcher_problem_from_heartbeat(vault):
    assert "isn't running" in watcher_problem(vault, NOW)  # never started
    beat(vault, datetime(2026, 10, 5, 8, 50))
    assert watcher_problem(vault, NOW) is None
    beat(vault, datetime(2026, 10, 5, 7, 0))
    stale = watcher_problem(vault, NOW)
    assert "stopped (last seen Mon 05/10/2026 07:00)" in stale and "khub watch" in stale


def test_server_problem():
    assert server_problem(FakeLLM(), "Qwen3.5-4B-Q8_0") is None
    assert "local model server isn't running" in server_problem(FakeLLM(unavailable=True), "Qwen3.5-4B-Q8_0")
    assert server_problem(FakeLLM(unavailable=True), "claude-opus-5-5") is None  # the CLI needs no server




MEMORY = """## Tasks
- [ ] Hand in sheet ⏰ 09:45 📅 2026-10-05 ^m1
- [x] Done one ⏰ 09:30 📅 2026-10-05 ✅ 2026-10-04 ^m2
- [ ] Untimed 📅 2026-10-05 ^m3

## Events
- Lecture ⏰ 09:20 🔁 every week on Monday 📅 2026-09-14 ^m4
- Late show ⏰ 23:30 📅 2026-10-05 ^m5
- Early train ⏰ 00:15 📅 2026-10-06 ^m6
"""


def test_remind_announces_each_occurrence_once(vault, cfg):
    (cfg.memory_root / "memory.md").write_text(MEMORY, encoding="utf-8")
    assert remind(vault, NOW) == ["⏰ 09:20, in 20 min: Lecture (event)", "⏰ 09:45, in 45 min: Hand in sheet (m1)"]
    assert remind(vault, datetime(2026, 10, 5, 9, 15)) == []  # already sent
    sent = json.loads((vault.state_root / STATE).read_text(encoding="utf-8"))
    assert sorted(sent) == ["1|2026-10-05 09:45", "4|2026-10-05 09:20"]
    assert remind(vault, datetime(2026, 10, 5, 23, 20)) == ["⏰ 23:30, in 10 min: Late show (event)",
                                                            "⏰ 00:15 tomorrow, in 55 min: Early train (event)"]
    # next Monday the repeating lecture is announced again
    assert remind(vault, datetime(2026, 10, 12, 9, 0)) == ["⏰ 09:20, in 20 min: Lecture (event)"]
    # records older than a week are dropped
    assert remind(vault, datetime(2026, 10, 19, 12, 0)) == []
    assert json.loads((vault.state_root / STATE).read_text(encoding="utf-8")) == {}


def test_remind_without_memory_is_quiet(vault, cfg):
    assert remind(vault, NOW) == []
    assert not (vault.state_root / STATE).exists()
