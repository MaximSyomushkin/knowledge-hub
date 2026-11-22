"""Safe file I/O: the hub only writes inside its memory, ideas and state folders."""

from __future__ import annotations

import os
import time
from pathlib import Path

from .config import Config


class PathNotAllowed(Exception):
    """A write outside the folders the hub owns."""


class Vault:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.root = cfg.vault.resolve()
        self.memory_root = cfg.memory_root.resolve()
        self.ideas_root = cfg.ideas_root.resolve()
        self.state_root = cfg.state_dir.resolve()

    def _resolve(self, path: Path | str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve()

    def check_write(self, path: Path | str) -> Path:
        resolved = self._resolve(path)
        if not any(resolved.is_relative_to(root) for root in (self.memory_root, self.ideas_root, self.state_root)):
            raise PathNotAllowed(f"write not allowed: {path}")
        return resolved

    def read_text(self, path: Path | str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_text(self, path: Path | str, text: str) -> None:
        target = self.check_write(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        for attempt in range(5):  # Obsidian or a sync client can hold the file for a moment
            try:
                os.replace(tmp, target)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

    def rel(self, path: Path | str) -> str:
        return self._resolve(path).relative_to(self.root).as_posix()
