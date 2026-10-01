"""The one door to the LLM (design_backend.md 14.2). Nodes get a client as an argument.

LLM_MODE=recorded (default): answers are read from data/llm_recordings/<node>/<key>.json; a
missing recording is a failed call, so the demo runs with the network off.
LLM_MODE=live: a real call to the OpenAI-compatible endpoint in LLM_BASE_URL (DeepSeek since
2026-09-26). It is an external action: the owner confirms the prompt and
the cost before the first live run of each node (CLAUDE.md rule 2). Each live answer is saved
as a recording. temperature=0 (design_eval.md 2: determinism) on every call, for every node
sharing this client; a repeated question or a re-run of the same email should not get a
different answer by chance. [AMENDMENT 2026-09-28, third live-demo finding] the same chat
question, asked twice, named a different arbitrary subset of a 33-item queue each time; the
prompt was missing a total-count rule (see prompts.md, design_backend.md section 29) and this
client had never actually set temperature, though design_eval.md always called for it.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from src.settings import DATASET_ROOT, Settings

RECORDINGS = DATASET_ROOT / "data" / "llm_recordings"


def _content_hash(value: str) -> str:
    """[AMENDMENT 2026-09-29, protocol/chordx_agent.md 9] content-addressed, so it can never go
    stale from a forgotten manual bump: the same prompt/tool-schema text always hashes the same,
    and a changed one always hashes differently."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


# [AMENDMENT 2026-10-01, design_agent_e16_v7.md 4.1] Nodes that have a strict output schema.
# node -> (schema name, JSON schema). A registered node on an OpenAI endpoint asks for
# response_format json_schema strict (accepted together with function tools, probed 2026-10-01 on
# gpt-4o-mini and gpt-5.5); every other node, and every other provider, keeps json_object.
STRICT_SCHEMAS: dict[str, tuple[str, dict]] = {}


def register_schema(node: str, name: str, schema: dict) -> None:
    STRICT_SCHEMAS[node] = (name, schema)


class LlmError(Exception):
    """The call gave no usable answer (network, timeout, no recording, not JSON)."""


class LlmClient(Protocol):
    def complete_json(self, node: str, key: str, system: str, user: str) -> dict: ...

    def complete_chat(
        self, node: str, key: str, system: str, user: str, tools: list[dict], turns: list[dict]
    ) -> dict: ...


class RecordedLlm:
    def __init__(self, folder: Path = RECORDINGS):
        self.folder = folder

    def complete_json(self, node: str, key: str, system: str, user: str) -> dict:
        path = self.folder / node / f"{key}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LlmError(f"no recording {node}/{key}") from None
        except (OSError, ValueError) as exc:
            raise LlmError(f"recording {node}/{key} unreadable: {exc}") from None

    def complete_chat(
        self, node: str, key: str, system: str, user: str, tools: list[dict], turns: list[dict]
    ) -> dict:
        """design_backend.md 9.4: a plain (pre-tools) recording is one JSON, replayed as a
        single {"final": ...} turn, unchanged from before; a tool-using recording is a
        {"turns": [...]} transcript. Either way this only ever hands back the *model's own*
        next turn (tool_calls or final) — the caller re-runs the real E17/E18 code for any
        tool call, so a stale recording can never serve stale data."""
        raw = self.complete_json(node, key, system, user)
        model_turns = raw["turns"] if isinstance(raw, dict) and "turns" in raw else [{"final": raw}]
        if len(turns) >= len(model_turns):
            raise LlmError(f"recording {node}/{key} has no turn {len(turns)}")
        next_turn = model_turns[len(turns)]
        if "tool_calls" not in next_turn and "final" not in next_turn:
            raise LlmError(f"recording {node}/{key}: turn {len(turns)} is not a model turn")
        return next_turn


class LiveLlm:
    """Real call (OpenAI-compatible API, JSON output); saves what it gets as a recording."""

    def __init__(self, settings: Settings, folder: Path = RECORDINGS, reasoning_effort: str | None = None):
        from openai import OpenAI  # imported here so tests and recorded mode never need it

        if not settings.has_api_key or not settings.llm_model:
            raise LlmError("live mode needs LLM_API_KEY and LLM_MODEL in .env")
        key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        # max_retries: the client backs off and retries on 429/5xx itself. The v6 benchmark hit
        # gpt-4.1's per-minute limit (three parallel router samples) with the default of 2.
        self.client = OpenAI(api_key=key, base_url=settings.llm_base_url, timeout=240, max_retries=6)
        self.model = settings.llm_model
        # DeepSeek thinks before answering unless told not to; the reasoning is billed as output
        self.extra = (
            {"thinking": {"type": settings.llm_thinking}}
            if "deepseek" in settings.llm_base_url
            else {}
        )
        self.folder = folder
        # Reasoning models (gpt-5.x, o-series) accept only their default temperature; sending 0
        # is a request error. Every other model keeps temperature=0 exactly as before.
        reasoning = self.model.startswith(("gpt-5", "o1", "o3", "o4"))
        self._sampling: dict = {} if reasoning else {"temperature": 0}
        if reasoning and reasoning_effort:  # e.g. "low": much faster on gpt-5.x (eval harness)
            self._sampling["reasoning_effort"] = reasoning_effort
        self._strict = "api.openai.com" in settings.llm_base_url

    def _strict_format(self, node: str) -> dict | None:
        spec = STRICT_SCHEMAS.get(node)
        if spec is None or not self._strict:
            return None
        return {"type": "json_schema", "json_schema": {"name": spec[0], "strict": True, "schema": spec[1]}}

    def _debug_write(self, node: str, key: str, system: str, user: str) -> None:
        """LLM_DEBUG_LOG=1: write the exact request next to the recording, so the owner can read
        it after asking a question in the browser, without printing it in a server log a real
        deployment would keep. Never written unless the env var is set; off by default."""
        try:
            user_readable = json.loads(user)
        except ValueError:
            user_readable = user
        path = self.folder / node / f"{key}.request.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"node": node, "key": key, "system": system, "user": user_readable},
                       ensure_ascii=False, indent=1),  # fmt: skip
            encoding="utf-8",
        )

    def complete_json(self, node: str, key: str, system: str, user: str) -> dict:
        if os.getenv("LLM_DEBUG_LOG"):  # for the owner to eyeball a live prompt while testing
            self._debug_write(node, key, system, user)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                **self._sampling,  # design_eval.md 2: determinism, no repeated cost from a flaky retry
                response_format=self._strict_format(node) or {"type": "json_object"},
                extra_body=self.extra or None,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            answer = json.loads(response.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001 - any failure of the call is an LlmError
            raise LlmError(f"{type(exc).__name__}: {exc}") from None
        path = self.folder / node / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(answer, ensure_ascii=False, indent=1), encoding="utf-8")
        usage = getattr(response, "usage", None)
        with (self.folder / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "node": node, "key": key, "model": self.model,
                "prompt_version": _content_hash(system),  # [AMENDMENT 2026-09-29] chordx_agent.md 9
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            }) + "\n")  # fmt: skip
        return answer

    @staticmethod
    def _messages(system: str, user: str, turns: list[dict]) -> list[dict]:
        """Rebuilds the OpenAI-shaped message list from the abstract turn history each call
        (at most 3 tool rounds, so this is cheap); the OpenAI wire format never leaks past
        this method (design_backend.md 14.2: "the one door to the LLM")."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for i, turn in enumerate(turns):
            if "tool_calls" in turn:
                messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": f"call_{i}_{j}", "type": "function",
                         "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {})}}
                        for j, c in enumerate(turn["tool_calls"])
                    ],
                })  # fmt: skip
            elif "tool_results" in turn:
                for j, r in enumerate(turn["tool_results"]):
                    content = {"result": r.get("result")} if r.get("error") is None else {"error": r["error"]}
                    messages.append({"role": "tool", "tool_call_id": f"call_{i - 1}_{j}",
                                     "content": json.dumps(content, ensure_ascii=False, default=str)})  # fmt: skip
        return messages

    def complete_chat(
        self, node: str, key: str, system: str, user: str, tools: list[dict], turns: list[dict]
    ) -> dict:
        """One more model turn of E16's tool loop (design_backend.md 9.4). `tools` is already
        empty once the caller's code-enforced cap is reached, so the model then has no way to
        ask for another call. Saves the growing transcript after every turn, so a run that ends
        mid-loop (an exception) still leaves a readable partial recording."""
        if os.getenv("LLM_DEBUG_LOG"):
            self._debug_write(node, key, system, user)
        messages = self._messages(system, user, turns)
        try:
            kwargs: dict = {
                "model": self.model, **self._sampling, "extra_body": self.extra or None,
                "messages": messages,
            }
            strict = self._strict_format(node)
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
                if strict:  # applies to the final (non-tool) message only
                    kwargs["response_format"] = strict
            else:
                kwargs["response_format"] = strict or {"type": "json_object"}
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            if message.tool_calls:
                turn = {"tool_calls": [
                    {"name": tc.function.name, "arguments": json.loads(tc.function.arguments or "{}")}
                    for tc in message.tool_calls
                ]}
            else:
                turn = {"final": json.loads(message.content or "")}
        except Exception as exc:  # noqa: BLE001 - any failure of the call is an LlmError
            raise LlmError(f"{type(exc).__name__}: {exc}") from None
        path = self.folder / node / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                # [AMENDMENT 2026-09-29, protocol/chordx_agent.md 9] Reproducibility &
                # Behavioral Stability: model/prompt/tool-schema versions travel with the
                # trajectory, so a replay (or a human reading it later) knows exactly what
                # produced it, not just what it said.
                "model": self.model,
                "prompt_version": _content_hash(system),
                "tool_schema_version": _content_hash(json.dumps(tools, sort_keys=True)),
                "turns": [*turns, turn],
            }, ensure_ascii=False, indent=1),  # fmt: skip
            encoding="utf-8",
        )
        usage = getattr(response, "usage", None)
        with (self.folder / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "node": node, "key": key, "model": self.model,
                "prompt_version": _content_hash(system),
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            }) + "\n")  # fmt: skip
        return turn


def make_client(settings: Settings) -> LlmClient:
    return LiveLlm(settings) if settings.llm_mode == "live" else RecordedLlm()
