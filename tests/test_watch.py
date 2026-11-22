import threading
import time

from knowledgehub.watch import watch


def run_watch(tick, until, timeout=10, every=0.05):
    stop = threading.Event()
    messages: list[str] = []
    thread = threading.Thread(target=watch, args=(tick,),
                              kwargs={"every": every, "stop": stop, "on_message": messages.append})
    thread.start()
    try:
        deadline = time.monotonic() + timeout
        while not until() and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        stop.set()
        thread.join(timeout=5)
    return messages


def test_watch_ticks_until_stopped():
    ticks = []
    run_watch(lambda: ticks.append(1), until=lambda: len(ticks) >= 3)
    assert len(ticks) >= 3


def test_a_failing_tick_does_not_stop_the_watcher():
    calls = []

    def broken():
        calls.append(1)
        raise OSError("disk full")

    messages = run_watch(broken, until=lambda: len(calls) >= 2)
    assert len(calls) >= 2 and any("periodic task failed: OSError: disk full" in m for m in messages)
