"""E11 e11_apply_changes and E12 e12_record_correction: the eXecute nodes that write the
officer's decision (design_backend.md E11, E12 rows; 11.A guards; U1, U2 amendments).

Every write of one decision happens in one transaction: the proposal moves open to applied
(compare-and-swap), the task is written against the version D6 read (compare-and-swap), facts
are inserted (never overwritten), and a history row, an undo record and an audit row are added.
Any failure rolls everything back and the proposal stays open."""

import logging
import uuid
from datetime import datetime

from src import schemas as s
from src import store as st

log = logging.getLogger(__name__)


class InvalidDecision(ValueError):
    """The input breaks a rule (E11-S20, S21, S24, S26, S27); nothing is changed."""


def _token() -> str:
    return uuid.uuid4().hex


def _task_actions(task_id: str, proposal: s.Proposal, decision: s.Decision) -> list[s.TaskAction]:
    """The confirmed actions: the officer's list when given (U1), else the proposal's."""
    if decision.actions is not None:
        source = [(a, a.set_by) for a in decision.actions]
    else:
        source = [(s.ConfirmedAction(**a.model_dump(include={"action_type", "description", "priority", "due_type",
                                                             "due_other", "needs_approval", "awaiting_reply"}),
                                     due_date=a.due, set_by="ai"), "ai") for a in proposal.actions.items]  # fmt: skip
    return [
        s.TaskAction(
            action_id=f"{task_id}-{_token()[:8]}",
            task_id=task_id,
            action_type=a.action_type,
            description=a.description,
            priority=a.priority,
            due_type=a.due_type,
            due_other=a.due_other,
            due_date=a.due_date,
            set_by=set_by,
            source_email_id=proposal.email_id,
            needs_approval=a.needs_approval,
            awaiting_reply=a.awaiting_reply,
        )  # fmt: skip
        for a, set_by in source
    ]


def _check(proposal: s.Proposal, decision: s.Decision) -> None:
    if decision.kind == "auto" and proposal.lane.lane != "auto_apply":
        raise InvalidDecision("an automatic decision needs the automatic lane")
    if (
        decision.kind in ("approve", "edit")
        and proposal.task.close_warning
        and not (decision.reason or "").strip()
    ):
        raise InvalidDecision("approving this close needs a reason (close_warning)")
    if (
        decision.statuses
        and "Close" in decision.statuses
        and proposal.task.kind != "close_proposal"
    ):
        raise InvalidDecision("the status Close needs a close proposal")


def e11_apply_changes(proposal_id: str, decision: s.Decision, store: st.Store) -> s.ApplyResult:
    """E11 eXecute for a proposal and the officer's (or the system's) decision."""
    proposal = store.get_proposal(proposal_id)
    _check(proposal, decision)
    at = decision.decided_at
    actor = decision.actor
    try:
        with store.transaction() as tx:
            if decision.kind == "reject":
                tx.set_proposal_status(proposal_id, expected="open", new="rejected")
                tx.add_audit(
                    actor, "reject", "proposal", proposal_id, {"reason": decision.reason}, at
                )
                result = s.ApplyResult(status="noop", reason="no_change")
            else:
                tx.set_proposal_status(proposal_id, expected="open", new="applied")
                result = _apply(tx, proposal, decision, at, actor)
    except st.AlreadyDecided:
        return s.ApplyResult(status="noop", reason="already_decided")
    except st.StaleVersion as exc:
        return s.ApplyResult(
            status="conflict", reason="stale_task_version", conflict_detail=str(exc)
        )
    except st.DuplicateOpenKey as exc:
        return s.ApplyResult(
            status="conflict", reason="duplicate_open_key", conflict_detail=str(exc)
        )
    except _Conflict as exc:
        return s.ApplyResult(status="conflict", reason=exc.reason, conflict_detail=str(exc))
    except st.StoreError as exc:
        return s.ApplyResult(status="rolled_back", conflict_detail=f"{type(exc).__name__}: {exc}")
    e12_record_correction(proposal, decision, store)
    return result


class _Conflict(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


def _apply(
    tx: st.Tx, proposal: s.Proposal, decision: s.Decision, at: datetime, actor: str
) -> s.ApplyResult:
    fact_ids = []
    for change in proposal.fact_changes:
        fact_id = f"F-{_token()[:12]}"
        tx.insert_fact(s.FactRecord(
            fact_id=fact_id, vessel_code=proposal.vessel.vessel_code or "", fact_key=change.fact_key, value=change.new,
            event_time=change.event_time or at, event_time_basis=change.event_time_basis or "email_sent_time",
            sent_time=change.event_time or at, source_email_id=proposal.email_id, version=(change.base_version or 0) + 1,
        ))  # fmt: skip
        fact_ids.append(fact_id)
    task = proposal.task
    statuses = [x for x in (decision.statuses or proposal.statuses) if x != "Close"] or [
        "Action Required"
    ]
    token, task_id, undo_kind, produced, previous = _token(), None, None, None, None
    if task.kind == "create":
        task_id = f"T-{_token()[:10]}"
        actions = _task_actions(task_id, proposal, decision)
        first = actions[0] if actions else None
        tx.insert_task(s.Task(
            task_id=task_id, task_key=task.task_key, vessel_code=proposal.vessel.vessel_code or "",
            voyage_no=proposal.voyage.voyage_no, action_type=first.action_type if first else proposal.event.event_type,
            description=first.description if first else proposal.event.event_type, statuses=statuses, status="open",
            version=1, source_email_ids=[proposal.email_id], priority=max([a.priority for a in actions], default=proposal.priority),
            actions=actions,
        ))  # fmt: skip
        undo_kind, produced, previous = "task_create", 1, None
        tx.add_task_history(
            task_id,
            1,
            {"kind": "create", "proposal": proposal.proposal_id},
            proposal.email_id,
            actor,
            at,
        )
    elif task.kind in ("update", "close_proposal"):
        task_id = task.target_task_id
        current = tx.get_task(task_id)
        if current.status == "closed":
            raise _Conflict("stale_task_version", f"task {task_id} is already closed")  # E11-S09
        previous = current.model_dump(mode="json")
        if task.kind == "update":
            new_actions = [a for a in _task_actions(task_id, proposal, decision)
                           if a.action_type not in [x.action_type for x in current.actions]]  # fmt: skip
            for a in new_actions:
                tx.insert_action(a)
            changes = {"statuses": task.new_statuses or statuses,
                       "source_email_ids": [*current.source_email_ids, proposal.email_id]}  # fmt: skip
            produced = tx.update_task(task_id, task.target_task_version, changes)
            undo_kind = "task_update"
            detail = {
                "kind": "update",
                "added_actions": [a.action_id for a in new_actions],
                "statuses": changes["statuses"],
            }
        else:
            produced = tx.update_task(task_id, task.target_task_version,
                                      {"status": "closed", "source_email_ids": [*current.source_email_ids, proposal.email_id]})  # fmt: skip
            undo_kind, detail = "task_close", {"kind": "close", "reason": decision.reason}
        previous["added_actions"] = detail.get("added_actions", [])
        tx.add_task_history(task_id, produced, detail, proposal.email_id, actor, at)
    if undo_kind:
        tx.add_undo(token, undo_kind, task_id, produced, {"previous": previous, "facts": fact_ids})
    elif fact_ids:
        tx.add_undo(token, "facts", proposal.proposal_id, None, {"facts": fact_ids})
    else:
        token = None
    tx.add_audit(actor, decision.kind, "proposal", proposal.proposal_id,
                 {"task": task_id, "task_kind": task.kind, "facts": fact_ids}, at)  # fmt: skip
    return s.ApplyResult(
        status="applied", applied_fact_ids=fact_ids, applied_task_id=task_id, undo_token=token
    )


def e11_apply_manual(change: s.ManualTaskChange, store: st.Store, at: datetime) -> s.ApplyResult:
    """E11 for a ManualTaskChange from the Vessel page (Update): same guards, history, undo."""
    token = _token()
    try:
        with store.transaction() as tx:
            current = tx.get_task(change.task_id)
            if current.version != change.expected_version:
                raise st.StaleVersion(f"task {change.task_id} is at version {current.version}")
            if current.status == "closed":
                raise _Conflict("stale_task_version", f"task {change.task_id} is closed")
            previous = current.model_dump(mode="json")
            version = change.expected_version
            for ac in change.action_changes:
                fields = ac.model_dump(exclude={"action_id"}, exclude_none=True)
                if fields:
                    version = tx.update_action(change.task_id, version, ac.action_id, {**fields})
            task_changes = {}
            if change.new_statuses is not None:
                task_changes["statuses"] = change.new_statuses
            if change.close:
                task_changes["status"] = "closed"
            if task_changes:
                version = tx.update_task(change.task_id, version, task_changes)
            detail = {"kind": "manual", "statuses": change.new_statuses, "close": change.close,
                      "action_changes": [a.model_dump(exclude_none=True) for a in change.action_changes],
                      "reason": change.reason}  # fmt: skip
            tx.add_task_history(change.task_id, version, detail, None, change.actor, at)
            tx.add_undo(
                token,
                "task_manual",
                change.task_id,
                version,
                {"previous": {**previous, "added_actions": []}},
            )
            tx.add_audit(change.actor, "manual_change", "task", change.task_id, detail, at)
    except st.StaleVersion as exc:
        return s.ApplyResult(
            status="conflict", reason="stale_task_version", conflict_detail=str(exc)
        )
    except _Conflict as exc:
        return s.ApplyResult(status="conflict", reason=exc.reason, conflict_detail=str(exc))
    except st.NotFound as exc:
        return s.ApplyResult(
            status="conflict", reason="stale_task_version", conflict_detail=str(exc)
        )
    except st.StoreError as exc:
        return s.ApplyResult(status="rolled_back", conflict_detail=f"{type(exc).__name__}: {exc}")
    return s.ApplyResult(status="applied", applied_task_id=change.task_id, undo_token=token)


def e11_undo(token: str, store: st.Store, actor: str, at: datetime) -> s.ApplyResult:
    """Undo one applied change. A task undo only while no later change exists (E11-S13); a fact
    undo retracts the record and the current value is derived again (E11-S17). A closed task is
    never reopened, so the undo of a close is a conflict."""
    try:
        with store.transaction() as tx:
            record = tx.use_undo(token)
            kind, target, payload = record["kind"], record["target_id"], record["payload"]
            for fact_id in payload.get("facts", []):
                tx.retract_fact(fact_id)
            if kind in ("task_create", "task_update", "task_close", "task_manual"):
                current = tx.get_task(target)
                if current.version != record["produced_version"]:
                    raise _Conflict(
                        "later_change_exists", f"task {target} changed after this change"
                    )
                if kind == "task_close":
                    raise _Conflict(
                        "later_change_exists",
                        "a closed task is never reopened; create a new task instead",
                    )
                if kind == "task_create":
                    version = tx.update_task(target, current.version, {"status": "closed"})
                else:
                    before = payload["previous"]
                    for action_id in before.get("added_actions", []):
                        tx.delete_action(action_id)
                    for a in before["actions"]:
                        keep = {k: a[k] for k in ("priority", "due_type", "due_other", "due_date",
                                                  "needs_approval", "awaiting_reply")}  # fmt: skip
                        if any(x.action_id == a["action_id"] for x in current.actions):
                            tx.update_action(
                                target, tx.get_task(target).version, a["action_id"], keep
                            )
                    version = tx.update_task(target, tx.get_task(target).version, {
                        "statuses": before["statuses"], "source_email_ids": before["source_email_ids"]})  # fmt: skip
                tx.add_task_history(
                    target, version, {"kind": "undo", "undo_of": kind}, None, actor, at
                )
            tx.add_audit(actor, "undo", kind, target, {"token": token}, at)
    except st.AlreadyDecided:
        return s.ApplyResult(status="noop", reason="already_decided")
    except _Conflict as exc:
        return s.ApplyResult(status="conflict", reason=exc.reason, conflict_detail=str(exc))
    except st.StoreError as exc:
        return s.ApplyResult(status="rolled_back", conflict_detail=f"{type(exc).__name__}: {exc}")
    return s.ApplyResult(
        status="applied", applied_task_id=target if kind.startswith("task") else None
    )


def e12_record_correction(
    proposal: s.Proposal, decision: s.Decision, store: st.Store
) -> list[s.CorrectionRecord]:
    """E12 eXecute: what the officer changed next to what was suggested, with the reason. A
    failure here is logged and never changes E11's result (E12-S02)."""
    records: list[s.CorrectionRecord] = []

    def add(field, suggested, final):
        records.append(s.CorrectionRecord(proposal_id=proposal.proposal_id, field=field, suggested=suggested,
                                          final=final, reason=decision.reason))  # fmt: skip

    if decision.kind == "reject":
        add("decision", "approve", "reject")
    if decision.statuses is not None and decision.statuses != proposal.statuses:
        add("statuses", proposal.statuses, decision.statuses)
    overridden = {"vessel_code": proposal.vessel.vessel_code, "voyage_no": proposal.voyage.voyage_no,
                  "event_type": proposal.event.event_type}  # fmt: skip
    for field, final in decision.edits.items():
        if field != "statuses":
            add(field, overridden.get(field, getattr(proposal, field, None)), final)
    if decision.actions is not None:
        suggested = {a.action_type: a for a in proposal.actions.items}
        for a in decision.actions:
            old = suggested.get(a.action_type)
            if old is None:
                add(f"action:{a.action_type}", None, "added")
                continue
            for field, before, after in (("priority", old.priority, a.priority), ("due_type", old.due_type, a.due_type),
                                         ("due_date", old.due, a.due_date), ("needs_approval", old.needs_approval, a.needs_approval),
                                         ("awaiting_reply", old.awaiting_reply, a.awaiting_reply)):  # fmt: skip
                if before != after:
                    add(f"action:{a.action_type}:{field}", before, after)
        for action_type in suggested.keys() - {a.action_type for a in decision.actions}:
            add(f"action:{action_type}", "suggested", "removed")
    try:
        with store.transaction() as tx:
            for record in records:
                tx.add_correction(record, decision.decided_at)
    except st.StoreError:
        log.exception(
            "E12 could not record %d corrections for %s", len(records), proposal.proposal_id
        )
    return records
