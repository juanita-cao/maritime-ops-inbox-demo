"""E17 e17_get_email, E18 e18_search_emails: scenarios E17-S01 to S03, E18-S01 to S05
(design_backend.md sections 4, 10.15, "read-only tools", 2026-09-28)."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src import e_nodes as e
from src import store as st
from src.kb_loader import KnowledgeBase
from src.schemas import (
    EventDecision, FactChanges, NeedsActionDecision, ParsedEmail, RankedActions, SearchEmailsArgs,
    TaskDisposition, VesselMatch, VoyageMatch,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
SENT = datetime(2026, 7, 30, 10, 0, tzinfo=CST)
KB = KnowledgeBase(taxonomy={}, action_rules={}, event_families={}, vessels={}, voyages={},
                   charter_links=[], parties={}, contacts={})  # fmt: skip


def mail(email_id, sent=SENT, new_text="Noon report."):
    return ParsedEmail(email_id=email_id, subject=f"{email_id} subject", subject_norm=f"{email_id} subject",
                       sent_time=sent, direction="Inbound", sender="mail05@CPY-03.example",
                       new_text=new_text)  # fmt: skip


def save(db, email_id, vessel_code, event_type, statuses, sent=SENT):
    """Saves an applied proposal (and its email), the only status E18 searches (build_chat_context
    and E13's vessel view use the same "applied" set for a resolved vessel/event/status)."""
    vessel = VesselMatch(vessel_code=vessel_code, status="matched", tier="High", score=1.0, rule_triggered="r")
    voyage = VoyageMatch(voyage_no="V202", basis="stated", rule_triggered="r")
    event = EventDecision(event_type=event_type, tier="High", unsure=False, is_report=True, sources_agree=True,
                          rule_triggered="r")  # fmt: skip
    needs = NeedsActionDecision(statuses=statuses, priority=3, reason="r", rule_triggered="r")
    task = TaskDisposition(kind="none", rule_triggered="r")
    proposal = e.e10_build_proposal(f"P-{email_id}", mail(email_id, sent), vessel, voyage, event, needs,
                                    FactChanges(), RankedActions(), task, e.Lane(lane="auto_apply"))  # fmt: skip
    e.e10b_save_proposal(proposal, mail(email_id, sent), None, db)
    with db.transaction() as tx:
        tx.set_proposal_status(f"P-{email_id}", expected="open", new="applied")


@pytest.fixture
def db(tmp_path):
    store = st.Store.open(tmp_path / "app.sqlite")
    yield store
    store.close()


# --- E17 -------------------------------------------------------------------------------------


def test_e17_s01_known_clean_id_returns_the_chat_email(db):
    save(db, "E010", "VSL-02", "Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)", ["FYI - No Action"])
    view = e.e17_get_email("E010", db, KB)
    assert view.email_id == "E010" and view.subject == "E010 subject"


def test_e17_s02_unknown_id_returns_none(db):
    save(db, "E010", "VSL-02", "General / FYI", ["FYI - No Action"])
    assert e.e17_get_email("E999", db, KB) is None


def test_e17_s03_unsanitized_email_returns_none(db):
    """Same E4-clean boundary as _chat_email today: a real-looking phone number blocks it."""
    save(db, "E011", "VSL-02", "General / FYI", ["FYI - No Action"])
    with db.transaction() as tx:
        tx.save_email(mail("E011", new_text="Call +86 138 1234 5678 now."), None)
    assert e.e17_get_email("E011", db, KB) is None


# --- E18 -------------------------------------------------------------------------------------


def test_e18_s01_filters_by_vessel(db):
    save(db, "E010", "VSL-02", "General / FYI", ["FYI - No Action"])
    save(db, "E011", "VSL-03", "General / FYI", ["FYI - No Action"])
    out = e.e18_search_emails("VSL-02", None, None, 10, db, KB)
    assert [v.email_id for v in out] == ["E010"]


def test_e18_s02_filters_by_status(db):
    save(db, "E010", "VSL-02", "General / FYI", ["Approval Required"])
    save(db, "E011", "VSL-02", "General / FYI", ["FYI - No Action"])
    out = e.e18_search_emails(None, None, "Approval Required", 10, db, KB)
    assert [v.email_id for v in out] == ["E010"]


def test_e18_s03_no_filters_is_rejected_as_invalid():
    """Not "return everything": SearchEmailsArgs itself requires at least one filter, checked
    before e18_search_emails ever runs (e_nodes._execute_tool_calls validates it first)."""
    with pytest.raises(ValidationError):
        SearchEmailsArgs()


def test_e18_s04_limit_is_capped_at_20_in_code_regardless_of_the_argument(db):
    for i in range(25):
        save(db, f"E{i:03d}", "VSL-02", "General / FYI", ["FYI - No Action"], sent=SENT + timedelta(minutes=i))
    out = e.e18_search_emails("VSL-02", None, None, 1000, db, KB)
    assert len(out) == 20


def test_e18_s05_no_matches_is_an_empty_list(db):
    save(db, "E010", "VSL-02", "General / FYI", ["FYI - No Action"])
    assert e.e18_search_emails("VSL-99", None, None, 10, db, KB) == []


def test_e18_orders_newest_first(db):
    save(db, "E010", "VSL-02", "General / FYI", ["FYI - No Action"], sent=SENT)
    save(db, "E011", "VSL-02", "General / FYI", ["FYI - No Action"], sent=SENT + timedelta(hours=1))
    out = e.e18_search_emails("VSL-02", None, None, 10, db, KB)
    assert [v.email_id for v in out] == ["E011", "E010"]
