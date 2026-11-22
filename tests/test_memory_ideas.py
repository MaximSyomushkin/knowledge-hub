from datetime import date

from fakes import FakeLLM
from knowledgehub.memory import MemoryDoc, add_from_message
from knowledgehub.prompts import memory_prompt
from knowledgehub.schemas import MemoryDraft, MemoryExtraction

TODAY = date(2026, 10, 4)


def test_memory_prompt_offers_ideas_and_lists_existing_ones():
    prompt = memory_prompt("x", TODAY, ideas=[("i3", "Plant-watering robot", "A plant robot.")])
    assert "- idea:" in prompt
    assert "i3: Plant-watering robot: A plant robot." in prompt
    assert "idea_ref" in prompt and "title" in prompt
    assert prompt.rstrip().endswith("x")


def test_memory_prompt_without_ideas_and_only_idea():
    assert "- idea:" not in memory_prompt("x", TODAY, allow_ideas=False)
    assert "exactly one item of kind idea" in memory_prompt("x", TODAY, only_idea=True)


def test_add_from_message_keeps_idea_drafts_out_of_memory():
    doc = MemoryDoc([])
    llm = FakeLLM(memory=MemoryExtraction(items=[
        MemoryDraft(kind="idea", text="plant robot", title="Plant-watering robot"),
        MemoryDraft(kind="task", text="Pay rent", due="2026-10-09"),
    ]))
    result = add_from_message(doc, llm, None, "plant robot idea and pay rent friday", TODAY)
    assert [i.text for i in result["added"]] == ["Pay rent"]
    assert [d.title for d in result["ideas"]] == ["Plant-watering robot"]
    assert all(i.kind != "idea" for i in doc.items())
    assert result["question"] is False


def test_add_from_message_without_ideas_keeps_an_idea_as_a_task():
    llm = FakeLLM(memory=MemoryExtraction(items=[MemoryDraft(kind="idea", text="", title="Plant robot")]))
    result = add_from_message(MemoryDoc([]), llm, None, "plant robot", TODAY, allow_ideas=False)
    assert [(i.kind, i.text) for i in result["added"]] == [("task", "Plant robot")]
    assert result["ideas"] == []


def test_add_from_message_only_idea_ignores_other_kinds():
    llm = FakeLLM(memory=MemoryExtraction(items=[MemoryDraft(kind="task", text="Build a plant robot")]))
    result = add_from_message(MemoryDoc([]), llm, None, "build a plant robot", TODAY, only_idea=True)
    assert result["added"] == []
    assert [(d.kind, d.title) for d in result["ideas"]] == [("idea", "Build a plant robot")]


def test_only_idea_with_nothing_back_still_makes_an_idea():
    llm = FakeLLM(memory=MemoryExtraction(items=[]))
    result = add_from_message(MemoryDoc([]), llm, None, "a little robot that waters plants. it beeps", TODAY,
                              only_idea=True)
    assert [d.title for d in result["ideas"]] == ["a little robot that waters plants"]
