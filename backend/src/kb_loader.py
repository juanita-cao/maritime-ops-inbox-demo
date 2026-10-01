"""Read-only knowledge base (design_backend.md section 3): load the kb/ CSV tables once at
startup and check them against the taxonomy and against each other.

Every problem found is collected and raised together as one KbError, so a broken table stops
the service at startup instead of producing a wrong decision later. Nodes receive the loaded
KnowledgeBase as an argument; nothing reads it as a hidden global.
"""

import csv
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel

from src.schemas import DueType, NeedsAction, check_statuses

# The label workbook keeps the charter party as its own columns (cp_dependency, cp_clause_used);
# the taxonomy list decision_basis holds only the other sources. A rule row may therefore name
# the charter party with this value.
CP_BASIS = "CP terms"

REQUIRED_LISTS = (
    "event_types",
    "needs_action",
    "action_type",
    "decision_basis",
    "contract_level",
    "roles",
    "priority",
    "due_type",
    "facts_updated",
)
TaskPolicy = Literal["update", "facts_only", "none"]
LinkLevel = Literal["Owner-Head", "Head-Sub", "Management"]
Confidence = Literal["stated", "inferred", "unknown"]


class KbError(Exception):
    """The knowledge base cannot be used. `problems` lists every finding."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("knowledge base invalid:\n- " + "\n- ".join(problems))


class ActionRule(BaseModel):
    event_type: str
    default_needs_action: list[str]  # [AMENDMENT 2026-09-26 U2] one or more statuses
    outbound_needs_action: list[str]
    default_action_types: list[str]
    decision_basis: str | None
    task_key: str
    task_policy: str
    escalate_when: str
    notes: str
    default_priority: int
    default_due_type: str | None


class Party(BaseModel):
    party_code: str
    party_type: str
    role: str  # taxonomy role [AMENDMENT 2026-09-26 T2.3]
    description: str
    vessel_codes: list[str]
    confidence: str
    evidence: str


class Contact(BaseModel):
    contact_code: str
    party_code: str | None
    party_type: str


class Vessel(BaseModel):
    vessel_code: str
    source_document: str
    voyages: list[str]
    owner_party: str
    manager_party: str
    vessel_mailbox_party: str


class Voyage(BaseModel):
    vessel_code: str
    voyage_no: str
    status: str
    route: str
    start: str
    end: str
    facts: str
    source: str


class CharterLink(BaseModel):
    link_id: str
    vessel_code: str
    voyage_nos: list[str]
    level: str
    from_party: str
    to_party: str
    cp_reference: str
    start: str
    end: str
    confidence: str
    evidence: str


class KnowledgeBase(BaseModel):
    taxonomy: dict[str, list[str]]
    action_rules: dict[str, ActionRule]  # by event type
    event_families: dict[str, str]  # event type -> family
    parties: dict[str, Party]
    contacts: dict[str, Contact]
    vessels: dict[str, Vessel]
    voyages: dict[tuple[str, str], Voyage]  # (vessel_code, voyage_no)
    charter_links: list[CharterLink]


OWN_PARTY_TYPE = "operator / manager"


def own_domains(kb: KnowledgeBase) -> frozenset[str]:
    """Our mail domains (E1 argument, [AMENDMENT 2026-09-26 T2.1]): the domains of the contacts
    whose party type is operator / manager."""
    return frozenset(
        code.rsplit("@", 1)[1].lower()
        for code, contact in kb.contacts.items()
        if contact.party_type == OWN_PARTY_TYPE and "@" in code
    )


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def _read(kb_dir: Path, name: str, problems: list[str]) -> list[dict[str, str]]:
    path = kb_dir / name
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]
    except (FileNotFoundError, OSError) as exc:
        problems.append(f"{name}: cannot be read ({exc.__class__.__name__})")
        return []


def load_kb(kb_dir: Path) -> KnowledgeBase:
    problems: list[str] = []

    taxonomy: dict[str, list[str]] = {}
    for row in _read(kb_dir, "taxonomy.csv", problems):
        taxonomy.setdefault(row["list_name"], []).append(row["value"])
    for name in REQUIRED_LISTS:
        if taxonomy.get(name) is None and taxonomy:
            problems.append(f"taxonomy.csv: list {name} is missing")
    # The code and the taxonomy must name the same values (no silent drift).
    for list_name, code_values in (("needs_action", NeedsAction), ("due_type", DueType)):
        if taxonomy and taxonomy.get(list_name) != list(get_args(code_values)):
            problems.append(
                f"taxonomy.csv: list {list_name} {taxonomy.get(list_name)} differs from "
                f"schemas.py {list(get_args(code_values))}"
            )

    def known(list_name: str) -> set[str]:
        return set(taxonomy.get(list_name, []))

    def check(where: str, field: str, value: str, allowed: set[str]) -> None:
        if value not in allowed:
            problems.append(f"{where}: {field} {value!r} is not a known value")

    # --- action rules ---
    action_rules: dict[str, ActionRule] = {}
    rule_statuses = known("needs_action") - {"Close"}
    for i, row in enumerate(_read(kb_dir, "action_rules.csv", problems), start=2):
        where = f"action_rules.csv line {i}"
        check(where, "event_type", row["event_type"], known("event_types"))
        statuses: dict[str, list[str]] = {}
        for field in ("default_needs_action", "outbound_needs_action"):
            # [AMENDMENT 2026-09-26 U2] several statuses, separated by ";"
            parts = _split(row[field])
            for part in parts:
                check(where, field, part, rule_statuses)
            try:
                statuses[field] = check_statuses(parts)
            except ValueError as exc:
                problems.append(f"{where}: {field} {row[field]!r}: {exc}")
                statuses[field] = parts
        actions = _split(row["default_action_types"])
        for action in actions:
            check(where, "default_action_types", action, known("action_type"))
        if row["decision_basis"]:
            check(
                where, "decision_basis", row["decision_basis"], known("decision_basis") | {CP_BASIS}
            )
        check(where, "task_policy", row["task_policy"], set(get_args(TaskPolicy)))
        try:
            priority = int(row["default_priority"])
        except ValueError:
            priority = 0
        if not 1 <= priority <= 5:
            problems.append(f"{where}: default_priority {row['default_priority']!r} is not 1 to 5")
        if row["default_due_type"]:
            check(where, "default_due_type", row["default_due_type"], known("due_type"))
        action_rules[row["event_type"]] = ActionRule(
            event_type=row["event_type"],
            default_needs_action=statuses["default_needs_action"],
            outbound_needs_action=statuses["outbound_needs_action"],
            default_action_types=actions,
            decision_basis=row["decision_basis"] or None,
            task_key=row["task_key"],
            task_policy=row["task_policy"],
            escalate_when=row["escalate_when"],
            notes=row["notes"],
            default_priority=priority,
            default_due_type=row["default_due_type"] or None,
        )
    if taxonomy:
        for event_type in known("event_types") - set(action_rules):
            problems.append(f"action_rules.csv: event type {event_type!r} has no action_rules row")

    # --- event families ---
    event_families: dict[str, str] = {}
    for i, row in enumerate(_read(kb_dir, "event_families.csv", problems), start=2):
        check(f"event_families.csv line {i}", "event_type", row["event_type"], known("event_types"))
        event_families[row["event_type"]] = row["family"]

    # --- ontology: parties, contacts, vessels, voyages, charter links ---
    parties = {
        row["party_code"]: Party(**{**row, "vessel_codes": _split(row["vessel_codes"])})
        for row in _read(kb_dir, "parties.csv", problems)
    }
    vessels = {
        row["vessel_code"]: Vessel(**{**row, "voyages": _split(row["voyages"])})
        for row in _read(kb_dir, "vessels.csv", problems)
    }
    voyages = {
        (row["vessel_code"], row["voyage_no"]): Voyage(**row)
        for row in _read(kb_dir, "voyages.csv", problems)
    }
    contacts = {
        row["contact_code"]: Contact(
            contact_code=row["contact_code"],
            party_code=row["party_code"] or None,
            party_type=row["party_type"],
        )
        for row in _read(kb_dir, "contacts.csv", problems)
    }
    charter_links = [
        CharterLink(
            **{k: v for k, v in row.items() if k != "voyage_no"},
            voyage_nos=_split(row["voyage_no"]),
        )
        for row in _read(kb_dir, "charter_links.csv", problems)
    ]

    for code, party in parties.items():
        check(f"parties.csv {code}", "confidence", party.confidence, set(get_args(Confidence)))
        check(f"parties.csv {code}", "role", party.role, known("roles"))
        for vessel in party.vessel_codes:
            check(f"parties.csv {code}", "vessel_codes", vessel, set(vessels))
    for code, contact in contacts.items():
        if contact.party_code is not None:
            check(f"contacts.csv {code}", "party_code", contact.party_code, set(parties))
    for code, vessel in vessels.items():
        for field in ("owner_party", "manager_party", "vessel_mailbox_party"):
            check(f"vessels.csv {code}", field, getattr(vessel, field), set(parties))
        for voyage_no in vessel.voyages:
            check(
                f"vessels.csv {code}", "voyages", voyage_no, {v for (c, v) in voyages if c == code}
            )
    for code, voyage_no in voyages:
        check(f"voyages.csv {code} {voyage_no}", "vessel_code", code, set(vessels))
    for link in charter_links:
        where = f"charter_links.csv {link.link_id}"
        check(where, "vessel_code", link.vessel_code, set(vessels))
        check(where, "level", link.level, set(get_args(LinkLevel)))
        check(where, "confidence", link.confidence, set(get_args(Confidence)))
        for party in (link.from_party, link.to_party):
            check(where, "party", party, set(parties))
        for voyage_no in link.voyage_nos:
            check(where, "voyage_no", voyage_no, {v for (c, v) in voyages if c == link.vessel_code})

    if problems:
        raise KbError(problems)
    return KnowledgeBase(
        taxonomy=taxonomy,
        action_rules=action_rules,
        event_families=event_families,
        parties=parties,
        contacts=contacts,
        vessels=vessels,
        voyages=voyages,
        charter_links=charter_links,
    )
