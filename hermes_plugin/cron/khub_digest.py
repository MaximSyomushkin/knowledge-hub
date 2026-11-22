"""Hermes no-agent cron wrapper for the morning digest (`khub digest`).

Prints stdout verbatim (empty output = silent tick; non-zero exit = failure alert).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def khub_command() -> list[str]:
    return [os.environ.get("KHUB_BIN") or str(Path.home() / "Hermes" / "knowledge-hub" / ".venv" / "Scripts" / "khub.exe")]


def main(args: tuple[str, ...] = ("digest",)) -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([*khub_command(), *args], capture_output=True, env=env, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"knowledge-hub digest: cannot run khub: {exc}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(proc.stdout)
    sys.stdout.flush()
    sys.stderr.buffer.write(proc.stderr)
    sys.stderr.flush()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
