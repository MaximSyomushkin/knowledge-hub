"""Folder picker logic, free of Discord: map sandbox paths to the vault on disk, list folders, and track where a
picker is (path + page), what its message says and which buttons it shows.

Paths are always sandbox paths (/vault/readwrite/...), the form the agent's tools take.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

PAGE_SIZE = 20  # folder buttons per page: rows 0-3 of a Discord message, 5 per row
FILES_SHOWN = 15
LABEL_MAX = 80  # Discord button label limit
CONTENT_MAX = 2000  # Discord message limit


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _natural(name: str) -> list[tuple[int, int | str]]:
    """Sort key so "Lecture 2" comes before "Lecture 10"."""
    return [(0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", name.lower())]


@dataclass(frozen=True)
class Listing:
    path: str
    folders: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


class FolderBrowser:
    """Read-only view of the vault folders the agent's sandbox can see; nothing outside ``roots`` is reachable."""

    def __init__(self, vault: Path, roots: dict[str, str]):
        self.vault = Path(vault)
        self.roots = dict(roots)  # sandbox path -> vault-relative folder
        self._top = {root.rsplit("/", 1)[-1]: root for root in self.roots}

    def _root_of(self, path: str) -> str | None:
        return next((r for r in self.roots if path == r or path.startswith(r + "/")), None)

    def _root_dir(self, root: str) -> Path:
        return (self.vault / self.roots[root]).resolve()

    def _within(self, root: str, candidate: Path) -> bool:
        try:
            return candidate.resolve().is_relative_to(self._root_dir(root))
        except OSError:
            return False

    def host(self, path: str) -> Path | None:
        root = self._root_of(path)
        if root is None:
            return None
        rest = [p for p in path[len(root):].split("/") if p]
        candidate = self.vault.joinpath(self.roots[root], *rest)
        return candidate if self._within(root, candidate) else None

    def normalize(self, path: str) -> str:
        """A safe starting point: "" (top level) for escapes or paths outside the roots, otherwise the deepest
        existing folder along ``path`` (a wrong guess or a file name stops at the folder above it)."""
        cleaned = (path or "").strip().replace("\\", "/").rstrip("/")
        parts = [p for p in cleaned.split("/") if p]
        if any(p in (".", "..") for p in parts):
            return ""
        root = self._root_of("/" + "/".join(parts))
        if root is None:
            return ""
        current = root
        for part in parts[len(root.strip("/").split("/")):]:
            base = self.host(current)
            if base is None:
                return ""
            candidate = base / part
            if part.startswith(".") or not self._within(root, candidate) or not candidate.is_dir():
                break
            current = f"{current}/{part}"
        return current

    def listing(self, path: str) -> Listing:
        if not path:
            return Listing("", sorted(self._top, key=_natural))
        root = self._root_of(path)
        folder = self.host(path)
        folders, files = [], []
        try:
            for entry in folder.iterdir() if folder is not None and root is not None else []:
                if entry.name.startswith(".") or not self._within(root, entry):
                    continue
                (folders if entry.is_dir() else files).append(entry.name)
        except OSError:
            pass
        return Listing(path, sorted(folders, key=_natural), sorted(files, key=_natural))

    def child(self, path: str, name: str) -> str:
        return f"{path}/{name}" if path else self._top[name]

    def parent(self, path: str) -> str:
        if not path or path in self.roots:
            return ""
        return path.rsplit("/", 1)[0]


@dataclass(frozen=True)
class Button:
    key: str  # what press() takes: f:<index on page>, up, prev, next, ok, cancel
    label: str
    kind: str  # folder, nav, ok, cancel
    row: int
    disabled: bool = False


class PickerState:
    """Where one picker is. ``press`` moves it and returns "ok" or "cancel" when the user is done."""

    def __init__(self, browser: FolderBrowser, start: str = "", question: str = ""):
        self.browser = browser
        self.question = _clip((question or "").strip(), 300)
        self._go(browser.normalize(start))

    def _go(self, path: str) -> None:
        self.path = path
        self.page = 0
        self.listing = self.browser.listing(path)

    @property
    def pages(self) -> int:
        return max(1, math.ceil(len(self.listing.folders) / PAGE_SIZE))

    def _page_folders(self) -> list[str]:
        return self.listing.folders[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]

    def buttons(self) -> list[Button]:
        out = [Button(f"f:{i}", _clip(name, LABEL_MAX), "folder", i // 5) for i, name in enumerate(self._page_folders())]
        out.append(Button("up", "⬆ Up", "nav", 4, disabled=not self.path))
        if self.pages > 1:
            out.append(Button("prev", "◀", "nav", 4, disabled=self.page == 0))
            out.append(Button("next", "▶", "nav", 4, disabled=self.page >= self.pages - 1))
        out.append(Button("ok", "✅ Use this folder", "ok", 4, disabled=not self.path))
        out.append(Button("cancel", "✖ Cancel", "cancel", 4))
        return out

    def press(self, key: str) -> str | None:
        enabled = {b.key for b in self.buttons() if not b.disabled}
        if key not in enabled:
            return None  # stale click on a button that is gone or disabled
        if key in ("ok", "cancel"):
            return key
        if key == "up":
            self._go(self.browser.parent(self.path))
        elif key == "prev":
            self.page -= 1
        elif key == "next":
            self.page += 1
        else:
            self._go(self.browser.child(self.path, self._page_folders()[int(key[2:])]))
        return None

    def content(self) -> str:
        lines = [self.question] if self.question else []
        lines.append(f"📂 `{self.path}`" if self.path else "📂 **Vault** — pick a folder")
        folders, files = self.listing.folders, self.listing.files
        if self.pages > 1:
            lines.append(f"📁 {len(folders)} folders (page {self.page + 1}/{self.pages})")
        lines += [f"📄 {_clip(name, 100)}" for name in files[:FILES_SHOWN]]
        if len(files) > FILES_SHOWN:
            lines.append(f"…and {len(files) - FILES_SHOWN} more files")
        if not folders and not files:
            lines.append("(empty)")
        return _clip("\n".join(lines), CONTENT_MAX)

    def final_text(self, outcome: str, hint: str = "") -> str:
        if outcome == "ok":
            return f"📁 Picked `{self.path}`" + (f"\n{hint}" if hint else "")
        if outcome == "cancel":
            return "✖ Cancelled — no folder picked."
        return "⌛ Folder picker expired."
