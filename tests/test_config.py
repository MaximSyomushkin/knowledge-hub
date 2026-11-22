from pathlib import Path

import pytest

from knowledgehub.config import REPO_ROOT, ConfigError, config_from_dict, load_config


def test_defaults_from_minimal_dict(tmp_path: Path):
    cfg = config_from_dict({"vault": str(tmp_path)})
    assert cfg.vault == tmp_path
    assert cfg.school_dirs == ()
    assert cfg.memory_root == tmp_path / "ReadWrite" / "Memory"
    assert cfg.ideas_root == tmp_path / "ReadWrite" / "Ideas"
    assert cfg.state_dir == tmp_path / "ReadWrite" / "Memory" / ".state"
    assert cfg.llm.url == "http://127.0.0.1:8080" and cfg.llm.model == "Qwen3.5-4B-Q8_0"
    assert cfg.digest.mention == ""


def test_overrides(tmp_path: Path):
    cfg = config_from_dict({"vault": str(tmp_path), "school_dirs": ["ReadWrite/Year-1"], "memory_dir": "M",
                            "llm": {"model": "claude-opus-5-5", "claude_command": "claude.exe"},
                            "digest": {"mention": "42"}})
    assert cfg.school_dirs == ("ReadWrite/Year-1",)
    assert cfg.memory_root == tmp_path / "M"
    assert (cfg.llm.model, cfg.llm.claude_command, cfg.digest.mention) == ("claude-opus-5-5", "claude.exe", "42")


@pytest.mark.parametrize("data, message", [
    ({}, "'vault' is required"),
    ({"vault": "v", "old_dir": "W"}, r"unknown keys \['old_dir'\]"),
    ({"vault": "v", "llm": {"embed_url": "x"}}, "embed_url"),
    ({"vault": "v", "school_dirs": "ReadWrite"}, "list of strings"),
])
def test_bad_config_says_what_is_wrong(data, message):
    with pytest.raises(ConfigError, match=message):
        config_from_dict(data)


def test_load_config_from_file(tmp_path: Path):
    path = tmp_path / "khub.toml"
    path.write_text("vault = 'C:/v'\n[llm]\nmodel = 'm'\n", encoding="utf-8")
    assert load_config(path).llm.model == "m"
    with pytest.raises(ConfigError, match="config not found"):
        load_config(tmp_path / "missing.toml")
    path.write_text("vault = [", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_the_example_config_loads():
    cfg = load_config(REPO_ROOT / "khub.toml.example")
    assert cfg.school_dirs and cfg.llm.model
