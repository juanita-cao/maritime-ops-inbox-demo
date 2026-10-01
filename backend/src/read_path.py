"""Read path (design_backend.md P6): D7 d7_rank_open_tasks, E13 e13_build_vessel_view,
E14 e14_list_review_queue, E15 e15_list_dues. Pure functions over what the store returns; the
clock is passed in. [AMENDMENT 2026-09-26 T2.20: a task's deadline is the earliest due date of
its actions at 00:00 in the clock's offset; held emails come after the proposals in the queue.]"""

from datetime import datetime, time

from src import schemas as s

GROUPS = ("Action Required", "Approval Required", "Waiting for Reply")
STATUS_ORDER = [
    "Approval Required",
    "Action Required",
    "Waiting for Reply",
    "FYI - No Action",
    "Close",
]


def _deadline(task: s.Task, now: datetime) -> datetime | None:
    dues = [a.due_date for a in task.actions if a.due_date]
    if not dues:
        return task.deadline
    earliest = datetime.combine(min(dues), time(0, 0), tzinfo=now.tzinfo)
    return min(earliest, task.deadline) if task.deadline else earliest


def _row(task: s.Task, now: datetime) -> s.TaskRow:
    deadline = _deadline(task, now)
    dated = [a for a in task.actions if a.due_date]
    first_due = min(dated, key=lambda a: a.due_date).due_type if dated else None
    return s.TaskRow(task_id=task.task_id, vessel=task.vessel_code, voyage=task.voyage_no, action=task.description,
                     priority=task.priority, due_type=first_due, deadline=deadline,
                     overdue=bool(deadline and deadline < now), statuses=task.statuses,
                     source_email_id=task.source_email_ids[-1] if task.source_email_ids else "",
                     task_key=task.task_key, version=task.version, actions=task.actions)  # fmt: skip


def d7_rank_open_tasks(tasks: list[s.Task], now: datetime) -> s.RankedTaskList:
    """D7 Ranking (U1, U2): a task is listed in the group of each of its statuses; inside a group
    overdue first, then priority (high first), then the earliest deadline, then id."""
    rows = [_row(t, now) for t in tasks if t.status == "open"]
    far = datetime.max.replace(tzinfo=now.tzinfo)
    groups = []
    for name in GROUPS:
        items = sorted((r for r in rows if name in r.statuses),
                       key=lambda r: (not r.overdue, -r.priority, r.deadline or far, r.task_id))  # fmt: skip
        if items:
            groups.append(s.TaskGroup(name=name, items=items))
    return s.RankedTaskList(groups=groups)


def e15_list_dues(tasks: list[s.Task], now: datetime, store_status: str = "ok") -> s.DueList:
    """E15 Select (U1): every action of an open task with a due date; soonest first, then priority."""
    if store_status != "ok":
        return s.DueList(store_status="unavailable")
    today = now.date()
    items = [
        s.DueRow(
            task_id=t.task_id,
            action_id=a.action_id,
            vessel=t.vessel_code,
            voyage=t.voyage_no,
            action=a.description,
            due_type=a.due_type,
            due_other=a.due_other,
            due_date=a.due_date,
            priority=a.priority,
            overdue=a.due_date < today,
        )  # fmt: skip
        for t in tasks
        if t.status == "open"
        for a in t.actions
        if a.due_date
    ]
    items.sort(key=lambda r: (r.due_date, -r.priority, r.task_id, r.action_id))
    return s.DueList(items=items, store_status="ok")


def e14_list_review_queue(rows: list[dict], store_status: str = "ok") -> s.ReviewQueue:
    """E14 Select: open and held proposals, apart from confirmed tasks; the highest status first
    (design_knowledge section 4 order), then the email time; held emails after them."""
    if store_status != "ok":
        return s.ReviewQueue(store_status="unavailable")
    shown = [r for r in rows if r["status"] in ("open", "held_blocked", "held_store_unavailable")]
    far = datetime.max
    items = []
    for r in sorted(shown, key=lambda r: _queue_key(r, far)):
        p: s.Proposal | None = r["proposal"]
        items.append(s.ReviewRow(proposal_id=r["proposal_id"], email_id=r["email_id"],
                                 vessel=p.vessel.vessel_code if p else None, event_type=p.event.event_type if p else None,
                                 statuses=p.statuses if p else None, status=r["status"]))  # fmt: skip
    return s.ReviewQueue(items=items, store_status="ok")


def _queue_key(r: dict, far: datetime):
    p = r["proposal"]
    rank = (
        min((STATUS_ORDER.index(x) for x in p.statuses), default=len(STATUS_ORDER))
        if p
        else len(STATUS_ORDER) + 1
    )
    sent = r["sent_time"].replace(tzinfo=None) if r["sent_time"] else far
    return (rank, sent, r["email_id"])


def e13_build_vessel_view(vessel_code: str, facts: list[s.FactRecord], tasks: list[s.Task], applied: list[dict],
                          now: datetime) -> s.VesselView:  # fmt: skip
    """E13 Transform: current value per fact (latest event time, then sent time, then email id);
    older ones kept as superseded (list facts such as nor:{port}:{n} have their own keys); the
    timeline by event time, not arrival; the vessel's open tasks; the automatic applies."""
    floor = datetime.min.replace(tzinfo=now.tzinfo)
    current: dict[str, s.FactRecord] = {}
    for f in facts:
        best = current.get(f.fact_key)
        if best is None or (f.event_time, f.sent_time or floor, f.source_email_id) > (
            best.event_time,
            best.sent_time or floor,
            best.source_email_id,
        ):
            current[f.fact_key] = f
    rows = sorted(
        (s.FactRow(fact_key=f.fact_key, value=f.value, event_time=f.event_time, source_email_id=f.source_email_id,
                   superseded=current[f.fact_key].fact_id != f.fact_id) for f in facts),
        key=lambda r: (r.fact_key, r.event_time),
    )  # fmt: skip
    events = {r["email_id"]: r["proposal"].event.event_type for r in applied if r["proposal"]}
    by_email: dict[str, list[s.FactRecord]] = {}
    for f in facts:
        by_email.setdefault(f.source_email_id, []).append(f)
    timeline = sorted(
        (s.TimelineRow(event_time=min(x.event_time for x in fs), event_type=events.get(eid, "General / FYI"),
                       email_id=eid, changed_fact_keys=sorted({x.fact_key for x in fs})) for eid, fs in by_email.items()),
        key=lambda r: (r.event_time, r.email_id),
    )  # fmt: skip
    auto = [
        s.AutoAppliedRow(
            email_id=r["email_id"],
            fact_keys=[c.fact_key for c in r["proposal"].fact_changes],
            applied_at=r["sent_time"] or now,
            undo_available=True,
        )  # fmt: skip
        for r in applied
        if r["proposal"]
        and r["proposal"].lane.lane == "auto_apply"
        and r["proposal"].vessel.vessel_code == vessel_code
    ]
    return s.VesselView(vessel_code=vessel_code, facts=rows, timeline=timeline,
                        open_tasks=[_row(t, now) for t in tasks if t.status == "open" and t.vessel_code == vessel_code],
                        auto_applied=auto)  # fmt: skip
