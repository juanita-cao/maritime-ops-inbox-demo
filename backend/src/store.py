"""State store (design_backend.md 9.3, 9.4, 11.A, 11.B): SQLite schema, transactions and the
guards that keep the "read, decide, write back" chains safe.

Guards built into the schema, so no caller can forget them:
- one open task per task_key (partial unique index), one open proposal per email;
- tasks change only by compare-and-swap on `version`; a closed task is never reopened;
- fact records and task history are insert-only (the only allowed fact update is
  active -> retracted, used by undo).

Failures keep their meaning apart (11.B): StoreUnavailable (the store cannot be used),
NotFound (a known id that does not exist), StaleVersion (someone changed it meanwhile),
DuplicateOpenKey, AlreadyDecided, InvalidChange. Lookups return status "unavailable" instead
of an empty result when the store cannot be read.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from src import schemas as s


class StoreError(Exception):
    pass


class StoreUnavailable(StoreError):
    """The store cannot be read or written (not the same as "nothing found")."""


class NotFound(StoreError):
    pass


class StaleVersion(StoreError):
    """The record changed since it was read: a conflict, not a failure."""


class DuplicateOpenKey(StoreError):
    pass


class AlreadyDecided(StoreError):
    pass


class InvalidChange(StoreError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    email_id TEXT PRIMARY KEY,
    thread_id TEXT,
    sent_time TEXT,
    direction TEXT,
    subject TEXT,
    parsed_json TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'to_review'
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    email_id TEXT NOT NULL,
    status TEXT NOT NULL,
    supersedes_proposal_id TEXT,
    task_kind TEXT,
    task_key TEXT,
    body_json TEXT NOT NULL
);
-- exactly one open proposal per email (X-S08)
CREATE UNIQUE INDEX IF NOT EXISTS ux_open_proposal ON proposals(email_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    task_key TEXT NOT NULL,
    vessel_code TEXT NOT NULL,
    voyage_no TEXT,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    statuses TEXT NOT NULL,  -- JSON list [AMENDMENT 2026-09-26 U2]
    deadline TEXT,
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    version INTEGER NOT NULL CHECK (version >= 1),
    source_email_ids TEXT NOT NULL,
    base_priority INTEGER NOT NULL CHECK (base_priority BETWEEN 1 AND 5)
);
-- no two open tasks share a key (11.A, E11-S15)
CREATE UNIQUE INDEX IF NOT EXISTS ux_open_task_key ON tasks(task_key) WHERE status = 'open';
CREATE TRIGGER IF NOT EXISTS tasks_never_reopen BEFORE UPDATE OF status ON tasks
WHEN OLD.status = 'closed' AND NEW.status = 'open'
BEGIN SELECT RAISE(ABORT, 'invalid_change: a closed task is never reopened'); END;

CREATE TABLE IF NOT EXISTS task_actions (
    action_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
    due_type TEXT NOT NULL,
    due_other TEXT,
    due_date TEXT,
    set_by TEXT NOT NULL,
    source_email_id TEXT NOT NULL,
    needs_approval INTEGER NOT NULL DEFAULT 0,  -- [AMENDMENT 2026-09-26 U2]
    awaiting_reply INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_history (
    task_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    change_json TEXT NOT NULL,
    email_id TEXT,
    actor TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (task_id, version)
);
CREATE TRIGGER IF NOT EXISTS task_history_no_update BEFORE UPDATE ON task_history
BEGIN SELECT RAISE(ABORT, 'invalid_change: task history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS task_history_no_delete BEFORE DELETE ON task_history
BEGIN SELECT RAISE(ABORT, 'invalid_change: task history is append-only'); END;

CREATE TABLE IF NOT EXISTS fact_records (
    fact_id TEXT PRIMARY KEY,
    vessel_code TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    value TEXT NOT NULL,
    event_time TEXT NOT NULL,
    event_time_basis TEXT NOT NULL,
    sent_time TEXT,
    source_email_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'retracted'))
);
CREATE TRIGGER IF NOT EXISTS facts_no_delete BEFORE DELETE ON fact_records
BEGIN SELECT RAISE(ABORT, 'invalid_change: facts are insert-only'); END;
CREATE TRIGGER IF NOT EXISTS facts_only_retract BEFORE UPDATE ON fact_records
WHEN NOT (OLD.state = 'active' AND NEW.state = 'retracted'
          AND NEW.fact_id IS OLD.fact_id AND NEW.vessel_code IS OLD.vessel_code
          AND NEW.fact_key IS OLD.fact_key AND NEW.value IS OLD.value
          AND NEW.event_time IS OLD.event_time AND NEW.sent_time IS OLD.sent_time
          AND NEW.source_email_id IS OLD.source_email_id AND NEW.version IS OLD.version)
BEGIN SELECT RAISE(ABORT, 'invalid_change: facts are insert-only'); END;

CREATE TABLE IF NOT EXISTS corrections (
    proposal_id TEXT NOT NULL,
    field TEXT NOT NULL,
    suggested TEXT,
    final TEXT,
    reason TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS undo_records (
    undo_token TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    produced_version INTEGER,
    payload_json TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'invalid_change: audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'invalid_change: audit log is append-only'); END;
"""

TASK_FIELDS = {
    "task_key",
    "action_type",
    "description",
    "statuses",
    "deadline",
    "status",
    "source_email_ids",
}
ACTION_FIELDS = {
    "priority",
    "due_type",
    "due_other",
    "due_date",
    "description",
    "needs_approval",
    "awaiting_reply",
}
_STATUSES = TypeAdapter(s.Statuses)


def _ts(value: datetime | None) -> str | None:
    """UTC ISO text, so that text order equals time order."""
    return (
        None if value is None else value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    )


def _dt(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def _day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _map_sqlite_error(exc: sqlite3.Error) -> StoreError | None:
    message = str(exc)
    if isinstance(exc, sqlite3.IntegrityError):
        if "invalid_change" in message:
            return InvalidChange(message)
        if "UNIQUE constraint failed: tasks.task_key" in message:
            return DuplicateOpenKey("an open task with this key already exists")
        if "UNIQUE constraint failed: proposals.email_id" in message:
            return DuplicateOpenKey("this email already has an open proposal")
        return None
    if isinstance(exc, (sqlite3.OperationalError, sqlite3.ProgrammingError, sqlite3.DatabaseError)):
        return StoreUnavailable(message)
    return None


def _run(conn_getter, fn):
    """Run fn(conn), translating sqlite errors into the store's own errors."""
    try:
        return fn(conn_getter())
    except sqlite3.Error as exc:
        mapped = _map_sqlite_error(exc)
        if mapped is None:
            raise
        raise mapped from exc


class _Reader:
    """Read operations, shared by Store (outside a transaction) and Tx (inside one)."""

    def _conn(self) -> sqlite3.Connection:  # pragma: no cover - overridden
        raise NotImplementedError

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return _run(self._conn, lambda c: c.execute(sql, args).fetchall())

    # --- tasks ---
    def _task_from_row(self, row: sqlite3.Row) -> s.Task:
        actions = [
            s.TaskAction(
                action_id=a["action_id"],
                task_id=a["task_id"],
                action_type=a["action_type"],
                description=a["description"],
                priority=a["priority"],
                due_type=a["due_type"],
                due_other=a["due_other"],
                due_date=None if a["due_date"] is None else date.fromisoformat(a["due_date"]),
                set_by=a["set_by"],
                source_email_id=a["source_email_id"],
                needs_approval=bool(a["needs_approval"]),
                awaiting_reply=bool(a["awaiting_reply"]),
            )
            for a in self._q(
                "SELECT * FROM task_actions WHERE task_id = ? ORDER BY rowid", (row["task_id"],)
            )
        ]
        return s.Task(
            task_id=row["task_id"],
            task_key=row["task_key"],
            vessel_code=row["vessel_code"],
            voyage_no=row["voyage_no"],
            action_type=row["action_type"],
            description=row["description"],
            statuses=json.loads(row["statuses"]),
            deadline=_dt(row["deadline"]),
            status=row["status"],
            version=row["version"],
            source_email_ids=json.loads(row["source_email_ids"]),
            priority=max((a.priority for a in actions), default=row["base_priority"]),
            actions=actions,
        )

    def get_task(self, task_id: str, missing_ok: bool = False) -> s.Task | None:
        rows = self._q("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        if not rows:
            if missing_ok:
                return None
            raise NotFound(f"task {task_id}")
        return self._task_from_row(rows[0])

    def open_tasks(self, vessel_code: str, voyage_no: str | None) -> list[s.Task]:
        rows = self._q(
            "SELECT * FROM tasks WHERE status = 'open' AND vessel_code = ? AND voyage_no IS ? ORDER BY rowid",
            (vessel_code, voyage_no),
        )
        return [self._task_from_row(r) for r in rows]

    def task_deadline(self, task_id: str) -> date | None:
        rows = self._q("SELECT MIN(due_date) AS d FROM task_actions WHERE task_id = ?", (task_id,))
        value = rows[0]["d"] if rows else None
        return None if value is None else date.fromisoformat(value)

    # --- proposals ---
    def get_proposal(self, proposal_id: str, missing_ok: bool = False) -> s.Proposal | None:
        rows = self._q("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,))
        if not rows:
            if missing_ok:
                return None
            raise NotFound(f"proposal {proposal_id}")
        proposal = s.Proposal.model_validate_json(rows[0]["body_json"])
        return proposal.model_copy(update={"status": rows[0]["status"]})

    # --- facts ---
    def _active_facts(self, vessel_code: str) -> list[s.FactRecord]:
        rows = self._q(
            "SELECT * FROM fact_records WHERE vessel_code = ? AND state = 'active' "
            "ORDER BY event_time, sent_time, source_email_id",
            (vessel_code,),
        )
        return [
            s.FactRecord(
                fact_id=r["fact_id"],
                vessel_code=r["vessel_code"],
                fact_key=r["fact_key"],
                value=r["value"],
                event_time=_dt(r["event_time"]),
                event_time_basis=r["event_time_basis"],
                sent_time=_dt(r["sent_time"]),
                source_email_id=r["source_email_id"],
                version=r["version"],
                state=r["state"],
            )
            for r in rows
        ]

    def current_facts(self, vessel_code: str) -> dict[str, s.FactRecord]:
        """Current value per fact key: latest event_time, then sent_time, then email id (11.A)."""
        current: dict[str, s.FactRecord] = {}
        for fact in self._active_facts(vessel_code):  # ascending, so the last one wins
            current[fact.fact_key] = fact
        return current

    # --- emails and threads (pipeline) ---
    def get_email(self, email_id: str) -> s.ParsedEmail | None:
        rows = self._q("SELECT parsed_json FROM emails WHERE email_id = ?", (email_id,))
        return s.ParsedEmail.model_validate_json(rows[0]["parsed_json"]) if rows else None

    def email_ids(self) -> list[str]:
        return [r["email_id"] for r in self._q("SELECT email_id FROM emails ORDER BY rowid")]

    def open_proposal_id(self, email_id: str) -> str | None:
        rows = self._q(
            "SELECT proposal_id FROM proposals WHERE email_id = ? AND status = 'open'", (email_id,)
        )
        return rows[0]["proposal_id"] if rows else None

    def thread_index(self) -> s.ThreadIndex:
        """E2's input: every stored email with its thread and its final vessel and voyage (the
        latest proposal that is not stale or rejected; an officer's correction is in it)."""
        from src.e_nodes import normalise_subject  # the one normaliser of E1 and E2

        entries = []
        for row in self._q("SELECT email_id, thread_id, parsed_json FROM emails ORDER BY rowid"):
            email = s.ParsedEmail.model_validate_json(row["parsed_json"])
            latest = self._q(
                "SELECT body_json FROM proposals WHERE email_id = ? AND status IN ('open', 'applied') "
                "ORDER BY rowid DESC LIMIT 1",
                (row["email_id"],),
            )
            vessel = voyage = None
            if latest:
                body = json.loads(latest[0]["body_json"])
                vessel = (body.get("vessel") or {}).get("vessel_code")
                voyage = (body.get("voyage") or {}).get("voyage_no")
            entries.append(s.ThreadIndexEntry(
                email_id=email.email_id, thread_id=row["thread_id"] or f"T-{email.email_id}",
                sent_time=email.sent_time, subject_norm=email.subject_norm,
                quoted_subjects_norm=[normalise_subject(q) for q in email.quoted_subjects],
                vessel_code=vessel, voyage_no=voyage,
            ))  # fmt: skip
        return s.ThreadIndex(entries=entries)

    # --- read path (D7, E13, E14, E15) ---
    def all_tasks(self, status: str = "open", vessel_code: str | None = None) -> list[s.Task]:
        sql, args = "SELECT * FROM tasks WHERE status = ?", [status]
        if vessel_code:
            sql, args = sql + " AND vessel_code = ?", [*args, vessel_code]
        return [self._task_from_row(r) for r in self._q(sql + " ORDER BY rowid", tuple(args))]

    def fact_history(self, vessel_code: str) -> list[s.FactRecord]:
        """Every active fact record of a vessel (current and older ones)."""
        return self._active_facts(vessel_code)

    def proposal_rows(self, statuses: tuple[str, ...]) -> list[dict]:
        """Proposals (or held records) with the email's time, for the review queue and timeline."""
        marks = ",".join("?" for _ in statuses)
        rows = self._q(
            f"SELECT p.proposal_id, p.email_id, p.status, p.body_json, e.sent_time, e.subject FROM proposals p "
            f"LEFT JOIN emails e ON e.email_id = p.email_id WHERE p.status IN ({marks}) ORDER BY p.rowid",
            statuses,
        )
        out = []
        for r in rows:
            body = json.loads(r["body_json"])
            proposal = s.Proposal.model_validate(body) if "lane" in body else None
            out.append({"proposal_id": r["proposal_id"], "email_id": r["email_id"], "status": r["status"],
                        "proposal": proposal, "held": None if proposal else body,
                        "sent_time": _dt(r["sent_time"]), "subject": r["subject"]})  # fmt: skip
        return out

    def corrections(self, proposal_id: str) -> list[s.CorrectionRecord]:
        rows = self._q(
            "SELECT * FROM corrections WHERE proposal_id = ? ORDER BY rowid", (proposal_id,)
        )
        return [s.CorrectionRecord(proposal_id=r["proposal_id"], field=r["field"], suggested=json.loads(r["suggested"]),
                                   final=json.loads(r["final"]), reason=r["reason"]) for r in rows]  # fmt: skip

    def task_history(self, task_id: str) -> list[dict]:
        rows = self._q("SELECT * FROM task_history WHERE task_id = ? ORDER BY version", (task_id,))
        return [
            {"version": r["version"], "change": json.loads(r["change_json"]), "actor": r["actor"]}
            for r in rows
        ]

    def audit_count(self) -> int:
        return self._q("SELECT COUNT(*) AS n FROM audit_log")[0]["n"]

    def fact_lookup(self, vessel_code: str) -> s.FactLookup:
        try:
            return s.FactLookup(status="ok", facts=self._active_facts(vessel_code))
        except StoreUnavailable:
            return s.FactLookup(status="unavailable")

    def task_lookup(self, vessel_code: str, voyage_no: str | None) -> s.TaskLookup:
        try:
            prefix = f"{vessel_code}|{voyage_no or 'UNK'}|"
            pending = [
                s.PendingRef(
                    proposal_id=r["proposal_id"], task_key=r["task_key"], kind=r["task_kind"]
                )
                for r in self._q(
                    "SELECT proposal_id, task_key, task_kind FROM proposals WHERE status = 'open' "
                    "AND task_key IS NOT NULL AND substr(task_key, 1, ?) = ? ORDER BY rowid",
                    (len(prefix), prefix),
                )
            ]
            return s.TaskLookup(
                status="ok",
                tasks=self.open_tasks(vessel_code, voyage_no),
                pending_proposals=pending,
            )
        except StoreUnavailable:
            return s.TaskLookup(status="unavailable")


class Tx(_Reader):
    """Writes inside one SQLite transaction (opened by Store.transaction)."""

    def __init__(self, conn: sqlite3.Connection):
        self._c = conn

    def _conn(self) -> sqlite3.Connection:
        return self._c

    def execute(self, sql: str, args: tuple = ()) -> int:
        return _run(self._conn, lambda c: c.execute(sql, args).rowcount)

    # --- tasks ---
    def insert_task(self, task: s.Task) -> None:
        self.execute(
            "INSERT INTO tasks (task_id, task_key, vessel_code, voyage_no, action_type, description, "
            "statuses, deadline, status, version, source_email_ids, base_priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.task_id,
                task.task_key,
                task.vessel_code,
                task.voyage_no,
                task.action_type,
                task.description,
                json.dumps(task.statuses),
                _ts(task.deadline),
                task.status,
                task.version,
                json.dumps(task.source_email_ids),
                task.priority,
            ),
        )
        for action in task.actions:
            self.insert_action(action)

    def insert_action(self, action: s.TaskAction) -> None:
        self.execute(
            "INSERT INTO task_actions (action_id, task_id, action_type, description, priority, "
            "due_type, due_other, due_date, set_by, source_email_id, needs_approval, awaiting_reply) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                action.action_id,
                action.task_id,
                action.action_type,
                action.description,
                action.priority,
                action.due_type,
                action.due_other,
                _day(action.due_date),
                action.set_by,
                action.source_email_id,
                int(action.needs_approval),
                int(action.awaiting_reply),
            ),
        )

    def _bump_version(self, task_id: str, expected_version: int, sets: dict[str, Any]) -> int:
        """Compare-and-swap on the task version; returns the new version."""
        assignments = "".join(f"{k} = ?, " for k in sets)
        changed = self.execute(
            f"UPDATE tasks SET {assignments}version = version + 1 WHERE task_id = ? AND version = ?",
            (*sets.values(), task_id, expected_version),
        )
        if changed == 0:
            if not self._q("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)):
                raise NotFound(f"task {task_id}")
            raise StaleVersion(f"task {task_id} is no longer at version {expected_version}")
        return expected_version + 1

    def update_task(self, task_id: str, expected_version: int, changes: dict[str, Any]) -> int:
        unknown = set(changes) - TASK_FIELDS
        if unknown:
            raise InvalidChange(f"task fields cannot be changed: {sorted(unknown)}")
        sets: dict[str, Any] = {}
        for key, value in changes.items():
            if key == "statuses":
                try:
                    value = json.dumps(_STATUSES.validate_python(value))
                except ValidationError as exc:
                    raise InvalidChange(f"statuses {value!r}: {exc.errors()[0]['msg']}") from None
            elif key == "deadline":
                value = _ts(value)
            elif key == "source_email_ids":
                value = json.dumps(value)
            sets[key] = value
        return self._bump_version(task_id, expected_version, sets)

    def update_action(
        self, task_id: str, expected_version: int, action_id: str, changes: dict[str, Any]
    ) -> int:
        """Change one action; the task's version rises (a change to an action is a task change)."""
        unknown = set(changes) - ACTION_FIELDS
        if unknown:
            raise InvalidChange(f"action fields cannot be changed: {sorted(unknown)}")
        task = self.get_task(task_id)
        current = next((a for a in task.actions if a.action_id == action_id), None)
        if current is None:
            raise NotFound(f"action {action_id} of task {task_id}")
        updated = s.TaskAction.model_validate({**current.model_dump(), **changes})
        version = self._bump_version(task_id, expected_version, {})
        self.execute(
            "UPDATE task_actions SET priority = ?, due_type = ?, due_other = ?, due_date = ?, "
            "description = ?, needs_approval = ?, awaiting_reply = ? WHERE action_id = ?",
            (
                updated.priority,
                updated.due_type,
                updated.due_other,
                _day(updated.due_date),
                updated.description,
                int(updated.needs_approval),
                int(updated.awaiting_reply),
                action_id,
            ),
        )
        return version

    def add_task_history(
        self,
        task_id: str,
        version: int,
        change: dict,
        email_id: str | None,
        actor: str,
        at: datetime,
    ) -> None:
        self.execute(
            "INSERT INTO task_history (task_id, version, change_json, email_id, actor, at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, version, json.dumps(change, default=str), email_id, actor, _ts(at)),
        )

    # --- proposals ---
    def save_email(self, email: s.ParsedEmail, thread_id: str | None) -> None:
        """The email row of E10b; a re-run of the same email updates it, never a second row."""
        self.execute(
            "INSERT INTO emails (email_id, thread_id, sent_time, direction, subject, parsed_json) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(email_id) DO UPDATE SET thread_id = excluded.thread_id, "
            "parsed_json = excluded.parsed_json",
            (
                email.email_id,
                thread_id,
                _ts(email.sent_time),
                email.direction,
                email.subject,
                email.model_dump_json(),
            ),
        )

    def save_proposal(self, proposal: s.Proposal) -> s.SavedProposal:
        self.execute(
            "INSERT INTO proposals (proposal_id, email_id, status, supersedes_proposal_id, task_kind, "
            "task_key, body_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proposal.proposal_id,
                proposal.email_id,
                proposal.status,
                proposal.supersedes_proposal_id,
                proposal.task.kind,
                proposal.task.task_key,
                proposal.model_dump_json(),
            ),
        )
        return s.SavedProposal(proposal_id=proposal.proposal_id, status=proposal.status)

    def save_held(self, held: s.HeldRecord) -> s.SavedProposal:
        status = (
            "held_blocked" if held.reason == "blocked_unsanitized" else "held_store_unavailable"
        )
        proposal_id = f"H-{uuid.uuid4().hex[:12]}"
        self.execute(
            "INSERT INTO proposals (proposal_id, email_id, status, body_json) VALUES (?, ?, ?, ?)",
            (proposal_id, held.email_id, status, held.model_dump_json()),
        )
        return s.SavedProposal(proposal_id=proposal_id, status=status)

    def set_proposal_status(self, proposal_id: str, expected: str, new: str) -> None:
        """Compare-and-swap on the proposal status (E11-S14)."""
        changed = self.execute(
            "UPDATE proposals SET status = ? WHERE proposal_id = ? AND status = ?",
            (new, proposal_id, expected),
        )
        if changed == 0:
            if not self._q("SELECT 1 FROM proposals WHERE proposal_id = ?", (proposal_id,)):
                raise NotFound(f"proposal {proposal_id}")
            raise AlreadyDecided(f"proposal {proposal_id} is no longer {expected}")

    # --- facts ---
    def insert_fact(self, fact: s.FactRecord) -> None:
        self.execute(
            "INSERT INTO fact_records (fact_id, vessel_code, fact_key, value, event_time, "
            "event_time_basis, sent_time, source_email_id, version, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fact.fact_id,
                fact.vessel_code,
                fact.fact_key,
                fact.value,
                _ts(fact.event_time),
                fact.event_time_basis,
                _ts(fact.sent_time),
                fact.source_email_id,
                fact.version,
                fact.state,
            ),
        )

    def retract_fact(self, fact_id: str) -> None:
        changed = self.execute(
            "UPDATE fact_records SET state = 'retracted' WHERE fact_id = ? AND state = 'active'",
            (fact_id,),
        )
        if changed == 0:
            if not self._q("SELECT 1 FROM fact_records WHERE fact_id = ?", (fact_id,)):
                raise NotFound(f"fact {fact_id}")
            raise InvalidChange(f"fact {fact_id} is already retracted")

    # --- E11 and E12: undo records, audit log, corrections ---
    def add_undo(
        self, token: str, kind: str, target_id: str, produced_version: int | None, payload: dict
    ) -> None:
        self.execute(
            "INSERT INTO undo_records (undo_token, kind, target_id, produced_version, payload_json) VALUES (?, ?, ?, ?, ?)",
            (token, kind, target_id, produced_version, json.dumps(payload, default=str)),
        )

    def use_undo(self, token: str) -> dict:
        """Compare-and-swap: an undo token is used once. Returns the record."""
        rows = self._q("SELECT * FROM undo_records WHERE undo_token = ?", (token,))
        if not rows:
            raise NotFound(f"undo token {token}")
        if (
            self.execute(
                "UPDATE undo_records SET used = 1 WHERE undo_token = ? AND used = 0", (token,)
            )
            == 0
        ):
            raise AlreadyDecided(f"undo token {token} was used")
        row = rows[0]
        return {"kind": row["kind"], "target_id": row["target_id"], "produced_version": row["produced_version"],
                "payload": json.loads(row["payload_json"])}  # fmt: skip

    def add_audit(
        self, actor: str, action: str, target_type: str, target_id: str, detail: dict, at: datetime
    ) -> None:
        self.execute(
            "INSERT INTO audit_log (actor, action, target_type, target_id, detail_json, at) VALUES (?, ?, ?, ?, ?, ?)",
            (actor, action, target_type, target_id, json.dumps(detail, default=str), _ts(at)),
        )

    def add_correction(self, record: s.CorrectionRecord, at: datetime) -> None:
        self.execute(
            "INSERT INTO corrections (proposal_id, field, suggested, final, reason, at) VALUES (?, ?, ?, ?, ?, ?)",
            (record.proposal_id, record.field, json.dumps(record.suggested, default=str),
             json.dumps(record.final, default=str), record.reason, _ts(at)),
        )  # fmt: skip

    def relabel_threads(self, old_ids: list[str], new_id: str) -> None:
        """E2 joined these threads into new_id (merged_thread_ids)."""
        for old in old_ids:
            self.execute("UPDATE emails SET thread_id = ? WHERE thread_id = ?", (new_id, old))

    def delete_action(self, action_id: str) -> None:
        """Only an undo removes the actions its own change added."""
        self.execute("DELETE FROM task_actions WHERE action_id = ?", (action_id,))


class Store(_Reader):
    """One SQLite file. Reads go straight through; writes go through `transaction()`."""

    def __init__(self, conn: sqlite3.Connection):
        self._c: sqlite3.Connection | None = conn

    @classmethod
    def open(cls, path: Path) -> "Store":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA)
        except (sqlite3.Error, OSError) as exc:
            raise StoreUnavailable(str(exc)) from exc
        return cls(conn)

    def close(self) -> None:
        if self._c is not None:
            self._c.close()

    def _conn(self) -> sqlite3.Connection:
        if self._c is None:
            raise StoreUnavailable("store not open")
        return self._c

    @contextmanager
    def transaction(self) -> Iterator[Tx]:
        """BEGIN IMMEDIATE ... COMMIT; any exception rolls everything back and is re-raised."""
        conn = _run(self._conn, lambda c: c)
        _run(lambda: conn, lambda c: c.execute("BEGIN IMMEDIATE"))
        try:
            yield Tx(conn)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        _run(lambda: conn, lambda c: c.execute("COMMIT"))
