import json

import pytest
from typer.testing import CliRunner

from fakes import FakeLLM
from knowledgehub import cli
from knowledgehub.ideas import IdeaStore
from knowledgehub.llm import LLMError
from knowledgehub.schemas import MemoryDraft, MemoryExtraction
from knowledgehub.vault import Vault

runner = CliRunner()
ROBOT = "What if there was a little desk robot that checks soil moisture and waters plants"


@pytest.fixture
def toml(vault_dir, tmp_path):
    path = tmp_path / "khub.toml"
    path.write_text(f"vault = '{vault_dir}'\n", encoding="utf-8")
    return path


def run(toml, *args):
    return runner.invoke(cli.app, ["--config", str(toml), *args])


def jout(result):
    return json.loads(result.stdout.strip().splitlines()[-1])


def model(monkeypatch, *drafts, **kw):
    llm = FakeLLM(memory=MemoryExtraction(items=list(drafts)), **kw)
    monkeypatch.setattr(cli, "make_llm", lambda c: llm)
    return llm


def idea(title, ref="", text="x"):
    return MemoryDraft(kind="idea", text=text, title=title, idea_ref=ref)


def test_new_idea_gets_its_own_note(toml, cfg, monkeypatch):
    model(monkeypatch, idea("Plant-watering robot"), MemoryDraft(kind="task", text="Pay rent", due="2026-10-09"))
    data = jout(run(toml, "memory-add", "--via", "telegram", "--today", "2026-10-04", "--json", "--", ROBOT))
    found = data["idea"]
    assert (found["action"], found["id"], found["title"], found["entry"]) == ("new", "i1", "Plant-watering robot", 1)
    assert found["path"] == "Ideas/Plant-watering robot.md"
    note = (cfg.ideas_root / "Plant-watering robot.md").read_text(encoding="utf-8")
    assert "04/10/2026" in note and f"· Telegram\n> {ROBOT}\n" in note and "-->\nA tidy summary.\n" in note
    assert [i["text"] for i in data["added"]] == ["Pay rent"]
    assert "robot" not in (cfg.memory_root / "memory.md").read_text(encoding="utf-8").casefold()


def test_follow_up_appends_to_the_idea(toml, cfg, monkeypatch):
    model(monkeypatch, idea("Plant-watering robot"))
    jout(run(toml, "memory-add", "--json", "--", ROBOT))
    llm = model(monkeypatch, idea("Plant bot", ref="i1"))
    data = jout(run(toml, "memory-add", "--json", "--", "more on the plant bot: light sensor"))
    assert (data["idea"]["action"], data["idea"]["id"], data["idea"]["entry"]) == ("added", "i1", 2)
    assert data["idea"]["title"] == "Plant-watering robot"
    assert "i1: Plant-watering robot" in llm.calls[0][1]
    assert list(cfg.ideas_root.glob("*.md")) == [cfg.ideas_root / "Plant-watering robot.md"]


def test_unknown_ref_and_several_ideas_make_one_new_note(toml, cfg, monkeypatch):
    model(monkeypatch, idea("Alpha", ref="i9"), idea("Beta"))
    data = jout(run(toml, "memory-add", "--json", "--", "alpha and beta"))
    assert (data["idea"]["action"], data["idea"]["id"]) == ("new", "i1")
    assert [p.name for p in cfg.ideas_root.glob("*.md")] == ["Alpha.md"]


def test_kind_idea_forces_an_idea(toml, cfg, monkeypatch):
    llm = model(monkeypatch, MemoryDraft(kind="task", text="Build a plant robot"))
    data = jout(run(toml, "memory-add", "--kind", "idea", "--json", "--", "build a plant robot"))
    assert data["idea"]["title"] == "Build a plant robot" and data["added"] == []
    assert "exactly one item of kind idea" in llm.calls[0][1]
    assert run(toml, "memory-add", "--kind", "task", "--json", "--", "x").exit_code == 1


def test_summary_failure_keeps_the_note(toml, cfg, monkeypatch):
    model(monkeypatch, idea("Robot"), idea_summary=LLMError("busy"))
    data = jout(run(toml, "memory-add", "--json", "--", ROBOT))
    store = IdeaStore(Vault(cfg))
    assert data["idea"]["id"] == "i1" and store.get("i1").summary == ""
    assert store.get("i1").entries == [ROBOT]


def test_digest_survives_an_odd_created_value(toml, cfg, monkeypatch):
    model(monkeypatch, idea("Robot"))
    jout(run(toml, "memory-add", "--json", "--", ROBOT))
    note = cfg.ideas_root / "Robot.md"
    text = note.read_text(encoding="utf-8")
    note.write_text(text.replace(text.split("created: ")[1].split("\n")[0], "2026-10-22T14:05"), encoding="utf-8")
    result = run(toml, "digest", "--no-health", "--today", "2026-10-23")
    assert result.exit_code == 0 and "**Robot** · from 22/10/2026" in result.stdout
    note.write_text(text.replace(text.split("created: ")[1].split("\n")[0], "someday"), encoding="utf-8")
    result = run(toml, "digest", "--no-health", "--today", "2026-10-24")
    assert result.exit_code == 0 and "**Robot**\n" in result.stdout


def test_ideas_switch_and_count(toml, cfg, monkeypatch):
    model(monkeypatch, idea("Robot"))
    jout(run(toml, "memory-add", "--json", "--", ROBOT))
    assert jout(run(toml, "ideas", "--json")) == {"ok": True, "remind": True, "count": 1, "total": 1}
    assert jout(run(toml, "ideas", "--json", "off"))["remind"] is False
    assert jout(run(toml, "ideas", "--json"))["remind"] is False
    assert jout(run(toml, "ideas", "--json", "on"))["remind"] is True
    assert run(toml, "ideas", "--json", "maybe").exit_code == 1
