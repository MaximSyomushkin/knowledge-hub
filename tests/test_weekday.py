from datetime import date

import pytest

from fakes import FakeLLM
from knowledgehub.memory import MemoryDoc, add_from_message, weekday_due
from knowledgehub.schemas import MemoryDraft, MemoryExtraction

TUESDAY = date(2026, 11, 3)


@pytest.mark.parametrize("message, due", [
    ("gym on monday", "2026-11-09"),
    ("email professor about the lab extension by friday", "2026-11-06"),
    ("submit the essay this sunday", "2026-11-08"),
    ("meeting with tutor on Wednesday 11am", "2026-11-04"),
    ("football friday after next", "2026-11-13"),
    ("call mum on tues", "2026-11-10"),  # the day named is today: the next one
    ("dentist next thursday at 3pm", "2026-11-05"),
])
def test_weekday_due(message, due):
    assert weekday_due(message, TUESDAY)[0].isoformat() == due


@pytest.mark.parametrize("message", [
    "buy milk tomorrow",
    "gym on monday and dentist on thursday",  # two days: the model decides
    "exam on friday the 20th",
    "party on saturday 14 november",
    "lab every tuesday",
    "do the weekday shopping",
    "nothing about days",
    "thursday or friday, whichever is free",
])
def test_weekday_due_leaves_other_messages_alone(message):
    assert weekday_due(message, TUESDAY) is None


def test_next_weekday_accepts_the_week_after_too():
    day, week_later_ok = weekday_due("dentist next thursday", TUESDAY)
    assert (day.isoformat(), week_later_ok) == ("2026-11-05", True)
    assert weekday_due("dentist on thursday", TUESDAY)[1] is False


def _add(message, *drafts):
    llm = FakeLLM(memory=MemoryExtraction(items=list(drafts)))
    return add_from_message(MemoryDoc([]), llm, None, message, TUESDAY)["added"]


def test_add_from_message_corrects_a_wrong_weekday():
    [item] = _add("email professor by friday", MemoryDraft(kind="task", text="Email professor", due="2026-11-07"))
    assert item.due == "2026-11-06"


def test_add_from_message_keeps_next_week_for_next_weekday():
    [item] = _add("dentist next thursday", MemoryDraft(kind="event", text="Dentist", due="2026-11-12"))
    assert item.due == "2026-11-12"


def test_add_from_message_leaves_undated_and_repeating_items():
    undated, repeating = _add("gym on monday, buy milk",
                              MemoryDraft(kind="task", text="Buy milk", due=""),
                              MemoryDraft(kind="event", text="Gym", due="2026-11-10", repeat="every week"))
    assert undated.due is None
    assert repeating.due == "2026-11-10"
