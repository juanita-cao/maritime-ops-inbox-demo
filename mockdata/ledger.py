"""The fact ledger of the mock dataset (docs/design_mock_data.md 4): one model for a vessel's parties,
voyages, timeline of events and scenario ground truth, and a validator that refuses inconsistent facts.
Every number lives here once; emails and golden answers are derived from it."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class Party(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str  # OPR-01 (our side) or CPY-nn
    name: str  # invented
    role: str  # owner | operator | charterer | sub_charterer | port_agent | pni_correspondent | master | surveyor | supplier
    domain: str  # the .example mailbox domain

    @field_validator("domain")
    @classmethod
    def _example(cls, v: str) -> str:
        if not v.endswith(".example"):
            raise ValueError("mock mailboxes must end in .example")
        return v


class Voyage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    no: str  # V101
    status: str  # completed | in_progress | planned
    cp_ref: str
    load_port: str
    disch_port: str
    cargo: str
    qty_mt: float
    sailed: str | None = None  # ISO with offset
    eta: str | None = None


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str  # M0001
    time: str  # ISO with offset
    event_type: str  # a taxonomy event type
    sender: str  # party code
    receivers: list[str]
    thread: str
    reply_to: str | None = None
    subject: str
    voyage: str | None = None
    scenario: str | None = None
    facts: dict[str, str | float | int] = {}  # what this email states, rendered by the template or the polish step
    note: str = ""  # intent, for the skeleton renderer


class Truth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str
    question: str
    answer: str
    evidence: list[str]  # event ids that prove it


class Ledger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vessel: str  # VSL-01
    parties: list[Party]
    voyages: list[Voyage]
    events: list[Event]
    truths: list[Truth] = []
    discrepancies: list[str] = []  # fact keys that a scenario makes disagree on purpose (e.g. bl_qty_mt)


# descriptive text may differ between emails; amounts, quantities, dates and references may not
_FIXED_SUFFIXES = ("_mt", "_usd", "_usd_mt", "_usd_day", "_pct", "_hours", "_kn", "_date", "_due", "_no", "_days", "_ref", "_total_usd")


def _t(value: str) -> datetime:
    return datetime.fromisoformat(value)


def validate(ledger: Ledger, event_types: set[str]) -> list[str]:
    """Every problem found; empty means consistent."""
    problems: list[str] = []
    parties = {p.code for p in ledger.parties}
    voyages = {v.no for v in ledger.voyages}
    ids = [e.id for e in ledger.events]
    if len(set(ids)) != len(ids):
        problems.append("repeated event ids")
    by_id = {e.id: e for e in ledger.events}
    for e in ledger.events:
        if e.event_type not in event_types:
            problems.append(f"{e.id}: unknown event type {e.event_type!r}")
        for code in [e.sender, *e.receivers]:
            if code not in parties:
                problems.append(f"{e.id}: unknown party {code}")
        if e.voyage and e.voyage not in voyages:
            problems.append(f"{e.id}: unknown voyage {e.voyage}")
        if e.reply_to:
            parent = by_id.get(e.reply_to)
            if parent is None:
                problems.append(f"{e.id}: replies to unknown {e.reply_to}")
            elif _t(parent.time) >= _t(e.time):
                problems.append(f"{e.id}: replies to {e.reply_to} but is not later")
    for v in ledger.voyages:
        if v.sailed and v.eta and _t(v.eta) <= _t(v.sailed):
            problems.append(f"{v.no}: ETA is not after sailing")
    seen: dict[tuple[str, str], tuple[str, str | float | int]] = {}  # (voyage, fact key) -> (event, value)
    for e in sorted(ledger.events, key=lambda x: _t(x.time)):
        for key, value in e.facts.items():
            fixed = isinstance(value, int | float) or key.endswith(_FIXED_SUFFIXES)
            if not fixed or key in ledger.discrepancies or key.startswith(("eta_", "rob_", "pos_", "draft_", "speed_", "wind_", "sea_", "cons_", "waiting_")):
                continue  # a deliberate disagreement, or a quantity that changes by the hour
            prev = seen.get((e.voyage or "", key))
            if prev and prev[1] != value:
                problems.append(f"{e.id}: {key} = {value!r} but {prev[0]} says {prev[1]!r} (list {key} in discrepancies if intended)")
            seen[(e.voyage or "", key)] = (e.id, value)
    for t in ledger.truths:
        for ev in t.evidence:
            if ev not in by_id:
                problems.append(f"truth {t.scenario}: evidence {ev} is not an event")
    return problems
