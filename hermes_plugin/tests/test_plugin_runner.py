import asyncio
import sys
import textwrap

from knowledge_hub.runner import HubRunner

SCRIPT = textwrap.dedent("""
    import json, os, sys
    args = sys.argv[1:]
    if args[0] == "fail":
        print(json.dumps({"ok": False, "code": 2, "error": "model server down"}, ensure_ascii=False))
        sys.exit(2)
    if args[0] == "garbage":
        print("not json"); print("boom", file=sys.stderr); sys.exit(1)
    if args[0] == "unicode":
        print(json.dumps({"ok": True, "answer": "Line1 Line2"}, ensure_ascii=False))
        sys.exit(0)
    if args[0] == "no_json":
        print("just some text")
        sys.exit(0)
    if args[0] == "sleep":
        import time; time.sleep(5)
    print(json.dumps({"ok": True, "args": args, "config": os.environ.get("KHUB_CONFIG"), "emoji": "✅"}, ensure_ascii=False))
""")


def make(tmp_path, **kw):
    script = tmp_path / "fake_khub.py"
    script.write_text(SCRIPT, encoding="utf-8")
    return HubRunner([sys.executable, str(script)], **kw)


def test_success_parses_json_and_inserts_flag_after_subcommand(tmp_path):
    result = asyncio.run(make(tmp_path, config_path="C:/x/khub.toml").run("ask", "--", "hi there"))
    assert result.ok
    assert result.data["args"] == ["ask", "--json", "--", "hi there"]
    assert result.data["config"] == "C:/x/khub.toml"
    assert result.data["emoji"] == "✅"


def test_failure_uses_json_error(tmp_path):
    result = asyncio.run(make(tmp_path).run("fail"))
    assert result.code == 2 and not result.ok
    assert result.error == "model server down"


def test_non_json_failure_uses_stderr(tmp_path):
    result = asyncio.run(make(tmp_path).run("garbage"))
    assert result.code == 1 and result.data is None
    assert "boom" in result.error


def test_timeout(tmp_path):
    result = asyncio.run(make(tmp_path, timeout_s=0.5).run("sleep"))
    assert result.code == -1 and "timed out" in result.error


def test_missing_binary():
    result = asyncio.run(HubRunner(["C:/definitely/not/khub.exe"]).run("status"))
    assert result.code == -1 and "cannot start" in result.error


def test_raw_unicode_in_json(tmp_path):
    result = asyncio.run(make(tmp_path).run("unicode"))
    assert result.ok
    assert result.data["answer"] == "Line1\u2028Line2"


def test_success_with_no_json_output(tmp_path):
    result = asyncio.run(make(tmp_path).run("no_json"))
    assert result.code == 0 and not result.ok
    assert result.error == "khub returned no JSON output"


def test_dash_question_stays_positional(tmp_path):
    result = asyncio.run(make(tmp_path).run("ask", "--model", "m", "--", "-dash question"))
    assert result.data["args"] == ["ask", "--json", "--model", "m", "--", "-dash question"]


def test_timeout_override(tmp_path):
    runner = make(tmp_path, timeout_s=0.5)
    slow = asyncio.run(runner.run("sleep", timeout_s=30))
    assert slow.ok and slow.data["args"] == ["sleep", "--json"]
    default = asyncio.run(runner.run("sleep"))
    assert default.code == -1 and "timed out" in default.error
