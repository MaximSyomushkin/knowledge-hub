"""Pydantic schemas for structured JSON LLM responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MemoryKind = Literal["task", "event", "idea"]


class MemoryDraft(BaseModel):
    kind: MemoryKind
    text: str
    due: str = ""  # YYYY-MM-DD, or "" when the message gives no date
    time: str = ""  # HH:MM (24-hour), or "" when the message gives no time
    repeat: str = ""  # e.g. "every week on Tuesday", or "" for a one-off
    title: str = ""  # ideas: a short name, e.g. "Plant-watering robot"
    idea_ref: str = ""  # ideas: the id of an existing idea this message adds to (i3), or ""


class MemoryExtraction(BaseModel):
    items: list[MemoryDraft] = Field(default_factory=list)
    is_question: bool = False


class IdeaSummary(BaseModel):
    summary: str
