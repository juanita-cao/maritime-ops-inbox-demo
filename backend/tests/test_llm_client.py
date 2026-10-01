"""LlmClient: the live call is deterministic (design_eval.md 2) and recorded mode is offline.
[AMENDMENT 2026-09-28, third live-demo finding] the same chat question named a different
arbitrary subset of a 33-item queue on each call; the live call had never set temperature=0,
though design_eval.md always called for it."""

import json
from datetime import timezone

import pytest

from src import llm_client as m
from src.settings import Settings


def settings(**over):
    base = dict(llm_mode="live", chat_llm_mode="live", llm_model="gpt-4o-mini",
                llm_base_url="https://api.openai.com/v1", llm_thinking="disabled",
                has_api_key=True, database_path="data/app.sqlite",
                default_utc_offset=timezone.utc)  # fmt: skip
    base.update(over)
    return Settings(**base)


class FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, content, tool_calls=None):
        self.message = FakeMessage(content, tool_calls)


class FakeResponse:
    def __init__(self, content, usage=None, tool_calls=None):
        self.choices = [FakeChoice(content, tool_calls)]
        self.usage = usage


class FakeToolCall:
    """Stands in for an OpenAI tool_call: only .function.name/.arguments are read."""

    def __init__(self, name, arguments):
        self.function = type("FakeFunctionCall", (), {"name": name, "arguments": arguments})()


TOOLS = [{"type": "function", "function": {"name": "get_email"}}]


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeOpenAI:
    """Stands in for openai.OpenAI: same shape, no network."""

    instances = []

    def __init__(self, api_key=None, base_url=None, timeout=None, max_retries=None):
        self.api_key, self.base_url, self.timeout, self.max_retries = api_key, base_url, timeout, max_retries
        self.chat = FakeChat(FakeCompletions(FakeResponse(json.dumps({"text": "ok"}))))
        FakeOpenAI.instances.append(self)


def live(tmp_path, monkeypatch, **over):
    """LiveLlm imports `openai` inside __init__ (so recorded mode never needs the package);
    stand in for the module in sys.modules before construction picks it up."""
    import sys

    fake_module = type(sys)("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return m.LiveLlm(settings(**over), folder=tmp_path)


def test_live_call_sets_temperature_zero(tmp_path, monkeypatch):
    """A repeated question must not get a different answer by chance."""
    client = live(tmp_path, monkeypatch)
    client.complete_json("E16", "q-1", "system", "user")
    call = FakeOpenAI.instances[-1].chat.completions.calls[0]
    assert call["temperature"] == 0


def test_live_call_saves_the_answer_as_a_recording(tmp_path, monkeypatch):
    client = live(tmp_path, monkeypatch)
    client.complete_json("E16", "q-1", "system", "user")
    assert json.loads((tmp_path / "E16" / "q-1.json").read_text())["text"] == "ok"


def test_recorded_mode_never_imports_openai(tmp_path):
    """The demo runs with the network off: RecordedLlm must not need the openai package."""
    (tmp_path / "E5").mkdir()
    (tmp_path / "E5" / "k.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert m.RecordedLlm(tmp_path).complete_json("E5", "k", "s", "u") == {"a": 1}


def test_live_mode_needs_a_key_and_a_model():
    with pytest.raises(m.LlmError):
        m.LiveLlm(settings(has_api_key=False))


def test_make_client_picks_by_mode(tmp_path, monkeypatch):
    assert isinstance(m.make_client(settings(llm_mode="recorded")), m.RecordedLlm)
    import sys

    fake_module = type(sys)("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    assert isinstance(m.make_client(settings(llm_mode="live")), m.LiveLlm)


def test_debug_log_off_by_default(tmp_path, monkeypatch):
    """No LLM_DEBUG_LOG: a real deployment never writes the prompt text to disk."""
    monkeypatch.delenv("LLM_DEBUG_LOG", raising=False)
    client = live(tmp_path, monkeypatch)
    client.complete_json("E16", "q-1", "system text", '{"question": "hi"}')
    assert not (tmp_path / "E16" / "q-1.request.json").exists()


def test_debug_log_writes_the_exact_request_when_set(tmp_path, monkeypatch):
    """LLM_DEBUG_LOG=1: the owner can read the exact system and user text sent, next to the
    recording, without it appearing in a server log a real deployment would keep."""
    monkeypatch.setenv("LLM_DEBUG_LOG", "1")
    client = live(tmp_path, monkeypatch)
    client.complete_json("E16", "q-1", "system text", '{"question": "hi"}')
    written = json.loads((tmp_path / "E16" / "q-1.request.json").read_text())
    assert written["system"] == "system text"
    assert written["user"] == {"question": "hi"}  # parsed, not left as a JSON string


# --- complete_chat (E16 read-only tools, design_backend.md 9.4) [AMENDMENT 2026-09-28] -------


def test_live_complete_chat_returns_tool_calls_when_the_model_asks_for_one(tmp_path, monkeypatch):
    client = live(tmp_path, monkeypatch)
    tc = FakeToolCall("get_email", '{"email_id": "E010"}')
    client.client.chat.completions.response = FakeResponse(None, tool_calls=[tc])
    step = client.complete_chat("E16", "q-1", "sys", "user", TOOLS, [])
    assert step == {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E010"}}]}
    call = client.client.chat.completions.calls[0]
    assert (call["tools"], call["tool_choice"]) == (TOOLS, "auto")
    assert "response_format" not in call
    assert call["temperature"] == 0


def test_live_complete_chat_returns_final_when_the_model_just_answers(tmp_path, monkeypatch):
    client = live(tmp_path, monkeypatch)
    client.client.chat.completions.response = FakeResponse(json.dumps({"text": "done", "sources": []}))
    step = client.complete_chat("E16", "q-1", "sys", "user", [], [])
    assert step == {"final": {"text": "done", "sources": []}}
    call = client.client.chat.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert "tools" not in call and "tool_choice" not in call


def test_live_complete_chat_saves_a_growing_transcript(tmp_path, monkeypatch):
    client = live(tmp_path, monkeypatch)
    tc = FakeToolCall("get_email", '{"email_id": "E010"}')
    client.client.chat.completions.response = FakeResponse(None, tool_calls=[tc])
    first = client.complete_chat("E16", "q-1", "sys", "user", TOOLS, [])
    saved = json.loads((tmp_path / "E16" / "q-1.json").read_text())
    assert saved["turns"] == [first]
    assert saved["model"] == "gpt-4o-mini" and saved["prompt_version"] and saved["tool_schema_version"]
    client.client.chat.completions.response = FakeResponse(json.dumps({"text": "done", "sources": []}))
    tool_results = {"tool_results": [{"name": "get_email", "arguments": {"email_id": "E010"},
                                      "result": None, "error": None}]}  # fmt: skip
    client.complete_chat("E16", "q-1", "sys", "user", [], [first, tool_results])
    saved = json.loads((tmp_path / "E16" / "q-1.json").read_text())
    assert saved["turns"] == [first, tool_results, {"final": {"text": "done", "sources": []}}]


def test_live_complete_chat_builds_messages_with_matching_tool_call_ids(tmp_path, monkeypatch):
    client = live(tmp_path, monkeypatch)
    client.client.chat.completions.response = FakeResponse(json.dumps({"text": "ok", "sources": []}))
    turns = [
        {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E010"}}]},
        {"tool_results": [{"name": "get_email", "arguments": {"email_id": "E010"},
                           "result": {"email_id": "E010"}, "error": None}]},
    ]  # fmt: skip
    client.complete_chat("E16", "q-1", "sys", "user text", [], turns)
    messages = client.client.chat.completions.calls[0]["messages"]
    assert [msg["role"] for msg in messages] == ["system", "user", "assistant", "tool"]
    assert messages[2]["tool_calls"][0]["function"]["name"] == "get_email"
    assert messages[3]["tool_call_id"] == messages[2]["tool_calls"][0]["id"]
    assert json.loads(messages[3]["content"]) == {"result": {"email_id": "E010"}}


def test_live_complete_chat_prompt_version_changes_when_the_prompt_does(tmp_path, monkeypatch):
    """protocol/chordx_agent.md §9: content-addressed, so a changed prompt is never silently
    replayed under the old version's identity."""
    client = live(tmp_path, monkeypatch)
    client.client.chat.completions.response = FakeResponse(json.dumps({"text": "ok", "sources": []}))
    client.complete_chat("E16", "q-1", "system A", "user", [], [])
    v1 = json.loads((tmp_path / "E16" / "q-1.json").read_text())["prompt_version"]
    client.complete_chat("E16", "q-2", "system B", "user", [], [])
    v2 = json.loads((tmp_path / "E16" / "q-2.json").read_text())["prompt_version"]
    assert v1 != v2


def test_live_complete_json_usage_log_records_the_prompt_version(tmp_path, monkeypatch):
    client = live(tmp_path, monkeypatch)
    client.complete_json("E16", "q-1", "system text", "user")
    last_line = (tmp_path / "usage.jsonl").read_text().strip().splitlines()[-1]
    assert json.loads(last_line)["prompt_version"] == m._content_hash("system text")


def test_recorded_complete_chat_wraps_a_plain_recording_as_one_final_turn(tmp_path):
    """A recording made before tools existed (or a question that never used one) still replays
    unchanged: one JSON becomes a single {"final": ...} turn."""
    (tmp_path / "E16").mkdir()
    (tmp_path / "E16" / "q-1.json").write_text(
        json.dumps({"text": "old-format answer", "sources": []}), encoding="utf-8"
    )
    step = m.RecordedLlm(tmp_path).complete_chat("E16", "q-1", "sys", "user", [], [])
    assert step == {"final": {"text": "old-format answer", "sources": []}}


def test_recorded_complete_chat_replays_a_transcript_turn_by_turn(tmp_path):
    (tmp_path / "E16").mkdir()
    (tmp_path / "E16" / "q-1.json").write_text(json.dumps({"turns": [
        {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E010"}}]},
        {"tool_results": [{"name": "get_email", "arguments": {"email_id": "E010"}, "result": None, "error": None}]},
        {"final": {"text": "answer", "sources": []}},
    ]}), encoding="utf-8")  # fmt: skip
    client = m.RecordedLlm(tmp_path)
    first = client.complete_chat("E16", "q-1", "sys", "user", [], [])
    assert first == {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E010"}}]}
    second = client.complete_chat("E16", "q-1", "sys", "user", [], [first, {"tool_results": []}])
    assert second == {"final": {"text": "answer", "sources": []}}


def test_recorded_complete_chat_past_the_end_of_the_transcript_is_an_llm_error(tmp_path):
    (tmp_path / "E16").mkdir()
    (tmp_path / "E16" / "q-1.json").write_text(json.dumps({"text": "x", "sources": []}), encoding="utf-8")
    client = m.RecordedLlm(tmp_path)
    with pytest.raises(m.LlmError):
        client.complete_chat("E16", "q-1", "sys", "user", [], [{"final": {"text": "x"}}])


def test_registered_node_asks_for_a_strict_schema_on_openai(tmp_path, monkeypatch):
    """[AMENDMENT 2026-10-01] design_agent_e16_v7.md 4.1."""
    monkeypatch.setitem(m.STRICT_SCHEMAS, "E16_X", ("x_out", {"type": "object", "properties": {}}))
    client = live(tmp_path, monkeypatch, llm_base_url="https://api.openai.com/v1")
    client.complete_json("E16_X", "q-1", "s", "u")
    client.complete_chat("E16_X", "q-2", "s", "u", TOOLS, [])
    client.complete_chat("E16_X", "q-3", "s", "u", [], [])
    calls = FakeOpenAI.instances[-1].chat.completions.calls
    want = {"type": "json_schema", "json_schema": {"name": "x_out", "strict": True, "schema": {"type": "object", "properties": {}}}}
    assert [c["response_format"] for c in calls] == [want, want, want]  # tools turn too


def test_unregistered_node_or_other_provider_keeps_json_object(tmp_path, monkeypatch):
    monkeypatch.setitem(m.STRICT_SCHEMAS, "E16_X", ("x_out", {"type": "object"}))
    other = live(tmp_path, monkeypatch, llm_base_url="https://api.deepseek.com")
    other.complete_json("E16_X", "q-1", "s", "u")
    assert FakeOpenAI.instances[-1].chat.completions.calls[0]["response_format"] == {"type": "json_object"}
    openai = live(tmp_path, monkeypatch, llm_base_url="https://api.openai.com/v1")
    openai.complete_json("E16_OTHER", "q-1", "s", "u")
    openai.complete_chat("E16_OTHER", "q-2", "s", "u", TOOLS, [])
    calls = FakeOpenAI.instances[-1].chat.completions.calls
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1]  # tools turn without a schema: as before
