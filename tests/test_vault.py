import pytest

from knowledgehub.vault import PathNotAllowed


@pytest.mark.parametrize("rel", ["ReadWrite/Memory/memory.md", "ReadWrite/Ideas/Robot.md",
                                 "ReadWrite/Memory/.state/reminded.json"])
def test_writes_inside_the_hub_folders(vault, cfg, rel):
    vault.write_text(rel, "x\n")
    assert (cfg.vault / rel).read_text(encoding="utf-8") == "x\n"
    assert not list((cfg.vault / rel).parent.glob("*.tmp"))


@pytest.mark.parametrize("rel", ["ReadWrite/Year-1/notes.md", "ReadWrite/other.md", "ReadWrite/Memory/../x.md",
                                 "../outside.md"])
def test_writes_elsewhere_are_refused(vault, rel):
    with pytest.raises(PathNotAllowed):
        vault.write_text(rel, "x")


def test_rel_is_posix_relative_to_vault(vault, cfg):
    assert vault.rel(cfg.memory_root / "memory.md") == "ReadWrite/Memory/memory.md"
