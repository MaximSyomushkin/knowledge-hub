"""Load khub.toml into a frozen Config."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """Invalid or missing configuration."""


@dataclass(frozen=True)
class LLMConfig:
    """Model settings for memory extraction and idea summaries. Uses an OpenAI-compatible HTTP endpoint (`url`) by
    default, or the local CLI backend when `model` starts with `claude-`."""

    url: str = "http://127.0.0.1:8080"
    model: str = "Qwen3.5-4B-Q8_0"
    timeout_s: float = 600.0
    claude_command: str = ""  # optional CLI executable for claude-* models; empty uses PATH
    claude_effort: str = ""  # optional --effort flag for CLI models


@dataclass(frozen=True)
class DigestConfig:
    mention: str = ""  # Discord user id put first in every digest so it pings; empty = no mention


@dataclass(frozen=True)
class Config:
    vault: Path
    school_dirs: tuple[str, ...] = ()  # year folders holding <Course>/Lecture N/, e.g. "ReadWrite/Year-1"
    memory_dir: str = "ReadWrite/Memory"
    ideas_dir: str = "ReadWrite/Ideas"
    llm: LLMConfig = field(default_factory=LLMConfig)
    digest: DigestConfig = field(default_factory=DigestConfig)

    @property
    def memory_root(self) -> Path:
        return self.vault / self.memory_dir

    @property
    def ideas_root(self) -> Path:
        return self.vault / self.ideas_dir

    @property
    def state_dir(self) -> Path:
        return self.memory_root / ".state"


_KNOWN = {"vault", "school_dirs", "memory_dir", "ideas_dir", "llm", "digest"}


def config_from_dict(data: dict) -> Config:
    if "vault" not in data:
        raise ConfigError("khub.toml: 'vault' is required")
    unknown = set(data) - _KNOWN
    if unknown:
        raise ConfigError(f"khub.toml: unknown keys {sorted(unknown)}")
    try:
        llm = LLMConfig(**data.get("llm", {}))
        digest = DigestConfig(**data.get("digest", {}))
    except TypeError as exc:
        raise ConfigError(f"khub.toml: {exc}") from exc
    school = data.get("school_dirs", [])
    if not isinstance(school, list) or not all(isinstance(item, str) for item in school):
        raise ConfigError("khub.toml: 'school_dirs' must be a list of strings")
    kwargs = {key: data[key] for key in ("memory_dir", "ideas_dir") if key in data}
    return Config(vault=Path(data["vault"]), school_dirs=tuple(school), llm=llm, digest=digest, **kwargs)


def default_config_path() -> Path:
    env = os.environ.get("KHUB_CONFIG")
    if env:
        return Path(env)
    local = Path.cwd() / "khub.toml"
    return local if local.exists() else REPO_ROOT / "khub.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return config_from_dict(data)
