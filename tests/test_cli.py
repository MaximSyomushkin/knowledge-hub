import json

import pytest
from typer.testing import CliRunner

from fakes import FakeLLM
from knowledgehub import cli

runner = CliRunner()


@pytest.fixture
def toml(vault_dir, tmp_path):
    path = tmp_path / "khub.toml"
    path.write_text(f"vault = '{vault_dir}'\nschool_dirs = ['ReadWrite/Year-1']\n", encoding="utf-8")
    return path


def run(toml, *args):
    return runner.invoke(cli.app, ["--config", str(toml), *args])


def jout(result):
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_bad_config_is_input_error(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("vault = 'x'\nold_dir = 'W'\n", encoding="utf-8")
    result = run(bad, "memory-list", "--json")
    assert result.exit_code == 1 and "unknown keys" in jout(result)["error"]


def test_bad_via_is_input_error(toml):
    assert run(toml, "memory-add", "--via", "fax", "--json", "--", "x").exit_code == 1


def test_lecture_notes_writes_hubs_then_has_nothing_to_do(toml, vault_dir):
    lecture = vault_dir / "ReadWrite/Year-1/Intro-to-Physics/Lecture 1"
    lecture.mkdir(parents=True)
    (lecture / "Lecture1.pdf").write_bytes(b"%PDF")
    written = jout(run(toml, "lecture-notes", "--json"))["written"]
    assert written == ["ReadWrite/Year-1/Intro-to-Physics/Lecture 1/Lecture 1.md",
                       "ReadWrite/Year-1/Intro-to-Physics/Intro to Physics.md"]
    assert run(toml, "lecture-notes").stdout == "all lecture notes up to date\n"


def test_memory_add_list_done_forget(toml, cfg, monkeypatch):
    from knowledgehub.schemas import MemoryDraft, MemoryExtraction

    llm = FakeLLM(memory=MemoryExtraction(items=[MemoryDraft(kind="task", text="Finish lab", due="2026-10-09"),
                                                 MemoryDraft(kind="event", text="Exam", due="2026-10-20")]))
    monkeypatch.setattr(cli, "make_llm", lambda c: llm)
    added = jout(run(toml, "memory-add", "--today", "2026-10-04", "--json", "--", "lab friday, exam on the 20th"))
    assert [(i["id"], i["kind"], i["due"]) for i in added["added"]] == [("m1", "task", "2026-10-09"),
                                                                         ("m2", "event", "2026-10-20")]
    assert added["question"] is False and added["skipped"] == []
    text = (cfg.memory_root / "memory.md").read_text(encoding="utf-8")
    assert "- [ ] Finish lab 📅 2026-10-09 ➕ 2026-10-04 ^m1" in text

    listed = jout(run(toml, "memory-list", "--today", "2026-10-04", "--json"))
    assert [i["id"] for i in listed["items"]] == ["m1", "m2"]
    assert listed["items"][0]["status"] == "open"

    done = jout(run(toml, "memory-done", "--today", "2026-10-05", "--json", "--", "lab"))
    assert done["item"]["status"] == "done" and done["item"]["done"] == "2026-10-05"
    assert jout(run(toml, "memory-list", "--kind", "task", "--json"))["items"] == []

    gone = jout(run(toml, "memory-forget", "--json", "--", "m2"))
    assert gone["item"]["text"] == "Exam"
    assert "Exam" not in (cfg.memory_root / "memory.md").read_text(encoding="utf-8")


def test_memory_bad_ref_and_server_down(toml, monkeypatch):
    monkeypatch.setattr(cli, "make_llm", lambda c: FakeLLM(unavailable=True))
    result = run(toml, "memory-done", "--json", "--", "nothing")
    assert result.exit_code == 1 and "nothing matches" in jout(result)["error"]
    assert run(toml, "memory-add", "--json", "--", "x").exit_code == 2
    assert run(toml, "memory-list", "--kind", "bogus", "--json").exit_code == 1


def test_digest_empty_prints_nothing(toml):
    result = run(toml, "digest", "--no-health", "--today", "2026-10-09")
    assert result.exit_code == 0 and result.stdout == ""
    data = jout(run(toml, "digest", "--weekly", "--today", "2026-10-09", "--json"))
    assert data["text"] == "" and data["sections"]["undated"] == 0


def test_digest_daily_and_weekly(toml, cfg):
    (cfg.memory_root / "memory.md").write_text(
        "## Tasks\n- [ ] Lab report 📅 2026-10-09 ^m1\n- [x] Email ✅ 2026-10-08 ^m2\n", encoding="utf-8")
    result = run(toml, "digest", "--no-health", "--today", "2026-10-09")
    assert result.exit_code == 0
    assert result.stdout == ("# ☀️ Friday 09/10/2026\n\n## 📌 Today\n- Lab report (m1)\n\n"
                             "## ⏭️ Tomorrow, Sat 10/10/2026\n- Nothing due\n")
    week = jout(run(toml, "digest", "--weekly", "--today", "2026-10-09", "--json"))
    assert "## ⚠️ Still open, due by today\n- Lab report · was due Fri 09/10/2026 (m1)" in week["text"]


def test_digest_mention_idea_of_the_day_and_weekend(toml, cfg):
    toml.write_text(toml.read_text(encoding="utf-8") + "[digest]\nmention = '123456789012345678'\n", encoding="utf-8")
    (cfg.memory_root / "memory.md").write_text("## Tasks\n- [ ] Pay rent 📅 2026-10-23 ^m1\n", encoding="utf-8")
    from datetime import datetime

    from knowledgehub.ideas import IdeaStore
    from knowledgehub.vault import Vault

    store = IdeaStore(Vault(cli.load_config(toml)))
    store.set_summary(store.create("Plant robot", "a plant robot", datetime(2026, 10, 22, 9, 0), "telegram"), "Waters plants. More.")
    day = run(toml, "digest", "--no-health", "--today", "2026-10-23").stdout
    assert day.startswith("<@123456789012345678>\n# ☀️ Friday 23/10/2026\n")
    assert day.endswith("## 💡 Idea\n**Plant robot** · from 22/10/2026\nWaters plants.\n-# Ideas/Plant robot.md\n")
    assert store.state()["shown"] == {"i1": "2026-10-23"}
    end = run(toml, "digest", "--weekend", "--today", "2026-10-23").stdout
    assert end.startswith("<@123456789012345678>\n# 🛠️ Weekend work · Fri 23/10\n")
    assert run(toml, "digest", "--weekend", "--weekly", "--today", "2026-10-23").exit_code == 1
    store.set_reminders(False)
    assert "💡" not in run(toml, "digest", "--no-health", "--today", "2026-10-24").stdout


def test_digest_health_and_remind(toml, cfg):
    result = run(toml, "digest", "--today", "2026-10-09")
    assert "hub watcher isn't running" in result.stdout  # no heartbeat yet
    (cfg.memory_root / "memory.md").write_text("## Events\n- Exam ⏰ 09:30 📅 2026-10-09 ^m1\n", encoding="utf-8")
    first = run(toml, "remind", "--now", "2026-10-09 09:00")
    assert first.exit_code == 0 and first.stdout == "⏰ 09:30, in 30 min: Exam (event)\n"
    assert run(toml, "remind", "--now", "2026-10-09 09:15").stdout == ""
