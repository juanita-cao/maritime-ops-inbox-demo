"""T2.11 E6b e6b_derive_fact_changes: scenarios E6b-S01 to S07 (design_backend.md sections 10.3,
10.4) with the fact keys of design_knowledge section 2. Synthetic data, codes only."""

from datetime import datetime, timedelta, timezone

from src import e_nodes as e
from src.schemas import (
    DateFact, EventDecision, Evidence, ExtractedEntities, FactLookup, FactRecord, Mention, ParsedEmail,
    QuantityFact, Reference, VesselMatch, VoyageMatch,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
SENT = datetime(2026, 7, 30, 10, 0, tzinfo=CST)
VESSEL = VesselMatch(vessel_code="VSL-02", status="matched", tier="High", score=1.0)
VOYAGE = VoyageMatch(voyage_no="V202", basis="stated")
EVENT = EventDecision(event_type="Vessel Schedule Update (ETA/ETB/ETD)", tier="High", unsure=False,
                      is_report=False, sources_agree=True)  # fmt: skip
EMPTY = FactLookup(status="ok")


def ev(quote):
    return Evidence(quote=quote, source="new_text")


def mail():
    return ParsedEmail(email_id="E010", subject="VSL-02 ETA", subject_norm="vsl-02 eta", sent_time=SENT,
                       direction="Inbound", sender="x@CPY-05.example", new_text="text")  # fmt: skip


def ents(dates=(), quantities=(), ports=(), references=()):
    return ExtractedEntities(dates=list(dates), quantities=list(quantities), references=list(references),
                             ports=[Mention(text=p, evidence=ev(p)) for p in ports], llm_status="ok")  # fmt: skip


def fact(key, value, hours=0, version=1):
    return FactRecord(fact_id=f"F{version}", vessel_code="VSL-02", fact_key=key, value=value,
                      event_time=SENT + timedelta(hours=hours), event_time_basis="email_sent_time",
                      sent_time=SENT + timedelta(hours=hours), source_email_id="E001", version=version)  # fmt: skip


def run(entities, lookup=EMPTY, vessel=VESSEL):
    return e.e6b_derive_fact_changes(entities, vessel, VOYAGE, EVENT, mail(), lookup)


def test_e6b_s01_eta_with_an_effective_time_is_stated():
    d = DateFact(
        kind="eta",
        value="2026-08-04 15:00 LT",
        evidence=ev("As of 2026-07-30 08:00 LT, ETA Newcastle 4 Aug 15:00 LT"),
    )
    [change] = run(ents([d], ports=["Newcastle"])).items
    assert (change.fact_key, change.new, change.event_time_basis) == (
        "eta:newcastle",
        "2026-08-04 15:00 LT",
        "stated",
    )
    assert change.event_time == datetime(2026, 7, 30, 8, 0, tzinfo=CST)


def test_e6b_s02_eta_without_an_effective_time_uses_the_sent_time():
    d = DateFact(kind="eta", value="2026-08-04 15:00 LT", evidence=ev("ETA Newcastle 4 Aug 15:00 LT"))
    [change] = run(ents([d], ports=["Newcastle"])).items
    assert (change.event_time, change.event_time_basis) == (SENT, "email_sent_time")


def test_e6b_s03_value_equal_to_the_current_fact_gives_no_change():
    d = DateFact(kind="eta", value="2026-08-04 15:00 LT", evidence=ev("ETA Newcastle 4 Aug 15:00 LT"))
    lookup = FactLookup(status="ok", facts=[fact("eta:newcastle", "2026-08-04 15:00 LT")])
    assert run(ents([d], ports=["Newcastle"]), lookup).items == []


def test_e6b_s03_changed_value_carries_the_old_value_and_the_version_read():
    d = DateFact(kind="eta", value="2026-08-04 15:00 LT", evidence=ev("ETA Newcastle 4 Aug 15:00 LT"))
    lookup = FactLookup(
        status="ok", facts=[fact("eta:newcastle", "2026-08-05 08:00 LT", hours=-5, version=3)]
    )
    [change] = run(ents([d], ports=["Newcastle"]), lookup).items
    assert (change.old, change.base_version, change.older_than_current) == (
        "2026-08-05 08:00 LT",
        3,
        False,
    )


def test_e6b_s04_vessel_not_matched_gives_no_changes():
    d = DateFact(kind="eta", value="4 Aug", evidence=ev("ETA 4 Aug"))
    vessel = VesselMatch(vessel_code=None, status="ambiguous", tier="Low", score=0.5)
    assert run(ents([d]), vessel=vessel).items == []


def test_e6b_s05_fact_lookup_unavailable_gives_no_changes():
    d = DateFact(kind="eta", value="4 Aug", evidence=ev("ETA 4 Aug"))
    assert run(ents([d]), FactLookup(status="unavailable")).items == []


def test_e6b_s06_older_event_time_is_kept_but_marked():
    d = DateFact(kind="eta", value="2026-08-03 LT", evidence=ev("ETA Newcastle 3 Aug"))
    lookup = FactLookup(status="ok", facts=[fact("eta:newcastle", "2026-08-04 15:00 LT", hours=5)])
    [change] = run(ents([d], ports=["Newcastle"]), lookup).items
    assert change.older_than_current is True


def test_e6b_s07_actual_arrival_time_is_an_arrived_fact_with_its_own_time():
    d = DateFact(
        kind="arrived",
        value="2026-07-25 13:00",
        evidence=ev("arrived Dampier on 25 July 2026 at 1300 hours"),
    )
    [change] = run(ents([d], ports=["Dampier"])).items
    assert (change.fact_key, change.event_time_basis) == ("arrived:dampier", "stated")
    assert change.event_time == datetime(2026, 7, 25, 13, 0, tzinfo=CST)


def test_e6b_nor_ordinal_and_voyage_keys():
    nor = DateFact(
        kind="nor_tendered",
        value="2026-07-25 13:50",
        ordinal=2,
        evidence=ev("2ND NOR Dampier 13:50"),
    )
    laycan = DateFact(kind="laycan", value="12-26 Aug", evidence=ev("laycan 12-26 Aug"))
    keys = [c.fact_key for c in run(ents([nor, laycan], ports=["Dampier"])).items]
    assert keys == ["nor:dampier:2", "laycan:V202"]


def test_e6b_port_unknown_when_the_quote_names_none_and_several_are_mentioned():
    d = DateFact(kind="eta", value="4 Aug", evidence=ev("ETA 4 Aug"))
    assert run(ents([d], ports=["Dampier", "Newcastle"])).items[0].fact_key == "eta:unknown"
    assert run(ents([d], ports=["Newcastle"])).items[0].fact_key == "eta:newcastle"


def test_e6b_quantities_map_to_their_keys():
    qs = [
        QuantityFact(
            kind="loaded", value=55180, unit="MT", evidence=ev("loaded 55,180 MT at Dampier")
        ),
        QuantityFact(kind="bunker_rob", value=450.5, unit="MT", evidence=ev("VLSFO 450.5")),
        QuantityFact(kind="speed", value=12.5, unit="kn", evidence=ev("speed 12.5 kn")),
        QuantityFact(kind="consumption", value=25.3, unit="MT", evidence=ev("ME cons LSMGO 25.3")),
        QuantityFact(
            kind="amount", value=5000, unit="USD", currency="USD", evidence=ev("INV-7 USD 5,000")
        ),
    ]
    refs = [Reference(kind="invoice", value="INV-7", evidence=ev("INV-7"))]
    changes = run(ents(quantities=qs, ports=["Dampier"], references=refs)).items
    assert [(c.fact_key, c.new) for c in changes] == [
        ("cargo_loaded_mt:dampier", "55180 MT"), ("bunker_rob:vlsfo", "450.5 MT"), ("speed_avg", "12.5 kn"),
        ("consumption:lsmgo", "25.3 MT"), ("invoice_amount:INV-7", "5000 USD"),
    ]  # fmt: skip


def test_e6b_other_kinds_are_not_facts():
    d = DateFact(kind="other", value="4 Aug", evidence=ev("4 Aug"))
    q = QuantityFact(kind="other", value=24, unit="hours", evidence=ev("24 hours"))
    assert run(ents([d], [q])).items == []


def test_e6b_one_change_per_key_the_text_before_the_subject():
    a = QuantityFact(
        kind="bunker_rob",
        value=450.5,
        unit="MT",
        evidence=Evidence(quote="VLSFO 450.5", source="subject"),
    )
    b = QuantityFact(kind="bunker_rob", value=440.0, unit="MT", evidence=ev("VLSFO 440"))
    [change] = run(ents(quantities=[a, b])).items
    assert change.new == "440 MT"
