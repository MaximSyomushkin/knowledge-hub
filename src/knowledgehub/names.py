"""Course folder names."""

from __future__ import annotations


def course_name(folder: str) -> str:
    """A course folder's name as words: "Intro-to-Physics" -> "Intro to Physics"."""
    return " ".join(folder.replace("-", " ").replace("_", " ").split())


def course_note_name(folder: str) -> str:
    """File name of the generated course note directly in a course folder, e.g. "Intro to Physics.md"."""
    return f"{course_name(folder)}.md"
