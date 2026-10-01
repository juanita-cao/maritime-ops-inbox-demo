"""T1.2 contract tests: one valid example of every model (design_backend.md 9.1, 9.2, 9.4),
plus one test per validation rule that section 9 states. Updated for UI round U1 (2026-09-26):
priority 1 to 5 and due per action replace the statuses Urgent and Risk."""

from datetime import date, datetime, timezone

import pytest
from pydantic import BaseModel, ValidationError

from src import schemas as s

NOW = datetime(2026, 7, 30, 14, 48, tzinfo=timezone.utc)


def ev(quote: str = "ETA 04 AUG 1500") -> s.Evidence:
    return s.Evidence(quote=quote, source="new_text")


def vessel_match() -> s.VesselMatch:
    return s.VesselMatch(
        vessel_code="VSL-12",
        status="matched",
        tier="High",
        score=0.95,
        evidence=[ev("VSL-12")],
        candidates=[s.Candidate(vessel_code="VSL-12", score=0.95)],
    )


def voyage_match() -> s.VoyageMatch:
    return s.VoyageMatch(
        voyage_no="V202", basis="stated", contract_level=None, evidence=[ev("V202")]
    )


def event_decision() -> s.EventDecision:
    return s.EventDecision(
        event_type="Vessel Report", tier="High", unsure=False, is_report=True, sources_agree=True
    )


def task_disposition_none() -> s.TaskDisposition:
    return s.TaskDisposition(kind="none")


def action_candidate() -> s.ActionCandidate:
    return s.ActionCandidate(
        action_type="Confirm Bunker ROB / Stem",
        description="Confirm ROB before redelivery",
        due=date(2026, 8, 5),
        owner_role="Operator",
        decision_basis="Company SOP / Operations Manual / Checklist",
        due_type="Redelivery",
        templated=False,
        for_event="Redelivery Notice",
    )


def fact_change() -> s.FactChange:
    return s.FactChange(
        fact_key="eta:Newcastle",
        old=None,
        new="2026-08-04T15:00+08:00",
        event_time=NOW,
        event_time_basis="stated",
        evidence=ev(),
        base_version=None,
    )


def task_action(priority: int = 4) -> s.TaskAction:
    return s.TaskAction(
        action_id="A1",
        task_id="T1",
        action_type="Check CP Terms",
        description="Check the redelivery clause",
        priority=priority,
        due_type="Redelivery",
        due_date=date(2026, 8, 6),
        set_by="ai",
        source_email_id="E001",
    )


def task() -> s.Task:
    return s.Task(
        task_id="T1",
        task_key="VSL-12|V202|redelivery",
        vessel_code="VSL-12",
        voyage_no="V202",
        action_type="Check CP Terms",
        description="Check the redelivery notice period",
        statuses=["Action Required"],
        deadline=None,
        status="open",
        version=1,
        source_email_ids=["E001"],
        priority=4,
        actions=[task_action()],
    )


def fact_record() -> s.FactRecord:
    return s.FactRecord(
        fact_id="F1",
        vessel_code="VSL-12",
        fact_key="eta:Newcastle",
        value="2026-08-04T15:00+08:00",
        event_time=NOW,
        event_time_basis="stated",
        sent_time=NOW,
        source_email_id="E001",
        version=1,
    )


def task_row() -> s.TaskRow:
    return s.TaskRow(
        task_id="T1",
        vessel="VSL-12",
        voyage="V202",
        action="Check CP Terms",
        priority=4,
        due_type="Redelivery",
        deadline=None,
        overdue=False,
        statuses=["Action Required"],
        source_email_id="E001",
    )


def proposal() -> s.Proposal:
    return s.Proposal(
        proposal_id="P1",
        email_id="E001",
        lane=s.Lane(lane="auto_apply", reasons=["report, High vessel tier"]),
        vessel=vessel_match(),
        voyage=voyage_match(),
        event=event_decision(),
        statuses=["FYI - No Action"],
        priority=1,
        fact_changes=[fact_change()],
        task=task_disposition_none(),
        actions=s.RankedActions(items=[]),
        trace=[s.TraceStep(node="D1", rule_or_basis="subject name", confidence=0.95, evidence=[])],
    )


def confirmed_action(**kw) -> s.ConfirmedAction:
    data = dict(
        action_type="Reserve Rights / Reply Without Prejudice",
        description="Reply without prejudice and reserve rights",
        priority=4,
        due_type="Others",
        due_other="Reply to charterers",
        due_date=date(2026, 8, 1),
        set_by="officer",
    )
    data.update(kw)
    return s.ConfirmedAction(**data)


EXAMPLES: dict[str, callable] = {
    "Evidence": ev,
    "ParsedEmail": lambda: s.ParsedEmail(
        email_id="E001",
        subject="RE: VSL-12 / V202 ETA",
        subject_norm="vsl-12 / v202 eta",
        sent_time=NOW,
        direction="Inbound",
        sender="mail01@example.com",
        receivers=["mail02@example.com"],
        new_text="ETA 04 AUG 1500",
        signature_text="",
        attachment_dependent=False,
        attachment_names=[],
        quoted_text="",
        quoted_subjects=[],
        parse_flags=[],
    ),
    "ThreadRef": lambda: s.ThreadRef(
        thread_id="TH1", is_new_thread=True, member_email_ids=["E001"]
    ),
    "PartyRoles": lambda: s.PartyRoles(
        sender=s.PartyRef(
            address="mail01@example.com", party_code="CPY-10", role="Charterer", confidence="stated"
        ),
        receivers=[],
        low_confidence=False,
    ),
    "SanitizationCheck": lambda: s.SanitizationCheck(status="clean"),
    "ExtractedEntities": lambda: s.ExtractedEntities(
        vessel_mentions=[s.Mention(text="VSL-12", evidence=ev("VSL-12"))],
        dates=[s.DateFact(kind="eta", value="2026-08-04T15:00+08:00", evidence=ev())],
        quantities=[
            s.QuantityFact(kind="amount", value=4500, unit="USD", currency="USD", evidence=ev())
        ],
        references=[s.Reference(kind="bl", value="BL-01", evidence=ev())],
        llm_status="ok",
    ),
    "VesselMatch": vessel_match,
    "VoyageMatch": voyage_match,
    "EventCandidates": lambda: s.EventCandidates(
        items=[
            s.EventCandidate(
                event_type="Vessel Report", confidence=0.9, source="rule", evidence=ev()
            )
        ],
        is_report=True,
        llm_status="skipped",
    ),
    "EventDecision": event_decision,
    "NeedsActionDecision": lambda: s.NeedsActionDecision(
        statuses=["Action Required"], priority=3, reason="rule row default"
    ),
    "ActionCandidates": lambda: s.ActionCandidates(items=[action_candidate()], llm_status="ok"),
    "RankedActions": lambda: s.RankedActions(
        items=[s.RankedAction(**action_candidate().model_dump(), rank=1, priority=3)]
    ),
    "ClosureCheck": lambda: s.ClosureCheck(
        results=[s.ClosureResult(task_id="T1", settled=True, evidence=ev("survey completed"))],
        llm_status="ok",
    ),
    "TaskDisposition": task_disposition_none,
    "Lane": lambda: s.Lane(lane="needs_confirm", reasons=["conversation"]),
    "FactChanges": lambda: s.FactChanges(items=[fact_change()]),
    "Proposal": proposal,
    "Decision": lambda: s.Decision(
        kind="edit",
        actor="officer",
        edits={"actions": "priority changed"},
        actions=[confirmed_action()],
        decided_at=NOW,
    ),
    "TaskAction": task_action,
    "DueList": lambda: s.DueList(
        items=[
            s.DueRow(
                task_id="T1",
                action_id="A1",
                vessel="VSL-12",
                voyage="V202",
                action="Check the redelivery clause",
                due_type="Others",
                due_other="reply to charterers",
                due_date=date(2026, 8, 1),
                priority=4,
                overdue=False,
            )
        ],
        store_status="ok",
    ),
    "ApplyResult": lambda: s.ApplyResult(status="applied", undo_token="U1"),
    "CorrectionRecord": lambda: s.CorrectionRecord(
        proposal_id="P1", field="vessel", suggested="VSL-11", final="VSL-12"
    ),
    "RankedTaskList": lambda: s.RankedTaskList(
        groups=[s.TaskGroup(name="Action Required", items=[task_row()])]
    ),
    "VesselView": lambda: s.VesselView(
        vessel_code="VSL-12",
        facts=[
            s.FactRow(
                fact_key="eta:Newcastle",
                value="2026-08-04T15:00+08:00",
                event_time=NOW,
                source_email_id="E001",
                superseded=False,
            )
        ],
        timeline=[
            s.TimelineRow(
                event_time=NOW,
                event_type="Vessel Report",
                email_id="E001",
                changed_fact_keys=["eta:Newcastle"],
            )
        ],
        open_tasks=[task_row()],
        auto_applied=[
            s.AutoAppliedRow(
                email_id="E001", fact_keys=["eta:Newcastle"], applied_at=NOW, undo_available=True
            )
        ],
    ),
    "Task": task,
    "FactRecord": fact_record,
    "TaskLookup": lambda: s.TaskLookup(
        status="ok",
        tasks=[task()],
        pending_proposals=[s.PendingRef(proposal_id="P2", task_key="k", kind="create")],
    ),
    "FactLookup": lambda: s.FactLookup(status="ok", facts=[fact_record()]),
    "HeldRecord": lambda: s.HeldRecord(
        email_id="E009", reason="blocked_unsanitized", detail="phone number"
    ),
    "SavedProposal": lambda: s.SavedProposal(proposal_id="P1", status="open"),
    "Overrides": lambda: s.Overrides(vessel_code="VSL-11"),
    "ReviewQueue": lambda: s.ReviewQueue(
        items=[
            s.ReviewRow(
                proposal_id="P1",
                email_id="E001",
                vessel="VSL-12",
                event_type="Redelivery Notice",
                statuses=["Action Required"],
                status="open",
            )
        ],
        store_status="ok",
    ),
    "ManualTaskChange": lambda: s.ManualTaskChange(
        task_id="T1", expected_version=2, new_statuses=["Approval Required"], close=False
    ),
}


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_schemas_builds_one_valid_example_of_each_model(name):
    model = EXAMPLES[name]()
    assert type(model).__name__ == name
    assert isinstance(model, BaseModel)
    assert type(model).model_validate(model.model_dump()) == model


def test_schemas_every_timestamp_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        s.Decision(kind="approve", actor="officer", decided_at=datetime(2026, 7, 30, 14, 48))


def test_schemas_evidence_quote_must_not_be_empty():
    with pytest.raises(ValidationError):
        s.Evidence(quote="", source="new_text")


def test_schemas_parsed_email_empty_new_text_is_a_hard_failure():
    data = EXAMPLES["ParsedEmail"]().model_dump()
    data["new_text"] = ""
    with pytest.raises(ValidationError):
        s.ParsedEmail(**data)


def test_schemas_sanitization_clean_has_no_findings_and_error_only_when_check_failed():
    with pytest.raises(ValidationError):
        s.SanitizationCheck(status="clean", findings=[s.Finding(kind="phone", count=1)])
    with pytest.raises(ValidationError):
        s.SanitizationCheck(status="clean", error="boom")
    assert s.SanitizationCheck(status="check_failed", error="boom").error == "boom"


def test_schemas_amount_quantity_needs_currency_and_value_not_negative():
    with pytest.raises(ValidationError):
        s.QuantityFact(kind="amount", value=10, unit="USD", evidence=ev())
    with pytest.raises(ValidationError):
        s.QuantityFact(kind="loaded", value=-1, unit="MT", evidence=ev())


def test_schemas_vessel_not_matched_means_low_tier_and_no_code():
    with pytest.raises(ValidationError):
        s.VesselMatch(vessel_code="VSL-11", status="ambiguous", tier="Low", score=0.5)
    with pytest.raises(ValidationError):
        s.VesselMatch(vessel_code=None, status="none", tier="High", score=0.0)
    assert s.VesselMatch(vessel_code=None, status="none", tier="Low", score=0.0).set_by == "rule"


def test_schemas_voyage_basis_none_requires_no_voyage():
    with pytest.raises(ValidationError):
        s.VoyageMatch(voyage_no="V202", basis="none")


def test_schemas_list_limits_on_candidates_secondary_events_and_actions():
    item = EXAMPLES["EventCandidates"]().items[0]
    with pytest.raises(ValidationError):
        s.EventCandidates(items=[item] * 4, is_report=False, llm_status="ok")
    with pytest.raises(ValidationError):
        s.EventDecision(
            event_type="X",
            tier="High",
            unsure=False,
            is_report=False,
            sources_agree=True,
            secondary_event_types=["A", "B", "C"],
        )
    with pytest.raises(ValidationError):
        s.ActionCandidates(items=[action_candidate()] * 6, llm_status="ok")
    ranked = s.RankedAction(**action_candidate().model_dump(), rank=1, priority=3)
    with pytest.raises(ValidationError):
        s.RankedActions(items=[ranked] * 4)


def test_schemas_action_description_at_most_300_characters():
    data = action_candidate().model_dump()
    data["description"] = "x" * 301
    with pytest.raises(ValidationError):
        s.ActionCandidate(**data)


def test_schemas_d4_never_produces_close():
    with pytest.raises(ValidationError):
        s.NeedsActionDecision(statuses=["Close"], priority=3, reason="x")


def test_schemas_closure_settled_without_evidence_becomes_not_settled():
    result = s.ClosureResult(task_id="T1", settled=True, evidence=None)
    assert result.settled is False


def test_schemas_task_disposition_required_fields_per_kind():
    with pytest.raises(ValidationError):
        s.TaskDisposition(kind="create")
    with pytest.raises(ValidationError):
        s.TaskDisposition(kind="update", task_key="k", target_task_id="T1")
    with pytest.raises(ValidationError):
        s.TaskDisposition(kind="close_proposal")
    with pytest.raises(ValidationError):
        s.TaskDisposition(
            kind="create",
            task_key="k",
            changed_fields={"deadline": s.FieldChange(old=None, new="2026-08-05")},
        )
    ok = s.TaskDisposition(kind="update", task_key="k", target_task_id="T1", target_task_version=3)
    assert ok.target_task_version == 3


def test_schemas_proposal_close_only_with_close_proposal():
    data = proposal().model_dump()
    data["statuses"] = ["Close"]
    with pytest.raises(ValidationError):
        s.Proposal(**data)


def test_schemas_decision_auto_only_by_system_and_edit_needs_edits():
    with pytest.raises(ValidationError):
        s.Decision(kind="auto", actor="officer", decided_at=NOW)
    with pytest.raises(ValidationError):
        s.Decision(kind="edit", actor="officer", edits={}, decided_at=NOW)
    edited = s.Decision(kind="edit", actor="officer", statuses=["Action Required"], decided_at=NOW)
    assert edited.statuses == ["Action Required"]
    assert s.Decision(kind="edit", actor="officer", actions=[], decided_at=NOW).actions == []


def test_schemas_manual_task_change_close_and_new_status_are_exclusive():
    with pytest.raises(ValidationError):
        s.ManualTaskChange(
            task_id="T1", expected_version=1, new_statuses=["Approval Required"], close=True
        )


# --- UI round U1 (2026-09-26): priority and due per action ---------------------


def test_schemas_needs_action_has_no_urgent_or_risk():
    for gone in ("Urgent", "Risk"):
        with pytest.raises(ValidationError):
            s.NeedsActionDecision(statuses=[gone], priority=5, reason="x")


def test_schemas_priority_must_be_between_1_and_5():
    for bad in (0, 6):
        with pytest.raises(ValidationError):
            confirmed_action(priority=bad)
        with pytest.raises(ValidationError):
            s.NeedsActionDecision(statuses=["Action Required"], priority=bad, reason="x")
    assert confirmed_action(priority=5).priority == 5


def test_schemas_due_type_others_needs_a_text():
    with pytest.raises(ValidationError):
        confirmed_action(due_type="Others", due_other=None)
    with pytest.raises(ValidationError):
        confirmed_action(due_type="Others", due_other="  ")
    data = action_candidate().model_dump()
    data.update(due_type="Others", due_other=None)
    with pytest.raises(ValidationError):
        s.ActionCandidate(**data)
    assert confirmed_action(due_type="Hire", due_other=None).due_other is None


def test_schemas_unknown_due_type_is_rejected():
    with pytest.raises(ValidationError):
        confirmed_action(due_type="Laycan", due_other=None)


def test_schemas_proposal_priority_is_the_highest_action_priority():
    data = proposal().model_dump()
    low = s.RankedAction(**action_candidate().model_dump(), rank=1, priority=3)
    high = s.RankedAction(**action_candidate().model_dump(), rank=2, priority=4)
    data["actions"] = {"items": [low.model_dump(), high.model_dump()]}
    data["priority"] = 3
    with pytest.raises(ValidationError):
        s.Proposal(**data)
    data["priority"] = 4
    assert s.Proposal(**data).priority == 4


def test_schemas_task_priority_is_the_highest_action_priority():
    data = task().model_dump()
    data["actions"] = [task_action(3).model_dump(), task_action(5).model_dump()]
    data["priority"] = 4
    with pytest.raises(ValidationError):
        s.Task(**data)
    data["priority"] = 5
    assert s.Task(**data).priority == 5


def test_schemas_manual_task_change_needs_something_to_change():
    with pytest.raises(ValidationError):
        s.ManualTaskChange(task_id="T1", expected_version=1)
    only_actions = s.ManualTaskChange(
        task_id="T1",
        expected_version=1,
        action_changes=[s.ActionChange(action_id="A1", priority=5)],
    )
    assert only_actions.action_changes[0].priority == 5


def test_schemas_task_groups_follow_the_remaining_statuses():
    with pytest.raises(ValidationError):
        s.TaskGroup(name="Urgent / Risk")
    for name in ("Action Required", "Approval Required", "Waiting for Reply"):
        assert s.TaskGroup(name=name).name == name


# --- UI round U2 (2026-09-26): several statuses, approval and reply marks per action ---


def test_schemas_d4_s21_statuses_are_kept_in_the_taxonomy_order():
    decision = s.NeedsActionDecision(
        statuses=["Waiting for Reply", "Action Required", "Approval Required"],
        priority=3,
        reason="rule row",
    )
    assert decision.statuses == ["Action Required", "Approval Required", "Waiting for Reply"]


@pytest.mark.parametrize(
    "bad",
    [
        [],
        ["Action Required", "Action Required"],
        ["FYI - No Action", "Action Required"],
        ["Close", "Action Required"],
    ],
    ids=["empty", "repeat", "fyi_with_other", "close_with_other"],
)
def test_schemas_e11_s27_invalid_status_sets_are_rejected(bad):
    with pytest.raises(ValidationError):
        s.Decision(
            kind="edit", actor="officer", edits={"statuses": bad}, statuses=bad, decided_at=NOW
        )
    with pytest.raises(ValidationError):
        s.ManualTaskChange(task_id="T1", expected_version=1, new_statuses=bad)


def test_schemas_e11_s28_decision_carries_statuses_and_action_marks():
    decision = s.Decision(
        kind="edit",
        actor="officer",
        edits={"statuses": ["Action Required", "Approval Required"]},
        statuses=["Approval Required", "Action Required"],
        actions=[confirmed_action(needs_approval=True)],
        decided_at=NOW,
    )
    assert decision.statuses == ["Action Required", "Approval Required"]
    assert decision.actions[0].needs_approval is True
    assert decision.actions[0].awaiting_reply is False


def test_schemas_e11_s29_manual_change_with_new_statuses_and_action_marks():
    change = s.ManualTaskChange(
        task_id="T1",
        expected_version=3,
        new_statuses=["Approval Required"],
        action_changes=[s.ActionChange(action_id="T1-A1", awaiting_reply=True)],
    )
    assert change.new_statuses == ["Approval Required"]
    assert change.action_changes[0].awaiting_reply is True


def test_schemas_manual_change_cannot_set_close_as_a_status():
    with pytest.raises(ValidationError):
        s.ManualTaskChange(task_id="T1", expected_version=1, new_statuses=["Close"])


def test_schemas_task_statuses_never_hold_close_or_awaiting_reply_field():
    data = task().model_dump()
    data["statuses"] = ["Close"]
    with pytest.raises(ValidationError):
        s.Task(**data)
    assert "awaiting_reply" not in s.Task.model_fields
    assert "awaiting_reply" not in s.TaskRow.model_fields


def test_schemas_d5_s06_ranked_and_stored_actions_carry_both_marks():
    ranked = s.RankedAction(**action_candidate().model_dump(), rank=1, priority=3)
    assert (ranked.needs_approval, ranked.awaiting_reply) == (False, False)
    assert task_action().model_copy(update={"needs_approval": True}).needs_approval is True
    assert set(s.TaskAction.model_fields) >= {"needs_approval", "awaiting_reply"}
