"""Hermes-facing behavior: #memory and the Telegram memory chats, slash commands, the folder picker and the
agent's tools.

No Hermes imports at module level; Hermes objects arrive as hook/command arguments.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable

from .folders import FolderBrowser, PickerState
from .picker import open_picker as default_open_picker
from .runner import RunResult, HubRunner
from .texts import (BROWSE_DISCORD_ONLY, BROWSE_FAILED, BROWSE_PICK_HINT, DONE_USAGE, FILE_HINT, FORGET_USAGE,
                    IDEA_USAGE, IDEAS_USAGE, REMEMBER_USAGE, TRANSCRIBE_FAILED, format_done, format_forgot,
                    format_ideas, format_memory_added, format_todo, heard, split_message)

log = logging.getLogger("knowledge-hub")

# Default sandbox mount path for the vault's ReadWrite folder.
SANDBOX_PATHS = {"/vault/readwrite": "ReadWrite"}
DEFAULT_VAULT = Path.home() / "vault"  # override via KHUB_VAULT
PICK_TIMEOUT_S = 270  # Hermes cancels an async tool after 300 s
BROWSE_TIMEOUT_S = 15 * 60
PICKED_TTL = timedelta(minutes=30)  # how long a /browse pick waits for the user's next message
PICK_UNAVAILABLE = "The folder picker is not available here. Ask the user to type the path."
TYPING_EVERY_S = 4.0  # Telegram's "typing…" fades after about 5 s
GUIDANCE = (
    "[school hub] The user's school work lives in their vault under /vault/readwrite/ (e.g. "
    "<year>/<Course>/Lecture N/). Never guess a folder path: when a task needs a folder the user hasn't named "
    "exactly, call pick_folder and they choose it with buttons. Do not write helper scripts or other files into "
    "the vault beyond what the user asked for. "
    "'Graph view', 'tree view' or 'connect these notes' means Obsidian's graph view: connect notes with "
    "[[wikilinks]] inside them, never with a mermaid or other diagram. Lecture folders already get a generated "
    "'Lecture N.md' linking the neighbouring lectures and that lecture's notes and PDF, and each module a course "
    "note named after the subject linking all its lectures (refreshed every minute); never write those yourself. "
    "If you cannot read a file the user mentions, say so plainly and stop; never fill in course content from web "
    "searches or general knowledge unless the user asks for that. "
    "For the user's own tasks, deadlines, dates and things they asked you to remember, call khub_memory "
    "instead of guessing; to add or tick items, tell them to use /remember, /done or the #memory channel. "
    "Ideas the user told the bot are notes in /vault/readwrite/Ideas/ (one per idea; /idea saves a new one); "
    "never rewrite their 'What I said' or 'My Notes' sections. "
    "Tools give dates as YYYY-MM-DD; always write dates for the user day first, as DD/MM/YYYY (e.g. "
    "Fri 09/10/2026), and read dates the user types in numbers as day/month."
)


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return get_session_env(name) or ""
    except Exception:
        return ""


def default_chat_id() -> str:
    return _session_env("HERMES_SESSION_CHAT_ID")


def _platform_name(source) -> str:
    platform = getattr(source, "platform", None)
    return str(getattr(platform, "value", platform) or "")


def _message_kind(event) -> str:
    kind = getattr(event, "message_type", None)
    return str(getattr(kind, "value", kind) or "")


def _is_audio(event) -> bool:
    """A voice note or audio clip: Hermes marks the message type; media types are the fallback."""
    if _message_kind(event) in ("voice", "audio"):
        return True
    return any(str(t).startswith("audio") for t in getattr(event, "media_types", None) or [])


async def default_transcribe(path: Path) -> str:
    """Hermes' configured speech-to-text. Raises when it fails."""
    from tools.transcription_tools import transcribe_audio

    result = await asyncio.to_thread(transcribe_audio, str(path), source="gateway")
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "transcription failed")
    return result.get("transcript") or ""


def _processing_outcome(ok: bool):
    try:
        from gateway.platforms.event import ProcessingOutcome

        return ProcessingOutcome.SUCCESS if ok else ProcessingOutcome.FAILURE
    except ImportError:
        return "success" if ok else "failure"


class HubPlugin:
    def __init__(self, runner: HubRunner, *, discord_memory: str | None = None,
                 telegram_memory: set[str] | frozenset[str] = frozenset(),
                 transcribe: Callable[[Path], Awaitable[str]] = default_transcribe,
                 now: Callable[[], datetime] = datetime.now, chat_id: Callable[[], str] = default_chat_id,
                 vault: Path | None = None, session: Callable[[str], str] = _session_env,
                 open_picker=default_open_picker, pick_timeout: float = PICK_TIMEOUT_S,
                 typing_every: float = TYPING_EVERY_S):
        self.runner = runner
        self.discord_memory = str(discord_memory) if discord_memory else None
        self.telegram_memory = {str(chat) for chat in telegram_memory}
        self.transcribe = transcribe
        self.now = now
        self.chat_id = chat_id
        # A thread lock, not asyncio.Lock: commands run on the gateway loop, agent tools on a worker loop.
        self._memory_lock = threading.Lock()
        self._tasks: set[asyncio.Task] = set()
        self.browser = FolderBrowser(vault or DEFAULT_VAULT, SANDBOX_PATHS)
        self.session = session
        self.open_picker = open_picker
        self.pick_timeout = pick_timeout
        self.typing_every = typing_every
        # Learned from the first inbound message: agent tools run on a worker loop, Discord views on this one.
        self._gateway = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._picked: dict[str, tuple[str, datetime]] = {}  # chat id -> (/browse folder, when picked)

    # --- helpers ---------------------------------------------------------------

    def _authorized(self, gateway, source) -> bool:
        if not str(getattr(source, "user_id", "") or ""):
            return False
        check = getattr(gateway, "_is_user_authorized_for_source", None)
        if check is None:
            return False
        try:
            return bool(check(source))
        except Exception:
            log.exception("knowledge-hub: authorization check failed; ignoring message")
            return False

    @staticmethod
    def _adapter(gateway, source):
        return (getattr(gateway, "adapters", None) or {}).get(source.platform)

    @staticmethod
    def _metadata(gateway, source):
        builder = getattr(gateway, "_thread_metadata_for_source", None)
        if builder is None:
            return None
        try:
            return builder(source)
        except Exception:
            return None

    async def _reply(self, gateway, source, text: str) -> None:
        adapter = self._adapter(gateway, source)
        if adapter is None:
            log.warning("knowledge-hub: no adapter for %s; reply dropped", source.platform)
            return
        metadata = self._metadata(gateway, source)
        for part in split_message(text):
            try:
                await adapter.send(source.chat_id, part, metadata=metadata)
            except Exception:
                log.exception("knowledge-hub: sending reply failed")

    def _spawn(self, coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for the background replies (tests and shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # Telegram acknowledgement: 👀 on the message and "typing…" at once, 👍/👎 when done. The reactions come from
    # the adapter's own processing hooks, so they follow Hermes' telegram `reactions` setting.

    async def _call_adapter(self, adapter, name: str, *args, **kw) -> None:
        method = getattr(adapter, name, None)
        if method is None:
            return
        try:
            await method(*args, **kw)
        except Exception:
            log.debug("knowledge-hub: %s failed", name, exc_info=True)

    async def _seen(self, gateway, source, event) -> None:
        adapter = self._adapter(gateway, source)
        await self._call_adapter(adapter, "on_processing_start", event)
        await self._call_adapter(adapter, "send_typing", source.chat_id, metadata=self._metadata(gateway, source))

    async def _keep_typing(self, gateway, source) -> None:
        while True:
            await asyncio.sleep(self.typing_every)
            await self._call_adapter(self._adapter(gateway, source), "send_typing", source.chat_id,
                                     metadata=self._metadata(gateway, source))

    async def _working(self, gateway, source, event, work: Awaitable[bool]) -> None:
        typing = asyncio.get_running_loop().create_task(self._keep_typing(gateway, source))
        ok = False
        try:
            ok = await work
        finally:
            typing.cancel()
            await self._call_adapter(self._adapter(gateway, source), "on_processing_complete", event,
                                     _processing_outcome(ok))

    # --- hook ----------------------------------------------------------------

    async def pre_gateway_dispatch(self, event=None, gateway=None, **_):
        if gateway is not None:
            self._gateway = gateway
            self._loop = asyncio.get_running_loop()
        try:
            source = getattr(event, "source", None)
            if source is None:
                return None
            return await self._dispatch(event, gateway, source)
        except Exception:
            log.exception("knowledge-hub: intake failed; passing message to Hermes")
            return None

    def _is_memory_chat(self, source) -> bool:
        """Match Discord #memory by exact channel id (threads pass through) or configured Telegram memory chats."""
        chat = str(getattr(source, "chat_id", "") or "")
        platform = _platform_name(source)
        if platform == "telegram":
            return chat in self.telegram_memory
        return platform == "discord" and bool(self.discord_memory) and chat == self.discord_memory

    async def _dispatch(self, event, gateway, source):
        if getattr(source, "is_bot", False):
            return None
        if not self._is_memory_chat(source):
            return self._with_picked_folder(gateway, source, event)
        if not self._authorized(gateway, source):
            return None
        media = list(getattr(event, "media_urls", None) or [])
        text = (event.text or "").strip()
        if not media and (not text or text.startswith("/")):
            return None  # empty, or a slash command for Hermes to run
        skip = {"action": "skip", "reason": "knowledge-hub memory"}
        if media and not _is_audio(event):
            await self._reply(gateway, source, FILE_HINT)
            return skip
        work = self._transcribe_then(gateway, source, Path(media[0])) if media else self._remember(gateway, source, text)
        if _platform_name(source) == "telegram":
            await self._seen(gateway, source, event)
            work = self._working(gateway, source, event, work)
        self._spawn(work)
        return skip

    def _with_picked_folder(self, gateway, source, event):
        """After /browse: the user's next message in that chat carries the folder they picked."""
        chat = str(getattr(source, "chat_id", "") or "")
        text = (event.text or "").strip()
        media = list(getattr(event, "media_urls", None) or [])
        if chat not in self._picked or text.startswith("/") or not self._authorized(gateway, source):
            return None
        if not text and not media:
            return None
        path, when = self._picked.pop(chat)
        if self.now() - when > PICKED_TTL:
            return None
        return {"action": "rewrite", "text": f"{event.text or ''}\n\n[Folder the user picked with /browse: {path}]".strip()}

    async def _transcribe_then(self, gateway, source, audio: Path) -> bool:
        """Voice note -> Hermes' speech-to-text -> echo what was heard -> remember it like typed text."""
        try:
            text = (await self.transcribe(audio) or "").strip()
        except Exception:
            log.exception("knowledge-hub: transcribing %s failed", audio.name)
            text = ""
        if not text:
            await self._reply(gateway, source, TRANSCRIBE_FAILED)
            return False
        await self._reply(gateway, source, heard(text))
        return await self._remember(gateway, source, text)

    async def _remember(self, gateway, source, text: str) -> bool:
        reply = await self._memory_add(text, _platform_name(source) or "cli")
        await self._reply(gateway, source, reply)
        return not reply.startswith("❌")

    # --- folder picker ---------------------------------------------------------

    def _discord_adapter(self):
        adapters = getattr(self._gateway, "adapters", None) or {}
        return next((a for p, a in adapters.items() if str(getattr(p, "value", p)) == "discord"), None)

    async def _open_picker(self, chat_id: str, state: PickerState, on_finish, timeout: float, hint: str = "") -> bool:
        """Post a picker in the current session's Discord chat; only the session's user can click it."""
        adapter = self._discord_adapter()
        if adapter is None or not chat_id:
            return False
        try:
            return await self.open_picker(adapter, chat_id, self.session("HERMES_SESSION_USER_ID"), state, on_finish,
                                          timeout=timeout, hint=hint)
        except Exception:
            log.exception("knowledge-hub: opening the folder picker failed")
            return False

    # --- memory ----------------------------------------------------------------

    async def _memory_run(self, *args: str) -> RunResult:
        """memory.md is read-modify-written by the CLI, so memory calls never overlap."""
        await asyncio.to_thread(self._memory_lock.acquire)
        try:
            return await self.runner.run(*args)
        finally:
            self._memory_lock.release()

    async def _memory_add(self, text: str, via: str, *flags: str) -> str:
        result = await self._memory_run("memory-add", *flags, "--via", via if via in ("telegram", "discord") else "cli",
                                        "--", text)
        if not result.ok:
            return f"❌ {result.error or 'memory failed'}"
        return format_memory_added(result.data or {})

    def _command_via(self) -> str:
        return self.session("HERMES_SESSION_PLATFORM") or "cli"

    async def _memory_change(self, command: str, raw_args: str, usage: str, fmt: Callable[[dict], str]) -> str:
        ref = (raw_args or "").strip()
        if not ref:
            return usage
        result = await self._memory_run(command, "--", ref)
        if not result.ok:
            return f"❌ {result.error or command + ' failed'}"
        return fmt((result.data or {}).get("item") or {})

    # --- commands --------------------------------------------------------------

    async def cmd_remember(self, raw_args: str) -> str:
        text = (raw_args or "").strip()
        return await self._memory_add(text, self._command_via()) if text else REMEMBER_USAGE

    async def cmd_idea(self, raw_args: str) -> str:
        """`/idea …`: the whole message is an idea, no guessing."""
        text = (raw_args or "").strip()
        return await self._memory_add(text, self._command_via(), "--kind", "idea") if text else IDEA_USAGE

    async def cmd_ideas(self, raw_args: str) -> str:
        switch = (raw_args or "").strip().lower()
        if switch not in ("", "on", "off"):
            return IDEAS_USAGE
        result = await self._memory_run("ideas", *([switch] if switch else []))
        if not result.ok:
            return f"❌ {result.error or 'ideas failed'}"
        return format_ideas(result.data or {})

    async def cmd_todo(self, raw_args: str) -> str:
        result = await self._memory_run("memory-list")
        if not result.ok:
            return f"❌ {result.error or 'memory failed'}"
        return format_todo(result.data or {})

    async def cmd_done(self, raw_args: str) -> str:
        return await self._memory_change("memory-done", raw_args, DONE_USAGE, format_done)

    async def cmd_forget(self, raw_args: str) -> str:
        return await self._memory_change("memory-forget", raw_args, FORGET_USAGE, format_forgot)

    async def cmd_browse(self, raw_args: str) -> str | None:
        """Folder picker; the picked folder rides along with the user's next message (see _with_picked_folder)."""
        if self.session("HERMES_SESSION_PLATFORM") != "discord":
            return BROWSE_DISCORD_ONLY
        chat = str(self.chat_id() or "")

        async def picked(outcome: str, path: str | None) -> None:
            if outcome == "ok" and path:
                self._picked[chat] = (path, self.now())

        state = PickerState(self.browser, (raw_args or "").strip())
        opened = await self._open_picker(chat, state, picked, BROWSE_TIMEOUT_S, BROWSE_PICK_HINT)
        return None if opened else BROWSE_FAILED

    # --- every agent turn -----------------------------------------------------

    def pre_llm_call(self, **_) -> str:
        """Context appended to each agent turn: vault layout, memory/folder tools, and error reporting."""
        return GUIDANCE

    # --- agent tools -----------------------------------------------------------

    async def tool_khub_memory(self, args: dict, **_) -> str:
        args = args or {}
        argv = ["memory-list"]
        if args.get("kind"):
            argv += ["--kind", str(args["kind"])]
        if args.get("all"):
            argv.append("--all")
        result = await self._memory_run(*argv)
        if not result.ok:
            return json.dumps({"error": result.error or "memory failed"}, ensure_ascii=False)
        return json.dumps({"items": (result.data or {}).get("items", [])}, ensure_ascii=False)

    async def tool_pick_folder(self, args: dict, **_) -> str:
        """Let the user click to a folder. Runs on Hermes' tool worker loop; the picker lives on the gateway loop,
        so the open is handed over there and the click comes back through a thread-safe future."""
        args = args or {}
        if self.session("HERMES_SESSION_PLATFORM") != "discord" or self._loop is None:
            return json.dumps({"error": PICK_UNAVAILABLE})
        state = PickerState(self.browser, str(args.get("start") or ""), str(args.get("question") or ""))
        chosen: concurrent.futures.Future = concurrent.futures.Future()

        def finished(outcome: str, path: str | None) -> None:
            if not chosen.done():
                chosen.set_result((outcome, path))

        opening = asyncio.run_coroutine_threadsafe(
            self._open_picker(str(self.chat_id() or ""), state, finished, self.pick_timeout), self._loop)
        if not await asyncio.wrap_future(opening):
            return json.dumps({"error": PICK_UNAVAILABLE})
        try:
            outcome, path = await asyncio.wait_for(asyncio.wrap_future(chosen), self.pick_timeout)
        except TimeoutError:
            outcome, path = "timeout", None
        if outcome == "ok" and path:
            listing = self.browser.listing(path)
            return json.dumps({"path": path, "folders": listing.folders, "files": listing.files}, ensure_ascii=False)
        if outcome == "cancel":
            return json.dumps({"cancelled": True,
                               "message": "The user cancelled the folder picker. Ask what they want instead."})
        return json.dumps({"error": "The user did not pick a folder in time. Ask them to type the path or use /browse."})
