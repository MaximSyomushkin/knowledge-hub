"""LLM client: schema-constrained JSON via an OpenAI-compatible HTTP endpoint (or optional local CLI)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import LLMConfig

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Strip ambient auth/session env vars before invoking the local CLI subprocess.
_CLAUDE_ENV_DROP = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDECODE",
                    "CLAUDE_CODE_ENTRYPOINT", "ELECTRON_RUN_AS_NODE")


class LLMError(Exception):
    """The model call failed or returned unusable output."""


class ModelServerUnavailable(LLMError):
    """The model server could not be reached at all."""


class LLM(Protocol):
    def generate_json(self, prompt: str, schema: type[T], *, system: str = "", model: str | None = None) -> T: ...
    def list_models(self) -> list[str]: ...


class LlamaServerClient:
    RETRIES = 2

    def __init__(self, cfg: LLMConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self._http = httpx.Client(base_url=cfg.url, timeout=cfg.timeout_s, transport=transport)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        http = self._http
        try:
            response = http.request(method, path, json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ModelServerUnavailable(f"The model server is not reachable at {http.base_url} — is it running?") \
                from exc
        except httpx.TimeoutException as exc:
            raise LLMError(f"The model server timed out after {self.cfg.timeout_s:.0f}s") from exc
        except httpx.TransportError as exc:
            raise LLMError(f"Model server connection error: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"Model server {path} returned {response.status_code}: {response.text[:300]}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"Model server {path} returned invalid JSON: {response.text[:100]}") from exc

    def _chat_raw(self, model: str, system: str, prompt: str, fmt: dict) -> str:
        if model.startswith("claude-"):
            return self._claude_raw(model, system, prompt, fmt)
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "reply", "schema": fmt}},
        }
        data = self._request("POST", "/v1/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected model server response: missing choices[0].message.content") from exc

    def _claude_raw(self, model: str, system: str, prompt: str, fmt: dict) -> str:
        """Run a single non-interactive CLI turn via stdin stream-json (avoids command-line length limits)."""
        exe = self.cfg.claude_command or shutil.which("claude")
        if not exe:
            raise ModelServerUnavailable("Claude Code CLI not found — install it or set llm.claude_command")
        message = json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}})
        with tempfile.TemporaryDirectory(prefix="knowledgehub-claude-") as work:
            cmd = [exe, "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
                   "--no-session-persistence", "--setting-sources", "", "--input-format", "stream-json",
                   "--output-format", "stream-json", "--verbose"]
            if self.cfg.claude_effort:
                cmd += ["--effort", self.cfg.claude_effort]
            if system:
                system_file = os.path.join(work, "system.txt")
                with open(system_file, "w", encoding="utf-8") as fh:
                    fh.write(system)
                cmd += ["--system-prompt-file", system_file]
            cmd += ["--json-schema", json.dumps(fmt)]
            env = {k: v for k, v in os.environ.items() if k not in _CLAUDE_ENV_DROP}
            env.setdefault("USER", env.get("USERNAME", ""))
            try:
                proc = subprocess.run(cmd, input=message, capture_output=True, text=True, encoding="utf-8",
                                      cwd=work, env=env, timeout=self.cfg.timeout_s,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"Claude timed out after {self.cfg.timeout_s:.0f}s") from exc
            except OSError as exc:
                raise ModelServerUnavailable(f"could not start Claude Code CLI ({exe}): {exc}") from exc
        result = None
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                result = event
        if result is None:
            raise LLMError(f"Claude CLI exited {proc.returncode} without a result: {(proc.stderr or proc.stdout)[-300:]}")
        if result.get("is_error") or result.get("subtype") != "success":
            raise LLMError(f"Claude returned {result.get('subtype')}: {str(result.get('result'))[:300]}")
        if result.get("structured_output") is not None:
            return json.dumps(result["structured_output"])
        return result.get("result") or ""

    def generate_json(self, prompt: str, schema: type[T], *, system: str = "", model: str | None = None) -> T:
        name = model or self.cfg.model
        attempts = 1 + self.RETRIES
        last: Exception | None = None
        for _ in range(attempts):
            raw = self._chat_raw(name, system, prompt, schema.model_json_schema())
            try:
                return schema.model_validate_json(raw)
            except ValidationError as exc:
                last = exc
                log.warning("invalid %s JSON from %s: %s", schema.__name__, name, str(exc)[:200])
        raise LLMError(f"no valid {schema.__name__} after {attempts} attempts: {last}")

    def list_models(self) -> list[str]:
        """Model names (llama-server aliases) on the server."""
        try:
            return [m["id"] for m in self._request("GET", "/v1/models")["data"]]
        except (KeyError, TypeError) as exc:
            raise LLMError("unexpected model server response: malformed models list") from exc
