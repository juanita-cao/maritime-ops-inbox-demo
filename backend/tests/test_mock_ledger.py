"""Ledger validator of the mock dataset (docs/design_mock_data.md 4)."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mockdata.ledger import Event, Ledger, Party, Truth, Voyage, validate  # noqa: E402

TYPES = {"Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)", "LOI (Letter of Indemnity)"}
RPT = TYPES and "Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)"


def ledger(events, **over):
    base = dict(vessel="VSL-01", parties=[Party(code="OPR-01", name="Op", role="operator", domain="op.example"),
                                          Party(code="CPY-01", name="Ch", role="charterer", domain="ch.example")],
                voyages=[Voyage(no="V101", status="in_progress", cp_ref="CP1", load_port="A", disch_port="B", cargo="x", qty_mt=1,
                                sailed="2026-10-01T10:00:00+08:00", eta="2026-10-09T10:00:00+08:00")], events=events)
    return Ledger(**{**base, **over})


def ev(i, t, facts=None, reply_to=None, **kw):
    return Event(id=i, time=t, event_type=kw.pop("event_type", RPT), sender="CPY-01", receivers=["OPR-01"], thread="T1",
                 subject="s", voyage="V101", facts=facts or {}, reply_to=reply_to, **kw)


def test_a_consistent_ledger_has_no_problems():
    lg = ledger([ev("M1", "2026-10-02T09:00:00+08:00", {"bl_qty_mt": 100}), ev("M2", "2026-10-03T09:00:00+08:00", {"bl_qty_mt": 100}, "M1")],
                truths=[Truth(scenario="S02", question="q", answer="a", evidence=["M1"])])
    assert validate(lg, TYPES) == []


def test_conflicting_facts_unknown_references_and_time_order_are_refused():
    lg = ledger([ev("M1", "2026-10-02T09:00:00+08:00", {"bl_qty_mt": 100}), ev("M2", "2026-10-01T09:00:00+08:00", {"bl_qty_mt": 120}, "M1", event_type="Nope"),
                 ev("M3", "2026-10-04T09:00:00+08:00", {"eta_port": "x", "bl_qty_mt": 100})],
                truths=[Truth(scenario="S02", question="q", answer="a", evidence=["M9"])])
    text = "\n".join(validate(lg, TYPES))
    assert "unknown event type" in text and "not later" in text and "bl_qty_mt =" in text and "M9" in text


def test_a_declared_discrepancy_and_hourly_quantities_are_allowed():
    lg = ledger([ev("M1", "2026-10-02T09:00:00+08:00", {"bl_qty_mt": 100, "rob_vlsfo": 400}), ev("M2", "2026-10-03T09:00:00+08:00", {"bl_qty_mt": 140, "rob_vlsfo": 380})],
                discrepancies=["bl_qty_mt"])
    assert validate(lg, TYPES) == []


def test_eta_before_sailing_and_a_real_mailbox_domain_are_refused():
    lg = ledger([], voyages=[Voyage(no="V101", status="in_progress", cp_ref="c", load_port="A", disch_port="B", cargo="x", qty_mt=1,
                                    sailed="2026-10-05T10:00:00+08:00", eta="2026-10-01T10:00:00+08:00")])
    assert any("ETA is not after sailing" in p for p in validate(lg, TYPES))
    try:
        Party(code="CPY-09", name="x", role="owner", domain="real.com")
    except ValueError:
        return
    raise AssertionError("a non-.example domain was accepted")


def test_the_fleet_plan_is_ten_vessels_in_three_depths_with_each_scenario_planned():
    fleet = yaml.safe_load((Path(__file__).resolve().parents[2] / "mockdata/fleet.yaml").read_text(encoding="utf-8"))
    vs = fleet["vessels"]
    assert len(vs) == 10 and len({v["code"] for v in vs}) == 10 and len({v["name"] for v in vs}) == 10
    assert [sum(v["depth"] == d for v in vs) for d in ("deep", "medium", "light")] == [3, 3, 4]
    planned = {s for v in vs for s in v["scenarios"]}
    assert {"S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17", "S18"} == planned


def _types():
    import csv

    root = Path(__file__).resolve().parents[2]
    return {r["value"] for r in csv.DictReader((root / "kb/taxonomy.csv").open(encoding="utf-8")) if r["list_name"] == "event_types"}


def _deep():
    from mockdata import vsl01, vsl02, vsl03

    return {"VSL-01": (vsl01.build(), {"S01", "S02", "S11", "S17"}), "VSL-02": (vsl02.build(), {"S03", "S04", "S05", "S13"}),
            "VSL-03": (vsl03.build(), {"S01", "S06", "S07", "S18"})}


def test_the_deep_vessels_expand_to_consistent_ledgers_with_their_planned_scenarios_and_no_future_email():
    for code, (lg, scenarios) in _deep().items():
        assert lg.vessel == code
        assert validate(lg, _types()) == [], code
        assert 30 <= len(lg.events) <= 40, code
        assert {e.scenario for e in lg.events if e.scenario} == scenarios, code
        assert {t.scenario for t in lg.truths} == scenarios, code
        assert max(e.time for e in lg.events) < "2026-10-12T18:00:00+08:00", code
        assert [e.id for e in lg.events] == sorted(e.id for e in lg.events), code


def test_across_the_fleet_ids_are_unique_and_a_party_code_always_means_the_same_party():
    from mockdata.build import all_ledgers

    ledgers = all_ledgers()
    ids = [e.id for lg in ledgers for e in lg.events]
    assert len(ids) == len(set(ids))
    seen: dict[str, tuple[str, str]] = {}
    for lg in ledgers:
        for p in lg.parties:
            assert seen.setdefault(p.code, (p.name, p.domain)) == (p.name, p.domain), p.code
    names = [v[0] for v in seen.values()]
    assert len(names) == len(set(names)), "one company under two party codes"


def test_the_medium_and_light_vessels_are_consistent_and_each_carries_its_one_scenario():
    from mockdata import minor

    plan = {"VSL-04": ("S08", 12, 20), "VSL-05": ("S09", 12, 20), "VSL-06": ("S10", 12, 20), "VSL-07": ("S14", 6, 11), "VSL-08": ("S15", 6, 11), "VSL-09": ("S16", 6, 11), "VSL-10": ("S12", 6, 11)}
    for code, build in minor.ALL.items():
        lg = build()
        scenario, low, high = plan[code]
        assert lg.vessel == code and validate(lg, _types()) == [], code
        assert low <= len(lg.events) <= high, (code, len(lg.events))
        assert {e.scenario for e in lg.events if e.scenario} == {scenario} == {t.scenario for t in lg.truths}, code
        assert max(e.time for e in lg.events) < "2026-10-12T18:00:00+08:00", code


# --- skeleton emails (docs/design_mock_data.md 5) -------------------------------------------------------


def _all_texts():
    from mockdata.build import all_ledgers, fleet_names
    from mockdata.render import assign_ids, render_all

    lgs = all_ledgers()
    return lgs, assign_ids(lgs), render_all(lgs, fleet_names())


def test_every_skeleton_email_is_read_by_e1_with_its_sender_time_subject_and_quoted_history():
    from datetime import timedelta, timezone

    from src import e_nodes
    from src.schemas import RawEmail

    lgs, ids, texts = _all_texts()
    own = frozenset({"meridianfleet.example"})
    assert len(texts) == sum(len(lg.events) for lg in lgs) == len(set(ids.values()))
    for lg in lgs:
        for ev in lg.events:
            eid = ids[ev.id]
            parsed = e_nodes.e1_parse_email(RawEmail(email_id=eid, text=texts[eid]), own, timezone(timedelta(hours=8)))
            assert parsed.subject == ev.subject and parsed.sent_time.isoformat() == ev.time, eid
            assert parsed.sender.endswith(".example") and parsed.receivers, eid
            assert bool(parsed.quoted_text) == bool(ev.reply_to), eid


def test_ids_are_e_numbers_in_time_order_and_vessel_codes_are_vsl_numbers():
    import re

    lgs, ids, _ = _all_texts()
    assert sorted(ids.values()) == [f"E{i:03d}" for i in range(1, len(ids) + 1)]
    ordered = sorted((e for lg in lgs for e in lg.events), key=lambda e: (e.time, e.id))
    assert [ids[e.id] for e in ordered] == sorted(ids.values())
    assert all(re.fullmatch(r"VSL-\d{2}", lg.vessel) for lg in lgs)


def test_the_noon_sailing_and_arrival_layouts_are_read_by_the_report_digest():
    from src import report_digest as rd

    lgs, ids, texts = _all_texts()
    ctx = {ev.id: ev for lg in lgs for ev in lg.events}
    noon = next(e for e in ctx.values() if "NOON REPORT" in e.subject and e.facts.get("wind_force") == 5 and e.facts.get("speed_log_kn"))
    d = rd.digest_email(ids[noon.id], noon.subject, noon.time, texts[ids[noon.id]])
    assert d.kind == "noon" and d.speed_day and d.consumption and d.wind and d.sea and "weather" in d.fields and "speed" in d.fields
    sail = next(e for e in ctx.values() if "SAILING REPORT" in e.subject and "draft_sailing" in e.facts)
    ds = rd.digest_email(ids[sail.id], sail.subject, sail.time, texts[ids[sail.id]])
    assert ds.kind == "departure" and ds.draft and ds.draft_label == "sailing"


def test_the_generated_knowledge_base_loads_and_knows_every_sender_and_receiver():
    import tempfile

    from mockdata.build import all_ledgers
    from mockdata.kbgen import build_kb
    from src.kb_loader import load_kb, own_domains

    lgs = all_ledgers()
    codes = {c for lg in lgs for e in lg.events for c in [e.sender, *e.receivers]}
    with tempfile.TemporaryDirectory() as tmp:
        build_kb(lgs, Path(tmp), set(codes))
        kb = load_kb(Path(tmp) / "kb")
    assert set(kb.vessels) == {lg.vessel for lg in lgs} and len(kb.vessels) == 10
    assert own_domains(kb) == frozenset({"meridianfleet.example"})
    assert codes <= set(kb.parties)
    assert {c.party_code for c in kb.contacts.values()} >= codes
    assert all(v.owner_party in kb.parties and v.vessel_mailbox_party in kb.parties for v in kb.vessels.values())
    assert {x.level for x in kb.charter_links} == {"Owner-Head", "Management"}
    for lg in lgs:  # every voyage has an owner-head link
        linked = {n for x in kb.charter_links if x.vessel_code == lg.vessel and x.level == "Owner-Head" for n in x.voyage_nos}
        assert linked == {v.no for v in lg.voyages}, lg.vessel


def test_the_skeleton_emails_pass_the_input_gate_e4():
    from datetime import timedelta, timezone

    from src import e_nodes
    from src.schemas import RawEmail

    _, _, texts = _all_texts()
    bad = []
    for eid, text in texts.items():
        parsed = e_nodes.e1_parse_email(RawEmail(email_id=eid, text=text), frozenset({"meridianfleet.example"}), timezone(timedelta(hours=8)))
        if e_nodes.e4_check_sanitized(parsed).status != "clean":
            bad.append(eid)
    assert bad == []
