"""The run order of the DEP (design_backend.md section 13.1, paths P1 to P5): E1 to E10b, the held
paths, the automatic lane, officer overrides and re-runs with proposal lineage.

The orchestrator holds no rules of its own beyond the order: every decision is a node. It reads
the store only through the lookups the nodes declare (thread index, fact lookup, task lookup)."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from src import d_nodes as d
from src import e_apply
from src import e_nodes as e
from src import schemas as s
from src.kb_loader import KnowledgeBase, own_domains
from src.llm_client import LlmClient
from src.store import Store


class PipelineResult(BaseModel):
    email_id: str
    saved: s.SavedProposal
    proposal: s.Proposal | None = None
    held: s.HeldRecord | None = None
    applied: s.ApplyResult | None = None


def _held(
    email: s.ParsedEmail, reason: str, detail: str, thread_id: str | None, store: Store
) -> PipelineResult:
    held = s.HeldRecord(email_id=email.email_id, reason=reason, detail=detail)
    saved = e.e10b_save_proposal(held, email, thread_id, store)
    return PipelineResult(email_id=email.email_id, saved=saved, held=held)


def run_email(raw: s.RawEmail, store: Store, kb: KnowledgeBase, llm: LlmClient, now: datetime,
              default_offset) -> PipelineResult:  # fmt: skip
    """P1 to P4 for a new email."""
    parsed = e.e1_parse_email(raw, own_domains(kb), default_offset)
    return run_parsed(parsed, store, kb, llm, now)


def run_parsed(
    email: s.ParsedEmail,
    store: Store,
    kb: KnowledgeBase,
    llm: LlmClient,
    now: datetime,
    overrides: s.Overrides | None = None,
) -> PipelineResult:
    """E2 onwards. With overrides (P5) the officer's vessel, voyage or event replaces D1, D2 or
    D3 (`set_by="officer"`), and the open proposal of the email becomes stale and is superseded."""
    overrides = overrides or s.Overrides()
    thread = e.e2_derive_thread_key(email, store.thread_index())
    if thread.merged_thread_ids:
        with store.transaction() as tx:
            tx.relabel_threads(thread.merged_thread_ids, thread.thread_id)
    roles = e.e3_resolve_sender(email, kb)
    check = e.e4_check_sanitized(email)
    if check.status != "clean":  # P3: no LLM node, no D node
        detail = check.error or ", ".join(f"{f.kind} x{f.count}" for f in check.findings)
        return _held(email, "blocked_unsanitized", detail, thread.thread_id, store)

    entities = e.e5_extract_entities(email, roles, check, llm)
    if overrides.vessel_code:
        vessel = s.VesselMatch(vessel_code=overrides.vessel_code, status="matched", tier="High", score=1.0,
                               set_by="officer", reason="set by the officer", rule_triggered="officer_override")  # fmt: skip
    else:
        vessel = d.d1_match_vessel(entities, thread, roles, kb.vessels)
    if overrides.voyage_no:
        voyage = s.VoyageMatch(voyage_no=overrides.voyage_no, basis="stated", set_by="officer",
                               reason="set by the officer", rule_triggered="officer_override")  # fmt: skip
    else:
        voyage = d.d2_match_voyage(vessel, entities, thread, email, roles, kb)
    if overrides.event_type:
        event = s.EventDecision(event_type=overrides.event_type, tier="High", unsure=False, is_report=False,
                                sources_agree=True, set_by="officer", reason="set by the officer",
                                rule_triggered="officer_override")  # fmt: skip
    else:
        event = d.d3_rank_event(
            e.e6_detect_event(email, entities, voyage, roles, kb.taxonomy, llm), kb.action_rules
        )
    needs = d.d4_rank_urgency(event, voyage, entities, email, kb.action_rules, now, roles.sender.role)

    fact_lookup = (
        store.fact_lookup(vessel.vessel_code) if vessel.vessel_code else s.FactLookup(status="ok")
    )
    if fact_lookup.status != "ok":  # P4
        return _held(email, "store_unavailable", "fact lookup", thread.thread_id, store)
    facts = e.e6b_derive_fact_changes(entities, vessel, voyage, event, email, fact_lookup)
    actions = d.d5_rank_actions(e.e7_generate_actions(event, entities, voyage, email, kb.action_rules, now, llm),
                                needs, event, kb.action_rules)  # fmt: skip
    closure = s.ClosureCheck(llm_status="skipped")  # E8 deferred (cut line item 2)
    if vessel.vessel_code:
        task_lookup = store.task_lookup(vessel.vessel_code, voyage.voyage_no)
        if task_lookup.status != "ok":  # P4
            return _held(email, "store_unavailable", "task lookup", thread.thread_id, store)
    else:
        task_lookup = s.TaskLookup(status="ok")
    task = d.d6_match_task(actions, vessel, voyage, event, needs, closure, entities, thread, email, task_lookup,
                           kb.event_families)  # fmt: skip
    lane = e.e9_route_by_policy(event, vessel, task, facts, email)

    previous = store.open_proposal_id(email.email_id)
    proposal = e.e10_build_proposal(f"P-{uuid.uuid4().hex[:12]}", email, vessel, voyage, event, needs, facts,
                                    actions, task, lane)  # fmt: skip
    if previous:  # X-S06, X-S08: exactly one open proposal; the old one is only marked stale
        proposal = proposal.model_copy(update={"supersedes_proposal_id": previous})
        with store.transaction() as tx:
            tx.set_proposal_status(previous, expected="open", new="stale")
    saved = e.e10b_save_proposal(proposal, email, thread.thread_id, store)

    applied = None
    if lane.lane == "auto_apply":  # P1
        applied = e_apply.e11_apply_changes(
            proposal.proposal_id, s.Decision(kind="auto", actor="system", decided_at=now), store
        )
        saved = s.SavedProposal(
            proposal_id=saved.proposal_id,
            status="applied" if applied.status == "applied" else saved.status,
        )
    return PipelineResult(email_id=email.email_id, saved=saved, proposal=proposal, applied=applied)


def rerun_with_overrides(email_id: str, overrides: s.Overrides, store: Store, kb: KnowledgeBase, llm: LlmClient,
                         now: datetime) -> PipelineResult:  # fmt: skip
    """P5: the officer corrected the vessel, voyage or event of an email; the correction is
    recorded by E12 and the chain re-runs from the corrected node."""
    email = store.get_email(email_id)
    if email is None:
        raise KeyError(email_id)
    old_id = store.open_proposal_id(email_id)
    result = run_parsed(email, store, kb, llm, now, overrides)
    if old_id and result.proposal:
        old = store.get_proposal(old_id)
        edits = {k: v for k, v in overrides.model_dump(exclude_none=True).items()}
        e_apply.e12_record_correction(
            old, s.Decision(kind="edit", actor="officer", edits=edits, decided_at=now), store
        )
    return result
