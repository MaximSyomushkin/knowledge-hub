"""`khub` command line. Every command supports --json for the Hermes plugin."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import typer

from .config import Config, ConfigError, load_config
from .digest import daily as daily_digest
from .digest import weekend as weekend_digest
from .digest import weekly as weekly_digest
from .health import beat, server_problem, watcher_problem
from .ideas import VIA, IdeaStore, gist, open_ideas, pick_of_the_day
from .ideas import capture as capture_idea
from .lectures import refresh as refresh_lectures
from .llm import LlamaServerClient, LLMError, ModelServerUnavailable
from .memory import KINDS, MemoryStore, add_from_message, forget, list_items, mark_done
from .remind import remind as remind_due
from .vault import PathNotAllowed, Vault
from .watch import watch as run_watch

EXIT_INPUT, EXIT_SERVER = 1, 2

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="School hub for an Obsidian vault: lecture hubs, tasks, ideas and digests.")


def make_llm(cfg: Config):
    return LlamaServerClient(cfg.llm)


class _State:
    config_path: Path | None = None


_state = _State()


@app.callback()
def _main(config: Path | None = typer.Option(None, "--config", help="Path to khub.toml")) -> None:
    _state.config_path = config


def _load() -> tuple[Config, Vault]:
    cfg = load_config(_state.config_path)
    return cfg, Vault(cfg)


def _out(as_json: bool, data: dict, human: str) -> None:
    if as_json:
        typer.echo(json.dumps({"ok": True, **data}, ensure_ascii=False))
    else:
        typer.echo(human)


def _fail(as_json: bool, code: int, message: str) -> None:
    if as_json:
        typer.echo(json.dumps({"ok": False, "code": code, "error": message}, ensure_ascii=False))
    else:
        typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


def _guard(as_json: bool, fn: Callable[[], None]) -> None:
    try:
        fn()
    except (typer.Exit, typer.Abort):
        raise
    except ModelServerUnavailable as exc:
        _fail(as_json, EXIT_SERVER, str(exc))
    except (ConfigError, PathNotAllowed, FileNotFoundError, ValueError, LLMError) as exc:
        _fail(as_json, EXIT_INPUT, str(exc))
    except Exception as exc:  # last resort: callers parse the final stdout line as JSON
        _fail(as_json, EXIT_INPUT, f"{type(exc).__name__}: {exc}")


def _today(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _memory_line(item, due: str | None = None) -> str:
    due = due or item.due
    when = f"  due {date.fromisoformat(due):%d/%m/%Y}" + (f" {item.time}" if item.time else "") if due else ""
    repeat = f"  🔁 {item.repeat}" if item.repeat else ""
    state = " (done)" if item.checked else ""
    return f"m{item.id}  {item.kind:<5} {item.text}{when}{repeat}{state}"


def _listed(item, day: date) -> dict:
    """An item as /todo shows it: a repeating event carries its next date as `due`, its first as `starts`."""
    data = item.to_dict()
    if item.kind == "event" and item.rule is not None:
        data["starts"], data["due"] = item.due, item.next_date(day)
    return data


def _now(today: str | None) -> datetime:
    """When a message arrived: now, or now's time on `--today` (tests and back-dated runs)."""
    now = datetime.now().replace(second=0, microsecond=0)
    return datetime.combine(date.fromisoformat(today), now.time()) if today else now


@app.command("memory-add")
def memory_add(text: str = typer.Argument(..., help="What to remember, in your own words"),
               kind: str | None = typer.Option(None, "--kind", help="'idea': the whole message is an idea"),
               no_ideas: bool = typer.Option(False, "--no-ideas", help="Never make an idea of it"),
               via: str = typer.Option("cli", "--via", help="Where it came from: telegram, discord or cli"),
               today: str | None = typer.Option(None, "--today", help="YYYY-MM-DD (default: today)"),
               json_: bool = typer.Option(False, "--json")) -> None:
    """Turn a message into tasks and events in memory.md, or an idea in its own note."""
    def run() -> None:
        if kind not in (None, "idea"):
            raise ValueError("--kind can only be 'idea'")
        if kind == "idea" and no_ideas:
            raise ValueError("--kind idea and --no-ideas don't go together")
        if via not in VIA:
            raise ValueError(f"--via must be one of {', '.join(VIA)}")
        cfg, vault = _load()
        llm = make_llm(cfg)
        ideas = IdeaStore(vault)
        store = MemoryStore(vault)
        doc = store.load()
        result = add_from_message(doc, llm, cfg.llm.model, text, _today(today), ideas=open_ideas(ideas),
                                  allow_ideas=not no_ideas, only_idea=kind == "idea")
        if result["added"]:
            doc.assign_ids()
            store.save(doc)
        idea = capture_idea(ideas, llm, cfg.llm.model, result["ideas"], text, _now(today), via)
        lines = [_memory_line(i) for i in result["added"]]
        if idea:
            lines.append(f"{idea['id']}  idea  {idea['title']} ({idea['action']})")
        data = {"added": [i.to_dict() for i in result["added"]], "skipped": result["skipped"],
                "question": result["question"], "idea": idea}
        _out(json_, data, "\n".join(lines) or "nothing to remember")
    _guard(json_, run)


@app.command("ideas")
def ideas_cmd(switch: str | None = typer.Argument(None, help="on or off: the idea section of the daily digest"),
              json_: bool = typer.Option(False, "--json")) -> None:
    """Show or switch the daily digest's idea of the day."""
    def run() -> None:
        if switch not in (None, "on", "off"):
            raise ValueError("say on or off")
        store = IdeaStore(_load()[1])
        if switch is not None:
            store.set_reminders(switch == "on")
        everything = store.all()
        data = {"remind": store.state()["remind"], "count": sum(1 for i in everything if i.remind and not i.resting),
                "total": len(everything)}
        _out(json_, data, f"idea of the day: {'on' if data['remind'] else 'off'}; "
                          f"{data['count']} of {data['total']} ideas in the rotation")
    _guard(json_, run)


@app.command("memory-list")
def memory_list(kind: str | None = typer.Option(None, "--kind", help="task or event"),
                all_: bool = typer.Option(False, "--all", help="Include done tasks and past events"),
                today: str | None = typer.Option(None, "--today"),
                json_: bool = typer.Option(False, "--json")) -> None:
    """List what the bot remembers: open tasks and upcoming events."""
    def run() -> None:
        if kind is not None and kind not in KINDS:
            raise ValueError(f"--kind must be one of {', '.join(KINDS)}")
        doc = MemoryStore(_load()[1]).load()
        day = _today(today)
        items = list_items(doc, day, kind=kind, all_=all_)
        listed = [_listed(i, day) for i in items]
        human = "\n".join(_memory_line(i, d["due"]) for i, d in zip(items, listed, strict=True)) or "empty"
        _out(json_, {"items": listed}, human)
    _guard(json_, run)


@app.command("memory-done")
def memory_done(ref: str = typer.Argument(..., help="Item id (m3) or part of its text"),
                today: str | None = typer.Option(None, "--today"),
                json_: bool = typer.Option(False, "--json")) -> None:
    """Tick an open task."""
    def run() -> None:
        store = MemoryStore(_load()[1])
        doc = store.load()
        item, following = mark_done(doc, ref, _today(today))
        store.save(doc)
        data = item.to_dict()
        if following is not None:
            data["next"] = following.to_dict()
        human = _memory_line(item) + (f"\nnext: {_memory_line(following)}" if following is not None else "")
        _out(json_, {"item": data}, human)
    _guard(json_, run)


@app.command("memory-forget")
def memory_forget(ref: str = typer.Argument(..., help="Item id (m3) or part of its text"),
                  json_: bool = typer.Option(False, "--json")) -> None:
    """Delete one item from memory.md."""
    def run() -> None:
        store = MemoryStore(_load()[1])
        doc = store.load()
        item = forget(doc, ref)
        store.save(doc)
        _out(json_, {"item": item.to_dict()}, f"forgot {_memory_line(item)}")
    _guard(json_, run)


@app.command()
def digest(weekly_: bool = typer.Option(False, "--weekly", help="The Sunday recap instead of the daily digest"),
           weekend_: bool = typer.Option(False, "--weekend", help="Friday/Saturday: open tasks to work on"),
           today: str | None = typer.Option(None, "--today", help="YYYY-MM-DD (default: today)"),
           health: bool = typer.Option(True, "--health/--no-health",
                                       help="Daily: warn when the watcher or the model server is not running"),
           json_: bool = typer.Option(False, "--json")) -> None:
    """Morning digest (or --weekly recap, or --weekend work list) from memory.md and the idea of the day. Prints
    nothing when there is nothing to say, so a Hermes no-agent cron job stays silent."""
    def run() -> None:
        if weekly_ and weekend_:
            raise ValueError("--weekly and --weekend are different digests; pick one")
        cfg, vault = _load()
        items = MemoryStore(vault).load().items()
        day = _today(today)
        mention = cfg.digest.mention.strip()
        if weekly_:
            text, sections = weekly_digest(items, day, mention=mention)
        elif weekend_:
            text, sections = weekend_digest(items, day, mention=mention)
        else:
            problems = [watcher_problem(vault, datetime.now()), server_problem(make_llm(cfg), cfg.llm.model)] \
                if health else []
            store = IdeaStore(vault)
            pick = pick_of_the_day(store, day)
            idea = {"title": pick.title, "created": pick.created, "gist": gist(pick.summary, pick.entries),
                    "path": store.display_path(pick)} if pick else None
            text, sections = daily_digest(items, day, [p for p in problems if p], idea=idea, mention=mention)
        if json_:
            _out(True, {"text": text, "sections": sections}, "")
        elif text:
            typer.echo(text)
    _guard(json_, run)


@app.command()
def remind(now: str | None = typer.Option(None, "--now", help="'YYYY-MM-DD HH:MM' (default: now)"),
           within: int = typer.Option(60, "--within", help="Minutes ahead to look"),
           json_: bool = typer.Option(False, "--json")) -> None:
    """Announce timed tasks and events starting within the next hour, each once. Prints nothing otherwise, so
    the Hermes job that runs it every 15 minutes stays silent."""
    def run() -> None:
        lines = remind_due(_load()[1], datetime.fromisoformat(now) if now else datetime.now(), within)
        if json_:
            _out(True, {"reminders": lines}, "")
        elif lines:
            typer.echo("\n".join(lines))
    _guard(json_, run)


@app.command("lecture-notes")
def lecture_notes(json_: bool = typer.Option(False, "--json")) -> None:
    """Create or update each `Lecture N.md`: links to the lecture's sheets, its neighbours and its PDF. The
    watcher does this every minute; run it by hand after moving lecture folders around."""
    def run() -> None:
        cfg, _ = _load()
        written = refresh_lectures(cfg)
        rel = [path.relative_to(cfg.vault).as_posix() for path in written]
        _out(json_, {"written": rel}, "\n".join(rel) or "all lecture notes up to date")
    _guard(json_, run)


@app.command()
def watch() -> None:
    """Every minute: heartbeat, lecture and course notes, and expiring past-due tasks."""
    def run() -> None:
        cfg, vault = _load()

        def tick() -> None:
            beat(vault)
            for path in refresh_lectures(cfg):
                typer.echo(f"📎 {path.relative_to(cfg.vault).as_posix()}")
            for item in MemoryStore(vault).expire(date.today()):  # past-due tasks; today's stay all day
                typer.echo(f"🗑️ expired {_memory_line(item)}")

        try:
            run_watch(tick)
        except KeyboardInterrupt:
            typer.echo("stopped")
    _guard(False, run)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    app()
