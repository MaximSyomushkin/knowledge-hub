import json
import subprocess

import httpx
import pytest

from knowledgehub.config import LLMConfig
from knowledgehub.llm import LlamaServerClient, LLMError, ModelServerUnavailable
from knowledgehub.schemas import IdeaSummary


def make_client(handler, **overrides):
    cfg = LLMConfig(**{"url": "http://chat", **overrides})
    return LlamaServerClient(cfg, transport=httpx.MockTransport(handler))


def chat_reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def test_generate_json_sends_schema_without_thinking():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.url.path, json.loads(request.content)))
        return chat_reply('{"summary": "s"}')

    out = make_client(handler).generate_json("p", IdeaSummary, system="sys")
    assert out.summary == "s"
    host, path, body = seen[0]
    assert (host, path) == ("chat", "/v1/chat/completions")
    assert body["model"] == "Qwen3.5-4B-Q8_0"
    assert body["stream"] is False
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["response_format"]["json_schema"]["schema"]["properties"]["summary"]["type"] == "string"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "p"}]


def test_generate_json_retries_then_gives_up():
    calls = []

    def handler(request):
        calls.append(1)
        return chat_reply("nope")

    with pytest.raises(LLMError, match="IdeaSummary after 3 attempts"):
        make_client(handler).generate_json("p", IdeaSummary)
    assert len(calls) == 3


def test_generate_json_recovers_on_a_retry():
    replies = iter(["nope", '{"summary": "ok"}'])
    assert make_client(lambda r: chat_reply(next(replies))).generate_json("p", IdeaSummary).summary == "ok"


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout])
def test_connect_failures_are_unavailable_and_not_retried(error):
    calls = []

    def handler(request):
        calls.append(1)
        raise error("refused", request=request)

    with pytest.raises(ModelServerUnavailable, match="model server is not reachable at http://chat"):
        make_client(handler).generate_json("p", IdeaSummary)
    assert len(calls) == 1


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(500, json={"error": "boom"}),
    lambda r: (_ for _ in ()).throw(httpx.ReadError("boom", request=r)),
    lambda r: httpx.Response(200, content=b"not json"),
    lambda r: httpx.Response(200, json={"choices": []}),
])
def test_server_errors_are_llm_errors_not_unavailable(handler):
    with pytest.raises(LLMError) as info:
        make_client(handler).generate_json("p", IdeaSummary)
    assert not isinstance(info.value, ModelServerUnavailable)


def test_list_models():
    client = make_client(lambda r: httpx.Response(200, json={"data": [{"id": "only"}]}))
    assert client.list_models() == ["only"]


def _claude_run(result, seen):
    def run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        lines = [json.dumps({"type": "system"}),
                 json.dumps({"type": "result", "subtype": "success", "is_error": False, **result})]
        return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(lines), stderr="")
    return run


def test_claude_models_go_through_the_cli_with_schema(monkeypatch):
    seen = []
    monkeypatch.setattr("knowledgehub.llm.subprocess.run", _claude_run({"result": "", "structured_output": {"summary": "s"}}, seen))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    def handler(request):
        raise AssertionError("claude-* must not reach llama-server")

    out = make_client(handler, claude_command="claude.exe").generate_json("p", IdeaSummary, system="sys",
                                                                          model="claude-opus-5-5")
    assert out.summary == "s"
    cmd, kwargs = seen[0]
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5" and "--json-schema" in cmd
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    assert json.loads(kwargs["input"])["message"]["content"] == [{"type": "text", "text": "p"}]


def test_claude_errors_are_llm_errors(monkeypatch):
    monkeypatch.setattr("knowledgehub.llm.subprocess.run", _claude_run({"subtype": "error_during_execution", "is_error": True}, []))
    client = make_client(lambda r: None, claude_command="claude.exe", model="claude-opus-5-5")
    with pytest.raises(LLMError, match="error_during_execution"):
        client.generate_json("q", IdeaSummary)
