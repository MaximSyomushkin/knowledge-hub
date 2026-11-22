import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from knowledge_hub.handlers import HubPlugin
from knowledge_hub.runner import RunResult
from knowledge_hub.texts import DONE_USAGE, FILE_HINT, FORGET_USAGE, REMEMBER_USAGE, TRANSCRIBE_FAILED, heard


class Platform:
    """Hashable stand-in for Hermes' Platform enum (SimpleNamespace is unhashable)."""

    def __init__(self, value):
        self.value = value


DISCORD = Platform("discord")
TELEGRAM = Platform("telegram")
MEMORY_ID = "300"
TG_CHAT = "111111111"


class FakeRunner:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    async def run(self, *args, timeout_s=None):
        self.calls.append(args)
        return self.results.pop(0) if self.results else RunResult(0, {"ok": True}, "")


class FakeAdapter:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append((chat_id, content))


class ReactingAdapter(FakeAdapter):
    """Records the processing hooks (Telegram's 👀 → 👍/👎 reactions) and typing indicators."""

    def __init__(self):
        super().__init__()
        self.hooks, self.typing = [], []

    async def on_processing_start(self, event):
        self.hooks.append(("start", event.text))

    async def on_processing_complete(self, event, outcome):
        self.hooks.append(("complete", event.text, getattr(outcome, "value", outcome)))

    async def send_typing(self, chat_id, metadata=None):
        self.typing.append(chat_id)


class FakeTranscriber:
    def __init__(self, text="lab report due friday", error=None):
        self.text, self.error, self.calls = text, error, []

    async def __call__(self, path):
        self.calls.append(Path(path).name)
        if self.error:
            raise self.error
        return self.text


def make_gateway(authorized=("7",)):
    adapter = FakeAdapter()
    gateway = SimpleNamespace(
        adapters={DISCORD: adapter, TELEGRAM: adapter},
        _is_user_authorized_for_source=lambda source: source.user_id in authorized,
        _thread_metadata_for_source=lambda source: None,
    )
    return gateway, adapter


def make_plugin(tmp_path, runner, **kw):
    kw.setdefault("now", lambda: datetime(2026, 10, 1, 9, 30))
    kw.setdefault("chat_id", lambda: "42")
    kw.setdefault("discord_memory", MEMORY_ID)
    kw.setdefault("telegram_memory", {TG_CHAT})
    kw.setdefault("transcribe", FakeTranscriber())
    kw.setdefault("vault", tmp_path)
    return HubPlugin(runner, **kw)


def event(tmp_path, text="", chat_id=MEMORY_ID, platform=DISCORD, user="7", name=None, content=b"%PDF-1.4 fake",
          media_type="application/pdf", message_type="text", is_bot=False):
    media_urls, media_types = [], []
    if name is not None:
        media = tmp_path / "cache" / name
        media.parent.mkdir(exist_ok=True)
        media.write_bytes(content)
        media_urls, media_types = [str(media)], [media_type]
    source = SimpleNamespace(platform=platform, chat_id=chat_id, user_id=user, message_id="1", thread_id=None,
                             chat_type="group", is_bot=is_bot)
    return SimpleNamespace(text=text, media_urls=media_urls, media_types=media_types,
                           message_type=SimpleNamespace(value=message_type), source=source)


def voice(tmp_path, **kw):
    return event(tmp_path, name="voice.ogg", content=b"OggS", media_type="audio/ogg", message_type="voice", **kw)


def dispatch(plugin, gateway, *events):
    async def go():
        results = [await plugin.pre_gateway_dispatch(event=e, gateway=gateway) for e in events]
        await plugin.drain()
        return results

    return asyncio.run(go())


MEMORY_ADDED = RunResult(0, {"ok": True, "added": [{"id": "m1", "kind": "task", "text": "Lab report",
                                                    "due": "2026-10-09", "status": "open"}],
                             "skipped": [], "question": False}, "")
GOT_IT = "🧠 Got it:\n• task: Lab report — due Fri 09/10/2026 (m1)"
SKIP = {"action": "skip", "reason": "knowledge-hub memory"}


def test_discord_memory_text_is_remembered(tmp_path):
    runner = FakeRunner([MEMORY_ADDED])
    gateway, adapter = make_gateway()
    assert dispatch(make_plugin(tmp_path, runner), gateway, event(tmp_path, text="lab report due friday")) == [SKIP]
    assert runner.calls == [("memory-add", "--via", "discord", "--", "lab report due friday")]
    assert adapter.sent == [(MEMORY_ID, GOT_IT)]


def test_voice_notes_are_transcribed_then_remembered(tmp_path):
    runner = FakeRunner([MEMORY_ADDED, MEMORY_ADDED])
    gateway, adapter = make_gateway()
    dispatch(make_plugin(tmp_path, runner), gateway, voice(tmp_path),
             voice(tmp_path, chat_id=TG_CHAT, platform=TELEGRAM))
    assert runner.calls == [("memory-add", "--via", "discord", "--", "lab report due friday"),
                            ("memory-add", "--via", "telegram", "--", "lab report due friday")]
    assert adapter.sent[0] == (MEMORY_ID, heard("lab report due friday"))
    assert (TG_CHAT, GOT_IT) in adapter.sent


def test_files_get_a_hint_and_commands_pass_through(tmp_path):
    runner = FakeRunner()
    gateway, adapter = make_gateway()
    results = dispatch(make_plugin(tmp_path, runner), gateway,
                       event(tmp_path, name="doc_0123456789ab_a.pdf"),
                       event(tmp_path, text="/todo"),
                       event(tmp_path, name="a.pdf", chat_id=TG_CHAT, platform=TELEGRAM))
    assert results == [SKIP, None, SKIP]
    assert adapter.sent == [(MEMORY_ID, FILE_HINT), (TG_CHAT, FILE_HINT)] and runner.calls == []


def test_other_chats_bots_and_strangers_pass_through(tmp_path):
    runner = FakeRunner()
    gateway, adapter = make_gateway()
    results = dispatch(make_plugin(tmp_path, runner), gateway,
                       event(tmp_path, text="hi", chat_id="201"),  # another channel or a thread
                       event(tmp_path, text="hi", is_bot=True),
                       event(tmp_path, text="hi", user="999"),  # not authorized
                       event(tmp_path, text="hi", chat_id="-100999", platform=TELEGRAM),  # not a memory chat
                       event(tmp_path, text="hi", chat_id=TG_CHAT, platform=Platform("slack")))
    assert results == [None] * 5
    assert adapter.sent == [] and runner.calls == []


def test_without_configured_chats_everything_passes_through(tmp_path):
    plugin = make_plugin(tmp_path, FakeRunner(), discord_memory=None, telegram_memory=set())
    gateway, _ = make_gateway()
    assert dispatch(plugin, gateway, event(tmp_path, text="hi"),
                    event(tmp_path, text="hi", chat_id=TG_CHAT, platform=TELEGRAM)) == [None, None]


def test_auth_check_error_fails_closed(tmp_path):
    gateway, adapter = make_gateway()

    def boom(source):
        raise RuntimeError("x")

    gateway._is_user_authorized_for_source = boom
    assert dispatch(make_plugin(tmp_path, FakeRunner()), gateway, event(tmp_path, text="x")) == [None]
    assert adapter.sent == []


def test_memory_error_is_reported(tmp_path):
    plugin = make_plugin(tmp_path, FakeRunner([RunResult(2, None, "The model server is not reachable")]))
    gateway, adapter = make_gateway()
    dispatch(plugin, gateway, event(tmp_path, text="x"))
    assert adapter.sent == [(MEMORY_ID, "❌ The model server is not reachable")]


def test_telegram_reacts_and_types_while_working(tmp_path):
    runner = FakeRunner([MEMORY_ADDED, RunResult(2, {"ok": False, "error": "model server not running"}, "")])
    plugin = make_plugin(tmp_path, runner)
    gateway, _ = make_gateway()
    adapter = gateway.adapters[TELEGRAM] = ReactingAdapter()
    dispatch(plugin, gateway, event(tmp_path, text="lab report due friday", chat_id=TG_CHAT, platform=TELEGRAM),
             event(tmp_path, text="gym at 7", chat_id=TG_CHAT, platform=TELEGRAM))
    assert adapter.hooks == [("start", "lab report due friday"), ("start", "gym at 7"),
                             ("complete", "lab report due friday", "success"), ("complete", "gym at 7", "failure")]
    assert adapter.typing and set(adapter.typing) == {TG_CHAT}


def test_telegram_failed_transcription_reacts_failure(tmp_path):
    plugin = make_plugin(tmp_path, FakeRunner(), transcribe=FakeTranscriber(error=RuntimeError("stt down")))
    gateway, _ = make_gateway()
    adapter = gateway.adapters[TELEGRAM] = ReactingAdapter()
    dispatch(plugin, gateway, voice(tmp_path, chat_id=TG_CHAT, platform=TELEGRAM))
    assert adapter.hooks == [("start", ""), ("complete", "", "failure")]
    assert adapter.sent == [(TG_CHAT, TRANSCRIBE_FAILED)]


def test_discord_memory_channel_does_not_react(tmp_path):
    gateway, _ = make_gateway()
    adapter = gateway.adapters[DISCORD] = ReactingAdapter()
    dispatch(make_plugin(tmp_path, FakeRunner([MEMORY_ADDED])), gateway, event(tmp_path, text="lab report"))
    assert adapter.hooks == [] and adapter.typing == []


def test_memory_commands(tmp_path):
    listed = RunResult(0, {"ok": True, "items": [{"id": "m1", "kind": "task", "text": "Lab report",
                                                  "due": None, "status": "open"}]}, "")
    done = RunResult(0, {"ok": True, "item": {"id": "m1", "kind": "task", "text": "Lab report"}}, "")
    forgot = RunResult(1, {"ok": False, "error": "'zzz' matches nothing"}, "nothing matches 'zzz'")
    runner = FakeRunner([MEMORY_ADDED, listed, done, forgot])
    plugin = make_plugin(tmp_path, runner)
    assert asyncio.run(plugin.cmd_remember("  ")) == REMEMBER_USAGE
    assert asyncio.run(plugin.cmd_done("")) == DONE_USAGE
    assert asyncio.run(plugin.cmd_forget("")) == FORGET_USAGE
    assert asyncio.run(plugin.cmd_remember("lab report due friday")) == GOT_IT
    assert asyncio.run(plugin.cmd_todo("")) == "📝 To do:\nm1 Lab report"
    assert asyncio.run(plugin.cmd_done("lab")) == "✅ Done: Lab report (m1)"
    assert asyncio.run(plugin.cmd_forget("zzz")) == "❌ nothing matches 'zzz'"
    assert runner.calls == [("memory-add", "--via", "cli", "--", "lab report due friday"), ("memory-list",),
                            ("memory-done", "--", "lab"), ("memory-forget", "--", "zzz")]


def test_khub_memory_tool(tmp_path):
    listed = RunResult(0, {"ok": True, "items": [{"id": "m2", "kind": "event", "text": "Exam"}]}, "")
    runner = FakeRunner([listed, listed, RunResult(1, None, "bad kind")])
    plugin = make_plugin(tmp_path, runner)
    assert json.loads(asyncio.run(plugin.tool_khub_memory({}))) == {"items": [{"id": "m2", "kind": "event",
                                                                              "text": "Exam"}]}
    asyncio.run(plugin.tool_khub_memory({"kind": "event", "all": True}))
    assert json.loads(asyncio.run(plugin.tool_khub_memory({"kind": "x"}))) == {"error": "bad kind"}
    assert runner.calls == [("memory-list",), ("memory-list", "--kind", "event", "--all"),
                            ("memory-list", "--kind", "x")]


def test_memory_calls_are_serialised(tmp_path):
    class CountingRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.active = self.peak = 0

        async def run(self, *args, timeout_s=None):
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return MEMORY_ADDED

    runner = CountingRunner()
    plugin = make_plugin(tmp_path, runner)

    async def go():
        await asyncio.gather(plugin.cmd_remember("a"), plugin.cmd_remember("b"), plugin.cmd_done("m1"))

    asyncio.run(go())
    assert runner.peak == 1


def test_pre_llm_call_adds_vault_guidance(tmp_path):
    context = make_plugin(tmp_path, FakeRunner()).pre_llm_call(platform="discord", user_message="hi")
    assert "pick_folder" in context and "khub_memory" in context and "/remember" in context
    assert "say so" in context.lower() and "DD/MM/YYYY" in context


def test_register_wires_everything(monkeypatch):
    import knowledge_hub

    recorded = {"hooks": [], "commands": {}, "tools": []}
    ctx = SimpleNamespace(
        register_hook=lambda name, cb: recorded["hooks"].append(name),
        register_command=lambda name, handler, **kw: recorded["commands"].__setitem__(name, kw.get("args_hint", "")),
        register_tool=lambda **kw: recorded["tools"].append((kw["name"], kw["toolset"], kw["is_async"])),
    )
    knowledge_hub.register(ctx)
    assert recorded["hooks"] == ["pre_gateway_dispatch", "pre_llm_call"]
    assert list(recorded["commands"]) == ["remember", "todo", "done", "forget", "browse", "idea", "ideas"]
    # Hermes leaves commands whose args_hint starts with "<" out of its slash-command menus.
    assert not any(hint.strip().startswith("<") for hint in recorded["commands"].values())
    assert recorded["tools"] == [("khub_memory", "knowledge-hub", True), ("pick_folder", "knowledge-hub", True)]


def test_build_plugin_reads_its_chats(monkeypatch, caplog):
    import logging
    import knowledge_hub

    monkeypatch.setenv("KHUB_DISCORD_MEMORY", "300")
    monkeypatch.setenv("KHUB_TELEGRAM_MEMORY", " 111111111, -100123 ")
    with caplog.at_level(logging.INFO, logger="knowledge-hub"):
        plugin = knowledge_hub.build_plugin()
    assert plugin.discord_memory == "300" and plugin.telegram_memory == {"111111111", "-100123"}
    assert "300" not in caplog.text and "111111111" not in caplog.text and "-100123" not in caplog.text


def test_memory_calls_are_serialised_across_event_loops(tmp_path):
    import threading

    class CountingRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.active = self.peak = 0

        async def run(self, *args, timeout_s=None):
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.05)
            self.active -= 1
            return MEMORY_ADDED

    runner = CountingRunner()
    plugin = make_plugin(tmp_path, runner)
    errors = []

    def on_own_loop(call):
        try:
            asyncio.run(call)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=on_own_loop, args=(plugin.cmd_todo(""),)),
               threading.Thread(target=on_own_loop, args=(plugin.tool_khub_memory({}),))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert errors == [] and runner.peak == 1
