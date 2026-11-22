"""Deterministic stand-in for LlamaServerClient used across tests."""

from __future__ import annotations

from knowledgehub.llm import ModelServerUnavailable
from knowledgehub.schemas import IdeaSummary, MemoryExtraction


class FakeLLM:
    """`memory` is a MemoryExtraction or a function of the prompt; `idea_summary` a string, a function of the
    prompt, or an exception to raise."""

    def __init__(self, memory=None, idea_summary="A tidy summary.", unavailable: bool = False):
        self.memory = memory or MemoryExtraction()
        self.idea_summary = idea_summary
        self.unavailable = unavailable
        self.calls: list[tuple[str, str]] = []

    def _check(self):
        if self.unavailable:
            raise ModelServerUnavailable("The model server is not reachable (fake)")

    def generate_json(self, prompt, schema, *, system="", model=None):
        self._check()
        self.calls.append((schema.__name__, prompt))
        if schema is MemoryExtraction:
            return self.memory(prompt) if callable(self.memory) else self.memory
        if schema is IdeaSummary:
            if isinstance(self.idea_summary, Exception):
                raise self.idea_summary
            if callable(self.idea_summary):
                return IdeaSummary(summary=self.idea_summary(prompt))
            return IdeaSummary(summary=self.idea_summary)
        raise AssertionError(f"unexpected schema {schema}")

    def list_models(self):
        self._check()
        return ["Qwen3.5-4B-Q8_0"]
