"""T2.17 E11 e11_apply_changes (and ManualTaskChange, undo) and E12 e12_record_correction:
scenarios E11-S01 to S30, E12-S01 to S02 (design_backend.md sections 10 to 10.9, 11.A)."""

import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from src import e_apply as a
from src import store as st
from src.schemas import (
    ActionCandidate, ActionChange, ConfirmedAction, Decision, EventDecision, Evidence, FactChange, Lane,
    ManualTaskChange, Proposal, RankedAction, RankedActions, TaskDisposition, VesselMatch, VoyageMatch,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
AT = datetime(2026, 7, 30, 12, 0, tzinfo=CST)
KEY = "VSL-12|V202|redelivery"


def ranked(*types, priority=3):
    return RankedActions(items=[
        RankedAction(**ActionCandidate(action_type=t, description=f"{t} now", due_type="Redelivery",
                                       owner_role="Operator (internal)", decision_basis="CP terms",
                                       for_event="Redelivery Notice").model_dump(), rank=i, priority=priority)
        for i, t in enumerate(types, start=1)])  # fmt: skip


def proposal(
    pid="P1",
    email_id="E001",
    task=None,
    actions=None,
    facts=(),
    lane="needs_confirm",
    close_warning=False,
):
    task = task or TaskDisposition(kind="create", task_key=KEY, new_statuses=["Action Required"])
    if close_warning:
        task = task.model_copy(update={"close_warning": True})
    actions = actions if actions is not None else ranked("Check CP Terms")
    return Proposal(
        proposal_id=pid, email_id=email_id, lane=Lane(lane=lane),
        vessel=VesselMatch(vessel_code="VSL-12", status="matched", tier="High", score=1.0),
        voyage=VoyageMatch(voyage_no="V202", basis="stated"),
        event=EventDecision(event_type="Redelivery Notice", tier="High", unsure=False, is_report=False, sources_agree=True),
        statuses=["Close"] if task.kind == "close_proposal" else ["Action Required"],
        priority=max([x.priority for x in actions.items], default=3), fact_changes=list(facts), task=task, actions=actions,
    )  # fmt: skip


def approve(**kw):
    return Decision(kind="approve", actor="officer", decided_at=AT, **kw)


@pytest.fixture
def db(tmp_path):
    store = st.Store.open(tmp_path / "app.sqlite")
    yield store
    store.close()


def save(db, *proposals):
    with db.transaction() as tx:
        for p in proposals:
            tx.save_proposal(p)


def created(db):
    save(db, proposal())
    result = a.e11_apply_changes("P1", approve(), db)
    return result, db.get_task(result.applied_task_id)


def update_proposal(
    pid, task, email_id="E002", types=("Reserve Rights / Reply Without Prejudice",), statuses=None
):
    disp = TaskDisposition(kind="update", task_key=KEY, target_task_id=task.task_id, target_task_version=task.version,
                           new_statuses=statuses or ["Action Required"])  # fmt: skip
    return proposal(pid, email_id, disp, ranked(*types))


def test_e11_s01_approve_a_create_writes_task_history_and_undo(db):
    result, task = created(db)
    assert (result.status, task.version, task.status) == ("applied", 1, "open")
    assert result.undo_token and db.task_history(task.task_id)[0]["change"]["kind"] == "create"
    assert db.get_proposal("P1").status == "applied" and db.audit_count() == 1


def test_e11_s02_approve_an_update_raises_the_version_and_adds_the_action(db):
    _, task = created(db)
    save(db, update_proposal("P2", task))
    result = a.e11_apply_changes("P2", approve(), db)
    after = db.get_task(task.task_id)
    assert (result.status, after.version) == ("applied", 2)
    assert [x.action_type for x in after.actions] == [
        "Check CP Terms",
        "Reserve Rights / Reply Without Prejudice",
    ]


def test_e11_s03_approve_a_close_keeps_everything(db):
    _, task = created(db)
    close = TaskDisposition(
        kind="close_proposal", task_key=KEY, target_task_id=task.task_id, target_task_version=1
    )
    save(db, proposal("P2", "E002", close, RankedActions()))
    result = a.e11_apply_changes("P2", approve(), db)
    assert result.status == "applied" and db.get_task(task.task_id).status == "closed"
    assert len(db.task_history(task.task_id)) == 2


def fact(value="2026-08-04 15:00 LT", hours=0):
    return FactChange(fact_key="eta:newcastle", new=value, event_time=AT + timedelta(hours=hours),
                      event_time_basis="email_sent_time", evidence=Evidence(quote="ETA", source="new_text"))  # fmt: skip


def auto(pid, value, hours, email_id):
    return proposal(
        pid,
        email_id,
        TaskDisposition(kind="none"),
        RankedActions(),
        [fact(value, hours)],
        lane="auto_apply",
    )


def test_e11_s04_s05_s16_auto_facts_in_either_order_give_the_same_current_value(tmp_path):
    values = []
    for name, order in (("a", ("P1", "P2")), ("b", ("P2", "P1"))):
        store = st.Store.open(tmp_path / f"{name}.sqlite")
        save(store, auto("P1", "5 Aug", 0, "E001"), auto("P2", "4 Aug", 5, "E002"))
        for pid in order:
            assert (
                a.e11_apply_changes(
                    pid, Decision(kind="auto", actor="system", decided_at=AT), store
                ).status
                == "applied"
            )
        values.append(store.current_facts("VSL-12")["eta:newcastle"].value)
        store.close()
    assert values == ["4 Aug", "4 Aug"]


def test_e11_s06_two_changes_on_the_same_version_first_applied_second_conflict(db):
    _, task = created(db)
    save(
        db,
        update_proposal("P2", task, "E002"),
        update_proposal("P3", task, "E003", ("Track Contractual Notice / Deadline",)),
    )
    assert a.e11_apply_changes("P2", approve(), db).status == "applied"
    second = a.e11_apply_changes("P3", approve(), db)
    assert (second.status, second.reason) == ("conflict", "stale_task_version")
    assert db.get_proposal("P3").status == "open"  # nothing silently overwritten


def test_e11_s06_two_overlapping_approvals_from_two_connections(tmp_path):
    """ChordX 23a 7b: two threads, two connections, one task version; one wins."""
    path = tmp_path / "race.sqlite"
    setup = st.Store.open(path)
    _, task = created(setup)
    save(
        setup,
        update_proposal("P2", task, "E002"),
        update_proposal("P3", task, "E003", ("Track Contractual Notice / Deadline",)),
    )
    setup.close()
    barrier, outcomes = threading.Barrier(2), []

    def run(pid):
        store = st.Store.open(path)
        barrier.wait()
        outcomes.append(a.e11_apply_changes(pid, approve(), store).status)
        store.close()

    threads = [threading.Thread(target=run, args=(pid,)) for pid in ("P2", "P3")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["applied", "conflict"]


def test_e11_s07_failure_in_the_middle_rolls_back_and_keeps_the_proposal_open(db, monkeypatch):
    save(db, proposal())

    def broken(*args, **kw):
        raise st.StoreUnavailable("disk full")

    monkeypatch.setattr(st.Tx, "add_task_history", broken)
    result = a.e11_apply_changes("P1", approve(), db)
    assert result.status == "rolled_back"
    assert db.get_proposal("P1").status == "open" and db.open_tasks("VSL-12", "V202") == []


def test_e11_s08_undo_restores_the_previous_version_in_history(db):
    _, task = created(db)
    save(db, update_proposal("P2", task))
    result = a.e11_apply_changes("P2", approve(), db)
    undone = a.e11_undo(result.undo_token, db, "officer", AT)
    after = db.get_task(task.task_id)
    assert undone.status == "applied" and [x.action_type for x in after.actions] == [
        "Check CP Terms"
    ]
    assert db.task_history(task.task_id)[-1]["change"]["kind"] == "undo"


def test_e11_s09_close_for_an_already_closed_task_is_a_conflict(db):
    _, task = created(db)
    close = TaskDisposition(
        kind="close_proposal", task_key=KEY, target_task_id=task.task_id, target_task_version=1
    )
    save(
        db,
        proposal("P2", "E002", close, RankedActions()),
        proposal("P3", "E003", close, RankedActions()),
    )
    assert a.e11_apply_changes("P2", approve(), db).status == "applied"
    assert a.e11_apply_changes("P3", approve(), db).status == "conflict"


def test_e11_s10_e12_reject_is_noop_and_the_correction_is_recorded(db):
    save(db, proposal())
    result = a.e11_apply_changes(
        "P1", Decision(kind="reject", actor="officer", reason="wrong vessel", decided_at=AT), db
    )
    assert (result.status, db.get_proposal("P1").status) == ("noop", "rejected")
    assert [(c.field, c.final, c.reason) for c in db.corrections("P1")] == [
        ("decision", "reject", "wrong vessel")
    ]


def test_e11_s13_undo_after_a_later_change_is_a_conflict(db):
    result, task = created(db)
    save(db, update_proposal("P2", task))
    a.e11_apply_changes("P2", approve(), db)
    undone = a.e11_undo(result.undo_token, db, "officer", AT)
    assert (undone.status, undone.reason) == ("conflict", "later_change_exists")


def test_e11_s14_the_same_proposal_confirmed_twice_is_noop(db):
    created(db)
    assert a.e11_apply_changes("P1", approve(), db).reason == "already_decided"


def test_e11_s15_two_creates_with_one_key_second_is_a_conflict(db):
    save(db, proposal("P1", "E001"), proposal("P2", "E002"))
    assert a.e11_apply_changes("P1", approve(), db).status == "applied"
    second = a.e11_apply_changes("P2", approve(), db)
    assert (second.status, second.reason) == ("conflict", "duplicate_open_key")


def test_e11_s17_undo_of_an_automatic_fact_retracts_it(db):
    save(db, auto("P1", "5 Aug", 0, "E001"), auto("P2", "4 Aug", 5, "E002"))
    a.e11_apply_changes("P1", Decision(kind="auto", actor="system", decided_at=AT), db)
    second = a.e11_apply_changes("P2", Decision(kind="auto", actor="system", decided_at=AT), db)
    assert a.e11_undo(second.undo_token, db, "officer", AT).status == "applied"
    assert db.current_facts("VSL-12")["eta:newcastle"].value == "5 Aug"


def test_e11_s18_s25_manual_change_of_an_action_priority(db):
    _, task = created(db)
    change = ManualTaskChange(task_id=task.task_id, expected_version=1,
                              action_changes=[ActionChange(action_id=task.actions[0].action_id, priority=5)])  # fmt: skip
    result = a.e11_apply_manual(change, db, AT)
    after = db.get_task(task.task_id)
    assert (result.status, after.version, after.priority) == ("applied", 2, 5) and result.undo_token


def test_e11_s19_manual_change_with_an_old_version_is_a_conflict(db):
    _, task = created(db)
    result = a.e11_apply_manual(
        ManualTaskChange(
            task_id=task.task_id, expected_version=7, new_statuses=["Approval Required"]
        ),
        db,
        AT,
    )
    assert (result.status, result.reason) == ("conflict", "stale_task_version")
    assert db.get_task(task.task_id).version == 1


def test_e11_s21_close_with_warning_and_no_reason_is_rejected(db):
    _, task = created(db)
    close = TaskDisposition(
        kind="close_proposal", task_key=KEY, target_task_id=task.task_id, target_task_version=1
    )
    save(db, proposal("P2", "E002", close, RankedActions(), close_warning=True))
    with pytest.raises(a.InvalidDecision):
        a.e11_apply_changes("P2", approve(), db)
    assert a.e11_apply_changes("P2", approve(reason="LOI returned"), db).status == "applied"


def test_e11_s23_e12_officer_priority_and_due_are_saved_and_recorded(db):
    save(db, proposal())
    confirmed = [ConfirmedAction(action_type="Check CP Terms", description="Check it", priority=5, due_type="Redelivery",
                                 due_date=date(2026, 8, 6), set_by="officer")]  # fmt: skip
    result = a.e11_apply_changes("P1", approve(actions=confirmed), db)
    action = db.get_task(result.applied_task_id).actions[0]
    assert (action.priority, action.due_date, action.set_by) == (5, date(2026, 8, 6), "officer")
    assert {c.field for c in db.corrections("P1")} == {
        "action:Check CP Terms:priority",
        "action:Check CP Terms:due_date",
    }


def test_e11_s28_statuses_and_approval_mark_are_saved_and_recorded(db):
    save(db, proposal())
    confirmed = [ConfirmedAction(action_type="Check CP Terms", description="x", priority=3, due_type="Redelivery",
                                 set_by="ai", needs_approval=True)]  # fmt: skip
    result = a.e11_apply_changes("P1", approve(statuses=["Action Required", "Approval Required"], actions=confirmed,
                                               edits={"statuses": ["Action Required", "Approval Required"]}), db)  # fmt: skip
    task = db.get_task(result.applied_task_id)
    assert (
        task.statuses == ["Action Required", "Approval Required"] and task.actions[0].needs_approval
    )
    assert {"statuses", "action:Check CP Terms:needs_approval"} <= {
        c.field for c in db.corrections("P1")
    }


def test_e11_s29_manual_new_statuses_replace_the_task_statuses(db):
    _, task = created(db)
    result = a.e11_apply_manual(
        ManualTaskChange(
            task_id=task.task_id, expected_version=1, new_statuses=["Approval Required"]
        ),
        db,
        AT,
    )
    assert result.status == "applied" and db.get_task(task.task_id).statuses == [
        "Approval Required"
    ]


def test_e11_undo_of_a_close_is_a_conflict_because_a_closed_task_is_never_reopened(db):
    _, task = created(db)
    close = TaskDisposition(
        kind="close_proposal", task_key=KEY, target_task_id=task.task_id, target_task_version=1
    )
    save(db, proposal("P2", "E002", close, RankedActions()))
    result = a.e11_apply_changes("P2", approve(), db)
    undone = a.e11_undo(result.undo_token, db, "officer", AT)
    assert undone.status == "conflict" and db.get_task(task.task_id).status == "closed"


def test_e11_an_undo_token_is_used_once(db):
    result, _ = created(db)
    assert a.e11_undo(result.undo_token, db, "officer", AT).status == "applied"
    assert a.e11_undo(result.undo_token, db, "officer", AT).reason == "already_decided"


def test_e12_s02_correction_write_failure_does_not_change_the_result(db, monkeypatch):
    save(db, proposal())

    def broken(*args, **kw):
        raise st.StoreUnavailable("x")

    monkeypatch.setattr(st.Tx, "add_correction", broken)
    result = a.e11_apply_changes(
        "P1", Decision(kind="reject", actor="officer", reason="x", decided_at=AT), db
    )
    assert result.status == "noop" and db.get_proposal("P1").status == "rejected"
