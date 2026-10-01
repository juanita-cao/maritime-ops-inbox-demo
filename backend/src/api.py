"""FastAPI routes of design_frontend.md Artifact 5 (T2.21). Each request opens its own store
connection (SQLite connections stay in one thread). The clock is DEMO_NOW when set (the sample
data ends on 30 Jul 2026), else the real time; nodes get it as an argument."""

import base64
import csv
import json
import os
import secrets
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src import e16_v2, e16_v3, e16_v4, e16_v5, e16_v6, e16_v7, e_apply, e_nodes, pipeline, read_path, retrieval
from src import playbooks as pbk
from src import schemas as s
from src.kb_loader import load_kb
from src.llm_client import LiveLlm, make_client
from src.settings import DATASET, DATASET_ROOT, REPO_ROOT, load_settings
from src.store import NotFound, Store

settings = load_settings()
# An invalid knowledge base stops the service here, at startup (T1.3).
kb = load_kb(DATASET_ROOT / "kb")
app = FastAPI(title="Maritime Operations Inbox")
# [AMENDMENT 2026-10-01, design_agent_e16_v7.md 7] An invalid playbook stops the service here, like the knowledge base.
PLAYBOOKS = pbk.load_playbooks(REPO_ROOT / "kb" / "playbooks")  # method assets, shared by both datasets


def _make_embedder():
    """Query embeddings for hybrid retrieval: only with a live chat on an OpenAI endpoint; otherwise
    search falls back to keywords (design_agent_e16_v7.md 5.2)."""
    key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if settings.chat_llm_mode != "live" or not key or "api.openai.com" not in settings.llm_base_url:
        return None
    return retrieval.openai_embedder(key, settings.llm_base_url)


RETRIEVAL = e16_v7.RetrievalBackend(DATASET_ROOT / "data" / "index", _make_embedder())


class State:
    """What the routes use; tests replace these."""

    db_path = settings.database_path
    llm = make_client(settings)
    # [AMENDMENT 2026-09-26 T2.22] the chat may run live while the pipeline replays recordings
    chat_llm = make_client(settings.model_copy(update={"llm_mode": settings.chat_llm_mode}))
    v51_llm = (
        make_client(settings.model_copy(update={"llm_mode": settings.chat_llm_mode,
                                                "llm_model": os.environ["E16_V51_LLM_MODEL"]}))  # fmt: skip
        if os.getenv("E16_V51_LLM_MODEL") else chat_llm
    )
    demo_now = settings.demo_now


state = State()


def now() -> datetime:
    return state.demo_now or datetime.now(timezone.utc)


def get_store() -> Iterator[Store]:
    store = Store.open(state.db_path)
    try:
        yield store
    finally:
        store.close()


# --- view models of the API (design_frontend.md Artifact 5) --------------------------


class InboxRow(BaseModel):
    email_id: str
    proposal_id: str | None
    subject: str
    sent_time: datetime | None
    sender: str
    sender_role: str  # E3 at read time: Charterer, Master, Port Agent ... or "Other"
    sender_party: str | None
    direction: str
    vessel: str | None
    voyage: str | None
    event_type: str | None
    statuses: list[str] | None
    priority: int | None
    review_status: str  # To review, Reviewed, Not matched, Held
    held_reason: str | None
    is_report: bool


class EmailDetail(BaseModel):
    email: s.ParsedEmail
    roles: s.PartyRoles
    proposal: s.Proposal | None
    proposal_status: str | None
    held: dict | None
    superseded: list[str]


class DecisionResponse(BaseModel):
    result: s.ApplyResult
    proposal: s.Proposal | None = None  # refreshed after a conflict


class VesselRow(BaseModel):
    vessel_code: str
    voyages: list[str]
    current_voyage: str | None
    counts: dict[str, int]
    high_priority: int
    # [AMENDMENT 2026-09-26 UI round U5] the voyage records of the kb, for the Vessel page strip
    voyage_details: list[dict[str, str]] = []


@app.get("/api/health")
def health() -> dict:
    """Liveness check; also shows the LLM mode so a live run is never started by surprise."""
    return {"status": "ok", "llm_mode": settings.llm_mode, "chat_llm_mode": settings.chat_llm_mode,
            "now": now().isoformat(), "dataset": DATASET}


@app.get("/api/taxonomy")
def taxonomy() -> dict[str, list[str]]:
    return kb.taxonomy


_LATEST_STATUSES = ("open", "applied", "rejected", "held_blocked", "held_store_unavailable")


def _latest(store: Store, email_id: str) -> dict | None:
    rows = [r for r in store.proposal_rows(_LATEST_STATUSES) if r["email_id"] == email_id]
    return rows[-1] if rows else None


def _inbox_row(email: s.ParsedEmail, latest: dict | None) -> InboxRow:
    p = latest["proposal"] if latest else None
    status = latest["status"] if latest else None
    sender = e_nodes.e3_resolve_sender(email, kb).sender
    if status and status.startswith("held"):
        review = "Held"
    elif p and p.vessel.status != "matched":
        review = "Not matched"
    elif status == "open":
        review = "To review"
    else:
        review = "Reviewed"
    return InboxRow(
        email_id=email.email_id, proposal_id=latest["proposal_id"] if latest else None, subject=email.subject,
        sent_time=email.sent_time, sender=email.sender, sender_role=sender.role, sender_party=sender.party_code,
        direction=email.direction,
        vessel=p.vessel.vessel_code if p else None, voyage=p.voyage.voyage_no if p else None,
        event_type=p.event.event_type if p else None, statuses=p.statuses if p else None,
        priority=p.priority if p else None, review_status=review,
        held_reason=(latest["held"] or {}).get("reason") if latest and latest["held"] else None,
        is_report=bool(p and p.event.is_report),
    )  # fmt: skip


@app.get("/api/emails")
def list_emails(store: Store = Depends(get_store)) -> list[InboxRow]:
    # [AMENDMENT 2026-10-01] the proposals are read once, not once per email: 168 emails took 9 s on the small
    # Render instance because each email re-read and re-parsed every proposal
    latest = {r["email_id"]: r for r in store.proposal_rows(_LATEST_STATUSES)}  # the last row of an email wins
    rows = []
    for email_id in store.email_ids():
        email = store.get_email(email_id)
        rows.append(_inbox_row(email, latest.get(email_id)))
    return sorted(
        rows, key=lambda r: (r.sent_time or datetime.min.replace(tzinfo=timezone.utc)), reverse=True
    )


@app.get("/api/emails/{email_id}")
def email_detail(email_id: str, store: Store = Depends(get_store)) -> EmailDetail:
    email = store.get_email(email_id)
    if email is None:
        raise HTTPException(404, f"email {email_id}")
    latest = _latest(store, email_id)
    stale = [r["proposal_id"] for r in store.proposal_rows(("stale",)) if r["email_id"] == email_id]
    return EmailDetail(email=email, roles=e_nodes.e3_resolve_sender(email, kb), proposal=latest["proposal"] if latest else None,
                       proposal_status=latest["status"] if latest else None,
                       held=latest["held"] if latest else None, superseded=stale)  # fmt: skip


@app.post("/api/emails")
def post_email(raw: s.RawEmail, store: Store = Depends(get_store)) -> pipeline.PipelineResult:
    return pipeline.run_email(raw, store, kb, state.llm, now(), settings.default_utc_offset)


@app.post("/api/demo/replay/next")
def replay_next(store: Store = Depends(get_store)) -> pipeline.PipelineResult:
    """The next library email (time order) that is not in the store yet; test emails never."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from check_threads_library import corpus_blocks  # noqa: PLC0415 - demo only

    from src import e_nodes  # noqa: PLC0415
    from src.kb_loader import own_domains  # noqa: PLC0415

    with (DATASET_ROOT / "eval/email_index.csv").open(encoding="utf-8") as f:
        where = {r["email_id"]: (r["document"], int(r["position"])) for r in csv.DictReader(f)}
    with (DATASET_ROOT / "eval/split_proposal.csv").open(encoding="utf-8-sig") as f:
        library = [r["email_id"] for r in csv.DictReader(f) if r["proposed_split"] == "library"]
    seen = set(store.email_ids())
    blocks = corpus_blocks()
    raws = [
        s.RawEmail(email_id=x, text="\n".join(blocks[where[x]])) for x in library if x not in seen
    ]
    if not raws:
        raise HTTPException(404, "no more sample emails")
    parsed = [
        (e_nodes.e1_parse_email(r, own_domains(kb), settings.default_utc_offset), r) for r in raws
    ]
    first = min(parsed, key=lambda pr: (pr[0].sent_time, pr[1].email_id))
    return pipeline.run_email(
        first[1], store, kb, state.llm, first[0].sent_time or now(), settings.default_utc_offset
    )


@app.post("/api/proposals/{proposal_id}/decision")
def decide(
    proposal_id: str, decision: s.Decision, store: Store = Depends(get_store)
) -> DecisionResponse:
    try:
        result = e_apply.e11_apply_changes(proposal_id, decision, store)
    except NotFound:
        raise HTTPException(404, f"proposal {proposal_id}") from None
    except e_apply.InvalidDecision as exc:
        raise HTTPException(422, str(exc)) from None
    refreshed = store.get_proposal(proposal_id) if result.status == "conflict" else None
    return DecisionResponse(result=result, proposal=refreshed)


@app.post("/api/proposals/{proposal_id}/rerun")
def rerun(
    proposal_id: str, overrides: s.Overrides, store: Store = Depends(get_store)
) -> pipeline.PipelineResult:
    old = store.get_proposal(proposal_id, missing_ok=True)
    if old is None:
        raise HTTPException(404, f"proposal {proposal_id}")
    return pipeline.rerun_with_overrides(old.email_id, overrides, store, kb, state.llm, now())


@app.post("/api/undo/{token}")
def undo(token: str, store: Store = Depends(get_store)) -> s.ApplyResult:
    try:
        return e_apply.e11_undo(token, store, "officer", now())
    except NotFound:
        raise HTTPException(404, "unknown undo token") from None


@app.get("/api/review-queue")
def review_queue(store: Store = Depends(get_store)) -> s.ReviewQueue:
    return read_path.e14_list_review_queue(
        store.proposal_rows(("open", "held_blocked", "held_store_unavailable"))
    )


@app.get("/api/tasks")
def tasks(vessel: str | None = Query(None), store: Store = Depends(get_store)) -> s.RankedTaskList:
    return read_path.d7_rank_open_tasks(store.all_tasks("open", vessel), now())


@app.post("/api/tasks/{task_id}/change")
def change_task(
    task_id: str, change: s.ManualTaskChange, store: Store = Depends(get_store)
) -> s.ApplyResult:
    if change.task_id != task_id:
        raise HTTPException(422, "task id in the path and the body differ")
    return e_apply.e11_apply_manual(change, store, now())


@app.get("/api/vessels")
def vessels(store: Store = Depends(get_store)) -> list[VesselRow]:
    rows = []
    open_tasks = store.all_tasks("open")
    applied = store.proposal_rows(("applied",))
    for code, vessel in kb.vessels.items():
        ranked = read_path.d7_rank_open_tasks(
            [t for t in open_tasks if t.vessel_code == code], now()
        )
        counts = {g.name: len(g.items) for g in ranked.groups}
        counts["FYI - No Action"] = sum(1 for r in applied if r["proposal"] and r["proposal"].vessel.vessel_code == code
                                        and r["proposal"].statuses == ["FYI - No Action"])  # fmt: skip
        mine = [t for t in open_tasks if t.vessel_code == code]
        current = next((v for v in reversed(vessel.voyages) if (code, v) in kb.voyages
                        and kb.voyages[(code, v)].status in ("in progress", "started")), None)  # fmt: skip
        details = [kb.voyages[(code, v)].model_dump(include={"voyage_no", "status", "route", "start", "end", "facts"})
                   for v in vessel.voyages if (code, v) in kb.voyages]  # fmt: skip
        rows.append(VesselRow(vessel_code=code, voyages=vessel.voyages, current_voyage=current, counts=counts,
                              high_priority=sum(1 for t in mine for a in t.actions if a.priority >= 4),
                              voyage_details=details))  # fmt: skip
    return rows


@app.get("/api/vessels/{code}")
def vessel_view(code: str, store: Store = Depends(get_store)) -> s.VesselView:
    if code not in kb.vessels:
        raise HTTPException(404, f"vessel {code}")
    return read_path.e13_build_vessel_view(code, store.fact_history(code), store.all_tasks("open", code),
                                           store.proposal_rows(("applied",)), now())  # fmt: skip


@app.get("/api/dues")
def dues(vessel: str | None = Query(None), store: Store = Depends(get_store)) -> s.DueList:
    return read_path.e15_list_dues(store.all_tasks("open", vessel), now())


# --- chat (E16, T2.22) ------------------------------------------------------------------------


def _chat_email(email: s.ParsedEmail) -> s.ChatEmail | None:
    """A short view of a stored email; never one that fails the E4 check. [AMENDMENT
    2026-09-28, read-only tools] the check itself now lives in e_nodes.chat_email_view, shared
    with E17/E18, so this context's emails and a tool result always agree."""
    return e_nodes.chat_email_view(email, kb)


def _run_chat_tool(name: str, args: dict, store: Store) -> s.ChatEmail | list[s.ChatEmail] | None:
    """[AMENDMENT 2026-09-28, read-only tools] the tool-executor E16 is given: it only knows
    the two approved, white-box lookups (E17, E18); e16_answer_chat decides *whether* and *how
    many times* to call it, never what it does."""
    if name == "get_email":
        return e_nodes.e17_get_email(args["email_id"], store, kb)
    if name == "search_emails":
        return e_nodes.e18_search_emails(
            args.get("vessel"), args.get("event_type"), args.get("status"), args.get("limit", 10), store, kb
        )
    raise ValueError(f"unknown tool {name!r}")


def build_chat_context(store: Store, at: datetime) -> s.ChatContext:
    """ChatContext of the E16 row: D7 tasks, E15 dues, E13 vessel views, E14 queue, and the
    emails they refer to (plus the latest ones), from the read path only."""
    open_tasks = store.all_tasks("open")
    applied = store.proposal_rows(("applied",))
    queue = read_path.e14_list_review_queue(
        store.proposal_rows(("open", "held_blocked", "held_store_unavailable"))
    )
    views = [read_path.e13_build_vessel_view(code, store.fact_history(code), open_tasks, applied, at)
             for code in kb.vessels]  # fmt: skip
    wanted = [i.email_id for i in queue.items] + [e for t in open_tasks for e in t.source_email_ids[-1:]]
    latest = sorted(
        (e for e in (store.get_email(x) for x in store.email_ids()) if e),
        key=lambda e: e.sent_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True,
    )  # fmt: skip
    wanted += [e.email_id for e in latest[:12]]
    emails, seen = [], set()
    for email_id in wanted:
        if email_id in seen or len(emails) >= 40:
            continue
        seen.add(email_id)
        email = store.get_email(email_id)
        view = _chat_email(email) if email else None
        if view:
            emails.append(view)
    return s.ChatContext(tasks=read_path.d7_rank_open_tasks(open_tasks, at),
                         dues=read_path.e15_list_dues(open_tasks, at), vessels=views,
                         review_queue=queue, emails=emails)  # fmt: skip


@app.post("/api/chat")
def chat(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    at = now()

    def run_tool(name: str, args: dict) -> s.ChatEmail | list[s.ChatEmail] | None:
        return _run_chat_tool(name, args, store)

    return e_nodes.e16_answer_chat(request, build_chat_context(store, at), state.chat_llm, at, run_tool)


@app.post("/api/chat/v2")
def chat_v2(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v2 (docs/design_agent_e16_v2.md): a separate route, not a replacement for /api/chat
    — the A/B experiment requires E16_legacy (above) to keep running untouched while v2 is
    evaluated side by side."""
    at = now()

    def run_tool(name: str, args: dict) -> s.ChatEmail | list[s.ChatEmail] | None:
        return _run_chat_tool(name, args, store)

    return e16_v2.e16v2_answer_chat(request, build_chat_context(store, at), state.chat_llm, at, run_tool)


@app.post("/api/chat/v3")
def chat_v3(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v3 (docs/design_agent_e16_v3.md, owner-authored): a third route — E16_legacy and
    E16 v2 both stay frozen and running for the three-way comparison."""
    at = now()

    def run_tool(name: str, args: dict) -> s.ChatEmail | list[s.ChatEmail] | None:
        return _run_chat_tool(name, args, store)

    return e16_v3.e16v3_answer_chat(request, build_chat_context(store, at), state.chat_llm, at, run_tool)


@app.post("/api/chat/v4")
def chat_v4(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v4 (docs/design_agent_e16_v4.md, owner-authored): a fourth route — E16_legacy,
    E16 v2 and E16 v3 all stay frozen and running for the four-way comparison."""
    at = now()

    def run_tool(name: str, args: dict) -> s.ChatEmail | list[s.ChatEmail] | None:
        return _run_chat_tool(name, args, store)

    return e16_v4.e16v4_answer_chat(request, build_chat_context(store, at), state.chat_llm, at, run_tool)


@app.post("/api/chat/v5")
def chat_v5(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v5 (docs/design_agent_e16_v5.md, owner-authored): a fifth route — E16_legacy and
    v2/v3/v4 all stay frozen and running for the five-way comparison. v5 has its own read tools
    (full email text + quoted thread, keyword search); v1-v4's E17/E18 are unchanged."""
    at = now()

    def run_tool(name: str, args: dict) -> dict | list[dict] | None:
        return e16_v5.run_tool_v5(name, args, store, kb)

    return e16_v5.e16v5_answer_chat(request, build_chat_context(store, at), state.chat_llm, at, run_tool,
                                    kb.taxonomy.get("event_types", []))  # fmt: skip


# [AMENDMENT v5.1 model picker] the only models the chat page may choose. A fixed allow-list, so a
# request cannot name an arbitrary (possibly very expensive) model.
# The options of the chat page's Model picker. Each one fixes the model of the simple steps (routing,
# wording a code-selected answer, checking claims) and of the reasoning step.
CHAT_MODELS = [
    {"id": "hybrid", "label": "Hybrid: 4o-mini + GPT-5.5", "short": "Hybrid",
     "note": "GPT-4o mini routes, words simple answers and checks claims; GPT-5.5 reasons through the harder questions",
     "fast": "gpt-4o-mini", "reasoning": "gpt-5.5"},  # fmt: skip
    {"id": "gpt-4o-mini", "label": "GPT-4o mini only", "short": "GPT-4o mini",
     "note": "every step on GPT-4o mini: fastest and cheapest", "fast": "gpt-4o-mini", "reasoning": "gpt-4o-mini"},  # fmt: skip
    {"id": "gpt-5.5", "label": "GPT-5.5 only", "short": "GPT-5.5",
     "note": "every step on GPT-5.5: slowest and costliest", "fast": "gpt-5.5", "reasoning": "gpt-5.5"},  # fmt: skip
]
DEFAULT_CHAT_OPTION = os.getenv("E16_CHAT_OPTION") or "hybrid"
REAL_MODELS = {m for o in CHAT_MODELS for m in (o["fast"], o["reasoning"])}  # the model ids the API may call
_chat_model_clients: dict[str, object] = {}


def v51_default_model() -> str:
    return os.getenv("E16_V51_LLM_MODEL") or settings.llm_model


def v51_client(model: str | None):
    """The default model uses state.v51_llm (tests replace it); another listed model gets its
    own cached client. A model not on CHAT_MODELS is a 422, never a silent fallback."""
    if model is None or model == v51_default_model():
        return state.v51_llm
    if model not in REAL_MODELS:
        raise HTTPException(422, f"model {model!r} is not offered")
    if model not in _chat_model_clients:
        _chat_model_clients[model] = make_client(
            settings.model_copy(update={"llm_mode": settings.chat_llm_mode, "llm_model": model}))
    return _chat_model_clients[model]


@app.get("/api/chat/models")
def chat_models() -> dict:
    return {"default": DEFAULT_CHAT_OPTION, "models": [{k: v for k, v in o.items() if k != "short"} for o in CHAT_MODELS]}


@app.post("/api/chat/v5.1")
def chat_v5_1(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v5.1 ([AMENDMENT v5.1] in docs/design_agent_e16_v5.md): the same v5 with two code
    fixes (router guard, verified vessel-facts rendering). /api/chat/v5 stays the frozen 5.0.
    The model is the request's `model` (from GET /api/chat/models), else E16_V51_LLM_MODEL,
    else the default chat model — a model experiment, not a new version."""
    at = now()
    llm = v51_client(request.model)

    def run_tool(name: str, args: dict) -> dict | list[dict] | None:
        return e16_v5.run_tool_v5(name, args, store, kb)

    answer = e16_v5.e16v5_answer_chat(request, build_chat_context(store, at), llm, at, run_tool,
                                      kb.taxonomy.get("event_types", []), revision="5.1")  # fmt: skip
    return answer.model_copy(update={"llm_model": request.model or v51_default_model()})


V6_FAST_MODEL = "gpt-4o-mini"
# "none": gpt-5.5 rejects any other reasoning_effort together with function tools on
# /v1/chat/completions (live probe 2026-10-01); benchmark: 20/23, avg 7.6 s with gpt-4o-mini as fast model.
V6_REASONING_EFFORT = os.getenv("E16_V6_REASONING_EFFORT", "none")
_v6_clients: dict[str, object] = {}


def v6_reasoning_client(model: str | None):
    """The model that answers v6's reasoning questions. A reasoning model (gpt-5.x) runs at
    E16_V6_REASONING_EFFORT (default none): default effort cost 10-60 s per answer."""
    model = model or v51_default_model()
    if model not in REAL_MODELS:
        raise HTTPException(422, f"model {model!r} is not offered")
    if settings.chat_llm_mode != "live" or not model.startswith("gpt-5"):
        return v51_client(model)
    if model not in _v6_clients:
        _v6_clients[model] = LiveLlm(settings.model_copy(update={"llm_mode": "live", "llm_model": model}),
                                     reasoning_effort=V6_REASONING_EFFORT)  # fmt: skip
    return _v6_clients[model]


@app.post("/api/chat/v6")
def chat_v6(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v6 (docs/design_agent_e16_v6.md): v5.1 plus answer shape, follow-ups, router voting
    and a grounding check. The picked model answers the reasoning questions; routing,
    deterministic wording and follow-up rewrites always run on V6_FAST_MODEL."""
    at = now()
    llm = v6_reasoning_client(request.model)
    fast = v51_client(V6_FAST_MODEL)

    def run_tool(name: str, args: dict) -> dict | list[dict] | None:
        return e16_v5.run_tool_v5(name, args, store, kb)

    answer = e16_v6.e16v6_answer_chat(request, build_chat_context(store, at), llm, at, run_tool,
                                      kb.taxonomy.get("event_types", []), fast_llm=fast)  # fmt: skip
    return answer.model_copy(update={"llm_model": request.model or v51_default_model()})


def chat_option(option_id: str | None) -> dict:
    """The picker option for a request; an id that is not offered is a 422, never a silent fallback."""
    wanted = option_id or DEFAULT_CHAT_OPTION
    for o in CHAT_MODELS:
        if o["id"] == wanted:
            return o
    raise HTTPException(422, f"model option {wanted!r} is not offered")


_REASONING_MODES = {"evidence_reasoning", "proposal_reasoning", "domain_knowledge", "hybrid", "follow_up"}


def model_use(option: dict, answer: s.ChatAnswer) -> tuple[dict[str, str], str | None]:
    """Which models this answer really used, and a line for the page. A deterministic or out-of-scope
    answer never reaches the reasoning model; say so instead of naming it."""
    if answer.llm_status == "failed":
        return {}, None
    fast, reasoning = option["fast"], option["reasoning"]
    used = {"fast": fast}
    if answer.execution_mode in _REASONING_MODES:
        used["reasoning"] = reasoning
    replay = "" if settings.chat_llm_mode == "live" else " (recorded replay, no live model)"
    if fast == reasoning:
        return used, f"{option['short']} only{replay}"
    if "reasoning" in used:
        return used, f"{option['short']} — {fast}: routing, wording, checks · {reasoning}: reasoning{replay}"
    return used, f"{option['short']} — {fast} only (no reasoning model needed for this answer){replay}"


@app.get("/api/chat/demo")
def chat_demo() -> dict:
    """The recorded demo conversation of the dataset (datasets/<name>/demo_chat.json, made by
    scripts/record_demo_chat.py): the chat page opens on it. Empty when the dataset has none."""
    path = DATASET_ROOT / "demo_chat.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"items": []}
    return {"items": [i for i in items if isinstance(i, dict) and "question" in i and "answer" in i]}


@app.post("/api/chat/v7")
def chat_v7(request: s.ChatRequest, store: Store = Depends(get_store)) -> s.ChatAnswer:
    """E16 v7 (docs/design_agent_e16_v7.md, approved 2026-10-01): v6 plus strict structured
    output, the evidence contract and the output scan. `request.model` is a picker option id."""
    at = now()
    option = chat_option(request.model)
    if settings.chat_llm_mode == "live":
        llm, fast = v6_reasoning_client(option["reasoning"]), v6_reasoning_client(option["fast"])
    else:
        llm = fast = state.v51_llm  # recorded mode (and the tests) has one client

    def run_tool(name: str, args: dict) -> dict | list[dict] | None:
        return e16_v7.run_tool_v7(name, args, store, kb, RETRIEVAL)

    answer = e16_v7.e16v7_answer_chat(request, build_chat_context(store, at), llm, at, run_tool,
                                      kb.taxonomy.get("event_types", []), fast_llm=fast, playbooks=PLAYBOOKS)  # fmt: skip
    models, note = model_use(option, answer)
    return answer.model_copy(update={"llm_model": option["id"], "models": models, "model_note": note})


# --- chat feedback (design_agent_e16_v7.md 8) ---------------------------------------------------

FEEDBACK_PATH = Path(os.getenv("FEEDBACK_PATH") or DATASET_ROOT / "data" / "feedback" / "feedback.jsonl")
_feedback_lock = threading.Lock()


class FeedbackAnswer(BaseModel):
    text: str = Field(max_length=8000)
    details: str | None = Field(default=None, max_length=8000)
    sources: list[str] = Field(default=[], max_length=12)
    trace: list[str] = Field(default=[], max_length=24)
    version: str | None = None
    model: str | None = None
    execution_mode: str | None = None
    playbook: str | None = None


class FeedbackIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[s.ChatTurn] = Field(default=[], max_length=6)
    answer: FeedbackAnswer
    thumbs: Literal["up", "down"]
    tag: Literal["too_long", "wrong", "missing", "not_useful"] | None = None
    comment: str | None = Field(default=None, max_length=500)


def _scrubbed(value):
    """Everything stored goes through the output scan first: free text can hold whatever a user typed."""
    if isinstance(value, str):
        return e16_v7.scrub(value)[0]
    if isinstance(value, list):
        return [_scrubbed(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrubbed(v) for k, v in value.items()}
    return value


@app.post("/api/chat/feedback")
def chat_feedback(item: FeedbackIn) -> dict:
    """One JSON line per thumb: appended to FEEDBACK_PATH (git-ignored) and written to stdout with the
    prefix FEEDBACK, because the demo database is rebuilt at every start and the disk is not kept.
    There is deliberately no read endpoint: the site has no password."""
    record = _scrubbed({"time": now().isoformat(), **item.model_dump(mode="json")})
    line = json.dumps(record, ensure_ascii=False)
    print("FEEDBACK " + line, flush=True)
    try:
        with _feedback_lock:
            FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
            with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass  # best effort: the stdout line above is the copy that survives
    return {"ok": True}


# --- deployment: one service for the API and the built frontend --------------------------

APP_PASSWORD = os.getenv("APP_PASSWORD", "")  # empty = no password (local use)


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """With APP_PASSWORD set, every page and API call needs it (browser login box, any user
    name), so a public link cannot spend the LLM key. /api/health stays open for the host."""
    if not APP_PASSWORD or request.url.path == "/api/health":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            given = base64.b64decode(header[6:]).decode("utf-8").partition(":")[2]
        except ValueError:
            given = ""
        if secrets.compare_digest(given.encode(), APP_PASSWORD.encode()):
            return await call_next(request)
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Marine Mind"'})


FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():  # built by the Dockerfile; locally the Vite dev server is used instead
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
