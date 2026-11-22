"""Discord side of the folder picker: one message whose buttons mirror a PickerState; each click edits that
message in place, so navigating costs no model call.

``discord`` is imported inside the functions: it exists in Hermes' environment, not in this repo's venv.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

from .folders import PickerState

log = logging.getLogger("knowledge-hub")

_STYLES = {"folder": "primary", "nav": "secondary", "ok": "success", "cancel": "danger"}
NOT_YOURS = "Only the person who asked can pick here."

# on_finish(outcome, path): outcome is "ok", "cancel" or "timeout"; path is set only for "ok".
OnFinish = Callable[[str, "str | None"], Any]


def _make_view(state: PickerState, user_id: str, on_finish: OnFinish, timeout: float, hint: str):
    import discord

    class FolderPickerView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=timeout)
            self._message = None  # set by the adapter's _send_prompt; used to edit on timeout
            self.finished = False
            self._render()

        def _render(self) -> None:
            self.clear_items()
            for spec in state.buttons():
                button = discord.ui.Button(
                    label=spec.label, style=getattr(discord.ButtonStyle, _STYLES[spec.kind]), row=spec.row,
                    disabled=spec.disabled, emoji="📁" if spec.kind == "folder" else None)
                button.callback = self._callback(spec.key)
                self.add_item(button)

        def _callback(self, key: str):
            async def callback(interaction: discord.Interaction):
                if user_id and str(interaction.user.id) != str(user_id):
                    await interaction.response.send_message(NOT_YOURS, ephemeral=True)
                    return
                if self.finished:
                    await interaction.response.defer()
                    return
                outcome = state.press(key)
                if outcome is None:
                    self._render()
                    await interaction.response.edit_message(content=state.content(), view=self)
                else:
                    await self._finish(outcome, interaction)
            return callback

        async def _finish(self, outcome: str, interaction=None) -> None:
            self.finished = True
            self.stop()
            text = state.final_text(outcome, hint)
            try:
                if interaction is not None:
                    await interaction.response.edit_message(content=text, view=None)
                elif self._message is not None:
                    await self._message.edit(content=text, view=None)
            except Exception:
                log.warning("knowledge-hub: could not update the folder picker message", exc_info=True)
            try:
                result = on_finish(outcome, state.path if outcome == "ok" else None)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.exception("knowledge-hub: folder picker callback failed")

        async def on_timeout(self) -> None:
            if not self.finished:
                await self._finish("timeout")

    return FolderPickerView()


async def open_picker(adapter, chat_id: str, user_id: str, state: PickerState, on_finish: OnFinish, *,
                      timeout: float, hint: str = "") -> bool:
    """Post the picker in ``chat_id`` through the Discord adapter. Must run on the gateway's event loop.
    False when it could not be sent."""
    send_prompt = getattr(adapter, "_send_prompt", None)
    if send_prompt is None:
        log.warning("knowledge-hub: Discord adapter has no _send_prompt; folder picker unavailable")
        return False
    view = _make_view(state, user_id, on_finish, timeout, hint)
    result = await send_prompt(chat_id, None, lambda _channel: ({"content": state.content(), "view": view}, view),
                               fail_log="knowledge-hub folder picker")
    return bool(getattr(result, "success", False))
