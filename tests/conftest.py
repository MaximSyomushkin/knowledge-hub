from pathlib import Path

import pytest

from knowledgehub.config import Config
from knowledgehub.vault import Vault


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    for folder in ("ReadWrite/Memory", "ReadWrite/Ideas", "ReadWrite/Year-1"):
        (root / folder).mkdir(parents=True)
    return root


@pytest.fixture
def cfg(vault_dir: Path) -> Config:
    return Config(vault=vault_dir, school_dirs=("ReadWrite/Year-1",))


@pytest.fixture
def vault(cfg) -> Vault:
    return Vault(cfg)
