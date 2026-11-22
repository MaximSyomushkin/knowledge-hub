"""Background loop: run periodic hub maintenance once per interval until stopped."""

from __future__ import annotations

import threading
from typing import Callable


def watch(tick: Callable[[], None], *, every: float = 60.0, stop: threading.Event | None = None,
          on_message: Callable[[str], None] = print) -> None:
    stop = stop or threading.Event()
    on_message(f"Hub watcher running every {every:g}s. Ctrl+C to stop.")
    while not stop.is_set():
        try:
            tick()
        except Exception as exc:  # a failing chore must never stop the watcher
            on_message(f"periodic task failed: {type(exc).__name__}: {exc}")
        stop.wait(every)
