import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from knowledge_hub.handlers import HubPlugin
from knowledge_hub.texts import BROWSE_DISCORD_ONLY, BROWSE_PICK_HINT


class Platform:
    def __init__(self, value):
        self.value = value


DISCORD = Platform("discord")
CHAT = "42"


class FakeRunner:
    async def run(self, *args, timeout_s=None):
        raise AssertionError("the picker never runs the khub CLI")


class FakeOpener:
    """Stands in for picker.open_picker: records the call; the test finishes the picker like a click would."""

    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    async def __call__(self, adapter, chat_id, user_id, state, on_finish, *, timeout, hint=""):
        self.calls.append(SimpleNamespace(adapter=adapter, chat_id=chat_id, user_id=user_id, state=state,
                                          on_finish=on_finish, timeout=timeout, hint=hint))
        return self.ok


def make_vault(tmp_path):
    lecture = tmp_path / "ReadWrite" / "Year-1" / "Intro-to-Physics" / "Lecture 1"
    lecture.mkdir(parents=True, exist_ok=True)
    (lecture / "Lecture1.pdf").write_bytes(b"%PDF")
    return tmp_path


def make_plugin(tmp_path, opener, platform="discord", now=None, **kw):
    session = {"HERMES_SESSION_PLATFORM": platform, "HERMES_SESSION_USER_ID": "7"}
    clock = now or (lambda: datetime(2026, 10, 5, 12, 0))
    return HubPlugin(FakeRunner(), vault=make_vault(tmp_path), chat_id=lambda: CHAT,
                      session=lambda name: session.get(name, ""), open_picker=opener, now=clock, **kw)


def gateway():
    adapter = SimpleNamespace(name="discord-adapter")
    return SimpleNamespace(adapters={DISCORD: adapter}, _is_user_authorized_for_source=lambda s: s.user_id == "7",
                           _thread_metadata_for_source=lambda s: None), adapter


def message(text, chat_id=CHAT, user="7"):
    source = SimpleNamespace(platform=DISCORD, chat_id=chat_id, user_id=user, message_id="1", thread_id=None,
                             chat_type="group", is_bot=False)
    return SimpleNamespace(text=text, media_urls=[], media_types=[], message_type=SimpleNamespace(value="text"),
                           source=source)


async def seen(plugin, gw):
    """Any inbound message lets the plugin learn the gateway and its event loop."""
    return await plugin.pre_gateway_dispatch(event=message("hello", chat_id="999"), gateway=gw)


def test_pick_folder_tool_returns_the_chosen_path_and_its_contents(tmp_path):
    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener)
        gw, adapter = gateway()
        await seen(plugin, gw)
        task = asyncio.ensure_future(plugin.tool_pick_folder(
            {"start": "/vault/readwrite/Year-1", "question": "Which lecture?"}))
        while not opener.calls:
            await asyncio.sleep(0)
        call = opener.calls[0]
        assert (call.adapter, call.chat_id, call.user_id) == (adapter, CHAT, "7")
        assert call.state.path == "/vault/readwrite/Year-1" and call.state.question == "Which lecture?"
        call.state.press("f:0")
        call.state.press("f:0")
        call.on_finish("ok", call.state.path)
        return json.loads(await task)

    result = asyncio.run(scenario())
    assert result == {"path": "/vault/readwrite/Year-1/Intro-to-Physics/Lecture 1",
                      "folders": [], "files": ["Lecture1.pdf"]}


def test_pick_folder_tool_reports_cancel(tmp_path):
    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener)
        await seen(plugin, gateway()[0])
        task = asyncio.ensure_future(plugin.tool_pick_folder({}))
        while not opener.calls:
            await asyncio.sleep(0)
        opener.calls[0].on_finish("cancel", None)
        return json.loads(await task)

    result = asyncio.run(scenario())
    assert result["cancelled"] is True


def test_pick_folder_tool_times_out(tmp_path):
    async def scenario():
        plugin = make_plugin(tmp_path, FakeOpener(), pick_timeout=0.05)
        await seen(plugin, gateway()[0])
        return json.loads(await plugin.tool_pick_folder({}))

    assert "did not pick" in asyncio.run(scenario())["error"]


def test_pick_folder_tool_only_on_discord(tmp_path):
    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener, platform="telegram")
        await seen(plugin, gateway()[0])
        return json.loads(await plugin.tool_pick_folder({})), opener

    result, opener = asyncio.run(scenario())
    assert "type the path" in result["error"] and not opener.calls


def test_pick_folder_tool_before_any_message_or_failed_send(tmp_path):
    async def scenario():
        fresh = json.loads(await make_plugin(tmp_path, FakeOpener()).tool_pick_folder({}))
        plugin = make_plugin(tmp_path, FakeOpener(ok=False))
        await seen(plugin, gateway()[0])
        return fresh, json.loads(await plugin.tool_pick_folder({}))

    fresh, failed = asyncio.run(scenario())
    assert "type the path" in fresh["error"] and "type the path" in failed["error"]


def test_browse_then_next_message_carries_the_folder(tmp_path):
    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener)
        gw, _ = gateway()
        await seen(plugin, gw)
        reply = await plugin.cmd_browse("/vault/readwrite/Year-1")
        call = opener.calls[0]
        assert call.hint == BROWSE_PICK_HINT and call.timeout > 300
        await call.on_finish("ok", "/vault/readwrite/Year-1")
        other_chat = await plugin.pre_gateway_dispatch(event=message("hi", chat_id="555"), gateway=gw)
        command = await plugin.pre_gateway_dispatch(event=message("/todo"), gateway=gw)
        first = await plugin.pre_gateway_dispatch(event=message("make flashcards"), gateway=gw)
        second = await plugin.pre_gateway_dispatch(event=message("thanks"), gateway=gw)
        return reply, other_chat, command, first, second

    reply, other_chat, command, first, second = asyncio.run(scenario())
    assert reply is None
    assert other_chat is None and command is None and second is None
    assert first["action"] == "rewrite"
    assert first["text"].startswith("make flashcards")
    assert "/vault/readwrite/Year-1" in first["text"]


def test_picked_folder_expires(tmp_path):
    times = [datetime(2026, 10, 5, 12, 0)]

    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener, now=lambda: times[0])
        gw, _ = gateway()
        await seen(plugin, gw)
        await plugin.cmd_browse("")
        await opener.calls[0].on_finish("ok", "/vault/readwrite")
        times[0] += timedelta(minutes=31)
        return await plugin.pre_gateway_dispatch(event=message("make flashcards"), gateway=gw)

    assert asyncio.run(scenario()) is None


def test_browse_cancel_sets_nothing_and_unauthorized_text_is_not_rewritten(tmp_path):
    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener)
        gw, _ = gateway()
        await seen(plugin, gw)
        await plugin.cmd_browse("")
        await opener.calls[0].on_finish("cancel", None)
        after_cancel = await plugin.pre_gateway_dispatch(event=message("do it"), gateway=gw)
        await plugin.cmd_browse("")
        await opener.calls[1].on_finish("ok", "/vault/readwrite")
        stranger = await plugin.pre_gateway_dispatch(event=message("do it", user="8"), gateway=gw)
        return after_cancel, stranger

    assert asyncio.run(scenario()) == (None, None)


def test_browse_off_discord(tmp_path):
    opener = FakeOpener()
    plugin = make_plugin(tmp_path, opener, platform="telegram")
    assert asyncio.run(plugin.cmd_browse("")) == BROWSE_DISCORD_ONLY
    assert not opener.calls


def pdf_message(tmp_path, name, text=""):
    event = message(text)
    pdf = tmp_path / "cache" / name
    pdf.parent.mkdir(exist_ok=True)
    pdf.write_bytes(b"%PDF")
    event.media_urls, event.media_types = [str(pdf)], ["application/pdf"]
    return event


def browse_then(tmp_path, folder, event):
    async def scenario():
        opener = FakeOpener()
        plugin = make_plugin(tmp_path, opener)
        gw, _ = gateway()
        await seen(plugin, gw)
        await plugin.cmd_browse("")
        await opener.calls[0].on_finish("ok", folder)
        return await plugin.pre_gateway_dispatch(event=event, gateway=gw)

    return asyncio.run(scenario())


COURSE = "/vault/readwrite/Year-1/Intro-to-Physics"






def test_files_after_browse_just_carry_the_folder(tmp_path):
    typed = browse_then(tmp_path, COURSE, pdf_message(tmp_path, "doc_0123456789ab_x.pdf", text="summarise this"))
    assert typed["text"] == f"summarise this\n\n[Folder the user picked with /browse: {COURSE}]"
    bare = browse_then(tmp_path, COURSE, pdf_message(tmp_path, "doc_0123456789ab_slides.pdf"))
    assert bare["text"] == f"[Folder the user picked with /browse: {COURSE}]"
