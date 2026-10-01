"""T2.20 read path: D7-S01 to S10, E13-S01 to S04, E14-S01 to S03, E15-S01 to S05
(design_backend.md sections 10, 10.3, 10.5, 10.6, 10.8)."""

from datetime import date, datetime, timedelta, timezone

from src import read_path as r
from src.schemas import (
    EventDecision, FactChange, FactRecord, Evidence, Lane, Proposal, RankedActions, Task, TaskAction, TaskDisposition,
    VesselMatch, VoyageMatch,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 1, 0, 0, tzinfo=CST)


def task(tid, statuses=("Action Required",), priority=3, due=None, status="open", vessel="VSL-12"):
    actions = [TaskAction(action_id=f"{tid}-A", task_id=tid, action_type="Check CP Terms", description=f"do {tid}",
                          priority=priority, due_type="Redelivery", due_date=due, set_by="ai", source_email_id="E1")]  # fmt: skip
    return Task(task_id=tid, task_key=f"{vessel}|V202|{tid}", vessel_code=vessel, voyage_no="V202", action_type="Check CP Terms",
                description=f"do {tid}", statuses=list(statuses), status=status, version=1, source_email_ids=["E1"],
                priority=priority, actions=actions)  # fmt: skip


def groups(ranked):
    return {g.name: [i.task_id for i in g.items] for g in ranked.groups}


def test_d7_s01_s07_grouped_by_status():
    out = r.d7_rank_open_tasks(
        [task("T1"), task("T2", ["Approval Required"]), task("T3", ["Waiting for Reply"])], NOW
    )
    assert groups(out) == {
        "Action Required": ["T1"],
        "Approval Required": ["T2"],
        "Waiting for Reply": ["T3"],
    }


def test_d7_s02_deadline_exactly_now_is_not_overdue():
    out = r.d7_rank_open_tasks([task("T1", due=date(2026, 8, 1))], NOW)
    assert out.groups[0].items[0].overdue is False
    later = r.d7_rank_open_tasks([task("T1", due=date(2026, 8, 1))], NOW + timedelta(seconds=1))
    assert later.groups[0].items[0].overdue is True


def test_d7_s03_s09_overdue_first_even_at_a_lower_priority():
    out = r.d7_rank_open_tasks(
        [
            task("T1", priority=5, due=date(2026, 8, 5)),
            task("T2", priority=2, due=date(2026, 7, 30)),
        ],
        NOW,
    )
    assert groups(out)["Action Required"] == ["T2", "T1"]


def test_d7_s04_s05_closed_tasks_not_listed_and_empty_is_empty():
    assert r.d7_rank_open_tasks([task("T1", status="closed")], NOW).groups == []
    assert r.d7_rank_open_tasks([], NOW).groups == []


def test_d7_s06_s10_a_task_is_listed_in_each_of_its_groups():
    out = r.d7_rank_open_tasks(
        [task("T1", ["Action Required", "Approval Required", "Waiting for Reply"])], NOW
    )
    assert groups(out) == {
        "Action Required": ["T1"],
        "Approval Required": ["T1"],
        "Waiting for Reply": ["T1"],
    }


def test_d7_rows_carry_version_and_actions_for_the_update():
    row = r.d7_rank_open_tasks([task("T1")], NOW).groups[0].items[0]
    assert (row.version, row.task_key, [a.action_id for a in row.actions]) == (1, "VSL-12|V202|T1", ["T1-A"])


def test_d7_s08_same_deadline_higher_priority_first():
    out = r.d7_rank_open_tasks(
        [
            task("T1", priority=3, due=date(2026, 8, 5)),
            task("T2", priority=5, due=date(2026, 8, 5)),
        ],
        NOW,
    )
    assert groups(out)["Action Required"] == ["T2", "T1"]


def test_e15_s01_to_s04_dues_soonest_first_then_priority_and_overdue():
    tasks = [task("T1", priority=3, due=date(2026, 8, 3)), task("T2", priority=5, due=date(2026, 8, 3)),
             task("T3", due=None), task("T4", due=date(2026, 7, 31), status="closed"), task("T5", due=date(2026, 7, 31)),
             task("T6", due=date(2026, 8, 1))]  # fmt: skip
    out = r.e15_list_dues(tasks, NOW)
    assert [(d.task_id, d.overdue) for d in out.items] == [
        ("T5", True),
        ("T6", False),
        ("T2", False),
        ("T1", False),
    ]


def test_e15_s05_store_unavailable_is_not_an_empty_list():
    assert r.e15_list_dues([], NOW, store_status="unavailable").store_status == "unavailable"


def proposal(pid, statuses, email="E1", lane="needs_confirm", facts=()):
    return Proposal(proposal_id=pid, email_id=email, lane=Lane(lane=lane),
                    vessel=VesselMatch(vessel_code="VSL-12", status="matched", tier="High", score=1.0),
                    voyage=VoyageMatch(voyage_no="V202", basis="stated"),
                    event=EventDecision(event_type="Redelivery Notice", tier="High", unsure=False, is_report=False, sources_agree=True),
                    statuses=statuses, priority=3, task=TaskDisposition(kind="none"), actions=RankedActions(),
                    fact_changes=list(facts))  # fmt: skip


def row(pid, status, statuses=None, hours=0, email="E1"):
    return {"proposal_id": pid, "email_id": email, "status": status,
            "proposal": proposal(pid, statuses, email) if statuses else None, "held": None if statuses else {"reason": "x"},
            "sent_time": NOW + timedelta(hours=hours), "subject": "s"}  # fmt: skip


def test_e14_s01_open_and_held_listed_by_highest_status_then_time_held_last():
    rows = [row("P1", "open", ["Action Required"], 1), row("P2", "open", ["Approval Required"], 5),
            row("H1", "held_blocked", None, 0), row("P3", "open", ["Action Required"], 0)]  # fmt: skip
    assert [i.proposal_id for i in r.e14_list_review_queue(rows).items] == ["P2", "P3", "P1", "H1"]


def test_e14_s02_applied_and_rejected_not_listed():
    rows = [row("P1", "applied", ["Action Required"]), row("P2", "rejected", ["Action Required"])]
    assert r.e14_list_review_queue(rows).items == []


def test_e14_s03_store_unavailable():
    assert r.e14_list_review_queue([], store_status="unavailable").store_status == "unavailable"


def fact(fid, key, value, hours, email):
    return FactRecord(fact_id=fid, vessel_code="VSL-12", fact_key=key, value=value, event_time=NOW + timedelta(hours=hours),
                      event_time_basis="stated", sent_time=NOW + timedelta(hours=hours), source_email_id=email, version=1)  # fmt: skip


def test_e13_s01_s03_latest_is_current_older_kept_timeline_by_event_time():
    facts = [
        fact("F2", "eta:newcastle", "4 Aug", 5, "E2"),
        fact("F1", "eta:newcastle", "5 Aug", 0, "E1"),
    ]
    view = r.e13_build_vessel_view("VSL-12", facts, [], [], NOW)
    assert [(f.value, f.superseded) for f in view.facts] == [("5 Aug", True), ("4 Aug", False)]
    assert [t.email_id for t in view.timeline] == ["E1", "E2"]


def test_e13_s02_vessel_with_no_facts_is_an_empty_view():
    view = r.e13_build_vessel_view("VSL-11", [], [], [], NOW)
    assert (view.facts, view.timeline, view.open_tasks) == ([], [], [])


def test_e13_s04_list_fact_with_two_records_shows_both():
    facts = [
        fact("F1", "nor:dampier:1", "25 Jul 13:50", 0, "E1"),
        fact("F2", "nor:dampier:2", "26 Jul 08:00", 5, "E2"),
    ]
    view = r.e13_build_vessel_view("VSL-12", facts, [], [], NOW)
    assert [(f.fact_key, f.superseded) for f in view.facts] == [
        ("nor:dampier:1", False),
        ("nor:dampier:2", False),
    ]


def test_e13_open_tasks_and_auto_applied_rows_of_the_vessel():
    change = FactChange(fact_key="eta:newcastle", new="4 Aug", event_time=NOW, event_time_basis="stated",
                        evidence=Evidence(quote="ETA", source="new_text"))  # fmt: skip
    applied = [{"email_id": "E1", "proposal": proposal("P1", ["FYI - No Action"], lane="auto_apply", facts=[change]),
                "sent_time": NOW, "status": "applied"}]  # fmt: skip
    view = r.e13_build_vessel_view(
        "VSL-12", [], [task("T1"), task("T9", vessel="VSL-11")], applied, NOW
    )
    assert [t.task_id for t in view.open_tasks] == ["T1"]
    assert [(a.email_id, a.fact_keys) for a in view.auto_applied] == [("E1", ["eta:newcastle"])]
