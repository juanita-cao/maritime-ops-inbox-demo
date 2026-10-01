"""E16 v7 (docs/design_agent_e16_v7.md, approved 2026-10-01) — M0: contracts and safety.

v7 is v6 plus: strict structured output for the router and the answer (pydantic models and an
OpenAI json_schema registered with the LLM client), an evidence contract (each key claim carries a
verbatim quote that code checks against the text actually read), an output scan (E4 patterns on
the answer, details and draft) and vessel-code grounding. The router vote, answer budget,
follow-ups, proposal rendering and deterministic queries are v5/v6's, imported unchanged.
Also in this module: hybrid retrieval wiring (M1), the verifier call (M2), playbook selection and
the steps view, and report-based vessel facts (M3). v1-v6 stay frozen; this module only imports
their helpers.
"""

import json
import re
import threading
from datetime import date, timedelta
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src import distances
from src import e16_v5 as v5
from src import e16_v6 as v6
from src import e_nodes, llm_client, retrieval, verifier
from src import playbooks as pbk
from src import report_digest as rd
from src.llm_client import LlmClient, LlmError
from src.schemas import (
    ChatAnswer, ChatContext, ChatEvidence, ChatPlaybook, ChatRequest, ChatStep, SourceRef, ToolCallLog,
)  # fmt: skip

E16V7_FAILED = "I cannot answer that now; the pages still show everything."
HIDDEN = "[hidden]"
MAX_EVIDENCE = 6
MIN_QUOTE = 8  # characters, after whitespace squashing; shorter quotes prove nothing

_MODES = ("deterministic", "evidence_reasoning", "proposal_reasoning", "domain_knowledge", "hybrid", "follow_up",
          "out_of_scope")  # fmt: skip
_INTENTS = ("open_tasks", "pending_reply", "review_queue", "dues", "vessel_facts", "email_by_id")
_SIZES = ("short", "standard", "detailed")
# The open_tasks intent is only for the officer's own task list; a port or voyage question that the router
# sent there is not one. And a question that asks for report fields (wind, speed, draft ...) but analyses
# nothing is answered from the reports.
_TASK_WORDS = re.compile(r"待办|代办|任务|待处理|要处理|需要处理|处理的|to-?do|\btasks?\b|outstanding|pending|on my plate|attention|需要关注|需要跟进", re.I)
_ANALYSIS_WORDS = re.compile(r"索赔|claim|分析|analy|是否合理|reasonable|warrant|保证|比较|compare|为什么|why", re.I)
_STATUSES = ("sufficient", "partial", "missing_required_evidence", "no_matching_data")
_KINDS = ("email", "vessel", "task", "page")

# --- 4.1 Structured output ----------------------------------------------------------------------


class RouterOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    execution_mode: Literal[_MODES]  # type: ignore[valid-type]
    deterministic_intent: Literal[_INTENTS] | None = None  # type: ignore[valid-type]
    answer_size: Literal[_SIZES] = "standard"  # type: ignore[valid-type]
    standalone_question: str = ""
    search_terms: list[str] = []
    playbook: str | None = None
    reason: str = ""


class SourceOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal[_KINDS]  # type: ignore[valid-type]
    id: str
    label: str = ""


class EvidenceOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    claim: str
    source_id: str
    quote: str


class PassageOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    distance_nm: float
    speed_kn: float
    distance_source: str = "S2"


class BasisOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    point: str
    source: str = ""


class ProposalOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    conclusion: str = ""
    basis: list[BasisOut] = []
    counter_evidence: list[str] = []
    missing_information: list[str] = []


class StepOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    step_id: str
    status: Literal["done", "missing", "not_applicable"]
    note: str = ""
    evidence_ids: list[str] = []


class AnswerOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: str = ""
    details: str = ""
    sources: list[SourceOut] = []
    evidence: list[EvidenceOut] = Field(default=[])
    draft: str | None = None
    evidence_status: Literal[_STATUSES] | None = None  # type: ignore[valid-type]
    reasoning_trace: list[str] = []
    passage_estimate: PassageOut | None = None
    proposal: ProposalOut | None = None
    steps: list[StepOut] = []

    @field_validator("draft", mode="before")
    @classmethod
    def _draft_object_to_text(cls, value: Any) -> Any:
        return v6._draft_text(value) if isinstance(value, dict) else value  # noqa: SLF001


_S = {"type": "string"}


def _obj(props: dict) -> dict:
    """OpenAI strict mode: every property required, no extras."""
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(item: dict) -> dict:
    return {"type": "array", "items": item}


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


ROUTER_SCHEMA = _obj({
    "execution_mode": {"type": "string", "enum": list(_MODES)},
    "deterministic_intent": {"type": ["string", "null"], "enum": [*_INTENTS, None]},
    "answer_size": {"type": "string", "enum": list(_SIZES)},
    "standalone_question": _S,
    "search_terms": _arr(_S),
    "playbook": {"type": ["string", "null"]},
    "reason": _S,
})  # fmt: skip

ANSWER_SCHEMA = _obj({
    "answer": _S,
    "details": _S,
    "sources": _arr(_obj({"kind": {"type": "string", "enum": list(_KINDS)}, "id": _S, "label": _S})),
    "evidence": _arr(_obj({"claim": _S, "source_id": _S, "quote": _S})),
    "draft": {"type": ["string", "null"]},
    "evidence_status": {"type": "string", "enum": list(_STATUSES)},
    "reasoning_trace": _arr(_S),
    "passage_estimate": _nullable(_obj({"distance_nm": {"type": "number"}, "speed_kn": {"type": "number"},
                                        "distance_source": _S})),  # fmt: skip
    "proposal": _nullable(_obj({
        "conclusion": _S,
        "basis": _arr(_obj({"point": _S, "source": _S})),
        "counter_evidence": _arr(_S),
        "missing_information": _arr(_S),
    })),  # fmt: skip
    "steps": _arr(_obj({"step_id": _S, "status": {"type": "string", "enum": ["done", "missing", "not_applicable"]},
                        "note": _S, "evidence_ids": _arr(_S)})),  # fmt: skip
})  # fmt: skip

PRESENT_SCHEMA = _obj({
    "summary": _S,
    "items": _arr(_obj({"label": _S, "value": _S, "time": _S, "source": _S})),
    "missing": _arr(_S),
})  # fmt: skip

llm_client.register_schema("E16_V7_ROUTER", "e16_v7_router", ROUTER_SCHEMA)
llm_client.register_schema("E16_V7", "e16_v7_answer", ANSWER_SCHEMA)
llm_client.register_schema("E16_V7_PRESENT", "e16_v7_present", PRESENT_SCHEMA)

# --- prompts: v6's, plus the evidence contract ----------------------------------------------------

# Live finding (v7 golden run, gpt-4o-mini): "Newcastle港要注意什么问题" went to open_tasks 3 of 3 and a weather
# question to out_of_scope. The v6 text is frozen, so v7 corrects it here.
_ROUTER_FIXES = [
    ("  - open_tasks: what is outstanding / what do I need to handle / 待办事项 / 今天有什么要处理",
     "  - open_tasks: the officer's own task list in the system: what is outstanding / 待办事项 / 今天有什么要处理 (NOT \"what to watch out for\" at a port or on a voyage: that is domain_knowledge or hybrid)"),
    ("reported speed/consumption/weather or recent events",
     "reported speed/consumption, weather, wind, sea state, current (海流), or recent events"),
]


def build_router_system(menu: str) -> str:
    """v6's router prompt with the playbook menu (when there is one) and the `playbook` field."""
    head, tail = v6.E16_ROUTER_SYSTEM_V6.split("OUTPUT CONTRACT\n", 1)
    for old, new in _ROUTER_FIXES:
        assert old in head, old
        head = head.replace(old, new, 1)
    tail = tail.replace('"search_terms": [], "reason": ""}', '"search_terms": [], "playbook": null, "reason": ""}', 1)
    note = '\n"playbook": an id from PLAYBOOKS, or null.' if menu else '\n"playbook": always null.'
    return head + menu + "OUTPUT CONTRACT\n" + tail + note


E16_ROUTER_SYSTEM_V7 = build_router_system("")

_EVIDENCE_RULES = """EVIDENCE
- "evidence": one item per key claim of your answer, at most six: {"claim": the claim in a few words, "source_id": the email id (or task id, or vessel code) you read, "quote": an exact, contiguous passage of at most 200 characters copied verbatim from that source — same language, same spelling, no paraphrase}.
- Quote only what you actually read through a tool, the context or s1_prefetch. If you cannot quote it, you did not read it: do not state it as a company fact.
- The quote must contain the key fact of its claim (the number, party, port or date the claim states), not a nearby sentence.
- General practice (S2) and the passage estimate need no evidence item.
- Wording for the reader: never write the internal codes S1 or S2. Title the general-knowledge section "行业通用做法" (English: "General industry practice") and the recommendation section "建议" (English: "Recommendation"); never "建议口径" or "一般做法".

"""

_OUTPUT_CONTRACT = """OUTPUT CONTRACT
Return JSON only. Every field is required; use "" , [] or null when there is nothing:
{"answer": "", "details": "", "sources": [{"kind": "email|vessel|task|page", "id": "", "label": ""}], "evidence": [{"claim": "", "source_id": "", "quote": ""}], "draft": null, "evidence_status": "sufficient|partial|missing_required_evidence|no_matching_data", "reasoning_trace": [], "passage_estimate": null, "proposal": null, "steps": []}
"passage_estimate": null or {"distance_nm": <number>, "speed_kn": <number>, "distance_source": "E046|S2"}. "proposal": null outside proposal_reasoning/hybrid, else {"conclusion": "", "basis": [{"point": "", "source": ""}], "counter_evidence": [], "missing_information": []}. "steps": [] unless a PLAYBOOK is given, then one {"step_id": "", "status": "done|missing|not_applicable", "note": "", "evidence_ids": []} per playbook step."""


def _build_system() -> str:
    head, _ = v6.E16_SYSTEM_V6.split("\nOUTPUT CONTRACT\n", 1)
    assert "\nTRACE\n" in head
    head = head.replace("\nTRACE\n", "\n" + _EVIDENCE_RULES + "TRACE\n", 1)
    return head + "\n" + _OUTPUT_CONTRACT


E16_SYSTEM_V7 = _build_system()

# --- 4.2 Evidence contract -----------------------------------------------------------------------

_TEXT_FIELDS = ("subject", "sender", "text", "quoted_thread", "excerpt", "match")


def _squash(s: str) -> str:
    s = (s.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"'))
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in_text(quote: str, text: str) -> bool:
    """The quote, whitespace- and case-insensitive, occurs in the text. An ellipsis ("..." or "…")
    splits a quote into fragments that must each occur."""
    if len(_squash(quote)) < MIN_QUOTE:
        return False
    body = _squash(text)
    fragments = [f for f in (_squash(x) for x in re.split(r"\.{3}|…", quote)) if f]
    return bool(fragments) and all(f in body for f in fragments)


def source_texts(context_json: dict, context: ChatContext, seen: list[dict], prefetch: dict) -> dict[str, str]:
    """Text actually available for each source id: tool results, the s1 prefetch, the context's
    email views, tasks and vessels. Nothing the model did not receive counts."""
    out: dict[str, list[str]] = {}

    def add(key: str, *parts: Any) -> None:
        out.setdefault(key, []).extend(str(p) for p in parts if p)

    for d in [*seen, *(h for hits in prefetch.values() for h in hits)]:
        if isinstance(d, dict) and d.get("email_id"):
            add(d["email_id"], *(d.get(f) for f in _TEXT_FIELDS))
    for e in context.emails:
        add(e.email_id, e.subject, e.sender, e.excerpt)
    for t in context_json.get("open_tasks", []):
        add(t["task_id"], json.dumps(t, ensure_ascii=False, default=str))
    for v in context_json.get("vessels", []):
        add(v["vessel"], json.dumps(v, ensure_ascii=False, default=str))
    return {k: "\n".join(v) for k, v in out.items()}


def verify_evidence(items: list[EvidenceOut], texts: dict[str, str]) -> list[ChatEvidence]:
    checked = []
    for it in items[:MAX_EVIDENCE]:
        if it.source_id not in texts:
            status = "source_not_read"
        else:
            status = "verified" if quote_in_text(it.quote, texts[it.source_id]) else "quote_not_found"
        checked.append(ChatEvidence(claim=it.claim, source_id=it.source_id, quote=it.quote, status=status))
    return checked


def ungrounded(answer: str, corpus: str, known_ids: set[str]) -> list[str]:
    """v6's number / email-id check plus vessel codes: a vessel code in the answer must occur in
    something the model was given or read."""
    flagged = v6._unverified(answer, corpus, known_ids)  # noqa: SLF001
    upper = corpus.upper()
    flagged += [c for c in dict.fromkeys(m.upper() for m in v5._VESSEL.findall(answer)) if c not in upper]  # noqa: SLF001
    return flagged


# --- 4.3 Output scan -----------------------------------------------------------------------------


def scrub(text: str | None) -> tuple[str | None, int]:
    """Hide every value the E4 patterns would block on input (e-mail, phone, URL, address, id
    number) in text the chat is about to show. Returns the text and how many values were hidden."""
    if not text:
        return text, 0
    spans = sorted({(a, b) for _, a, b in e_nodes._scan_text(text)})  # noqa: SLF001
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in reversed(merged):
        text = text[:a] + HIDDEN + text[b:]
    return text, len(merged)


def _finalize(answer: ChatAnswer) -> ChatAnswer:
    text, n1 = scrub(answer.text)
    details, n2 = scrub(answer.details)
    draft, n3 = scrub(answer.draft)
    n = n1 + n2 + n3
    if not n:
        return answer.model_copy(update={"version": "v7"})
    return answer.model_copy(update={
        "text": text or answer.text, "details": details, "draft": draft, "version": "v7",
        "reasoning_trace": [*answer.reasoning_trace, f"Output scan (code): {n} value(s) hidden"],
    })  # fmt: skip


# --- router (v6's vote, v7's node and schema) ----------------------------------------------------


def _route(llm: LlmClient, key: str, question: str, history: list[dict], system: str = E16_ROUTER_SYSTEM_V7,
           playbook_ids: set[str] | None = None) -> tuple[dict, str]:  # fmt: skip
    user = v6._router_user(question, history)  # noqa: SLF001

    def sample(i: int) -> RouterOut | None:
        try:
            raw = v6._repair_route(llm.complete_json("E16_V7_ROUTER", f"{key}-s{i}", system, user))  # noqa: SLF001
            out = RouterOut.model_validate(raw)
            return out if out.execution_mode != "deterministic" or out.deterministic_intent else None
        except (LlmError, ValidationError, AttributeError, TypeError):
            return None

    with ThreadPoolExecutor(v6.ROUTER_SAMPLES) as pool:
        valid = [r.model_dump() for r in pool.map(sample, range(v6.ROUTER_SAMPLES)) if r is not None]
    if not valid:
        raise LlmError("no usable router sample")
    votes = Counter(v6._vote_key(r) for r in valid)  # noqa: SLF001
    top, count = votes.most_common(1)[0]
    chosen = next(r for r in valid if v6._vote_key(r) == top)  # noqa: SLF001
    if chosen["execution_mode"] == "out_of_scope" and history:
        alt = next((r for r in valid if r["execution_mode"] == "follow_up"), None)
        if alt is not None:
            chosen = alt
    agreeing = [r["playbook"] for r in valid if v6._vote_key(r) == top and r.get("playbook") in (playbook_ids or set())]  # noqa: SLF001
    chosen = {**chosen, "playbook": Counter(agreeing).most_common(1)[0][0] if agreeing else None}
    label = "/".join(x for x in top if x)
    return chosen, f"Router: {count}/{len(valid)} samples agree on {label}" + (
        "" if len(votes) == 1 else f" (others: {', '.join('/'.join(x for x in k if x) for k in votes if k != top)})")


# --- tool loop (v5's, with the node name as a parameter so the strict schema applies) -------------


def _tool_loop(llm: LlmClient, key: str, system: str, user: str, run_tool: Callable, specs: list[dict],
               ) -> tuple[dict, list[ToolCallLog], list[dict], bool]:  # fmt: skip
    turns: list[dict] = []
    logs: list[ToolCallLog] = []
    seen: list[dict] = []
    used = 0
    cap_reached = False
    for _ in range(v5.MAX_TOOL_CALLS + 2):
        cap_reached = used >= v5.MAX_TOOL_CALLS
        step = llm.complete_chat("E16_V7", key, system, user, [] if cap_reached else specs, turns)
        if "final" in step:
            return step["final"], logs, seen, cap_reached
        calls = step.get("tool_calls") or []
        if not calls:
            raise LlmError(f"E16_V7 turn for {key} had neither tool_calls nor final")
        results: list[dict] = []
        for i, call in enumerate(calls):
            name, raw_args = call.get("name"), call.get("arguments") or {}
            args_model = v5._TOOL_ARGS.get(name)  # noqa: SLF001
            if args_model is None:
                results.append({"name": name, "arguments": raw_args, "error": f"unknown tool {name!r}"})
                continue
            if used + i >= v5.MAX_TOOL_CALLS:
                results.append({"name": name, "arguments": raw_args, "error": "tool call cap reached"})
                logs.append(ToolCallLog(name=name, arguments=raw_args, result_summary="cap reached"))
                continue
            try:
                clean = args_model.model_validate(raw_args).model_dump(exclude_none=True)
                value = run_tool(name, clean)
            except ValidationError as exc:
                err = exc.errors()[0]["msg"]
                results.append({"name": name, "arguments": raw_args, "error": err})
                logs.append(ToolCallLog(name=name, arguments=raw_args, result_summary=f"error: {err}"))
                continue
            except Exception as exc:  # noqa: BLE001 - a broken tool fails closed, not a crash
                results.append({"name": name, "arguments": raw_args, "error": type(exc).__name__})
                logs.append(ToolCallLog(name=name, arguments=raw_args, result_summary=f"error: {type(exc).__name__}"))
                continue
            dumped = v5._as_dicts(value)  # noqa: SLF001
            results.append({"name": name, "arguments": clean,
                            "result": dumped if isinstance(value, list) else (dumped[0] if dumped else None)})  # fmt: skip
            logs.append(ToolCallLog(name=name, arguments=clean, result_summary=v5._summary(value)))  # noqa: SLF001
            seen.extend(dumped)
        used += len(calls)
        turns.append({"tool_calls": calls})
        turns.append({"tool_results": results})
    raise LlmError(f"E16_V7 tool loop for {key} did not reach a final answer")


# --- reasoning -----------------------------------------------------------------------------------


def _parse_answer(raw: Any, llm: LlmClient, key: str, system: str, user: str) -> AnswerOut:
    """Validate the answer object; on failure one repair attempt carrying the validation error
    (no tools), then fail closed (design 4.1)."""
    try:
        return AnswerOut.model_validate(raw)
    except ValidationError as exc:
        note = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:4])
        fixed = llm.complete_json("E16_V7", f"{key}-r", system,
                                  user + f"\n\nYour previous JSON was invalid ({note}). Return the corrected JSON only.")
        try:
            return AnswerOut.model_validate(fixed)
        except ValidationError as exc2:
            raise LlmError("answer failed validation twice") from exc2


def _reason(asked: ChatRequest, request: ChatRequest, context: ChatContext, llm: LlmClient, key: str, zh: bool,
            mode: str, size: str, terms: list[str], today: str, run_tool: Callable | None,
            event_types: list[str] | None, pre_trace: list[str], playbook: pbk.Playbook | None = None,
            verify_llm: LlmClient | None = None) -> ChatAnswer:  # fmt: skip
    failed = ChatAnswer(text=E16V7_FAILED, llm_status="failed")
    history = [t.model_dump() for t in request.history]
    prefetch, pre_logs, pre_seen = v5._s1_prefetch(terms, run_tool)  # noqa: SLF001
    context_json = v6._slim_context(context, asked.question)  # noqa: SLF001
    user = json.dumps({"question": asked.question, "execution_mode": mode, "answer_size": size, "history": history,
                       "context": context_json, "s1_prefetch": prefetch, "today": today},
                      ensure_ascii=False, separators=(",", ":"), default=str)  # fmt: skip
    system = E16_SYSTEM_V7 + (("\n\n" + pbk.prompt_block(playbook)) if playbook else "")
    allowed = v5._allowed_ids(context)  # noqa: SLF001
    if run_tool is None:
        final = llm.complete_json("E16_V7", key, system, user)
        tool_logs: list[ToolCallLog] = []
        seen: list[dict] = []
        cap_reached = False
    else:
        final, tool_logs, seen, cap_reached = _tool_loop(llm, key, system, user, run_tool,
                                                         v5.tool_specs(event_types or []))  # fmt: skip
    out = _parse_answer(final, llm, key, system, user)
    raw = out.model_dump()
    tool_logs, seen = pre_logs + tool_logs, pre_seen + seen
    for d in seen:
        if d.get("email_id"):
            allowed["email"].setdefault(d["email_id"], d.get("subject") or d["email_id"])

    answer, details, draft = out.answer.strip(), out.details.strip() or None, out.draft.strip() if out.draft else None
    l2 = v5._AUTHORITY[mode] == "supported_l2"  # noqa: SLF001
    if not answer and not draft and not (l2 and out.proposal) and not out.passage_estimate:
        return failed
    evidence_status = out.evidence_status
    if cap_reached and evidence_status not in ("sufficient", None):
        evidence_status = "retrieval_limit_reached"
    trace = pre_trace + v5._trace(raw, tool_logs)  # noqa: SLF001

    # M0 checks run on the model's own words, before any code-written line is added.
    texts = source_texts(context_json, context, seen, prefetch)
    evidence = verify_evidence(out.evidence, texts)
    corpus = "\n".join([asked.question, request.question, json.dumps(context_json, ensure_ascii=False, default=str),
                        json.dumps(prefetch, ensure_ascii=False), json.dumps(seen, ensure_ascii=False),
                        *[h["text"] for h in history]])  # fmt: skip
    flagged = ungrounded(answer + "\n" + (draft or ""), corpus, set(allowed["email"]))
    unverified = [e for e in evidence if e.status != "verified"]
    cites_company_records = any(s.kind in ("email", "task") for s in out.sources)
    no_evidence = cites_company_records and not out.evidence and mode != "domain_knowledge"

    # M2: does a quote that exists support the claim it is attached to?
    unsupported: list[tuple[ChatEvidence, str]] = []
    if verify_llm is not None and verifier.needs_verification(mode, size, asked.question):
        idx = [i for i, e in enumerate(evidence) if e.status == "verified" and not verifier.weak_quote(e.claim, e.quote)]
        verdicts = verifier.verify_claims(verify_llm, key, asked.question,
                                          [(evidence[i].claim, evidence[i].source_id, evidence[i].quote) for i in idx], zh)  # fmt: skip
        checked = 0
        for i, v in zip(idx, verdicts, strict=True):
            if v is None:
                continue
            checked += 1
            evidence[i] = evidence[i].model_copy(update={"support": v.verdict})
            if v.verdict != "supports":
                unsupported.append((evidence[i], v.reason))
        if idx:
            trace.append(f"Verifier: {checked} of {len(idx)} claim(s) checked, {len(unsupported)} not supported"
                         if checked else "Verifier unavailable: answer shown unchecked")  # fmt: skip

    sources, dropped = v5._relevance_gate(v5._sources(raw, allowed), asked.question,  # noqa: SLF001
                                          v5._email_vessels(context, seen))  # noqa: SLF001
    answer, overflow = v6._enforce_budget(answer, "short" if draft else size)  # noqa: SLF001
    if overflow:
        trace.append(f"Answer budget ({size}): {len(v6._lines(overflow))} line(s) moved to details")  # noqa: SLF001
    lines: list[str] = []
    extra_details: list[str | None] = []
    proposal_line = False
    if l2:
        for eid, _ in dropped:
            allowed["email"].pop(eid, None)
        rendered = v6._render_proposal(raw.get("proposal"), allowed, zh)  # noqa: SLF001
        if rendered is not None:
            line, block, grounded = rendered
            if unsupported:
                line = line.replace(v6._REVIEW_TAG_ZH, "（建议，证据不足，需复核）").replace(  # noqa: SLF001
                    v6._REVIEW_TAG_EN, " (proposal — evidence insufficient, needs review)")  # noqa: SLF001
            lines.append(line)
            proposal_line = True
            extra_details.append(block)
            trace.append("Proposal: conclusion in the answer, full contract in details (code)")
            if not grounded and evidence_status in ("sufficient", "partial", None):
                evidence_status = "missing_required_evidence"
        elif not v5._REVIEW_LINE.search(answer):  # noqa: SLF001
            answer += v6._REVIEW_TAG_ZH if zh else v6._REVIEW_TAG_EN  # noqa: SLF001
    lines.append(answer)
    passage, passage_note = v6._passage_line(raw.get("passage_estimate"), zh)  # noqa: SLF001
    src = out.passage_estimate.distance_source if out.passage_estimate else ""
    if passage and src in allowed["email"] and all(x.id != src for x in sources):
        sources.append(SourceRef(kind="email", id=src, label=allowed["email"][src]))
    if passage:
        lines.append(passage)
        extra_details.append(passage_note)
        trace.append("Passage time computed in code from the stated distance and speed")
    if dropped:
        ids = "、".join(eid for eid, _ in dropped)
        lines.append(f"⚠ {ids} 是其他船的邮件，已从来源剔除，相关结论请核对。" if zh
                     else f"⚠ {ids} concern another vessel; removed from the sources — check any conclusion based on them.")
        trace.append(f"Relevance gate (code): dropped {ids} — other vessel")
        if evidence_status == "sufficient":
            evidence_status = "partial"
    if unsupported:
        n = len(unsupported)
        lines.append(f"⚠ 核验：{n} 条结论没有被所引原文支持，见依据。" if zh
                     else f"⚠ Check: {n} claim(s) are not supported by the quoted text; see the basis.")
        extra_details.append(("所引原文不能支持以下结论：\n" if zh else "The quoted text does not support these claims:\n")
                             + "\n".join(f"- {e.claim} [{e.source_id}]：{reason}" for e, reason in unsupported))  # fmt: skip
        evidence_status = ("missing_required_evidence" if l2 and proposal_line
                           else "partial" if evidence_status == "sufficient" else evidence_status)  # fmt: skip
    # the emails are the numbered reference list under the answer (design 7.1 section 3): only the
    # "general knowledge, not a company record" statement is still written into the text
    tag = None if any(x.kind == "email" for x in sources) else v6._source_tag(sources, mode, zh)  # noqa: SLF001
    if tag:
        lines.append(tag)
    if mode in ("domain_knowledge", "hybrid"):
        extra_details.append("一般航运知识部分不是公司记录；未接入实时外部数据（天气、最新港口限制、routing distance），需另行确认。" if zh
                             else "General-practice points are not company records; no live external data is connected.")
    if unverified:
        extra_details.append(("以下结论的原文摘录未能在已读记录中找到，请核对：\n" if zh
                              else "The quote for these claims was not found in the records read — check them:\n")
                             + "\n".join(f"- {e.claim} [{e.source_id}]" for e in unverified))  # fmt: skip
        trace.append(f"Evidence check (code): {len(unverified)} of {len(evidence)} quote(s) not verified")
    elif evidence:
        trace.append(f"Evidence check (code): {len(evidence)} of {len(evidence)} quote(s) verified")
    if no_evidence:
        extra_details.append("回答引用了公司记录，但没有给出原文摘录，请核对。" if zh
                             else "The answer cites company records but gave no quote — check it against them.")
        trace.append("Evidence check (code): company records cited without any quote")
    if (unverified or no_evidence) and evidence_status == "sufficient":
        evidence_status = "partial"
    if flagged:
        extra_details.append(("以下数字/编号未在已读记录中原样出现（可能是推算，请核对）：" if zh
                              else "Not found verbatim in the records read (may be a calculation — check): ") + "、".join(flagged))
        trace.append(f"Grounding check (code): {len(flagged)} item(s) not found verbatim in what was read")

    steps: list[ChatStep] = []
    if playbook is not None:
        for r in pbk.reconcile_steps(playbook, [x.model_dump() for x in out.steps], set(texts), bool(draft)):
            steps.append(ChatStep(step_id=r.step_id, primitive=r.primitive, text=r.text, status=r.status,
                                  note=r.note, evidence_ids=r.evidence_ids))  # fmt: skip
        trace.append(f"Playbook {playbook.id}: {sum(x.status == 'done' for x in steps)} of {len(steps)} step(s) done, "
                     f"{sum(x.status == 'missing' for x in steps)} missing")  # fmt: skip

    return ChatAnswer(
        text="\n".join(x for x in lines if x.strip()) or "Here is a draft reply.",
        details=v6._join(overflow, details, *extra_details), sources=sources, draft=draft, llm_status="ok",  # noqa: SLF001
        tool_calls=tool_logs, execution_mode=mode, capability_authority=v5._AUTHORITY[mode],  # noqa: SLF001
        evidence_status=evidence_status, retrieval_outcome=v5._EVIDENCE_TO_RETRIEVAL_OUTCOME.get(evidence_status),  # noqa: SLF001
        evidence=evidence, steps=steps,
        playbook=ChatPlaybook(id=playbook.id, title=playbook.title, status=playbook.status) if playbook else None,
        reasoning_trace=trace[:18],
    )  # fmt: skip


# --- M1: hybrid retrieval wired into the search tool ---------------------------------------------


class RetrievalBackend:
    """The process-wide index and the query embedder. `search_emails` with a `text` filter becomes
    keyword + semantic; without one it is v5's filter. No embedder or no index: keyword only."""

    def __init__(self, index_dir: Path | None, embedder: retrieval.Embedder | None = None):
        self.index_dir, self.embedder = index_dir, embedder
        self._idx: retrieval.HybridIndex | None = None
        self._ids: frozenset[str] = frozenset()
        self._queries: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def index(self, store, kb) -> retrieval.HybridIndex:
        ids = frozenset(store.email_ids())
        with self._lock:
            if self._idx is None or ids != self._ids:
                rows = []
                for eid in sorted(ids):
                    email = store.get_email(eid)
                    if email is not None and e_nodes.chat_email_view(email, kb) is not None:  # the E4 gate
                        rows.append((eid, email.subject, email.new_text, email.quoted_text))
                self._idx, self._ids = retrieval.HybridIndex.from_emails(rows, self.index_dir), ids
            return self._idx

    def _query_vector(self, text: str) -> list[float] | None:
        if self.embedder is None:
            return None
        if text not in self._queries:
            try:
                self._queries[text] = self.embedder([text])[0]
            except Exception:  # noqa: BLE001 - a failed embedding call means keyword-only, never an error
                return None
        return self._queries[text]

    def search(self, args: dict, store, kb) -> list[dict]:
        a = v5.V5SearchArgs.model_validate(args)
        if not (a.text and a.text.strip()):
            return v5.v5_search_emails(args, store, kb)
        idx = self.index(store, kb)
        latest = v5._latest_proposals(store)  # noqa: SLF001

        def passes(eid: str) -> bool:
            p = latest.get(eid)
            if a.vessel and not (p and p.vessel.vessel_code.upper() == a.vessel.upper()):
                return False
            if a.event_type and not (p and p.event.event_type == a.event_type):
                return False
            return not (a.status and not (p and a.status in p.statuses))

        allowed = {eid for eid in idx.email_ids if passes(eid)}
        out = []
        qvec = self._query_vector(a.text) if idx.vec else None  # no vectors in the index: no embedding call
        for h in idx.search(a.text, qvec, allowed, min(a.limit, v5.SEARCH_LIMIT_CAP), retrieval.SEM_WEIGHT):
            email = store.get_email(h.email_id)
            view = e_nodes.chat_email_view(email, kb) if email else None
            if view is None:
                continue
            p = latest.get(h.email_id)
            out.append({
                "email_id": h.email_id, "subject": email.subject,
                "sent_time": email.sent_time.isoformat() if email.sent_time else None, "sender": view.sender,
                "vessel": p.vessel.vessel_code if p else None, "event_type": p.event.event_type if p else None,
                "excerpt": " ".join(email.new_text.split())[:300], "match": h.snippet,
            })  # fmt: skip
        return out


def run_tool_v7(name: str, args: dict, store, kb, backend: RetrievalBackend) -> dict | list[dict] | None:
    if name == "get_email":
        return v5.v5_get_email(args["email_id"], store, kb)
    if name == "search_emails":
        return backend.search(args, store, kb)
    raise ValueError(f"unknown tool {name!r}")


# --- M3: vessel facts with report fields extracted in code -----------------------------------------

E16_PRESENT_FACTS_SYSTEM_V7 = v5.E16_PRESENT_FACTS_SYSTEM_V51 + """

REPORT DIGESTS
context.report_digests are rows read by code out of the vessel's latest noon, arrival, departure and daily reports: date, kind, email id, speed, consumption, wind, sea, sky, current, draft. Use them for draft, weather, sea state, current, speed and consumption. For a draft that is not in current_facts, use the newest digest that has one and say its date and kind in the label, for example "吃水（7/24 午报）". Copy values exactly."""

_FIELD_LABEL = {"speed": ("航速", "speed"), "consumption": ("油耗", "consumption"), "weather": ("天气/海况", "weather and sea state"),
                "draft": ("吃水", "draft")}  # fmt: skip


def _report_digests(views: list, run_tool: Callable | None) -> tuple[list[rd.ReportDigest], dict[str, str]]:
    digests: list[rd.ReportDigest] = []
    texts: dict[str, str] = {}
    if run_tool is None:
        return digests, texts
    for v in views:
        ids = [t.email_id for t in reversed(v.timeline) if "report" in t.event_type.lower()][:25]
        for eid in dict.fromkeys(ids):
            got = (v5._as_dicts(run_tool("get_email", {"email_id": eid})) or [None])[0]  # noqa: SLF001
            if got:
                texts[eid] = str(got.get("text") or "")
                digests.append(rd.digest_email(eid, str(got.get("subject") or ""), str(got.get("sent_time") or ""), texts[eid]))
    return digests, texts


def _vessel_facts(request: ChatRequest, context: ChatContext, llm: LlmClient, key: str, today: str, zh: bool,
                  run_tool: Callable | None) -> ChatAnswer:  # fmt: skip
    """v5.1's vessel-facts answer plus design 7.5: weather, sea state, current, speed, consumption
    and draft come out of the reports in code. A question that asks only for those is answered in
    code; one that also asks for ETA, ROB or cargo goes to the model with the digests."""
    vessels = v5._question_vessels(request.question)  # noqa: SLF001
    views = [v for v in context.vessels if v.vessel_code.upper() in vessels]
    base = {"llm_status": "ok", "execution_mode": "deterministic", "capability_authority": "supported_l1"}
    if not views:
        return ChatAnswer(text="当前记录里没有找到指定的船。请确认船名。" if zh else "I could not find the named vessel.",
                          evidence_status="no_matching_data", retrieval_outcome="no_data",
                          reasoning_trace=["Deterministic lookup: vessel_facts — no matching record"], **base)  # fmt: skip
    wanted = rd.wanted_fields(request.question)
    digests, texts = _report_digests(views, run_tool)
    if wanted and not rd.needs_base_facts(request.question):
        return _render_reports(request.question, vessels, digests, wanted, zh, base)

    source_text: dict[str, str] = dict(texts)
    slice_: dict[str, list] = {"vessels": [], "report_digests": []}
    for v in views:
        facts = sorted((f for f in v.facts if not f.superseded), key=lambda f: f.event_time, reverse=True)
        seen_kinds: set[str] = set()
        rows = []
        for f in facts:
            kind = f.fact_key.split(":")[0]
            rows.append({"fact": f.fact_key, "value": f.value, "time": f.event_time.isoformat(), "email_id": f.source_email_id,
                         "latest_of_kind": kind not in seen_kinds})  # fmt: skip
            seen_kinds.add(kind)
            source_text[f.source_email_id] = source_text.get(f.source_email_id, "") + " " + f.value
        slice_["vessels"].append({"vessel": v.vessel_code, "current_facts": rows})
    picked = rd.select(digests, wanted) if wanted else []
    slice_["report_digests"] = [{k: val for k, val in asdict(d).items() if val and k != "fields"} for d in picked]
    user = json.dumps({"question": request.question, "context": slice_, "today": today},
                      ensure_ascii=False, separators=(",", ":"), default=str)  # fmt: skip
    raw = llm.complete_json("E16_V7_PRESENT", key, E16_PRESENT_FACTS_SYSTEM_V7, user)
    trace = [f"Deterministic lookup: vessel_facts + {len(picked)} report digest(s) extracted in code"]
    lines, sources, dropped = [], [], 0
    for it in raw.get("items") or []:
        if not isinstance(it, dict):
            continue
        label, value, src = (str(it.get(k) or "").strip() for k in ("label", "value", "source"))
        if not value or src not in source_text or not v5._numbers(value) <= v5._numbers(source_text[src]):  # noqa: SLF001
            dropped += 1
            continue
        time = str(it.get("time") or "").strip()
        lines.append((f"- {label}：{value}" + (f"（{time}）" if time else "") + f" [{src}]") if zh
                     else (f"- {label}: {value}" + (f" ({time})" if time else "") + f" [{src}]"))
        if all(x.id != src for x in sources):
            sources.append(SourceRef(kind="email", id=src, label=src))
    if dropped:
        trace.append(f"Value check (code): dropped {dropped} item(s) whose numbers are not in the cited source")
    missing = v5._strs(raw.get("missing"))  # noqa: SLF001
    if not lines:
        lines = [f"- {r['fact']}: {r['value']} ({r['time'][:16].replace('T', ' ')}) [{r['email_id']}]"
                 for v in slice_["vessels"] for r in v["current_facts"] if r["latest_of_kind"]]  # fmt: skip
        trace.append("No verifiable items from the model; latest value of each fact listed by code")
    summary = str(raw.get("summary") or "").strip() or (f"{'、'.join(sorted(vessels))} 当前记录：" if zh else "Current records:")
    text = summary + "\n" + "\n".join(lines)
    if missing:
        text += "\n" + "\n".join(f"- {m}：当前记录中没有找到" if zh else f"- {m}: not found in the current records" for m in missing)
    return ChatAnswer(text=text, sources=sources[:6], evidence_status="partial" if missing else "sufficient",
                      reasoning_trace=trace, **base)  # fmt: skip


def _render_reports(question: str, vessels: set[str], digests: list[rd.ReportDigest], wanted: set[str], zh: bool,
                    base: dict) -> ChatAnswer:  # fmt: skip
    picked = rd.select(digests, wanted)
    rows = [rd.render_row(d, wanted, zh) for d in picked]
    missing = rd.missing_fields(picked, wanted)
    gaps = [_FIELD_LABEL[f][0 if zh else 1] for f in missing]
    if re.search(r"流|current", question, re.I) and not rd.has_current(picked) and "weather" not in missing:
        gaps.append("海流" if zh else "current")
    who = "、".join(sorted(vessels))
    if not rows:
        text = f"当前记录里没有找到 {who} 的相关船报数据。" if zh else f"No report data for {who} in the current records."
        status = "no_matching_data"
    else:
        head = f"{who} 最近的船报数据（从船长报告原文提取）：" if zh else f"{who} - from the master's latest reports:"
        text = "\n".join([head, *rows, *[(f"- {g}：当前记录中没有找到" if zh else f"- {g}: not found in the records") for g in gaps]])
        status = "partial" if gaps else "sufficient"
    sources = [SourceRef(kind="email", id=d.email_id, label=d.email_id) for d in picked][:6]
    return ChatAnswer(text=text, sources=sources, evidence_status=status,
                      retrieval_outcome="no_data" if not rows else None,
                      reasoning_trace=[f"Vessel reports: {len(picked)} row(s) extracted in code, no model call"], **base)  # fmt: skip


# --- orchestration -------------------------------------------------------------------------------


# --- dues, rendered in code ---------------------------------------------------------------------------
# [AMENDMENT 2026-10-01, design 7.1 section 12] The model that worded the due list answered an English question in Chinese and
# left the rows out of the text. Rows are chosen and written in code, in the language of the question.

_HORIZON = re.compile(r"(\d{1,3})\s*(?:days?|天|日)", re.I)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _short(text: str, limit: int = 110) -> str:
    """The first sentence, cut at a clause boundary, never with an ellipsis; a sentence that is too long is dropped to its label."""
    first = re.split(r"(?<=[.;])\s", text.strip())[0].rstrip(".;")
    if len(first) <= limit:
        return first
    clause = re.split(r"[,;]", first)[0].strip()
    return clause if len(clause) <= limit else ""


def _when(d, zh: bool) -> str:
    return f"{d.due_date.month}/{d.due_date.day}" if zh else f"{d.due_date.day} {_MONTHS[d.due_date.month - 1]}"


def _kind(d) -> str:
    return d.due_other if d.due_type == "Others" and d.due_other else str(d.due_type)


def _due_lines(rows, zh: bool) -> list[str]:
    """One line per (date, kind): several vessels due on the same day for the same thing are one line (a summary, not a list of sentences)."""
    groups: dict[tuple, list] = {}
    for d in rows:
        groups.setdefault((d.due_date, _kind(d)), []).append(d)
    lines = []
    for (_, kind), items in groups.items():
        if len(items) > 1:
            who = ", ".join(sorted({d.vessel for d in items}))
            lines.append(f"{_when(items[0], zh)} · {kind}：{who}" if zh else f"{_when(items[0], zh)} · {kind}: {who}")
        else:
            d = items[0]
            note = _short(d.action, 90)
            lines.append(f"{_when(d, zh)} · {d.vessel} · {kind}" + (f"：{note}" if zh and note else f": {note}" if note else ""))
    return lines


def dues_rendered(question: str, context: ChatContext, zh: bool, today: str) -> ChatAnswer | None:
    """Upcoming dues within the asked horizon (default 7 days), then a note on the overdue ones; None when there is nothing to
    render in code (an empty list is handled by v5)."""
    if context.dues.store_status != "ok":
        return None
    vessels = v5._question_vessels(question)  # noqa: SLF001
    rows = sorted((d for d in context.dues.items if not vessels or d.vessel.upper() in vessels), key=lambda d: (d.due_date, d.vessel))
    if not rows:
        return None
    m = _HORIZON.search(question)
    horizon = int(m.group(1)) if m else 7
    day = date.fromisoformat(today[:10])
    upcoming = [d for d in rows if day <= d.due_date <= day + timedelta(days=horizon)]
    overdue = [d for d in rows if d.due_date < day]
    lines = _due_lines(upcoming, zh)
    late_who = [f"{d.vessel} {_when(d, zh)}" for d in overdue[:8]]
    late_more = len(overdue) - len(late_who)
    if zh:
        head = f"未来 {horizon} 天内到期共 {len(upcoming)} 项" + (f"，另有 {len(overdue)} 项已逾期" if overdue else "") + ("：" if upcoming else "。")
        late = ("\n已逾期：" + "；".join(late_who) + (f" 等 {late_more} 项" if late_more > 0 else "")) if overdue else ""
    else:
        head = f"Dues in the next {horizon} days: {len(upcoming)}" + (f", plus {len(overdue)} overdue" if overdue else "") + (":" if upcoming else ".")
        late = ("\nOverdue: " + "; ".join(late_who) + (f" and {late_more} more" if late_more > 0 else "")) if overdue else ""
    shown = upcoming
    text = head + ("\n" + "\n".join(f"- {x}" for x in lines) if lines else "") + late
    sources = [SourceRef(kind="task", id=d.task_id, label=f"{_kind(d)} · {d.vessel}") for d in (shown or overdue)[:6]]
    return ChatAnswer(text=text, sources=sources, llm_status="ok", execution_mode="deterministic", capability_authority="supported_l1",
                      evidence_status="sufficient", reasoning_trace=[f"Deterministic filter: dues, {len(upcoming)} upcoming and {len(overdue)} overdue rows written in code, no model call"])  # fmt: skip


def e16v7_answer_chat(
    request: ChatRequest, context: ChatContext, llm: LlmClient, now,
    run_tool: Callable[[str, dict], Any] | None = None, event_types: list[str] | None = None,
    router_llm: LlmClient | None = None, fast_llm: LlmClient | None = None,
    playbooks: dict[str, pbk.Playbook] | None = None,
) -> ChatAnswer:
    """As v6: `llm` answers the reasoning questions and rewrites follow-ups; `fast_llm` routes,
    words deterministic answers and runs the verifier. Every answer leaves through the output scan."""
    fast = fast_llm or router_llm or llm
    failed = ChatAnswer(text=E16V7_FAILED, llm_status="failed")
    try:
        if e_nodes._count_findings(e_nodes._scan_text(request.question)):  # noqa: SLF001
            return failed
    except Exception:  # noqa: BLE001 - a broken scan fails closed
        return failed

    key = v6._chat_key(request)  # noqa: SLF001
    history = [t.model_dump() for t in request.history]
    zh = bool(v5._CJK.search(request.question))  # noqa: SLF001
    available = pbk.usable(playbooks or {})

    ref = distances.find(request.question)  # [AMENDMENT 2026-10-01, design 7.1 section 11] a tabled port pair at a stated speed: code, no model
    if ref is not None:
        text, basis = distances.render(ref[0], ref[1], zh)
        return _finalize(ChatAnswer(
            text=text, details=basis, llm_status="ok", execution_mode="deterministic", capability_authority="supported_l1", evidence_status="sufficient",
            reasoning_trace=[f"Reference distance (code): {ref[0].port_a}-{ref[0].port_b} {ref[0].nm:,.0f} nm from kb/distances.csv; passage time computed in code, no model call"]))  # fmt: skip

    try:
        route, vote_note = _route(fast, key, request.question, history, build_router_system(pbk.router_menu(available)), set(available))
    except LlmError:
        return failed
    mode = route["execution_mode"]
    intent = route.get("deterministic_intent")
    size = route["answer_size"]
    standalone = route["standalone_question"].strip() or request.question
    terms = [t.strip() for t in route["search_terms"] if t.strip()]
    playbook = available.get(route.get("playbook") or "")
    pre_trace = [vote_note]
    if mode == "deterministic" and intent == "dues" and v6._PAYMENT_STATUS.search(standalone):  # noqa: SLF001
        mode = "evidence_reasoning"
        pre_trace.append("Router guard (code): a payment-status question needs the emails, not the due list")
    if mode == "deterministic" and intent == "open_tasks" and not _TASK_WORDS.search(standalone):
        mode, intent = "domain_knowledge", None
        pre_trace.append("Router guard (code): no task wording — open_tasks overridden")
    if (mode not in ("deterministic", "follow_up") and not route.get("playbook") and rd.wanted_fields(standalone)
            and v5._question_vessels(standalone) and not _ANALYSIS_WORDS.search(standalone)):  # noqa: SLF001
        mode, intent = "deterministic", "vessel_facts"
        pre_trace.append("Router guard (code): a report-field question about a named vessel — answered from the reports")
    if mode == "out_of_scope" and v5._router_guard(standalone):  # noqa: SLF001
        mode = "evidence_reasoning"
        pre_trace.append("Router guard (code): question has shipping terms — out_of_scope overridden")
    if mode == "out_of_scope":
        return _finalize(ChatAnswer(
            text=route["reason"].strip() or "I can only help with shipping operations questions.", llm_status="ok",
            execution_mode="out_of_scope", capability_authority="out_of_scope", retrieval_outcome="out_of_scope",
            reasoning_trace=pre_trace))  # fmt: skip
    if playbook and mode == "follow_up":
        playbook = None
    if playbook:
        pre_trace.append(f"Playbook selected: {playbook.id}" + (" (draft)" if playbook.status == "draft" else ""))
        if mode != playbook.mode:  # the router cannot be trusted with the mode of a procedure: the playbook sets it
            pre_trace.append(f"Playbook mode (code): {mode} -> {playbook.mode}")
            mode = playbook.mode

    today = now.date().isoformat() if hasattr(now, "date") else str(now)
    asked = request.model_copy(update={"question": standalone})
    if standalone != request.question:
        pre_trace.append(f"Standalone question: {standalone}")

    try:
        if mode == "follow_up":
            answer = v6._follow_up(request, context, llm, key, zh)  # noqa: SLF001
            return _finalize(answer.model_copy(update={"reasoning_trace": pre_trace + answer.reasoning_trace}))
        if mode == "deterministic":
            if intent == "vessel_facts":
                answer = _vessel_facts(asked, context, fast, key, today, zh, run_tool)
            elif intent == "dues" and (answer := dues_rendered(asked.question, context, zh, today)) is not None:
                pass
            else:
                answer = v5._deterministic(intent, asked, context, fast, key, today, zh, run_tool)  # noqa: SLF001
            if answer is None:
                return failed
            return _finalize(answer.model_copy(update={"reasoning_trace": pre_trace + answer.reasoning_trace}))
        return _finalize(_reason(asked, request, context, llm, key, zh, mode, size, terms, today, run_tool,
                                 event_types, pre_trace, playbook, fast))  # fmt: skip
    except (LlmError, ValidationError, AttributeError, TypeError):
        return failed
