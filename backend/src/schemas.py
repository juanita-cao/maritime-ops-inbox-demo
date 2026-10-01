"""Pydantic models for every node boundary (design_backend.md sections 9.1, 9.2, 9.3 and 9.4).

Values typed as plain `str` but marked "taxonomy" in the design (event type, action type,
decision basis, contract level, role, fact key) are checked against kb/taxonomy.csv by
kb_loader at startup and by the nodes that produce them; the models here do not know the
knowledge base. Every timestamp is timezone-aware.
"""

from datetime import date
from typing import Annotated, Any, Literal, get_args

from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, model_validator

# --- 9.1 Shared types ---------------------------------------------------------

Tier = Literal["High", "Medium", "Low"]
Direction = Literal["Inbound", "Outbound"]
EvidenceSource = Literal["subject", "new_text", "quoted_text", "attachments", "kb"]
# Urgent and Risk were removed on 2026-09-26 (UI round U1): urgency is Priority, per action.
NeedsAction = Literal[
    "Action Required",
    "Approval Required",
    "Waiting for Reply",
    "FYI - No Action",
    "Close",
]
# skipped = not called on purpose; failed = called and no usable answer. Never merged.
LlmStatus = Literal["ok", "failed", "skipped"]
SetBy = Literal["rule", "officer"]
Priority = Annotated[int, Field(ge=1, le=5)]  # 1 low .. 5 critical; 4 and 5 shaded in the UI
DueType = Literal["Delivery", "Redelivery", "Hire", "Invoice", "Others"]
ProposalStatus = Literal[
    "open", "applied", "rejected", "stale", "held_blocked", "held_store_unavailable"
]
StoreStatus = Literal["ok", "unavailable"]

_STATUS_ORDER = list(get_args(NeedsAction))
_ALONE = ("FYI - No Action", "Close")


def check_statuses(value: list[str]) -> list[str]:
    """[AMENDMENT 2026-09-26 U2] A set of statuses: not empty, no repeats, taxonomy order;
    FYI - No Action and Close each stand alone."""
    if not value:
        raise ValueError("at least one status is needed")
    if len(set(value)) != len(value):
        raise ValueError("a status appears twice")
    for alone in _ALONE:
        if alone in value and len(value) > 1:
            raise ValueError(f"{alone} cannot be combined with another status")
    return sorted(value, key=_STATUS_ORDER.index)


Statuses = Annotated[list[NeedsAction], AfterValidator(check_statuses)]


class Evidence(BaseModel):
    """The quote must be a substring of the named source; the producing node checks that."""

    quote: str = Field(min_length=1)
    source: EvidenceSource


def _check_due_other(due_type: str, due_other: str | None) -> None:
    """A due of type Others needs a short text (design_backend.md 9.1, DueType)."""
    if due_type == "Others" and not (due_other and due_other.strip()):
        raise ValueError("a due of type Others needs a short text in due_other")


# --- E1 ParsedEmail -------------------------------------------------------------


class RawEmail(BaseModel):
    """E1 input [AMENDMENT 2026-09-26 T2.1]: the header block at the top, a blank line, then
    the body with quoted history, signature and postscript."""

    email_id: str = Field(min_length=1)
    text: str


class ParsedEmail(BaseModel):
    email_id: str = Field(min_length=1)
    subject: str
    subject_norm: str
    sent_time: AwareDatetime | None
    direction: Direction
    sender: str
    receivers: list[str] = []
    new_text: str = Field(min_length=1)
    signature_text: str = ""
    attachment_dependent: bool = False
    attachment_names: list[str] = []
    quoted_text: str = ""
    quoted_subjects: list[str] = []
    parse_flags: list[str] = []


# --- E2 ThreadRef -----------------------------------------------------------------


class ThreadIndexEntry(BaseModel):
    """One earlier email [AMENDMENT 2026-09-26 T2.2]. Vessel and voyage are the final confirmed
    values (the officer's correction wins, E2-S05)."""

    email_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    sent_time: AwareDatetime | None = None
    subject_norm: str
    quoted_subjects_norm: list[str] = []
    vessel_code: str | None = None
    voyage_no: str | None = None


class ThreadIndex(BaseModel):
    """E2 input [AMENDMENT 2026-09-26 T2.2]: read from the store by the pipeline."""

    entries: list[ThreadIndexEntry] = []


class ThreadRef(BaseModel):
    thread_id: str
    is_new_thread: bool
    member_email_ids: list[str] = []
    thread_vessel: str | None = None
    thread_voyage: str | None = None
    # threads joined into thread_id by this email; the pipeline relabels them [AMENDMENT T2.2]
    merged_thread_ids: list[str] = []


# --- E3 PartyRoles ----------------------------------------------------------------


class PartyRef(BaseModel):
    address: str
    party_code: str | None = None
    role: str = "Other"
    confidence: Literal["stated", "inferred", "unknown"] = "unknown"


class PartyRoles(BaseModel):
    sender: PartyRef
    receivers: list[PartyRef] = []
    low_confidence: bool = False


# --- E4 SanitizationCheck ---------------------------------------------------------


class Finding(BaseModel):
    kind: Literal["email", "phone", "url", "address", "id_number"]  # id_number: [AMENDMENT 2026-10-01]
    count: int = Field(ge=1)


class SanitizationCheck(BaseModel):
    """blocked_unsanitized = real finding; check_failed = the check itself broke."""

    status: Literal["clean", "blocked_unsanitized", "check_failed"]
    findings: list[Finding] = []
    error: str | None = None

    @model_validator(mode="after")
    def _status_rules(self) -> "SanitizationCheck":
        if self.status == "clean" and self.findings:
            raise ValueError("a clean check has no findings")
        if (self.error is not None) != (self.status == "check_failed"):
            raise ValueError("error is set exactly when status is check_failed")
        return self


# --- E5 ExtractedEntities ---------------------------------------------------------


class Mention(BaseModel):
    text: str
    evidence: Evidence


DateKind = Literal[
    "eta",
    "etb",
    "etd",
    "delivery",
    "redelivery",
    "laycan",
    "deadline",
    "arrived",
    "berthed",
    "commenced",
    "completed",
    "sailed",
    "nor_tendered",
    "other",
]


class DateFact(BaseModel):
    kind: DateKind
    value: str  # as normalised by E5 (ISO when possible), timezone words kept
    ordinal: int | None = Field(default=None, ge=1)  # "2ND NOR" gives 2 (E5-S12)
    evidence: Evidence


class QuantityFact(BaseModel):
    kind: Literal["loaded", "discharged", "bunker_rob", "speed", "consumption", "amount", "other"]
    value: float = Field(ge=0)
    unit: str
    currency: str | None = None
    evidence: Evidence

    @model_validator(mode="after")
    def _amount_has_currency(self) -> "QuantityFact":
        if self.kind == "amount" and not self.currency:
            raise ValueError("an amount needs a currency")
        return self


class Reference(BaseModel):
    kind: Literal["bl", "claim", "pi_case", "invoice", "fixture", "other"]
    value: str
    evidence: Evidence


class ExtractedEntities(BaseModel):
    vessel_mentions: list[Mention] = []
    voyage_numbers: list[Mention] = []
    ports: list[Mention] = []
    dates: list[DateFact] = []
    quantities: list[QuantityFact] = []
    cp_references: list[Mention] = []
    references: list[Reference] = []
    author_hint: Mention | None = None
    subject_text_conflict: bool = False  # subject and text disagree; text value used (E5-S13)
    llm_status: LlmStatus


# --- D1 VesselMatch, D2 VoyageMatch -----------------------------------------------


class Candidate(BaseModel):
    vessel_code: str
    score: float = Field(ge=0, le=1)


class VesselMatch(BaseModel):
    vessel_code: str | None
    status: Literal["matched", "ambiguous", "none"]
    tier: Tier
    score: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []
    candidates: list[Candidate] = []
    set_by: SetBy = "rule"
    # audit trail of a D node (ChordX 23a) [AMENDMENT 2026-09-26 T2.6]
    reason: str = ""
    rule_triggered: str = ""
    inputs_snapshot: dict[str, Any] = {}

    @model_validator(mode="after")
    def _status_rules(self) -> "VesselMatch":
        if self.status == "matched" and self.vessel_code is None:
            raise ValueError("a matched vessel needs a vessel_code")
        if self.status != "matched" and (self.vessel_code is not None or self.tier != "Low"):
            raise ValueError("ambiguous or none: tier Low and no vessel_code")
        return self


class VoyageMatch(BaseModel):
    voyage_no: str | None
    basis: Literal["stated", "inferred", "none"]
    contract_level: str | None = None
    evidence: list[Evidence] = []
    candidates: list[str] = []
    set_by: SetBy = "rule"
    # [AMENDMENT 2026-09-26 T2.7] flags (D2-S02) and the audit trail of a D node (ChordX 23a)
    flags: list[str] = []
    reason: str = ""
    rule_triggered: str = ""
    inputs_snapshot: dict[str, Any] = {}

    @model_validator(mode="after")
    def _none_basis(self) -> "VoyageMatch":
        if self.basis == "none" and self.voyage_no is not None:
            raise ValueError("basis none requires voyage_no None")
        return self


# --- E6 EventCandidates, D3 EventDecision, D4 NeedsActionDecision -----------------


class EventCandidate(BaseModel):
    event_type: str
    confidence: float = Field(ge=0, le=1)
    source: Literal["rule", "llm"]
    evidence: Evidence


class EventCandidates(BaseModel):
    items: list[EventCandidate] = Field(default=[], max_length=3)
    is_report: bool
    llm_status: LlmStatus


class EventDecision(BaseModel):
    event_type: str
    tier: Tier
    unsure: bool
    is_report: bool
    sources_agree: bool
    secondary_event_types: list[str] = Field(default=[], max_length=2)
    set_by: SetBy = "rule"
    # audit trail of a D node (ChordX 23a) [AMENDMENT 2026-09-26 T2.9]
    reason: str = ""
    rule_triggered: str = ""
    inputs_snapshot: dict[str, Any] = {}


class NeedsActionDecision(BaseModel):
    statuses: Statuses  # [AMENDMENT 2026-09-26 U2] was status: NeedsAction
    priority: Priority  # suggested priority for this email's actions
    reason: str
    deadline: AwareDatetime | None = None
    escalated_by: list[str] = []
    # [AMENDMENT 2026-09-26 T2.10] flags (no rule row) and the audit trail (ChordX 23a)
    flags: list[str] = []
    rule_triggered: str = ""
    inputs_snapshot: dict[str, Any] = {}

    @model_validator(mode="after")
    def _never_close(self) -> "NeedsActionDecision":
        if "Close" in self.statuses:
            raise ValueError("D4 never produces Close; only E10 sets it")
        return self


# --- E7 ActionCandidates, D5 RankedActions ----------------------------------------


class ActionCandidate(BaseModel):
    action_type: str
    description: str = Field(max_length=300)
    due: date | None = None  # the due date read from the email
    due_type: DueType
    due_other: str | None = None
    owner_role: str
    decision_basis: str
    templated: bool = False
    for_event: str

    @model_validator(mode="after")
    def _due_other(self) -> "ActionCandidate":
        _check_due_other(self.due_type, self.due_other)
        return self


class ActionCandidates(BaseModel):
    items: list[ActionCandidate] = Field(default=[], max_length=5)
    llm_status: LlmStatus


class RankedAction(ActionCandidate):
    rank: int = Field(ge=1)
    priority: Priority  # D4's suggestion; the officer sets each action's own priority
    needs_approval: bool = False  # [AMENDMENT 2026-09-26 U2] from the action type (D5)
    awaiting_reply: bool = False


class RankedActions(BaseModel):
    """An empty list means "No Action"."""

    items: list[RankedAction] = Field(default=[], max_length=3)
    # audit trail of a D node (ChordX 23a) [AMENDMENT 2026-09-26 T2.13]
    reason: str = ""
    rule_triggered: str = ""
    inputs_snapshot: dict[str, Any] = {}


# --- E8 ClosureCheck --------------------------------------------------------------


class ClosureResult(BaseModel):
    task_id: str
    settled: bool
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def _settled_needs_evidence(self) -> "ClosureResult":
        # A yes without a quoted phrase counts as no (design_backend.md E8 row).
        if self.settled and self.evidence is None:
            self.settled = False
        return self


class ClosureCheck(BaseModel):
    results: list[ClosureResult] = []
    llm_status: LlmStatus


# --- D6 TaskDisposition, E9 Lane --------------------------------------------------


class FieldChange(BaseModel):
    old: Any = None
    new: Any = None


class TaskDisposition(BaseModel):
    kind: Literal["create", "update", "close_proposal", "none"]
    task_key: str | None = None
    target_task_id: str | None = None
    target_task_version: int | None = None
    changed_fields: dict[str, FieldChange] = {}
    flags: list[str] = []  # for example duplicate_key_found, pending_same_key
    close_warning: bool = False
    new_statuses: Statuses | None = None  # [AMENDMENT 2026-09-26 U2] union rule of D6
    # audit trail of a D node (ChordX 23a) [AMENDMENT 2026-09-26 T2.15]
    reason: str = ""
    rule_triggered: str = ""
    inputs_snapshot: dict[str, Any] = {}

    @model_validator(mode="after")
    def _kind_rules(self) -> "TaskDisposition":
        if self.kind in ("create", "update") and self.task_key is None:
            raise ValueError("create and update need a task_key")
        if self.kind in ("update", "close_proposal") and self.target_task_id is None:
            raise ValueError("update and close_proposal need a target_task_id")
        if self.target_task_id is not None and self.target_task_version is None:
            raise ValueError("target_task_version is required with target_task_id")
        if self.changed_fields and self.kind != "update":
            raise ValueError("changed_fields only for update")
        return self


class Lane(BaseModel):
    lane: Literal["auto_apply", "needs_confirm"]
    reasons: list[str] = []


# --- E6b FactChanges --------------------------------------------------------------


class FactChange(BaseModel):
    fact_key: str
    old: str | None = None
    new: str
    event_time: AwareDatetime | None  # None: the change cannot be applied automatically
    event_time_basis: Literal["stated", "email_sent_time"] | None
    evidence: Evidence
    base_version: int | None = None
    older_than_current: bool = False  # recorded, but does not become current


class FactChanges(BaseModel):
    items: list[FactChange] = []


# --- E10 Proposal, E11/E12 inputs and outputs -------------------------------------


class TraceStep(BaseModel):
    node: str
    rule_or_basis: str
    confidence: float | None = None
    evidence: list[Evidence] = []


class Proposal(BaseModel):
    proposal_id: str
    email_id: str
    status: ProposalStatus = "open"
    supersedes_proposal_id: str | None = None
    lane: Lane
    vessel: VesselMatch
    voyage: VoyageMatch
    event: EventDecision
    statuses: Statuses  # [AMENDMENT 2026-09-26 U2] was needs_action
    priority: Priority  # highest action priority, or D4's when there are no actions
    fact_changes: list[FactChange] = []
    task: TaskDisposition
    actions: RankedActions
    trace: list[TraceStep] = []
    incomplete: bool = False

    @model_validator(mode="after")
    def _close_only_with_close_proposal(self) -> "Proposal":
        if "Close" in self.statuses and self.task.kind != "close_proposal":
            raise ValueError("status Close requires task.kind close_proposal")
        if self.actions.items and self.priority != max(a.priority for a in self.actions.items):
            raise ValueError("Proposal.priority is the highest priority of its actions")
        return self


class ConfirmedAction(BaseModel):
    """One action as the officer confirmed it on the Email page (U1)."""

    action_type: str
    description: str = Field(max_length=300)
    priority: Priority
    due_type: DueType
    due_other: str | None = None
    due_date: date | None = None
    set_by: Literal["ai", "officer"]
    needs_approval: bool = False  # [AMENDMENT 2026-09-26 U2]
    awaiting_reply: bool = False

    @model_validator(mode="after")
    def _due_other(self) -> "ConfirmedAction":
        _check_due_other(self.due_type, self.due_other)
        return self


class Decision(BaseModel):
    """Lane and close_warning checks need the proposal; E11 applies them."""

    kind: Literal["auto", "approve", "edit", "reject"]
    actor: Literal["system", "officer"]
    edits: dict[str, Any] = {}
    actions: list[ConfirmedAction] | None = None  # None means "as proposed"
    statuses: Statuses | None = None  # [AMENDMENT 2026-09-26 U2] None means "as proposed"
    reason: str | None = None
    decided_at: AwareDatetime

    @model_validator(mode="after")
    def _kind_rules(self) -> "Decision":
        if self.kind == "auto" and self.actor != "system":
            raise ValueError("auto decisions are made by the system only")
        # [AMENDMENT 2026-09-26 T3.3] the officer's action list and statuses are edits too (U1, U2)
        if self.kind == "edit" and not (self.edits or self.actions is not None or self.statuses is not None):
            raise ValueError("an edit needs at least one edited value")
        return self


class ActionChange(BaseModel):
    """An officer's change to one action of a confirmed task (Vessel page, U1)."""

    action_id: str
    priority: Priority | None = None
    due_type: DueType | None = None
    due_other: str | None = None
    due_date: date | None = None
    needs_approval: bool | None = None  # [AMENDMENT 2026-09-26 U2]
    awaiting_reply: bool | None = None

    @model_validator(mode="after")
    def _due_other(self) -> "ActionChange":
        if self.due_type is not None:
            _check_due_other(self.due_type, self.due_other)
        return self


class ManualTaskChange(BaseModel):
    task_id: str
    expected_version: int = Field(ge=1)
    new_statuses: Statuses | None = None  # [AMENDMENT 2026-09-26 U2] was new_needs_action
    close: bool = False
    action_changes: list[ActionChange] = []
    reason: str | None = None
    actor: Literal["officer"] = "officer"

    @model_validator(mode="after")
    def _exclusive(self) -> "ManualTaskChange":
        if self.close and self.new_statuses is not None:
            raise ValueError("close and new_statuses are mutually exclusive")
        if self.new_statuses is not None and "Close" in self.new_statuses:
            raise ValueError("a task is closed with close=True, not with the status Close")
        if not (self.close or self.new_statuses is not None or self.action_changes):
            raise ValueError("nothing to change")
        return self


class ApplyResult(BaseModel):
    """conflict (concurrent change) and rolled_back (something broke) are handled differently."""

    status: Literal["applied", "conflict", "rolled_back", "noop"]
    reason: (
        Literal[
            "already_decided",
            "no_change",
            "later_change_exists",
            "stale_task_version",
            "duplicate_open_key",
        ]
        | None
    ) = None
    applied_fact_ids: list[str] = []
    applied_task_id: str | None = None
    undo_token: str | None = None
    conflict_detail: str | None = None


class CorrectionRecord(BaseModel):
    proposal_id: str
    field: str
    suggested: Any = None
    final: Any = None
    reason: str | None = None


# --- 9.3 / 9.4 stored state and lookups -------------------------------------------


class TaskAction(BaseModel):
    """One confirmed action of a task; the Due list reads these rows (U1)."""

    action_id: str
    task_id: str
    action_type: str
    description: str
    priority: Priority
    due_type: DueType
    due_other: str | None = None
    due_date: date | None = None
    set_by: Literal["ai", "officer"]
    source_email_id: str
    needs_approval: bool = False  # [AMENDMENT 2026-09-26 U2]
    awaiting_reply: bool = False

    @model_validator(mode="after")
    def _due_other(self) -> "TaskAction":
        _check_due_other(self.due_type, self.due_other)
        return self


class Task(BaseModel):
    task_id: str
    task_key: str
    vessel_code: str
    voyage_no: str | None = None
    action_type: str
    description: str  # names the step the task waits for
    statuses: Statuses  # [AMENDMENT 2026-09-26 U2] was needs_action and awaiting_reply
    deadline: AwareDatetime | None = None
    status: Literal["open", "closed"]
    version: int = Field(ge=1)  # rises on every change, including a change to one of its actions
    source_email_ids: list[str] = []
    priority: Priority  # derived: highest priority of its actions
    actions: list[TaskAction] = []

    @model_validator(mode="after")
    def _derived_priority(self) -> "Task":
        if self.actions and self.priority != max(a.priority for a in self.actions):
            raise ValueError("Task.priority is the highest priority of its actions")
        if "Close" in self.statuses:
            raise ValueError("a task is closed by status closed, not by the status Close")
        return self


class FactRecord(BaseModel):
    """Insert-only. The current value is derived by (event_time, sent_time, email_id)."""

    fact_id: str
    vessel_code: str
    fact_key: str
    value: str
    event_time: AwareDatetime
    event_time_basis: Literal["stated", "email_sent_time"]
    sent_time: AwareDatetime | None = None  # tie-breaker of section 11.A
    source_email_id: str
    version: int = Field(ge=1)
    superseded_by: str | None = None
    state: Literal["active", "retracted"] = "active"


class PendingRef(BaseModel):
    proposal_id: str
    task_key: str
    kind: Literal["create", "update", "close_proposal", "none"]


class TaskLookup(BaseModel):
    """unavailable is never read as "no open task" (section 11.B)."""

    status: StoreStatus
    tasks: list[Task] = []
    pending_proposals: list[PendingRef] = []


class FactLookup(BaseModel):
    """unavailable is never read as "no facts" (section 11.B)."""

    status: StoreStatus
    facts: list[FactRecord] = []


class HeldRecord(BaseModel):
    email_id: str
    reason: Literal["blocked_unsanitized", "store_unavailable"]
    detail: str


class SavedProposal(BaseModel):
    proposal_id: str
    status: ProposalStatus


class Overrides(BaseModel):
    vessel_code: str | None = None
    voyage_no: str | None = None
    event_type: str | None = None


# --- Read path: D7, E13, E14 ------------------------------------------------------


class TaskRow(BaseModel):
    task_id: str
    vessel: str
    voyage: str | None = None
    action: str
    priority: Priority
    due_type: DueType | None = None  # type of the earliest due
    deadline: AwareDatetime | None = None
    overdue: bool = False
    statuses: Statuses  # [AMENDMENT 2026-09-26 U2] the row is listed in each of these groups
    source_email_id: str
    # [AMENDMENT 2026-09-26 T3.6] for the Action cards and the Vessel page Update
    task_key: str = ""
    version: int = 1
    actions: list[TaskAction] = []


class TaskGroup(BaseModel):
    name: Literal["Action Required", "Approval Required", "Waiting for Reply"]
    items: list[TaskRow] = []


class RankedTaskList(BaseModel):
    groups: list[TaskGroup] = []


class DueRow(BaseModel):
    task_id: str
    action_id: str
    vessel: str
    voyage: str | None = None
    action: str
    due_type: DueType
    due_other: str | None = None
    due_date: date
    priority: Priority
    overdue: bool = False


class DueList(BaseModel):
    """E15. store_status unavailable is not an empty list (E15-S05)."""

    items: list[DueRow] = []
    store_status: StoreStatus


class FactRow(BaseModel):
    fact_key: str
    value: str
    event_time: AwareDatetime
    source_email_id: str
    superseded: bool


class TimelineRow(BaseModel):
    event_time: AwareDatetime
    event_type: str
    email_id: str
    changed_fact_keys: list[str] = []


class AutoAppliedRow(BaseModel):
    email_id: str
    fact_keys: list[str] = []
    applied_at: AwareDatetime
    undo_available: bool


class VesselView(BaseModel):
    vessel_code: str
    facts: list[FactRow] = []
    timeline: list[TimelineRow] = []
    open_tasks: list[TaskRow] = []
    auto_applied: list[AutoAppliedRow] = []


class ReviewRow(BaseModel):
    proposal_id: str
    email_id: str
    vessel: str | None = None
    event_type: str | None = None
    statuses: Statuses | None = None  # [AMENDMENT 2026-09-26 U2]
    status: ProposalStatus


class ReviewQueue(BaseModel):
    """store_status unavailable is not an empty queue (E14-S03)."""

    items: list[ReviewRow] = []
    store_status: StoreStatus


# --- E16 chat [AMENDMENT 2026-09-26 U3] --------------------------------------------------


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default=[], max_length=10)  # the last 10 turns
    # [AMENDMENT 2026-09-29, v5.1 model picker] a model id from GET /api/chat/models; the API
    # rejects anything not on that list. None = the default model. Only /api/chat/v5.1 reads it.
    model: str | None = Field(default=None, max_length=64)


class ChatEmail(BaseModel):
    """[AMENDMENT 2026-09-26 T2.22] a short, sanitized view of an email the context refers to,
    so answers and drafts can name what the email says."""

    email_id: str
    subject: str
    sent_time: AwareDatetime | None = None
    sender: str  # role and party code, or "us"
    excerpt: str = Field(max_length=600)


class ChatContext(BaseModel):
    """Built by the read path; E16 reads nothing else."""

    tasks: RankedTaskList
    dues: DueList
    vessels: list[VesselView] = []
    review_queue: ReviewQueue
    emails: list[ChatEmail] = []  # [AMENDMENT 2026-09-26 T2.22]
    store_status: StoreStatus = "ok"


class SourceRef(BaseModel):
    kind: Literal["email", "vessel", "task", "page"]
    id: str
    label: str


# --- E16 read-only tools (E17 e17_get_email, E18 e18_search_emails)
# [AMENDMENT 2026-09-28, read-only tools] ------------------------------------------------


class GetEmailArgs(BaseModel):
    """E17's own Args model: a tool call's arguments are validated against this before it
    runs; a call that fails validation is a tool error, not a retry with guessed arguments."""

    email_id: str = Field(min_length=1)


class SearchEmailsArgs(BaseModel):
    """E18's own Args model. At least one filter is required (E18-S03): "no filters" means
    "rejected as invalid", not "return everything". `limit` is code-capped at 20 by E18
    itself, whatever is asked here."""

    vessel: str | None = None
    event_type: str | None = None
    status: NeedsAction | None = None
    limit: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _at_least_one_filter(self) -> "SearchEmailsArgs":
        if not (self.vessel or self.event_type or self.status):
            raise ValueError("at least one filter (vessel, event_type or status) is required")
        return self


class ToolCall(BaseModel):
    """One tool the model asked to run, in one turn of E16's tool loop (design_backend.md 9.4)."""

    name: Literal["get_email", "search_emails"]
    arguments: dict[str, Any] = {}


class ToolResult(BaseModel):
    """What running a ToolCall gave back; `error` is set instead of `result`, never both."""

    name: Literal["get_email", "search_emails"]
    arguments: dict[str, Any] = {}
    result: ChatEmail | list[ChatEmail] | None = None
    error: str | None = None


class ToolCallLog(BaseModel):
    """In ChatAnswer.tool_calls: the trace of one tool call, for V2 and for the owner reading
    LLM_DEBUG_LOG — never the full email content again, only a one-line summary."""

    name: Literal["get_email", "search_emails"]
    arguments: dict[str, Any] = {}
    result_summary: str


# [AMENDMENT 2026-09-29, protocol/chordx_agent.md 8] a controlled enum, not free prose: None
# means an ordinary answer was given. access_denied has no current trigger (single-tenant, no
# per-user scoping yet) but is kept in the enum so it activates automatically once one exists,
# rather than needing the type extended later.
# [AMENDMENT 2026-09-29-ii, docs/design_agent_e16.md] decision_not_authorized: the question is
# on topic (the officer's own vessels/emails/charter parties) but answering it would require a
# business decision (cost allocation, claim validity, an operational recommendation) this node
# has no authority to make — distinct from out_of_scope, whose topic is genuinely unrelated.
# [AMENDMENT 2026-09-29-iii, docs/design_agent_e16_v2.md] capability_not_available: distinct
# from no_data — a category-level gap (this system never tracks this kind of thing at all, for
# any vessel or date), not an instance-level miss (this particular thing wasn't found this
# time). Used by E16 v2 only; E16 legacy does not set this value.
RetrievalOutcome = Literal[
    "out_of_scope",
    "no_data",
    "access_denied",
    "retrieval_limit_reached",
    "decision_not_authorized",
    "capability_not_available",
]


CapabilityAuthority = Literal["supported_l1", "supported_l2", "action_requires_l3", "out_of_scope"]
EvidenceStatus = Literal[
    "sufficient", "partial", "missing_required_evidence", "no_matching_data",
    "retrieval_limit_reached", "access_denied",
]  # fmt: skip

# [AMENDMENT 2026-09-29-iv, docs/design_agent_e16_v5.md 2] E16 v5 only: how a question is
# answered (a different axis from capability_authority). None for v1-v4.
ExecutionMode = Literal[
    "deterministic", "evidence_reasoning", "proposal_reasoning",
    "domain_knowledge", "hybrid", "out_of_scope",
    "follow_up",  # [AMENDMENT 2026-09-30, design_agent_e16_v6.md 2] v6 only
]  # fmt: skip


EvidenceCheck = Literal["verified", "quote_not_found", "source_not_read"]
EvidenceSupport = Literal["supports", "contradicts", "unrelated", "insufficient"]


class ChatEvidence(BaseModel):
    """[AMENDMENT 2026-10-01, design_agent_e16_v7.md 4.2] One key claim of an answer with the
    passage that supports it. `status` is set by code: the quote must occur in the text actually
    read for `source_id`."""

    claim: str
    source_id: str
    quote: str
    status: EvidenceCheck
    support: EvidenceSupport | None = None  # [AMENDMENT 2026-10-01, v7 6] the verifier's verdict; None = not checked


class ChatStep(BaseModel):
    """[AMENDMENT 2026-10-01, design_agent_e16_v7.md 7.3] One step of a playbook as the answer worked it."""

    step_id: str
    primitive: str
    text: str
    status: Literal["done", "missing", "not_applicable"]
    note: str = ""
    evidence_ids: list[str] = []


class ChatPlaybook(BaseModel):
    id: str
    title: str
    status: Literal["draft", "approved"]


class ChatAnswer(BaseModel):
    text: str = Field(min_length=1)
    sources: list[SourceRef] = []
    draft: str | None = None  # reply text; never sent
    review_card: str | None = None  # proposal id from E14's queue, chosen by rule
    review_email_id: str | None = None  # [AMENDMENT 2026-09-26 T2.22] the card's email
    llm_status: LlmStatus
    tool_calls: list[ToolCallLog] = []  # [AMENDMENT 2026-09-28, read-only tools]
    retrieval_outcome: RetrievalOutcome | None = None  # [AMENDMENT 2026-09-29]
    # [AMENDMENT 2026-09-29-iii, docs/design_agent_e16_v4.md 9] E16 v4 only — a two-dimensional
    # outcome (capability/authority is separate from evidence sufficiency, never collapsed into
    # one enum). None for v1/v2/v3, which keep using retrieval_outcome alone.
    capability_authority: CapabilityAuthority | None = None
    evidence_status: EvidenceStatus | None = None
    # [AMENDMENT 2026-09-29-iv, docs/design_agent_e16_v5.md 28] E16 v5 only: the Execution Mode
    # set by the router, and the model's own short list of processing steps (self-reported, not
    # a verified execution log — tool_calls is the code-verified part of the trace).
    execution_mode: ExecutionMode | None = None
    reasoning_trace: list[str] = []
    llm_model: str | None = None  # [AMENDMENT v5.1 model picker] which model answered
    # [AMENDMENT 2026-09-30, design_agent_e16_v6.md 1] v6: evidence, missing information and full
    # proposal behind a collapsed "Show basis"; `text` is only what the officer needs to read.
    details: str | None = None
    evidence: list[ChatEvidence] = []  # v7 only
    steps: list[ChatStep] = []  # v7: the playbook's steps and how far each got
    playbook: ChatPlaybook | None = None
    version: str | None = None  # which chat version answered (v7)
    # [AMENDMENT 2026-10-01, model picker] which models this answer really used (a deterministic answer
    # never calls the reasoning model) and a one-line description for the page.
    models: dict[str, str] = {}
    model_note: str | None = None
