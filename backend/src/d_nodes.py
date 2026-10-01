"""D nodes of the DEP (design_backend.md section 4). Each is one plain rule with one primitive,
returns its decision with reason, rule_triggered and inputs_snapshot (ChordX 23a), and reads only
its arguments."""

import re
from datetime import date, datetime, timedelta, timezone

from src.kb_loader import KnowledgeBase, Vessel
from src.schemas import (
    ActionCandidate,
    ActionCandidates,
    Candidate,
    ClosureCheck,
    EventCandidates,
    EventDecision,
    Evidence,
    ExtractedEntities,
    FieldChange,
    NeedsActionDecision,
    ParsedEmail,
    PartyRoles,
    RankedAction,
    RankedActions,
    Task,
    TaskDisposition,
    TaskLookup,
    ThreadRef,
    VesselMatch,
    VoyageMatch,
    check_statuses,
)

# --- D1 d1_match_vessel (Matching) -------------------------------------------------

# design_knowledge section 4 [AMENDMENT 2026-09-26 T2.6]; tuned in T4.4
D1_WEIGHTS = {"subject": 0.8, "body": 0.5, "mailbox": 0.4, "thread": 0.4}
D1_HIGH = 0.8  # inclusive
D1_MEDIUM = 0.4  # inclusive; also the level at which a runner-up makes the match ambiguous
_SHIP_CODE = re.compile(r"(?:m\.?\s*/?\s*v\.?\s+)?(VSL-\d{2})", re.I)
_SOURCE_KIND = {"subject": "subject", "new_text": "body", "attachments": "body"}


def _vessel_code(text: str, known: dict[str, Vessel]) -> str | None:
    """A mention counts only when it is a full known code, with an optional ship prefix."""
    m = _SHIP_CODE.fullmatch(text.strip())
    code = m.group(1).upper() if m else None
    return code if code in known else None


def _tier(score: float) -> str:
    return "High" if score >= D1_HIGH else "Medium" if score >= D1_MEDIUM else "Low"


def d1_match_vessel(
    entities: ExtractedEntities, thread: ThreadRef, roles: PartyRoles, vessels: dict[str, Vessel]
) -> VesselMatch:
    """D1 Matching: which vessel the email is about. Never a silent pick: ambiguous or no
    evidence gives Low with every candidate listed."""
    kinds: dict[str, set[str]] = {}
    evidence: dict[str, list[Evidence]] = {}

    def add(code: str, kind: str, ev: Evidence) -> None:
        if kind not in kinds.setdefault(code, set()):
            evidence.setdefault(code, []).append(ev)
        kinds[code].add(kind)

    for mention in entities.vessel_mentions:
        code = _vessel_code(mention.text, vessels)
        kind = _SOURCE_KIND.get(mention.evidence.source)
        if code and kind:
            add(code, kind, mention.evidence)
    for code, vessel in vessels.items():
        if roles.sender.party_code and roles.sender.party_code == vessel.vessel_mailbox_party:
            add(
                code,
                "mailbox",
                Evidence(
                    quote=f"sender mailbox of {code} ({roles.sender.party_code})", source="kb"
                ),
            )
    if thread.thread_vessel in vessels:
        add(
            thread.thread_vessel,
            "thread",
            Evidence(
                quote=f"thread {thread.thread_id} matched {thread.thread_vessel}", source="kb"
            ),
        )

    # Decisions use the raw score; rounding is only for what is shown (review 2026-09-26: a
    # tuned weight of 0.39996 must not be rounded up into Medium).
    raw = {c: min(1.0, sum(D1_WEIGHTS[k] for k in ks)) for c, ks in kinds.items()}
    ranked = sorted(raw.items(), key=lambda item: (-item[1], item[0]))
    shown = {c: round(s, 4) for c, s in ranked}
    candidates = [Candidate(vessel_code=c, score=shown[c]) for c, _ in ranked]
    snapshot = {"scores": shown, "kinds": {c: sorted(kinds[c]) for c, _ in ranked}}

    if not ranked:
        return VesselMatch(vessel_code=None, status="none", tier="Low", score=0.0, reason="no vessel code, mailbox or thread evidence",
                           rule_triggered="no_evidence", inputs_snapshot=snapshot)  # fmt: skip
    best, best_score = ranked[0]
    if len(ranked) > 1 and ranked[1][1] >= D1_MEDIUM:
        reaching = ", ".join(f"{c} ({shown[c]})" for c, s in ranked if s >= D1_MEDIUM)
        return VesselMatch(
            vessel_code=None, status="ambiguous", tier="Low", score=shown[best], candidates=candidates,
            evidence=[ev for c, _ in ranked for ev in evidence[c]],
            reason=f"{reaching} reach Medium or above; the officer chooses",
            rule_triggered="runner_up_at_medium", inputs_snapshot=snapshot,
        )  # fmt: skip
    if best_score < D1_MEDIUM:
        return VesselMatch(
            vessel_code=None, status="none", tier="Low", score=shown[best], candidates=candidates,
            reason=f"best evidence {best} ({shown[best]}) is below Medium", rule_triggered="below_medium",
            inputs_snapshot=snapshot,
        )  # fmt: skip
    tier = _tier(best_score)
    return VesselMatch(
        vessel_code=best, status="matched", tier=tier, score=shown[best], evidence=evidence[best], candidates=candidates,
        reason=f"{best} from {', '.join(sorted(kinds[best]))} ({shown[best]})",
        rule_triggered=f"matched_{tier.lower()}", inputs_snapshot=snapshot,
    )  # fmt: skip


# --- D2 d2_match_voyage (Matching) -------------------------------------------------

# [AMENDMENT 2026-09-26 T2.7] G4 by cue words (D3 decides the event type only after D2)
_NEXT_VOYAGE_CUES = re.compile(
    # "next voyage" alone is not a cue: E045/E052 argue about the next fixture inside the
    # current charter (label check, owner approved 2026-09-26); only preparation words count
    r"\bpre-?stowage\b|\bstowage plan\b|\bpre-?loading\b"
    r"|\bvoyage instructions?\b|\bport nomination\b",
    re.I,
)
_LEVEL_LABELS = {
    "Owner-Head": "Owner – Head charterer",
    "Head-Sub": "Head charterer – Sub-charterer",
}
NOT_APPLICABLE = "Not applicable"
_OUR_ROLE = "Operator (internal)"
_PARTY_CODE = re.compile(r"\b(?:OWN-VSL-\d{2}|CO-\d+)\b")


def _bound(text: str, end: bool) -> date | None:
    """Leading date of a kb/voyages bound: "2026-07-25", "2026-08-06 (expected)", "2026-06"
    (a whole month), or None when empty (an open bound)."""
    m = re.match(r"\s*(\d{4})-(\d{2})(?:-(\d{2}))?", text or "")
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if m.group(3):
        return date(year, month, int(m.group(3)))
    if not end:
        return date(year, month, 1)
    return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def _latest_start(voyages: list[str], windows: dict) -> str | None:
    """The voyage that starts last among overlapping ones; None when start dates cannot tell
    (missing, or two share the latest start). Never list order (review 2026-09-26)."""
    starts = [(windows[v][0], v) for v in voyages]
    if any(s is None for s, _ in starts):
        return None
    latest = max(s for s, _ in starts)
    top = [v for s, v in starts if s == latest]
    return top[0] if len(top) == 1 else None


def _following(chosen: str, windows: dict) -> str | None:
    """The voyage with the earliest start after the chosen one's start (or end when its start
    is open); None when kb/ holds none or two share that start."""
    lo, hi = windows[chosen]
    after = lo or hi
    if after is None:
        return None
    later = [(s, v) for v, (s, _) in windows.items() if v != chosen and s is not None and s > after]
    if not later:
        return None
    first = min(s for s, _ in later)
    top = [v for s, v in later if s == first]
    return top[0] if len(top) == 1 else None


def _norm_place(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.casefold()).split())


def _route_ports(route: str) -> list[str]:
    """Port names of a kb/voyages route: "Western Australia (two loading ports) -> Rizhao"."""
    route = re.sub(r"\([^)]*\)", " ", route)
    return [_norm_place(p) for p in re.split(r"->|,|;|/", route) if _norm_place(p)]


def _same_place(mention: str, port: str) -> bool:
    """Whole-word match either way ("Newcastle Kooragang" names Newcastle; "Newc" does not)."""
    if not mention or not port:
        return False
    return bool(
        re.search(rf"\b{re.escape(port)}\b", mention)
        or re.search(rf"\b{re.escape(mention)}\b", port)
    )


def _counterparty(
    email: ParsedEmail, roles: PartyRoles, entities: ExtractedEntities, kb: KnowledgeBase
) -> tuple[str | None, str | None]:
    """(party code, role) of the other side of the email."""
    if entities.author_hint:
        m = _PARTY_CODE.search(entities.author_hint.text)
        if m and m.group(0) in kb.parties:
            return m.group(0), kb.parties[m.group(0)].role
    if email.direction == "Outbound":
        other = next((r for r in roles.receivers if r.party_code and r.role != _OUR_ROLE), None)
        return (other.party_code, other.role) if other else (None, None)
    return roles.sender.party_code, roles.sender.role


def _contract_level(
    vessel: str, voyage: str | None, counterparty: tuple[str | None, str | None], kb: KnowledgeBase
) -> str:
    """Owner-Head before Head-Sub: we are the owner side, so a party in both links deals with
    us as head charterer. A charterer-side party outside the chain (for example the head
    charterer's operator) deals with us for the head charterer (owner approved 2026-09-26)."""
    party, role = counterparty
    links = [
        link
        for link in kb.charter_links
        if link.vessel_code == vessel and (voyage is None or voyage in link.voyage_nos)
    ]
    for level in ("Owner-Head", "Head-Sub"):
        if party and any(
            link.level == level and party in (link.from_party, link.to_party) for link in links
        ):
            return _LEVEL_LABELS[level]
    if role == "Charterer":
        return _LEVEL_LABELS["Owner-Head"]
    return NOT_APPLICABLE


def d2_match_voyage(
    vessel: VesselMatch,
    entities: ExtractedEntities,
    thread: ThreadRef,
    email: ParsedEmail,
    roles: PartyRoles,
    kb: KnowledgeBase,
) -> VoyageMatch:
    """D2 Matching: which voyage of the matched vessel. Cascade: stated number, date window
    (ports break a tie), next-voyage cue words, thread; never a silent pick."""
    if vessel.status != "matched" or vessel.vessel_code not in kb.vessels:
        return VoyageMatch(
            voyage_no=None,
            basis="none",
            rule_triggered="vessel_not_matched",
            reason="no voyage without a matched vessel",
            inputs_snapshot={"vessel_status": vessel.status},
        )
    code = vessel.vessel_code
    order = kb.vessels[code].voyages
    windows = {
        v: (_bound(kb.voyages[(code, v)].start, False), _bound(kb.voyages[(code, v)].end, True))
        for v in order
        if (code, v) in kb.voyages
    }
    sent_day = email.sent_time.date() if email.sent_time else None  # the email's own offset
    in_window = [
        v
        for v, (lo, hi) in windows.items()
        if sent_day and (lo is None or lo <= sent_day) and (hi is None or sent_day <= hi)
    ]
    next_cue = _NEXT_VOYAGE_CUES.search(f"{email.subject}\n{email.new_text}")
    flags: list[str] = []
    snapshot = {
        "vessel": code,
        "sent_date": sent_day.isoformat() if sent_day else None,
        "windows": {
            v: [lo.isoformat() if lo else None, hi.isoformat() if hi else None]
            for v, (lo, hi) in windows.items()
        },
        "in_window": in_window,
        "next_voyage_cue": next_cue.group(0) if next_cue else None,
    }

    def result(voyage, basis, rule, reason, evidence=(), candidates=()):
        level = _contract_level(code, voyage, _counterparty(email, roles, entities, kb), kb)
        return VoyageMatch(
            voyage_no=voyage,
            basis=basis,
            contract_level=level,
            evidence=list(evidence),
            candidates=list(candidates),
            flags=flags,
            reason=reason,
            rule_triggered=rule,
            inputs_snapshot=snapshot,
        )

    def window_evidence(v):
        lo, hi = windows[v]
        quote = f"sent {sent_day} inside {v} window {lo or 'open'} to {hi or 'open'}"
        return Evidence(quote=quote, source="kb")

    # (1) stated numbers that belong to this vessel
    stated = []
    for m in entities.voyage_numbers:
        if m.text in order:
            if m.text not in [s.text for s in stated]:
                stated.append(m)
        elif "stated_number_of_other_vessel" not in flags:
            flags.append("stated_number_of_other_vessel")
    snapshot["stated"] = [s.text for s in stated]
    if len(stated) == 1:
        s = stated[0]
        return result(s.text, "stated", "stated", f"{s.text} stated in the email", [s.evidence])
    if len(stated) > 1:
        inside = [s for s in stated if s.text in in_window]
        if len(inside) == 1:
            s = inside[0]
            reason = f"{s.text} stated and inside the date window"
            return result(s.text, "stated", "stated", reason, [s.evidence])
        return result(
            None, "none", "stated_numbers_unresolved", "several stated voyages; the officer chooses",
            candidates=[s.text for s in stated],
        )  # fmt: skip

    # (2) date window; the ports named break a tie
    chosen, rule = None, None
    if len(in_window) == 1:
        chosen, rule = in_window[0], "date_window"
    elif len(in_window) > 1:
        ports = [_norm_place(p.text) for p in entities.ports]
        by_port = [
            v for v in in_window
            if any(_same_place(p, r) for p in ports for r in _route_ports(kb.voyages[(code, v)].route))
        ]  # fmt: skip
        later = _latest_start(in_window, windows)
        if len(by_port) == 1:
            chosen, rule = by_port[0], "date_window_ports"
        elif next_cue and later:
            # turnover day: the cue names the voyage that starts, by start date (not list order)
            reason = f"turnover day; '{next_cue.group(0)}' names {later}, the voyage that starts"
            evidence = [window_evidence(v) for v in in_window]
            return result(later, "inferred", "next_voyage_cue", reason, evidence, in_window)
        else:
            return result(
                None, "none", "date_window_tie",
                f"sent date fits {', '.join(in_window)}; the officer chooses",
                [window_evidence(v) for v in in_window], in_window,
            )  # fmt: skip

    # (3) next-voyage cue words move on to the following voyage (G4), by start date; when kb/
    # holds no following voyage the result is left open, never the current voyage
    if chosen and next_cue:
        following = _following(chosen, windows)
        if following:
            reason = f"'{next_cue.group(0)}' names the voyage after {chosen}"
            return result(
                following, "inferred", "next_voyage_cue", reason, [window_evidence(chosen)]
            )
        flags.append("next_voyage_not_in_kb")
        reason = f"'{next_cue.group(0)}' names the voyage after {chosen}, which kb/ does not hold"
        return result(
            None, "none", "next_voyage_not_in_kb", reason, [window_evidence(chosen)], [chosen]
        )
    if chosen:
        reason = f"sent {sent_day} inside the {chosen} window"
        return result(chosen, "inferred", rule, reason, [window_evidence(chosen)])

    # (4) the thread's earlier voyage
    if thread.thread_voyage in order and thread.thread_vessel in (None, code):
        ev = Evidence(
            quote=f"thread {thread.thread_id} matched {thread.thread_voyage}", source="kb"
        )
        return result(
            thread.thread_voyage, "inferred", "thread", "the thread's earlier voyage", [ev]
        )
    return result(None, "none", "no_fit", "no stated number, date window or thread voyage fits")


# --- D3 d3_rank_event (Ranking) ----------------------------------------------------

# design_knowledge section 4 [AMENDMENT 2026-09-26 T2.9]
D3_ACCEPT = 0.6  # inclusive; also the Medium bound
D3_HIGH = 0.8  # inclusive
D3_MAX_SECONDARY = 2
FYI_EVENT = "General / FYI"


def d3_rank_event(candidates: EventCandidates, action_rules: dict) -> EventDecision:
    """D3 Ranking: the event type from E6's candidates. Highest confidence at or above the
    threshold wins; below it the email is "General / FYI" and unsure. On a rule and LLM
    disagreement the rule's type stays, Low and unsure (never a silent choice)."""
    items = candidates.items
    snapshot = {
        "candidates": [[c.event_type, c.confidence, c.source] for c in items],
        "is_report": candidates.is_report,
        "llm_status": candidates.llm_status,
    }

    def ranked(pool):
        return sorted(pool, key=lambda c: (-c.confidence, c.event_type))

    def decision(event, tier, unsure, agree, rule, reason, secondary=()):
        return EventDecision(event_type=event, tier=tier, unsure=unsure, is_report=candidates.is_report,
                             sources_agree=agree, secondary_event_types=list(secondary)[:D3_MAX_SECONDARY],
                             reason=reason, rule_triggered=rule, inputs_snapshot=snapshot)  # fmt: skip

    if not items:
        return decision(FYI_EVENT, "Low", True, True, "no_candidates", "E6 gave no candidate")
    rule_top = next(iter(ranked(c for c in items if c.source == "rule")), None)
    llm_top = next(iter(ranked(c for c in items if c.source == "llm")), None)
    if rule_top and llm_top and rule_top.event_type != llm_top.event_type:
        return decision(
            rule_top.event_type, "Low", True, False, "rule_llm_disagree",
            f"rule says {rule_top.event_type}, the LLM says {llm_top.event_type}; the officer checks",
            [llm_top.event_type] if llm_top.event_type != FYI_EVENT else [],
        )  # fmt: skip

    top = ranked(items)[0]
    if top.confidence < D3_ACCEPT:
        reason = f"best candidate {top.event_type} ({top.confidence}) is below {D3_ACCEPT}"
        return decision(FYI_EVENT, "Low", True, True, "below_threshold", reason)
    if top.event_type not in action_rules:
        reason = f"{top.event_type} has no action_rules row"
        return decision(FYI_EVENT, "Low", True, True, "no_action_rule", reason)
    tier = "High" if top.confidence >= D3_HIGH else "Medium"
    secondary = []
    for c in ranked(items):
        if c.confidence < D3_ACCEPT:
            break
        if c.event_type not in (top.event_type, FYI_EVENT) and c.event_type not in secondary:
            secondary.append(c.event_type)
    reason = f"{top.event_type} at {top.confidence} ({top.source})"
    return decision(top.event_type, tier, False, True, "accepted", reason, secondary)


# --- D4 d4_rank_urgency (Ranking) --------------------------------------------------

# design_knowledge section 4 (D4 rows); only the conditions that can be read from the email are
# evaluated. The free-text `escalate_when` notes of kb/action_rules stay for the officer.
TIME_BAR_DAYS = 7
_URGENT_WORDS = re.compile(r"\b(?:urgent|asap|immediately|important)\b", re.I)
_MEDICAL_WORDS = re.compile(
    r"\bmedical\b|\binjur(?:ed|y|ies)\b|\bsick\b|\bhospital\b|医疗|受伤|生病", re.I
)
_OVERDUE = re.compile(r"\boverdue\b|逾期", re.I)
_REPLY_PREFIX = re.compile(r"^\s*(?:re|fw|fwd|回复|答复|转发)\s*(?:\[\d+\])?\s*[:：]", re.I)
_DATE_VALUE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?")
HIRE_EVENT = "Hire / SOA / Payment"
FYI_STATUS = "FYI - No Action"
# [AMENDMENT 2026-09-26 T4.1-a] a request in the Master's words: the email asks us for something
MASTER_ROLE = "Master / Vessel"
_REQUEST_WORDS = re.compile(
    r"\b(?:please|pls|kindly)\s+(?:kindly\s+)?(?:advise|approve|confirm|arrange|check|reply|revert|provide|send|"
    r"let us know|instruct)|\bapprov(?:e|al)\b|\brequest(?:ing|ed)?\b|\bapplication\b|\?|？|申请|审批|批准|"
    r"请(?:确认|回复|安排|告知|指示)",
    re.I,
)
ACTION_STATUS = "Action Required"


def _deadline(entities: ExtractedEntities, email: ParsedEmail) -> datetime | None:
    """Earliest readable date of kind deadline; a date without a time is 00:00 in the email's
    own offset. A value that cannot be read is ignored (never guessed)."""
    zone = email.sent_time.tzinfo if email.sent_time else timezone.utc
    found = []
    for fact in entities.dates:
        m = _DATE_VALUE.search(fact.value) if fact.kind == "deadline" else None
        if not m:
            continue
        try:
            found.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                  int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=zone))  # fmt: skip
        except ValueError:
            continue
    return min(found) if found else None


def d4_rank_urgency(
    event: EventDecision,
    voyage: VoyageMatch,
    entities: ExtractedEntities,
    email: ParsedEmail,
    action_rules: dict,
    now: datetime,
    sender_role: str | None = None,
) -> NeedsActionDecision:
    """D4 Ranking: the email's statuses and its suggested priority (U1, U2). Row default by
    direction, raised by the escalation conditions; a raise to 4 or 5 turns FYI into Action
    Required; reports stay FYI at 1; an attachment-only conversation is never FYI.
    [AMENDMENT 2026-09-26 T4.1-a] An inbound email from the Master that asks for nothing (no
    request words in the subject or the new text) and has no escalation is FYI at priority 2 at
    most: the Master keeps us informed; the officer files it."""
    deadline = _deadline(entities, email)
    rule = action_rules.get(event.event_type)
    snapshot = {
        "event_type": event.event_type, "is_report": event.is_report, "direction": email.direction,
        "row_priority": rule.default_priority if rule else None, "deadline": deadline.isoformat() if deadline else None,
        "now": now.isoformat(), "attachment_dependent": email.attachment_dependent, "sender_role": sender_role,
    }  # fmt: skip

    def decision(statuses, priority, rule_triggered, reason, escalated=(), flags=()):
        return NeedsActionDecision(statuses=statuses, priority=priority, reason=reason, deadline=deadline,
                                   escalated_by=list(escalated), flags=list(flags), rule_triggered=rule_triggered,
                                   inputs_snapshot=snapshot)  # fmt: skip

    if event.is_report:
        return decision([FYI_STATUS], 1, "report", "routine report: FYI at priority 1")
    if rule is None:
        return decision([ACTION_STATUS], 3, "no_rule_row", f"no action_rules row for {event.event_type}; a person checks",
                        flags=["no_rule_row"])  # fmt: skip

    statuses = list(
        rule.outbound_needs_action if email.direction == "Outbound" else rule.default_needs_action
    )
    raised: dict[str, int] = {}
    if deadline and deadline < now:
        raised["deadline_passed"] = 5
    elif deadline and deadline <= now + timedelta(days=TIME_BAR_DAYS):
        raised["time_bar_within_days"] = 5
    if _MEDICAL_WORDS.search(email.new_text):
        raised["medical"] = 5
    if event.event_type == HIRE_EVENT and _OVERDUE.search(email.new_text):
        raised["payment_overdue"] = 5
    first_subject = not _REPLY_PREFIX.match(email.subject)
    if _URGENT_WORDS.search(email.new_text) or (
        first_subject and _URGENT_WORDS.search(email.subject)
    ):
        raised["sender_marks_urgent"] = 5
    priority = max([rule.default_priority, *raised.values()])
    escalated = sorted(raised)
    reason = (
        f"{event.event_type}: row default {'/'.join(statuses)} at priority {rule.default_priority}"
    )
    rule_triggered = "row_default"
    if escalated:
        reason += f"; raised to {priority} by {', '.join(escalated)}"
        rule_triggered = "escalated"
    if (
        not escalated
        and email.direction == "Inbound"
        and sender_role == MASTER_ROLE
        and not _REQUEST_WORDS.search(f"{email.subject}\n{email.new_text}")
    ):
        statuses, priority = [FYI_STATUS], min(priority, 2)
        reason = f"{event.event_type}: the Master informs and asks for nothing: FYI at priority {priority}"
        rule_triggered = "master_informs"
    if priority >= 4 and FYI_STATUS in statuses:
        statuses = [ACTION_STATUS]
        reason += "; a raise to 4 or 5 makes FYI Action Required"
    if email.attachment_dependent and statuses == [FYI_STATUS]:
        statuses = [ACTION_STATUS]
        reason += "; content is in an attachment, so never FYI by rule"
        rule_triggered = rule_triggered if escalated else "attachment_dependent"
    return decision(statuses, priority, rule_triggered, reason, escalated)


# --- D5 d5_rank_actions (Ranking) --------------------------------------------------

D5_KEEP = 3
APPROVAL_ACTION_TYPES = {"Seek Internal Approval"}  # design_knowledge section 4 (U2)
REPLY_ACTION_TYPES = {"Follow Up (chase reply)"}


def d5_rank_actions(
    candidates: ActionCandidates,
    needs: NeedsActionDecision,
    event: EventDecision,
    action_rules: dict,
) -> RankedActions:
    """D5 Ranking (U1, U2, [AMENDMENT 2026-09-26 T2.13]): every action takes D4's priority; order
    by due date (none last), then rule order (primary event first, then the row's order); one
    per type and event (the earliest due); keep three; the approval and reply marks come from
    the action type."""
    events = [event.event_type, *event.secondary_event_types]

    def rule_order(c: ActionCandidate) -> tuple[int, int]:
        rule = action_rules.get(c.for_event)
        types = rule.default_action_types if rule else []
        event_rank = events.index(c.for_event) if c.for_event in events else len(events)
        return event_rank, types.index(c.action_type) if c.action_type in types else len(types)

    def key(c: ActionCandidate):
        return (c.due is None, c.due or date.max, *rule_order(c))

    kept: dict[tuple[str, str], ActionCandidate] = {}
    for c in sorted(candidates.items, key=key):
        kept.setdefault((c.action_type, c.for_event), c)
    ordered = list(kept.values())[:D5_KEEP]
    snapshot = {
        "priority": needs.priority,
        "candidates": [
            [c.action_type, c.for_event, c.due.isoformat() if c.due else None]
            for c in candidates.items
        ],
    }
    if not ordered:
        return RankedActions(
            items=[],
            reason="no candidates: No Action",
            rule_triggered="no_action",
            inputs_snapshot=snapshot,
        )
    items = [
        RankedAction(
            **c.model_dump(),
            rank=i,
            priority=needs.priority,
            needs_approval=c.action_type in APPROVAL_ACTION_TYPES,
            awaiting_reply=c.action_type in REPLY_ACTION_TYPES,
        )  # fmt: skip
        for i, c in enumerate(ordered, start=1)
    ]
    reason = f"{len(items)} of {len(candidates.items)} kept by due date and rule order, priority {needs.priority}"
    return RankedActions(
        items=items, reason=reason, rule_triggered="ranked", inputs_snapshot=snapshot
    )


# --- shared: the email's suggested statuses (U2, used by D6 and E10) ---------------

APPROVAL_STATUS = "Approval Required"
WAITING_STATUS = "Waiting for Reply"


def suggested_statuses(needs: NeedsActionDecision, actions: RankedActions) -> list[str]:
    """[AMENDMENT 2026-09-26 U2] D4's statuses, plus Approval Required when an action needs
    approval, plus Waiting for Reply when an action awaits a reply; with actions, FYI is dropped
    and, if nothing is left, the status is Action Required.
    [AMENDMENT 2026-09-26 T4.1-c, owner: "use whichever is more accurate"] When D4 itself says
    FYI, the suggestion stays FYI; the actions stay listed and the officer can still tick a status
    (statuses on the 74 library labels 65% to 70%, misses 1 to 3)."""
    if list(needs.statuses) == [FYI_STATUS]:
        return [FYI_STATUS]
    statuses = list(needs.statuses)
    if any(a.needs_approval for a in actions.items):
        statuses.append(APPROVAL_STATUS)
    if any(a.awaiting_reply for a in actions.items):
        statuses.append(WAITING_STATUS)
    if actions.items:
        statuses = [s for s in statuses if s != FYI_STATUS] or [ACTION_STATUS]
    return check_statuses(list(dict.fromkeys(statuses)))


# --- D6 d6_match_task (Matching) ---------------------------------------------------

MISSING = "-"
ALWAYS_HUMAN = {
    "LOI (Letter of Indemnity)",
    "Claim",
    "Off-hire",
    "Vessel Defect / Repair / Breakdown",
}
# design_knowledge section 1: topic template per event type; {part} is filled from the email
TOPICS = {
    "Vessel Schedule Update (ETA/ETB/ETD)": "schedule:{port}",
    "Voyage Instructions / Port Nomination": "nomination:{port}",
    "Delivery Notice": "delivery",
    "Redelivery Notice": "redelivery",
    "Hire / SOA / Payment": "hire:{invoice}",
    "Bunker (Stem / Quote / ROB / Quality)": "bunker:{port}",
    "Loading / Cargo Operations": "loading:{port}",
    "Discharging": "discharging:{port}",
    "Notice of Readiness / Laytime / Demurrage": "laytime:{port}",
    "Hold Cleaning / Cargo Hold Condition": "holdclean",
    "Survey Arrangement / Quotation": "survey:{port}",
    "Off-hire": "offhire:{missing}",
    "Vessel Defect / Repair / Breakdown": "defect:{missing}",
    "Claim": "claim:{claim}",
    "LOI (Letter of Indemnity)": "loi:{port_or_bl}",
    "P&I / Insurance": "pi:{pi_case}",
    "Stowage Plan / Cargo Clauses": "stowage",
    "Cash to Master / Supply (CTM, Fresh Water, Provisions)": "supply:{port}:{item}",
    "Port Agency / Port Costs (DA)": "da:{port}",
    "Port Delay / Congestion / Strike": "delay:{port}",
    "Crew (Change / Medical)": "crew:{crew}",
    "Inspection / Vetting / PSC": "inspection:{port}",
    "CP Terms / Recap / Addendum": "cp:{cp}",
    "Sanctions / Compliance / KYC": "kyc:{missing}",
    "Fixture Enquiry / Offer / Counter": "fixture:{fixture}",
}
_TOPIC_EVENT = {template.split(":")[0]: event_type for event_type, template in TOPICS.items()}
_SUPPLY_ITEMS = (
    ("cash", r"\bcash\b|\bctm\b"),
    ("fw", r"\bfresh water\b|\bfw\b"),
    ("provisions", r"\bprovisions?\b|\bstores\b"),
)


def _part(text: str | None) -> str:
    return "_".join(re.sub(r"[^\w]+", " ", (text or "").casefold()).split()) or MISSING


def _topic(event_type: str, entities: ExtractedEntities, email: ParsedEmail) -> str | None:
    template = TOPICS.get(event_type)
    if template is None:
        return None
    refs = {r.kind: r.value for r in reversed(entities.references)}
    port = _part(entities.ports[0].text) if entities.ports else MISSING
    item = next(
        (name for name, pattern in _SUPPLY_ITEMS if re.search(pattern, email.new_text, re.I)),
        "other",
    )
    crew = (
        "medical"
        if re.search(r"\bmedical\b|\binjur|\bsick\b|\bhospital\b", email.new_text, re.I)
        else "change"
    )
    parts = {
        "port": port, "invoice": _part(refs.get("invoice")), "claim": _part(refs.get("claim")),
        "pi_case": _part(refs.get("pi_case")), "port_or_bl": _part(refs.get("bl")) if "bl" in refs else port,
        "cp": _part(entities.cp_references[0].text) if entities.cp_references else MISSING,
        "fixture": _part(refs.get("fixture")), "item": item, "crew": crew, "missing": MISSING,
    }  # fmt: skip
    return template.format(**parts)


def _family(event_type: str, families: dict[str, str]) -> str:
    return families.get(event_type, event_type)


def _task_event(task: Task) -> str | None:
    return _TOPIC_EVENT.get(task.task_key.split("|")[-1].split(":")[0])


def _complete(key: str) -> bool:
    return MISSING not in key.split("|")[-1].split(":") and key.split("|")[1] != "UNK"


def _latest(tasks: list[Task]) -> Task:
    """The most recent open task: the one whose latest source email id is highest."""
    return max(tasks, key=lambda t: (max(t.source_email_ids, default=""), t.task_id))


def d6_match_task(
    actions: RankedActions,
    vessel: VesselMatch,
    voyage: VoyageMatch,
    event: EventDecision,
    needs: NeedsActionDecision,
    closure: ClosureCheck,
    entities: ExtractedEntities,
    thread: ThreadRef,
    email: ParsedEmail,
    lookup: TaskLookup,
    families: dict[str, str],
) -> TaskDisposition:
    """D6 Matching (design_backend.md D6 row, design_knowledge section 1): create, update, close
    proposal or none. Update, never duplicate: exact key, then same thread and family; a closed
    task is never reopened; the LLM's closure answer is input only."""
    statuses = suggested_statuses(needs, actions)
    snapshot = {"event_type": event.event_type, "statuses": statuses, "actions": [a.action_type for a in actions.items],
                "lookup": lookup.status, "open_tasks": [t.task_id for t in lookup.tasks]}  # fmt: skip

    def result(kind, rule, reason, **kw):
        return TaskDisposition(
            kind=kind, rule_triggered=rule, reason=reason, inputs_snapshot=snapshot, **kw
        )

    if lookup.status != "ok":
        return result(
            "none",
            "store_unavailable",
            "task lookup unavailable: the email is held",
            flags=["store_unavailable"],
        )
    if vessel.status != "matched" or not vessel.vessel_code:
        return result("none", "vessel_not_matched", "no task without a matched vessel")
    if event.is_report:
        return result("none", "report", "a report never makes a task")
    topic = _topic(event.event_type, entities, email)
    key = f"{vessel.vessel_code}|{voyage.voyage_no or 'UNK'}|{topic}" if topic else None
    snapshot["task_key"] = key
    open_tasks = [t for t in lookup.tasks if t.status == "open"]
    flags = []
    if key and any(p.task_key == key and p.kind == "create" for p in lookup.pending_proposals):
        flags.append("pending_same_key")

    # close proposal first (D6-S11); the LLM's answer is input only, this rule decides
    for r in closure.results:
        task = next((t for t in open_tasks if t.task_id == r.task_id), None)
        if (r.settled and r.evidence and task and task.vessel_code == vessel.vessel_code
                and task.voyage_no == voyage.voyage_no):  # fmt: skip
            return result("close_proposal", "closure_settled", f"E8 quotes that {task.task_id} is settled",
                          task_key=task.task_key, target_task_id=task.task_id, target_task_version=task.version,
                          close_warning=_task_event(task) in ALWAYS_HUMAN or event.event_type in ALWAYS_HUMAN,
                          flags=flags)  # fmt: skip

    target, rule = None, None
    if key and _complete(key):
        same = [t for t in open_tasks if t.task_key == key]
        if len(same) > 1:
            flags.append("duplicate_key_found")
        if same:
            target, rule = _latest(same), "exact_key"
    if target is None and key:
        members = set(thread.member_email_ids)
        family = _family(event.event_type, families)
        in_thread = [
            t for t in open_tasks
            if members & set(t.source_email_ids) and _task_event(t)
            and _family(_task_event(t), families) == family
            and not (_complete(key) and _complete(t.task_key) and t.task_key != key and _task_event(t) == event.event_type)
        ]  # fmt: skip
        if in_thread:
            target, rule = _latest(in_thread), "same_thread_family"

    if target is not None:
        old = list(target.statuses)
        merged = list(dict.fromkeys([*old, *statuses]))
        if (
            email.direction == "Inbound"
            and WAITING_STATUS in old
            and set(thread.member_email_ids) & set(target.source_email_ids)
        ):
            merged = [
                s for s in merged if s != WAITING_STATUS
            ]  # an inbound reply answers the wait (D6-S20)
        merged = [s for s in merged if s != FYI_STATUS] or [FYI_STATUS]
        merged = check_statuses(merged)
        changed = {}
        if merged != old:
            changed["statuses"] = FieldChange(old=old, new=merged)
        new_types = [
            a.action_type
            for a in actions.items
            if a.action_type not in [x.action_type for x in target.actions]
        ]
        if new_types:
            changed["actions_added"] = FieldChange(old=None, new=new_types)
        top = max([a.priority for a in actions.items], default=0)
        if top > target.priority:  # an email never lowers a priority (D6-S23)
            changed["priority"] = FieldChange(old=target.priority, new=top)
        return result("update", rule, f"{rule.replace('_', ' ')} with {target.task_id}", task_key=target.task_key,
                      target_task_id=target.task_id, target_task_version=target.version, changed_fields=changed,
                      new_statuses=merged, flags=flags)  # fmt: skip
    if key and actions.items:
        return result("create", "no_match_create", "no open task matches and the email needs an action",
                      task_key=key, new_statuses=statuses, flags=flags)  # fmt: skip
    return result("none", "no_action", "no open task matches and no action is needed", flags=flags)
