"""T2.16 E9 e9_route_by_policy, E10 e10_build_proposal, E10b e10b_save_proposal: scenarios E9-S01
to S07, E10-S01 to S10, E10b-S01 to S04 (design_backend.md sections 10, 10.3, 10.5, 10.6, 10.8)."""

from datetime import datetime, timedelta, timezone

import pytest

from src import e_nodes as e
from src import store as st
from src.schemas import (
    ActionCandidate, EventDecision, Evidence, FactChange, FactChanges, HeldRecord, NeedsActionDecision, ParsedEmail,
    RankedAction, RankedActions, TaskDisposition, VesselMatch, VoyageMatch,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
SENT = datetime(2026, 7, 30, 10, 0, tzinfo=CST)
REPORT = "Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)"
HIGH = VesselMatch(
    vessel_code="VSL-02",
    status="matched",
    tier="High",
    score=1.0,
    reason="subject",
    rule_triggered="matched_high",
)
VOYAGE = VoyageMatch(voyage_no="V202", basis="stated", rule_triggered="stated")
NONE_TASK = TaskDisposition(kind="none", rule_triggered="report")


def event(event_type=REPORT, is_report=True, unsure=False):
    return EventDecision(event_type=event_type, tier="High", unsure=unsure, is_report=is_report, sources_agree=True,
                         rule_triggered="accepted")  # fmt: skip


def email(attachment_dependent=False):
    return ParsedEmail(email_id="E010", subject="VSL-02 noon", subject_norm="vsl-02 noon", sent_time=SENT,
                       direction="Inbound", sender="x@CPY-05.example", new_text="Noon.",
                       attachment_dependent=attachment_dependent)  # fmt: skip


def change(older=False, event_time=SENT):
    return FactChange(fact_key="eta:newcastle", new="4 Aug", event_time=event_time,
                      event_time_basis="email_sent_time" if event_time else None,
                      evidence=Evidence(quote="ETA 4 Aug", source="new_text"), older_than_current=older)  # fmt: skip


def lane(ev=None, vessel=HIGH, task=NONE_TASK, facts=None, mail=None):
    return e.e9_route_by_policy(
        ev or event(), vessel, task, facts or FactChanges(items=[change()]), mail or email()
    )


# --- E9 ------------------------------------------------------------------------------------


def test_e9_s01_report_high_vessel_no_conflict_is_automatic():
    assert lane().lane == "auto_apply"


def test_e9_s02_report_with_a_medium_vessel_needs_confirm():
    medium = HIGH.model_copy(update={"tier": "Medium"})
    out = lane(vessel=medium)
    assert out.lane == "needs_confirm" and "vessel_not_high" in out.reasons


def test_e9_s03_report_value_older_than_the_current_fact_needs_confirm():
    out = lane(facts=FactChanges(items=[change(older=True)]))
    assert out.lane == "needs_confirm" and "conflicts_with_newer_fact" in out.reasons


def test_e9_s04_non_report_event_needs_confirm():
    assert lane(ev=event("Redelivery Notice", is_report=False)).lane == "needs_confirm"


def test_e9_s05_unsure_event_needs_confirm():
    assert "event_unsure" in lane(ev=event(unsure=True)).reasons


def test_e9_s06_fact_without_a_time_needs_confirm():
    assert "fact_without_time" in lane(facts=FactChanges(items=[change(event_time=None)])).reasons


def test_e9_s07_attachment_dependent_is_never_automatic():
    assert "attachment_dependent" in lane(mail=email(attachment_dependent=True)).reasons


def test_e9_never_auto_event_even_when_it_looks_like_a_report():
    assert "never_auto_event" in lane(ev=event("Claim", is_report=True)).reasons


# --- E10 -----------------------------------------------------------------------------------


def ranked(*priorities, approval=False, reply=False):
    items = [RankedAction(**ActionCandidate(action_type="Check CP Terms", description="x", due_type="Others",
                                            due_other="x", owner_role="Operator (internal)", decision_basis="",
                                            for_event="Redelivery Notice").model_dump(),
                          rank=i, priority=p, needs_approval=approval and i == 1, awaiting_reply=reply and i == 1)
             for i, p in enumerate(priorities, start=1)]  # fmt: skip
    return RankedActions(items=items)


def needs(*statuses, priority=3):
    return NeedsActionDecision(statuses=list(statuses) or ["Action Required"], priority=priority, reason="r",
                               rule_triggered="row_default")  # fmt: skip


def build(actions=None, statuses=None, task=None, lane_=None, vessel=HIGH, facts=None):
    return e.e10_build_proposal(
        "P1", email(), vessel, VOYAGE, event("Redelivery Notice", is_report=False), statuses or needs(),
        facts or FactChanges(), actions or RankedActions(), task or TaskDisposition(kind="create", task_key="k"),
        lane_ or e.Lane(lane="needs_confirm", reasons=["non_report_event"]),
    )  # fmt: skip


def test_e10_s01_complete_proposal_has_a_trace_step_per_decision_and_the_highest_priority():
    p = build(actions=ranked(3, 4))
    assert p.priority == 4 and p.incomplete is False
    assert [s.node for s in p.trace] == ["D1", "D2", "D3", "D4", "D5", "D6", "E9"]


def test_e10_s02_missing_upstream_result_is_incomplete_and_needs_confirm():
    p = e.e10_build_proposal("P1", email(), HIGH, None, None, None, FactChanges(), None, None,
                             e.Lane(lane="auto_apply"))  # fmt: skip
    assert p.incomplete is True and p.lane.lane == "needs_confirm"


def test_e10_s02_without_actions_the_priority_is_d4_s():
    assert build(statuses=needs(priority=4)).priority == 4


def test_e10_s03_close_proposal_gives_the_status_close():
    task = TaskDisposition(
        kind="close_proposal", task_key="k", target_task_id="T1", target_task_version=2
    )
    assert build(task=task).statuses == ["Close"]


def test_e10_s04_otherwise_statuses_from_d4_and_the_marks():
    assert build(actions=ranked(3)).statuses == ["Action Required"]


def test_e10_s05_close_and_a_new_eta_keep_the_fact_change():
    task = TaskDisposition(
        kind="close_proposal", task_key="k", target_task_id="T1", target_task_version=2
    )
    p = build(task=task, facts=FactChanges(items=[change()]))
    assert p.statuses == ["Close"] and [f.fact_key for f in p.fact_changes] == ["eta:newcastle"]


def test_e10_s08_approval_mark_adds_approval_required():
    assert build(actions=ranked(3, approval=True)).statuses == [
        "Action Required",
        "Approval Required",
    ]


def test_e10_s09_fyi_with_a_reply_action_stays_fyi():
    # [AMENDMENT 2026-09-26 T4.1-c] D4's FYI is kept; the officer can still tick a status
    assert build(actions=ranked(3, reply=True), statuses=needs("FYI - No Action")).statuses == [
        "FYI - No Action"
    ]


def test_e10_s10_fyi_with_plain_actions_stays_fyi():
    assert build(actions=ranked(3), statuses=needs("FYI - No Action")).statuses == [
        "FYI - No Action"
    ]


# --- E10b ----------------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    store = st.Store.open(tmp_path / "app.sqlite")
    yield store
    store.close()


def test_e10b_s01_normal_proposal_is_saved_open_with_its_email(db):
    saved = e.e10b_save_proposal(build(), email(), "T-E010", db)
    assert (saved.proposal_id, saved.status) == ("P1", "open")
    assert db.get_proposal("P1").email_id == "E010"


def test_e10b_s02_s03_held_emails_are_saved_with_their_status(db):
    blocked = e.e10b_save_proposal(
        HeldRecord(email_id="E010", reason="blocked_unsanitized", detail="phone"), email(), None, db
    )
    assert blocked.status == "held_blocked"
    down = e.e10b_save_proposal(
        HeldRecord(email_id="E011", reason="store_unavailable", detail="lookup"), None, None, db
    )
    assert down.status == "held_store_unavailable"


def test_e10b_rerun_of_the_same_email_keeps_one_email_row(db):
    e.e10b_save_proposal(build(), email(), "T-E010", db)
    with db.transaction() as tx:
        tx.set_proposal_status("P1", expected="open", new="stale")
    e.e10b_save_proposal(
        build().model_copy(update={"proposal_id": "P2", "supersedes_proposal_id": "P1"}),
        email(),
        "T-E001",
        db,
    )
    assert db.get_proposal("P2").supersedes_proposal_id == "P1"


def test_e10b_s04_write_failure_is_a_hard_failure(tmp_path):
    store = st.Store.open(tmp_path / "x.sqlite")
    store.close()  # a broken store
    with pytest.raises(st.StoreError):
        e.e10b_save_proposal(build(), email(), "T-E010", store)
