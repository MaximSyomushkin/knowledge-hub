"""Run the `khub` CLI as a subprocess and parse its --json output. No knowledgehub imports."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass


@dataclass
class RunResult:
    code: int
    data: dict | None
    error: str

    @property
    def ok(self) -> bool:
        return self.code == 0 and bool(self.data) and bool(self.data.get("ok"))


class HubRunner:
    def __init__(self, command: list[str], config_path: str | None = None, timeout_s: float = 1800.0):
        self.command = list(command)
        self.config_path = config_path
        self.timeout_s = timeout_s

    def _run_sync(self, args: tuple[str, ...], timeout_s: float) -> RunResult:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        if self.config_path:
            env["KHUB_CONFIG"] = self.config_path
        # --json goes right after the subcommand, so callers can end with "--" and free text.
        argv = [*self.command, *args[:1], "--json", *args[1:]]
        try:
            proc = subprocess.run(
                argv, capture_output=True, env=env, timeout=timeout_s,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return RunResult(-1, None, f"khub timed out after {timeout_s:.0f}s")
        except OSError as exc:
            return RunResult(-1, None, f"cannot start khub: {exc}")
        stdout = proc.stdout.decode("utf-8", "replace").strip()
        data = None
        if stdout:
            try:
                data = json.loads(stdout.split("\n")[-1].strip())
            except json.JSONDecodeError:
                data = None
        if proc.returncode == 0:
            if data is None:
                return RunResult(0, None, "khub returned no JSON output")
            return RunResult(0, data, "")
        error = (data or {}).get("error") or proc.stderr.decode("utf-8", "replace").strip()[-500:]
        return RunResult(proc.returncode, data, error or f"khub exited with {proc.returncode}")

    async def run(self, *args: str, timeout_s: float | None = None) -> RunResult:
        return await asyncio.to_thread(self._run_sync, args, self.timeout_s if timeout_s is None else timeout_s)
