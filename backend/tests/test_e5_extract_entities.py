"""T2.5 E5 e5_extract_entities: scenarios E5-S01 to S13 (design_backend.md sections 10, 10.4 and
10.5), on a fake LLM client (no network). Synthetic text with coded names only."""

from datetime import datetime, timezone

import pytest

from src import e_nodes as e
from src.llm_client import LlmError, RecordedLlm
from src.schemas import ParsedEmail, PartyRef, PartyRoles, SanitizationCheck

CLEAN = SanitizationCheck(status="clean")
ROLES = PartyRoles(sender=PartyRef(address="mail05@CPY-03.example", role="Master / Vessel"))


class FakeLlm:
    """Returns the given answers in turn; an exception in the list is raised."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[str, str, str]] = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, key, user))
        answer = self.answers.pop(0) if self.answers else {}
        if isinstance(answer, Exception):
            raise answer
        return answer


def email(new_text, subject="VSL-02 V202 sailing report", **kw) -> ParsedEmail:
    return ParsedEmail(
        email_id="E001",
        subject=subject,
        subject_norm=subject.lower(),
        sent_time=datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc),
        direction="Inbound",
        sender="mail05@CPY-03.example",
        new_text=new_text,
        **kw,
    )


def run(mail, llm, check=CLEAN):
    return e.e5_extract_entities(mail, ROLES, check, llm)


def test_e5_s01_voyage_number_by_rule_and_date_by_llm_both_with_valid_quotes():
    llm = FakeLlm(
        {
            "dates": [
                {
                    "kind": "eta",
                    "value": "2026-08-04 15:00 LT",
                    "quote": "ETA Newcastle 4 Aug 15:00 LT",
                }
            ]
        }
    )
    out = run(email("Voyage V202. ETA Newcastle 4 Aug 15:00 LT."), llm)
    assert [m.text for m in out.voyage_numbers] == ["V202"]
    assert out.voyage_numbers[0].evidence.source in ("subject", "new_text")
    assert (
        out.dates[0].kind == "eta" and out.dates[0].evidence.quote == "ETA Newcastle 4 Aug 15:00 LT"
    )
    assert out.llm_status == "ok"
    assert "V202" in llm.calls[0][2]  # already_found is in the prompt, so the LLM skips it


def test_e5_s01_rule_prepass_finds_vessel_code_cp_date_and_tonnage():
    out = run(email("MV VSL-02 CPDD 03APR2025, loaded 55,180 MT."), FakeLlm({}))
    assert [(m.text, m.evidence.source) for m in out.vessel_mentions] == [
        ("VSL-02", "new_text"),
        ("VSL-02", "subject"),
    ]
    assert [m.text for m in out.cp_references] == ["CPDD 03APR2025"]
    assert [(q.value, q.unit) for q in out.quantities] == [(55180.0, "MT")]


def test_e5_s02_value_whose_quote_is_not_in_the_text_is_dropped():
    llm = FakeLlm({"ports": [{"text": "Newcastle", "quote": "arrive Newcastle"},
                             {"text": "Qingdao", "quote": "arrive Qingdao"}]})  # fmt: skip
    out = run(email("We arrive Newcastle tomorrow."), llm)
    assert [p.text for p in out.ports] == ["Newcastle"]


def test_e5_s02_item_that_breaks_the_schema_is_dropped_not_repaired():
    llm = FakeLlm({"quantities": [{"kind": "amount", "value": 5000, "unit": "USD", "quote": "USD 5,000"},
                                  {"kind": "loaded", "value": -3, "unit": "MT", "quote": "USD 5,000"}]})  # fmt: skip
    out = run(email("Invoice USD 5,000 attached."), llm)
    assert out.quantities == []  # amount without currency and a negative value: both dropped


def test_e5_s03_llm_fails_twice_gives_rule_fields_only_and_failed():
    llm = FakeLlm(LlmError("timeout"), LlmError("timeout"))
    out = run(email("Voyage V202, ETA 4 Aug."), llm)
    assert len(llm.calls) == 2  # retried once
    assert out.llm_status == "failed"
    assert [m.text for m in out.voyage_numbers] == ["V202"] and out.dates == []


def test_e5_s03_one_failure_then_success_is_ok():
    llm = FakeLlm(LlmError("timeout"), {})
    assert run(email("Voyage V202."), llm).llm_status == "ok"


def test_e5_s03_recorded_mode_without_a_recording_is_failed(tmp_path):
    out = run(email("Voyage V202."), RecordedLlm(tmp_path))
    assert out.llm_status == "failed" and [m.text for m in out.voyage_numbers] == ["V202"]


def test_e5_s04_blocked_email_makes_no_call():
    llm = FakeLlm({})
    blocked = SanitizationCheck(
        status="blocked_unsanitized", findings=[{"kind": "phone", "count": 1}]
    )
    out = run(email("Call +65 6123 4567"), llm, blocked)
    assert llm.calls == [] and out.llm_status == "skipped" and out.vessel_mentions == []
    failed = SanitizationCheck(status="check_failed", error="x")
    assert run(email("x"), llm, failed).llm_status == "skipped" and llm.calls == []


def test_e5_s05_two_vessels_are_both_listed():
    out = run(email("VSL-01 and VSL-02 share the berth."), FakeLlm({}))
    assert [(m.text, m.evidence.source) for m in out.vessel_mentions] == [
        ("VSL-01", "new_text"),
        ("VSL-02", "new_text"),
        ("VSL-02", "subject"),  # the subject is its own evidence for D1 (T2.6 labels check)
    ]


def test_e5_d1_s01_code_in_text_and_subject_keeps_both_sources():
    llm = FakeLlm({"vessel_mentions": [{"text": "VSL-02", "quote": "VSL-02"}]})
    out = run(email("MV VSL-02 sailed."), llm)
    assert sorted(m.evidence.source for m in out.vessel_mentions) == ["new_text", "subject"]


def test_e5_s06_postscript_date_is_not_sent_or_extracted():
    llm = FakeLlm({})
    mail = email("Noted.", signature_text="Best regards\nPER-03\nP.S. Office moves on 15 Aug 2026.")
    out = run(mail, llm)
    assert "15 Aug" not in llm.calls[0][2]
    assert out.dates == []


def test_e5_s07_relay_author_hint_is_kept():
    llm = FakeLlm({"author_hint": {"text": "CPY-10", "quote": "Qte from CPY-10"}})
    out = run(email("Qte from CPY-10: please confirm. Unqte"), llm)
    assert out.author_hint.text == "CPY-10"


def test_e5_s08_sailed_time_keeps_its_timezone_words():
    llm = FakeLlm(
        {"dates": [{"kind": "sailed", "value": "2026-07-30 14:48 LT", "quote": "Sailed 14:48 LT"}]}
    )
    out = run(email("Sailed 14:48 LT, all fast."), llm)
    assert (out.dates[0].kind, out.dates[0].value) == ("sailed", "2026-07-30 14:48 LT")


def test_e5_s09_amount_with_currency():
    llm = FakeLlm(
        {
            "quantities": [
                {
                    "kind": "amount",
                    "value": 5000,
                    "unit": "USD",
                    "currency": "USD",
                    "quote": "USD 5,000",
                }
            ]
        }
    )
    out = run(email("Invoice USD 5,000 attached."), llm)
    assert (out.quantities[0].kind, out.quantities[0].currency) == ("amount", "USD")


def test_e5_s10_attachment_name_is_evidence_with_source_attachments():
    llm = FakeLlm(
        {"dates": [{"kind": "other", "value": "hire 01-15 Aug", "quote": "Hire 01-15Aug.pdf"}]}
    )
    out = run(email("See att.", attachment_names=["Hire 01-15Aug.pdf"]), llm)
    assert out.dates[0].evidence.source == "attachments"


def test_e5_s11_references_with_kinds():
    llm = FakeLlm({"references": [{"kind": "bl", "value": "BL-7", "quote": "B/L BL-7"},
                                  {"kind": "pi_case", "value": "PI-9", "quote": "case PI-9"}]})  # fmt: skip
    out = run(email("B/L BL-7 and P&I case PI-9."), llm)
    assert [(r.kind, r.value) for r in out.references] == [("bl", "BL-7"), ("pi_case", "PI-9")]


def test_e5_s12_second_nor_has_ordinal_2():
    llm = FakeLlm(
        {
            "dates": [
                {
                    "kind": "nor_tendered",
                    "value": "2026-07-30 10:00 LT",
                    "ordinal": 2,
                    "quote": "2ND NOR re-tendered",
                }
            ]
        }
    )
    out = run(email("2ND NOR re-tendered 10:00 LT."), llm)
    assert out.dates[0].ordinal == 2


def test_e5_s13_subject_and_text_disagree_text_value_used():
    llm = FakeLlm({"quantities": [{"kind": "bunker_rob", "value": 50, "unit": "MT", "quote": "50MT"},
                                  {"kind": "bunker_rob", "value": 100, "unit": "MT", "quote": "100MT"}]})  # fmt: skip
    out = run(email("Bunker ROB 100MT.", subject="VSL-02 bunker 50MT"), llm)
    rob = [q for q in out.quantities if q.kind == "bunker_rob"]
    assert [q.value for q in rob] == [100.0] and out.subject_text_conflict is True


@pytest.mark.parametrize("bad", [None, [], "text", {"dates": "not a list"}])
def test_e5_s02_answer_of_the_wrong_shape_counts_as_nothing_found(bad):
    out = run(email("Voyage V202."), FakeLlm(bad if isinstance(bad, dict) else {"x": bad}))
    assert out.llm_status == "ok" and out.dates == []


def test_e5_d1_s06_vessel_code_inside_a_party_code_is_not_a_mention():
    out = run(email("Owners OWN-VSL-12 confirm.", subject="Owners notice"), FakeLlm({}))
    assert out.vessel_mentions == []


# --- review 2026-09-26: malformed items, tonnage cues, grounding, status ----------------


def test_e5_s02_items_missing_required_keys_are_dropped_and_valid_ones_kept():
    llm = FakeLlm({
        "dates": [{"quote": "ETA 4 Aug"}, {"kind": "eta", "value": "4 Aug", "quote": "ETA 4 Aug"}],
        "quantities": [{"kind": "loaded", "quote": "55,180 MT"},
                       {"kind": "loaded", "value": 55180, "unit": "MT", "quote": "55,180 MT"}],
        "references": [{"value": "BL-7", "quote": "B/L BL-7"}, {"kind": "bl", "value": "BL-7", "quote": "B/L BL-7"}],
    })  # fmt: skip
    out = run(email("ETA 4 Aug. Loaded 55,180 MT. B/L BL-7."), llm)
    assert [d.kind for d in out.dates] == ["eta"]
    assert [(q.kind, q.value) for q in out.quantities] == [("loaded", 55180.0)]
    assert [r.value for r in out.references] == ["BL-7"]
    assert out.llm_status == "ok"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("There was a problem with 100 MT cargo.", [(100.0, "other")]),
        ("Loaded 50 MT, ROB 20 MT.", [(50.0, "loaded"), (20.0, "bunker_rob")]),
        ("Discharged 80 MT, bunker ROB 15 MT.", [(80.0, "discharged"), (15.0, "bunker_rob")]),
        ("Loaded 50 MT, 20 MT to go.", [(50.0, "loaded"), (20.0, "other")]),
    ],
)
def test_e5_s01_tonnage_kind_comes_from_the_nearest_whole_word_cue(text, expected):
    out = run(email(text, subject="VSL-02 report"), FakeLlm({}))
    assert [(q.value, q.kind) for q in out.quantities] == expected


def test_e5_s02_entity_not_supported_by_its_quote_is_dropped():
    llm = FakeLlm({
        "ports": [{"text": "Qingdao", "quote": "arrive Newcastle"}, {"text": "Newcastle", "quote": "arrive Newcastle"}],
        "references": [{"kind": "bl", "value": "BL-9", "quote": "B/L BL-7"}],
        "author_hint": {"text": "CPY-99", "quote": "Qte from CPY-10"},
    })  # fmt: skip
    out = run(email("We arrive Newcastle. B/L BL-7. Qte from CPY-10: ok. Unqte"), llm)
    assert [p.text for p in out.ports] == ["Newcastle"]
    assert out.references == [] and out.author_hint is None


def test_e5_s02_quantity_value_or_currency_not_in_its_quote_is_dropped():
    llm = FakeLlm({"quantities": [
        {"kind": "amount", "value": 900000, "unit": "USD", "currency": "USD", "quote": "USD 5,000"},
        {"kind": "amount", "value": 5000, "unit": "EUR", "currency": "EUR", "quote": "USD 5,000"},
        {"kind": "amount", "value": 5000, "unit": "USD", "currency": "USD", "quote": "USD 5,000"},
    ]})  # fmt: skip
    out = run(email("Invoice USD 5,000 attached."), llm)
    assert [(q.value, q.currency) for q in out.quantities] == [(5000.0, "USD")]


def test_e5_s08_normalised_date_value_is_not_matched_literally():
    """Known boundary: a date value may add context (the day) that is not in the quote."""
    llm = FakeLlm(
        {"dates": [{"kind": "sailed", "value": "2026-07-30 14:48 LT", "quote": "Sailed 14:48 LT"}]}
    )
    assert len(run(email("Sailed 14:48 LT."), llm).dates) == 1


@pytest.mark.parametrize("bad", [None, [], "text", 7])
def test_e5_s03_answer_that_is_not_a_json_object_is_failed_after_a_retry(bad):
    llm = FakeLlm(bad, bad)
    out = run(email("Voyage V202."), llm)
    assert len(llm.calls) == 2
    assert out.llm_status == "failed" and [m.text for m in out.voyage_numbers] == ["V202"]


def test_e5_characterization_same_tonnage_in_subject_and_text_is_kept_twice():
    """Quantities are evidence observations: the same value in subject and text stays twice,
    one per source (E6b turns them into one fact)."""
    out = run(email("Loaded 100 MT.", subject="VSL-02 loaded 100 MT"), FakeLlm({}))
    assert [(q.value, q.evidence.source) for q in out.quantities] == [
        (100.0, "new_text"),
        (100.0, "subject"),
    ]


def test_e5_s02_unit_from_context_is_accepted_but_a_different_named_unit_is_not():
    llm = FakeLlm({"quantities": [
        {"kind": "bunker_rob", "value": 339.11, "unit": "MT", "quote": "[BROB_VLSFO : 339.11]"},
        {"kind": "speed", "value": 13.5, "unit": "knots", "quote": "speed 13.5 %"},
    ]})  # fmt: skip
    out = run(email("[BROB_VLSFO : 339.11] and speed 13.5 %."), llm)
    assert [(q.kind, q.value) for q in out.quantities] == [("bunker_rob", 339.11)]


def test_e5_s02_metric_tons_is_a_ton_unit():
    llm = FakeLlm(
        {
            "quantities": [
                {
                    "kind": "loaded",
                    "value": 55180,
                    "unit": "metric tons",
                    "quote": "55,180 metric tons",
                }
            ]
        }
    )
    assert len(run(email("Loaded 55,180 metric tons."), llm).quantities) == 1


def test_e5_s02_quote_matches_across_case_spaces_and_curly_quotes():
    llm = FakeLlm({"ports": [{"text": "Newcastle", "quote": "ARRIVE  Newcastle’s"}]})
    out = run(email("We arrive Newcastle's anchorage."), llm)
    assert [p.text for p in out.ports] == ["Newcastle"]
