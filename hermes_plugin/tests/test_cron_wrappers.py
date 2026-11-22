import importlib
import sys
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1] / "cron"


@pytest.fixture
def wrappers(monkeypatch, tmp_path):
    """Both wrapper modules, with `khub` replaced by a fake that echoes its args and exits with FAKE_EXIT."""
    fake = tmp_path / "fake_khub.py"
    fake.write_text("import os, sys\nprint('ran:', ' '.join(sys.argv[1:]))\nsys.exit(int(os.environ.get('FAKE_EXIT', '0')))\n",
                    encoding="utf-8")
    monkeypatch.syspath_prepend(str(CRON_DIR))
    for name in ("khub_digest", "khub_weekly"):
        sys.modules.pop(name, None)
    daily = importlib.import_module("khub_digest")
    weekly = importlib.import_module("khub_weekly")
    monkeypatch.setattr(daily, "khub_command", lambda: [sys.executable, str(fake)])
    return daily, weekly


def test_daily_passes_output_through(wrappers, capfd):
    daily, _ = wrappers
    assert daily.main() == 0
    assert capfd.readouterr().out.strip() == "ran: digest"


def test_weekly_adds_flag(wrappers, capfd):
    _, weekly = wrappers
    assert weekly.main() == 0
    assert capfd.readouterr().out.strip() == "ran: digest --weekly"


def test_exit_code_is_propagated(wrappers, monkeypatch):
    daily, _ = wrappers
    monkeypatch.setenv("FAKE_EXIT", "3")
    assert daily.main() == 3


def test_missing_binary_is_an_error(wrappers, monkeypatch, capfd):
    daily, _ = wrappers
    monkeypatch.setattr(daily, "khub_command", lambda: [str(Path("nope") / "khub.exe")])
    assert daily.main() == 1
    assert "cannot run khub" in capfd.readouterr().err


def test_khub_command_prefers_env(wrappers, monkeypatch):
    sys.modules.pop("khub_digest", None)
    fresh = importlib.import_module("khub_digest")
    monkeypatch.setenv("KHUB_BIN", "C:/x/khub.exe")
    assert fresh.khub_command() == ["C:/x/khub.exe"]


def test_weekend_adds_flag(wrappers, capfd):
    sys.modules.pop("khub_weekend", None)
    weekend = importlib.import_module("khub_weekend")
    assert weekend.main() == 0
    assert capfd.readouterr().out.strip() == "ran: digest --weekend"


def test_remind_runs_khub_remind(wrappers, capfd):
    sys.modules.pop("khub_remind", None)
    remind = importlib.import_module("khub_remind")
    assert remind.main() == 0
    assert capfd.readouterr().out.strip() == "ran: remind"
