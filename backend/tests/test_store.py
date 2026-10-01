"""T1.4 store.py: SQLite schema and guards of design_backend.md 11.A and 11.B, tested on the
store alone (the E11 logic that uses them comes in T2.17)."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src import schemas as s
from src import store as st

T0 = datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path) -> st.Store:
    store = st.Store.open(tmp_path / "app.sqlite")
    yield store
    store.close()


def make_task(task_id="T1", key="VSL-02|V202|redelivery", priority=4) -> s.Task:
    return s.Task(
        task_id=task_id,
        task_key=key,
        vessel_code="VSL-02",
        voyage_no="V202",
        action_type="Check CP Terms",
        description="Check the redelivery clause",
        statuses=["Action Required"],
        status="open",
        version=1,
        source_email_ids=["E001"],
        priority=priority,
        actions=[
            s.TaskAction(
                action_id=f"{task_id}-A1",
                task_id=task_id,
                action_type="Check CP Terms",
                description="Check the redelivery clause",
                priority=priority,
                due_type="Redelivery",
                due_date=date(2026, 8, 6),
                set_by="ai",
                source_email_id="E001",
            )
        ],
    )


def make_fact(fact_id, value, event_time, sent_time=None, email_id="E001") -> s.FactRecord:
    return s.FactRecord(
        fact_id=fact_id,
        vessel_code="VSL-02",
        fact_key="eta:newcastle",
        value=value,
        event_time=event_time,
        event_time_basis="stated",
        sent_time=sent_time or event_time,
        source_email_id=email_id,
        version=1,
    )


def make_proposal(proposal_id="P1", email_id="E001", supersedes=None) -> s.Proposal:
    return s.Proposal(
        proposal_id=proposal_id,
        email_id=email_id,
        supersedes_proposal_id=supersedes,
        lane=s.Lane(lane="needs_confirm"),
        vessel=s.VesselMatch(vessel_code="VSL-02", status="matched", tier="High", score=0.9),
        voyage=s.VoyageMatch(voyage_no="V202", basis="stated"),
        event=s.EventDecision(
            event_type="Redelivery Notice",
            tier="High",
            unsure=False,
            is_report=False,
            sources_agree=True,
        ),
        statuses=["Action Required"],
        priority=4,
        task=s.TaskDisposition(kind="none"),
        actions=s.RankedActions(items=[]),
    )


# --- tasks: compare-and-swap and the open-key index (11.A) --------------------


def test_store_task_round_trip_derives_priority_and_deadline_from_actions(db):
    with db.transaction() as tx:
        tx.insert_task(make_task())
    task = db.get_task("T1")
    assert task == make_task()
    assert db.task_deadline("T1") == date(2026, 8, 6)


def test_store_e11_s06_second_change_on_the_same_version_is_stale(db):
    with db.transaction() as tx:
        tx.insert_task(make_task())
    with db.transaction() as tx:
        assert (
            tx.update_task(
                "T1",
                expected_version=1,
                changes={"statuses": ["Action Required", "Approval Required"]},
            )
            == 2
        )
    with pytest.raises(st.StaleVersion):
        with db.transaction() as tx:
            tx.update_task("T1", expected_version=1, changes={"statuses": ["Waiting for Reply"]})
    task = db.get_task("T1")
    assert task.statuses == ["Action Required", "Approval Required"]  # nothing overwritten
    assert task.version == 2


def test_store_unknown_task_is_not_found_not_stale(db):
    with pytest.raises(st.NotFound):
        with db.transaction() as tx:
            tx.update_task("NOPE", expected_version=1, changes={"statuses": ["Waiting for Reply"]})


def test_store_e11_s15_second_open_task_with_the_same_key_is_a_duplicate(db):
    with db.transaction() as tx:
        tx.insert_task(make_task("T1"))
    with pytest.raises(st.DuplicateOpenKey):
        with db.transaction() as tx:
            tx.insert_task(make_task("T2"))
    assert db.get_task("T2", missing_ok=True) is None


def test_store_closed_task_frees_its_key_and_is_never_reopened(db):
    with db.transaction() as tx:
        tx.insert_task(make_task("T1"))
        tx.update_task("T1", expected_version=1, changes={"status": "closed"})
    with db.transaction() as tx:
        tx.insert_task(make_task("T2"))  # same key, allowed once T1 is closed
    assert [t.task_id for t in db.open_tasks("VSL-02", "V202")] == ["T2"]
    with pytest.raises(st.InvalidChange):
        with db.transaction() as tx:
            tx.update_task("T1", expected_version=2, changes={"status": "open"})


def test_store_changing_an_action_raises_the_task_version(db):
    with db.transaction() as tx:
        tx.insert_task(make_task())
    with db.transaction() as tx:
        version = tx.update_action(
            "T1", expected_version=1, action_id="T1-A1", changes={"priority": 5}
        )
    assert version == 2
    task = db.get_task("T1")
    assert task.priority == 5 and task.actions[0].priority == 5


def test_store_task_history_is_append_only(db):
    with db.transaction() as tx:
        tx.insert_task(make_task())
        tx.add_task_history("T1", 1, {"kind": "create"}, "E001", "officer", T0)
    with pytest.raises(st.InvalidChange):
        with db.transaction() as tx:
            tx.execute("DELETE FROM task_history")


# --- proposals: one decision only, one open proposal per email ----------------


def test_store_e11_s14_a_proposal_is_decided_only_once(db):
    with db.transaction() as tx:
        tx.save_proposal(make_proposal())
    with db.transaction() as tx:
        tx.set_proposal_status("P1", expected="open", new="applied")
    with pytest.raises(st.AlreadyDecided):
        with db.transaction() as tx:
            tx.set_proposal_status("P1", expected="open", new="applied")
    assert db.get_proposal("P1").status == "applied"


def test_store_x_s08_one_open_proposal_per_email_and_lineage_kept(db):
    with db.transaction() as tx:
        tx.save_proposal(make_proposal("P1"))
    with pytest.raises(st.DuplicateOpenKey):
        with db.transaction() as tx:
            tx.save_proposal(make_proposal("P2", supersedes="P1"))
    with db.transaction() as tx:
        tx.set_proposal_status("P1", expected="open", new="stale")
        tx.save_proposal(make_proposal("P2", supersedes="P1"))
    assert db.get_proposal("P2").supersedes_proposal_id == "P1"
    assert db.get_proposal("P1").status == "stale"


def test_store_held_record_is_saved_with_its_status(db):
    with db.transaction() as tx:
        saved = tx.save_held(s.HeldRecord(email_id="E009", reason="store_unavailable", detail="x"))
    assert saved.status == "held_store_unavailable"


# --- facts: insert-only, current value derived (11.A) -------------------------


def test_store_e11_s16_current_fact_does_not_depend_on_write_order(tmp_path):
    older = make_fact("F1", "5 Aug", T0)
    newer = make_fact("F2", "4 Aug", T0 + timedelta(hours=5))
    results = []
    for name, order in (("a", [older, newer]), ("b", [newer, older])):
        store = st.Store.open(tmp_path / f"{name}.sqlite")
        with store.transaction() as tx:
            for fact in order:
                tx.insert_fact(fact)
        results.append(store.current_facts("VSL-02")["eta:newcastle"].value)
        store.close()
    assert results == ["4 Aug", "4 Aug"]


def test_store_fact_tie_is_broken_by_sent_time_then_email_id(db):
    with db.transaction() as tx:
        tx.insert_fact(make_fact("F1", "A", T0, sent_time=T0, email_id="E002"))
        tx.insert_fact(make_fact("F2", "B", T0, sent_time=T0, email_id="E001"))
    assert db.current_facts("VSL-02")["eta:newcastle"].value == "A"


def test_store_facts_are_insert_only(db):
    with db.transaction() as tx:
        tx.insert_fact(make_fact("F1", "5 Aug", T0))
    for sql in ("UPDATE fact_records SET value = 'x'", "DELETE FROM fact_records"):
        with pytest.raises(st.InvalidChange):
            with db.transaction() as tx:
                tx.execute(sql)


def test_store_e11_s17_retracted_fact_falls_back_to_the_previous_one(db):
    with db.transaction() as tx:
        tx.insert_fact(make_fact("F1", "5 Aug", T0))
        tx.insert_fact(make_fact("F2", "4 Aug", T0 + timedelta(hours=1)))
    with db.transaction() as tx:
        tx.retract_fact("F2")
    assert db.current_facts("VSL-02")["eta:newcastle"].value == "5 Aug"
    lookup = db.fact_lookup("VSL-02")
    assert lookup.status == "ok" and [f.fact_id for f in lookup.facts] == ["F1"]


# --- transactions and unavailability (11.B) -----------------------------------


def test_store_e11_s07_failure_in_the_middle_rolls_everything_back(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as tx:
            tx.insert_task(make_task())
            tx.save_proposal(make_proposal())
            raise RuntimeError("broken in the middle")
    assert db.get_task("T1", missing_ok=True) is None
    assert db.get_proposal("P1", missing_ok=True) is None


def test_store_unavailable_is_reported_as_unavailable_not_as_empty(tmp_path):
    store = st.Store.open(tmp_path / "app.sqlite")
    store.close()  # a closed connection stands in for a broken store
    assert store.task_lookup("VSL-02", "V202").status == "unavailable"
    assert store.fact_lookup("VSL-02").status == "unavailable"
    with pytest.raises(st.StoreUnavailable):
        store.get_task("T1")


def test_store_task_lookup_lists_open_tasks_and_pending_proposal_keys(db):
    proposal = make_proposal()
    proposal = proposal.model_copy(
        update={"task": s.TaskDisposition(kind="create", task_key="VSL-02|V202|delivery")}
    )
    with db.transaction() as tx:
        tx.insert_task(make_task())
        tx.save_proposal(proposal)
    lookup = db.task_lookup("VSL-02", "V202")
    assert lookup.status == "ok"
    assert [t.task_id for t in lookup.tasks] == ["T1"]
    assert lookup.pending_proposals == [
        s.PendingRef(proposal_id="P1", task_key="VSL-02|V202|delivery", kind="create")
    ]


# --- real overlap: two connections, two threads (ChordX 23a 7b) ---------------


def _race(path: Path, work) -> list[str]:
    """Run work(store) in two threads that start together; return each outcome."""
    import threading

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def run() -> None:
        store = st.Store.open(path)
        try:
            barrier.wait()
            work(store)
            outcomes.append("ok")
        except st.StoreError as exc:
            outcomes.append(type(exc).__name__)
        finally:
            store.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(outcomes)


def test_store_e11_s06_two_overlapping_changes_from_the_same_read(tmp_path):
    path = tmp_path / "app.sqlite"
    setup = st.Store.open(path)
    with setup.transaction() as tx:
        tx.insert_task(make_task())
    read_version = setup.get_task("T1").version  # both writers decided on this version
    setup.close()

    def change(store: st.Store) -> None:
        with store.transaction() as tx:
            tx.update_task(
                "T1", expected_version=read_version, changes={"statuses": ["Waiting for Reply"]}
            )

    assert _race(path, change) == ["StaleVersion", "ok"]
    check = st.Store.open(path)
    assert check.get_task("T1").version == 2
    check.close()


def test_store_e11_s15_two_overlapping_creates_with_one_key(tmp_path):
    path = tmp_path / "app.sqlite"
    st.Store.open(path).close()
    ids = iter(["T1", "T2"])
    lock = __import__("threading").Lock()

    def create(store: st.Store) -> None:
        with lock:
            task_id = next(ids)
        with store.transaction() as tx:
            tx.insert_task(make_task(task_id))

    assert _race(path, create) == ["DuplicateOpenKey", "ok"]
    check = st.Store.open(path)
    assert len(check.open_tasks("VSL-02", "V202")) == 1
    check.close()


# --- UI round U2 (2026-09-26) ---------------------------------------------------


def test_store_u2_statuses_and_action_marks_round_trip(db):
    task = make_task()
    task = task.model_copy(
        update={
            "statuses": ["Action Required", "Approval Required", "Waiting for Reply"],
            "actions": [task.actions[0].model_copy(update={"needs_approval": True})],
        }
    )
    with db.transaction() as tx:
        tx.insert_task(task)
    back = db.get_task("T1")
    assert back.statuses == ["Action Required", "Approval Required", "Waiting for Reply"]
    assert back.actions[0].needs_approval is True and back.actions[0].awaiting_reply is False


def test_store_u2_action_mark_change_raises_the_task_version(db):
    with db.transaction() as tx:
        tx.insert_task(make_task())
    with db.transaction() as tx:
        version = tx.update_action(
            "T1", expected_version=1, action_id="T1-A1", changes={"awaiting_reply": True}
        )
    assert version == 2
    assert db.get_task("T1").actions[0].awaiting_reply is True


def test_store_u2_invalid_statuses_are_rejected_before_writing(db):
    with db.transaction() as tx:
        tx.insert_task(make_task())
    with pytest.raises(st.InvalidChange):
        with db.transaction() as tx:
            tx.update_task(
                "T1",
                expected_version=1,
                changes={"statuses": ["FYI - No Action", "Action Required"]},
            )
    assert db.get_task("T1").version == 1
