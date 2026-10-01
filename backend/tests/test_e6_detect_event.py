"""T2.8 E6 e6_detect_event: scenarios E6-S01 to S06 (design_backend.md sections 10, 10.4), on a
fake LLM client. The report rule: inbound, a report keyword in the subject, and at least one
report field in the text [AMENDMENT 2026-09-26 T2.8]. Synthetic text, codes only."""

from datetime import datetime, timezone

import pytest

from src import e_nodes as e
from src.llm_client import LlmError
from src.schemas import ExtractedEntities, ParsedEmail, PartyRef, PartyRoles, VoyageMatch

REPORT = "Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)"
FYI = "General / FYI"
TAXONOMY = {
    "event_types": [REPORT, FYI, "Redelivery Notice", "Survey Arrangement / Quotation", "Claim"]
}
ENTS = ExtractedEntities(llm_status="ok")
VOYAGE = VoyageMatch(voyage_no="V202", basis="stated")
MASTER = PartyRoles(
    sender=PartyRef(address="mail06@CPY-05.example", party_code="CPY-05", role="Master / Vessel")
)


class FakeLlm:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, key, user))
        answer = self.answers.pop(0) if self.answers else {}
        if isinstance(answer, Exception):
            raise answer
        return answer


def email(subject, text, direction="Inbound"):
    return ParsedEmail(email_id="E010", subject=subject, subject_norm=subject.lower(),
                       sent_time=datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc), direction=direction,
                       sender="mail06@CPY-05.example", new_text=text)  # fmt: skip


def run(mail, llm):
    return e.e6_detect_event(mail, ENTS, VOYAGE, MASTER, TAXONOMY, llm)


NOON_TEXT = "Position 12-30N 125-10E. Speed 12.5 kn. ROB VLSFO 450.5 MT. ETA Newcastle 4 Aug."


def test_e6_s01_inbound_report_is_settled_by_the_rule_without_a_call():
    llm = FakeLlm()
    out = run(email("M/V VSL-02// NOON REPORT 20260730", NOON_TEXT), llm)
    assert out.is_report is True and out.llm_status == "skipped" and llm.calls == []
    item = out.items[0]
    assert (item.event_type, item.source) == (REPORT, "rule")
    assert item.evidence.source == "subject" and "NOON REPORT" in item.evidence.quote


@pytest.mark.parametrize(
    "subject",
    ["VSL-02//Daily Report 20260726", "VSL-01 - ARRIVAL REPORT", "VSL-02// COSP REPORT/BUNBURY",
     "VSL-01 - EOSP REPORT", "VSL-02//DAILY ETA NOTICE/2026.07.23", "VSL-01 -CPY-02 - BERTHING REPORT"],
)  # fmt: skip
def test_e6_s01_report_keywords_from_the_titles(subject):
    assert run(email(subject, NOON_TEXT), FakeLlm()).is_report is True


def test_e6_s02_report_keyword_without_report_fields_goes_to_the_llm():
    llm = FakeLlm(
        {"items": [{"event_type": "Claim", "confidence": 0.8, "quote": "cargo damage claim"}]}
    )
    out = run(email("VSL-02 - Noon report", "Please see the cargo damage claim attached."), llm)
    assert out.is_report is False and out.llm_status == "ok" and len(llm.calls) == 1
    assert [(i.event_type, i.source) for i in out.items] == [("Claim", "llm")]


def test_e6_s02_report_word_that_is_not_a_report_title_goes_to_the_llm():
    llm = FakeLlm({"items": []})
    out = run(email("VSL-02 - PSC INSPECTION REPORT", NOON_TEXT), llm)
    assert out.is_report is False and len(llm.calls) == 1


def test_e6_s03_outbound_email_with_a_report_keyword_is_not_a_report():
    llm = FakeLlm({"items": []})
    out = run(email("RE: VSL-02 NOON REPORT", NOON_TEXT, direction="Outbound"), llm)
    assert out.is_report is False and len(llm.calls) == 1


def test_e6_s04_type_outside_the_taxonomy_is_rejected_and_the_rest_kept():
    llm = FakeLlm({"items": [
        {"event_type": "Weather Chat", "confidence": 0.9, "quote": "redelivery"},
        {"event_type": "Redelivery Notice", "confidence": 0.7, "quote": "redelivery"},
    ]})  # fmt: skip
    out = run(email("VSL-02 notice", "Charterers give notice of redelivery."), llm)
    assert [i.event_type for i in out.items] == ["Redelivery Notice"]


def test_e6_s04_nothing_valid_left_gives_general_fyi():
    llm = FakeLlm({"items": [{"event_type": "Weather Chat", "confidence": 0.9, "quote": "x"}]})
    out = run(email("VSL-02 notice", "Thanks, noted."), llm)
    assert [(i.event_type, i.confidence) for i in out.items] == [(FYI, 0.0)]
    assert out.llm_status == "ok"


@pytest.mark.parametrize(
    "item",
    [{"event_type": "Claim", "confidence": 0.9, "quote": "not in the email"},
     {"event_type": "Claim", "confidence": 1.7, "quote": "claim"},
     {"event_type": "Claim", "quote": "claim"}],
)  # fmt: skip
def test_e6_s04_item_with_a_bad_quote_or_confidence_is_dropped(item):
    out = run(email("VSL-02", "A claim is filed."), FakeLlm({"items": [item]}))
    assert [i.event_type for i in out.items] == [FYI]


def test_e6_s04_at_most_three_items_most_confident_first():
    items = [{"event_type": t, "confidence": c, "quote": "survey"} for t, c in
             [("Claim", 0.2), ("Survey Arrangement / Quotation", 0.9), ("Redelivery Notice", 0.5), (FYI, 0.4)]]  # fmt: skip
    out = run(email("VSL-02", "Please arrange the survey."), FakeLlm({"items": items}))
    assert [i.event_type for i in out.items] == [
        "Survey Arrangement / Quotation",
        "Redelivery Notice",
        FYI,
    ]


def test_e6_s05_llm_fails_twice_gives_general_fyi_and_failed():
    llm = FakeLlm(LlmError("timeout"), LlmError("timeout"))
    out = run(email("VSL-02 notice", "Charterers give notice of redelivery."), llm)
    assert len(llm.calls) == 2
    assert [(i.event_type, i.confidence) for i in out.items] == [
        (FYI, 0.0)
    ] and out.llm_status == "failed"


def test_e6_s05_answer_that_is_not_an_object_counts_as_failed():
    out = run(email("VSL-02", "Noted."), FakeLlm("text", None))
    assert out.llm_status == "failed"


@pytest.mark.parametrize(
    "subject", ["M/V VSL-02 午报 20260730", "VSL-01 抵港报", "VSL-02 离港报/DAMPIER"]
)
def test_e6_s06_report_with_a_chinese_subject_is_accepted_by_the_chinese_keyword(subject):
    out = run(email(subject, NOON_TEXT), FakeLlm())
    assert out.is_report is True and out.items[0].source == "rule"


def test_e6_prompt_carries_the_taxonomy_and_not_the_signature():
    llm = FakeLlm({"items": []})
    mail = email("VSL-02 notice", "Notice of redelivery.").model_copy(
        update={"signature_text": "PER-03 office"}
    )
    run(mail, llm)
    user = llm.calls[0][2]
    assert "Redelivery Notice" in user and "PER-03 office" not in user


def test_e6_s04_quote_matches_across_case_spaces_and_curly_quotes_but_not_ellipsis():
    text = "Please find attached the hire statement.\nKindly confirm owner's safe receipt of funds."
    llm = FakeLlm({"items": [
        {"event_type": "Claim", "confidence": 0.9, "quote": "KINDLY CONFIRM owner’s safe   receipt"},
        {"event_type": "Redelivery Notice", "confidence": 0.8, "quote": "hire statement ... funds"},
    ]})  # fmt: skip
    out = run(email("VSL-01 hire", text), llm)
    assert [i.event_type for i in out.items] == ["Claim"]
