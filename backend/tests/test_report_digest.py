"""Field rules for vessel reports (docs/design_agent_e16_v7.md 7.5). The report layouts are the real
ones of the sample data (noon reports in two layouts, arrival, departure, in-port daily)."""

from src import report_digest as rd

NOON_A = """Dd: 24 Jul 2026
Please kindly find the Noon Report
(3) Daily GPS speed/Log speed:  14.2/13.0
(4) IFO Consumed/LSMGO consumed fm last report: VLSFO 25.530mt LSMGO 0
(6) Average GPS speed / Log Speed:  14.1/13.0
(8) Weather condition:SE/5  CLOUDY
(9) Sea/Swell condition: 2M
(10) ROB IFO/LSMGO/FW:  509.970MT/49.091MT/185MT
(11) Draft F/A:4.50/6.50"""
NOON_B = """Dd: 23 Jul 2026
5. Course/avg spd/rpm/eng slip: 025/14.0/105/-5.3
6. Avg daily consumption of fuel/diesel/water:  19.671/0/6
7. Bunker/qtty of ifo mdo and fw ROB: VLSFO 535.500/LSMGO 49.091/FW 180
8. Wind direction/force/sea cond/vis:  SE/4/0.5M/GOOD"""
ARRIVAL = """Dd: 25 Jul 2026
3.AVG SPD: 13.2KTS
5.DAILY FO CONSUMPTION: 25.523MT
8. Remarks:Vessel encounter adverse strong current about 2.5 kn"""
DEPARTURE = "Dd: 22 Jul 2026\n4. Sailing Draft: F 4.5m/A 6.5m\n6. Cosp ROB: VLSFO 555.171mt LSMGO 49.091mt"
DAILY = """Dd:30 Jul 2026
c. Bunker consumed in past 24.0 hrs while in anchorage(excl maneuvering)---VLSFO 6.008mt/LSMGO 0.200 mt
e. Weather condition---Cloudy"""
ETA = "Dd: 24 Jul 2026\nEst Arr Draft: FWD/ 4.50m  AFT/ 6.45m(1.023)"


def dig(eid, subject, iso, text):
    return rd.digest_email(eid, subject, iso, text)


def test_noon_report_layout_a_gives_speed_consumption_wind_sea_sky_and_draft():
    d = dig("E021", "M/V VSL-12//Noon Report 20260724", "2026-07-24T12:30:27+08:00", NOON_A)
    assert (d.kind, d.when) == ("noon", "2026-07-24")
    assert d.speed_day == "GPS 14.2 / Log 13.0 kn" and d.speed_avg == "GPS 14.1 / Log 13.0 kn"
    assert d.consumption == "VLSFO 25.530 mt, LSMGO 0 mt"
    assert (d.wind, d.sea, d.sky) == ("SE force 5", "2 m", "Cloudy")
    assert (d.draft, d.draft_label) == ("F 4.50 / A 6.50 m", "report")


def test_noon_report_layout_b_gives_avg_speed_consumption_wind_and_sea():
    d = dig("E017", "M/V VSL-12// NOON REPORT 20260723", "2026-07-23T12:21:53+08:00", NOON_B)
    assert d.speed_avg == "14.0 kn" and d.consumption == "VLSFO 19.671 mt, LSMGO 0 mt"
    assert (d.wind, d.sea) == ("SE force 4", "0.5 m") and d.draft is None


def test_arrival_report_has_the_masters_current_remark():
    d = dig("E024", "M/V VSL-12// ARRIVAL REPORT 20260725", "2026-07-25T12:34:54+08:00", ARRIVAL)
    assert d.kind == "arrival" and d.speed_avg == "13.2 kn" and d.consumption == "VLSFO 25.523 mt"
    assert d.current == "Vessel encounter adverse strong current about 2.5 kn"


def test_departure_and_eta_notice_drafts_are_labelled_and_in_port_daily_has_only_sky():
    dep = dig("E012", "M/V VSL-12// COSP REPORT/BUNBURY", "2026-07-22T18:18:58+08:00", DEPARTURE)
    assert (dep.draft, dep.draft_label, dep.kind) == ("F 4.5 / A 6.5 m", "sailing", "departure")
    eta = dig("E019", "M/V VSL-12//DAILY ETA NOTICE/2026.07.24", "2026-07-24T07:59:46+08:00", ETA)
    assert (eta.draft, eta.draft_label) == ("F 4.50 / A 6.45 m", "estimated arrival")
    daily = dig("E050", "M/V VSL-12//Daily Report 20260730", "2026-07-30T08:18:34+08:00", DAILY)
    assert daily.sky == "Cloudy" and daily.wind is None and daily.consumption == "VLSFO 6.008 mt, LSMGO 0.200 mt"


def test_wanted_fields_and_whether_base_facts_are_also_asked():
    assert rd.wanted_fields("VSL-12这几天的速度，油耗和天气") == {"speed", "consumption", "weather"}
    assert rd.wanted_fields("风级、浪高、逆流") == {"weather"}
    assert rd.wanted_fields("吃水多少") == {"draft"} and rd.wanted_fields("目前待办事项") == set()
    assert not rd.needs_base_facts("VSL-12这几天的速度，油耗和天气")
    assert rd.needs_base_facts("VSL-12船什么时候到港，船存淡水/燃油还有多少，吃水多少？")


def reports():
    return [dig("E016", "M/V VSL-12//Noon Report 20260723", "2026-07-23T12:17:41+08:00", NOON_B.replace("Dd: 23 Jul 2026", "Dd: 23 Jul 2026") + "\n(11) Draft F/A:4.50/6.50"),
            dig("E021", "M/V VSL-12//Noon Report 20260724", "2026-07-24T12:30:27+08:00", NOON_A),
            dig("E024", "M/V VSL-12// ARRIVAL REPORT 20260725", "2026-07-25T12:34:54+08:00", ARRIVAL),
            dig("E050", "M/V VSL-12//Daily Report 20260730", "2026-07-30T08:18:34+08:00", DAILY)]


def test_a_draft_question_takes_the_newest_report_that_states_one_and_says_which():
    picked = rd.select(reports(), {"draft"})
    assert [d.email_id for d in picked] == ["E021"]
    assert rd.render_row(picked[0], {"draft"}, True) == "- 7/24 午报（E021）：吃水 F 4.50 / A 6.50 m"


def test_a_weather_question_takes_the_noon_reports_of_the_leg_and_the_newest_sky():
    picked = rd.select(reports(), {"weather"})
    assert [d.email_id for d in picked] == ["E050", "E024", "E021", "E016"]  # the newest sky-only daily comes first
    rows = [rd.render_row(d, {"weather"}, True) for d in picked]
    assert rows[0] == "- 7/30 日报（E050）：天气 Cloudy"
    assert rows[1] == "- 7/25 抵港报（E024）：海流：Vessel encounter adverse strong current about 2.5 kn"
    assert rows[2] == "- 7/24 午报（E021）：风 SE 5 级；海浪/涌 2 m；天气 Cloudy"
    assert rd.has_current(picked)


def test_a_speed_consumption_question_skips_reports_without_those_fields_and_lists_the_missing():
    wanted = {"speed", "consumption"}
    picked = rd.select(reports(), wanted)
    assert [d.email_id for d in picked] == ["E050", "E024", "E021"]  # two newest per field: consumption E050, E024; speed E024, E021
    assert rd.render_row(picked[2], wanted, False) == "- 7/24 noon (E021): speed GPS 14.2 / Log 13.0 kn; consumption VLSFO 25.530 mt, LSMGO 0 mt"
    assert rd.missing_fields(rd.select([reports()[3]], {"draft", "speed"}), {"draft", "speed"}) == ["draft", "speed"]


def test_rows_are_capped():
    many = [dig(f"E{100 + i}", "Noon Report", f"2026-07-{i + 1:02d}T12:00:00+08:00", NOON_A) for i in range(12)]
    assert len(rd.select(many, {"weather"})) == rd.MAX_ROWS


def test_speed_is_not_crowded_out_by_newer_reports_that_only_carry_consumption_and_sky():
    daily = [dig(f"E1{i}", "M/V VSL-12//Daily Report", f"2026-07-{26 + i}T08:00:00+08:00", DAILY) for i in range(5)]
    picked = rd.select(daily + reports()[:3], {"speed", "consumption", "weather"})
    assert any(d.speed_day or d.speed_avg for d in picked), "speed rows must be present"
    assert {"E024", "E021"} <= {d.email_id for d in picked}
