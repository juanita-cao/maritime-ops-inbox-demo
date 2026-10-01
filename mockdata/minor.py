"""Medium (VSL-14 to 16) and light (VSL-17 to 20) vessels of the mock fleet: one scenario each (S08, S09, S10,
S14, S15, S16, S12), plus reports and routine mail. Invented throughout. Clock: 2026-10-12 18:00 +08:00."""

from mockdata.builder import T_REPORT, Builder
from mockdata.common import BROKER, OP, broker, noons, operator, party
from mockdata.ledger import Ledger

T_CARGO, T_SURVEY, T_HIRE = "Loading / Cargo Operations", "Survey Arrangement / Quotation", "Hire / SOA / Payment"
T_LAYTIME, T_CLAIM, T_PNI = "Notice of Readiness / Laytime / Demurrage", "Claim", "P&I / Insurance"
T_SPEED, T_HOLD, T_DELAY = "Weather Routing / Speed & Consumption", "Hold Cleaning / Cargo Hold Condition", "Port Delay / Congestion / Strike"
T_CREW, T_INSP, T_SANC, T_DISCH = "Crew (Change / Medical)", "Inspection / Vetting / PSC", "Sanctions / Compliance / KYC", "Discharging"
T_DEFECT, T_VOY = "Vessel Defect / Repair / Breakdown", "Voyage Instructions / Port Nomination"


# ------------------------------------------------------------------------------------------------------------------------------
def vsl14() -> Ledger:
    """S08: the charterer's speed and consumption claim; the warranty applies in good weather only."""
    b = Builder("VSL-14", "M14")
    operator(b)
    broker(b)
    own = party(b, "CPY-61", "Silver Anemone Shipping Co", "owner")
    ch = party(b, "CPY-62", "Harlow Fertilizer Trading", "charterer")
    ms = party(b, "CPY-68", "Master, MV Silver Anemone", "master")
    aq = party(b, "CPY-63", "Gulf of Aqaba Shipping Services", "port_agent")
    hal = party(b, "CPY-64", "Hooghly Port Agency", "port_agent")
    nxt = party(b, "CPY-65", "Kathiawar Fertilizer Exports", "charterer")
    b.voyage("V401", "completed", "CPDD 11MAR2026 (Harlow)", "Aqaba", "Haldia", "phosphate rock", 36800, sailed="2026-09-18 10:30")
    b.voyage("V402", "planned", "recap CPDD 05OCT2026 (Kathiawar)", "Kandla", "Mombasa", "urea", 33000)
    b.discrepancies += ["claim_amount_usd", "avg_speed_all_days_kn", "avg_cons_all_days_mt"]
    b.email("2026-09-18 11:10", T_REPORT, ms, [OP, aq], "V401-sail", "VSL-14 / V401 SAILING REPORT AQABA", "V401", note="sailed Aqaba, phosphate rock loaded", cargo_qty_mt=36800, rob_vlsfo=548.0)
    days = [("2026-09-22", 520.4, 12.6, 27.6, 3, 1.0, "12-50N 044-30E"), ("2026-09-24", 466.0, 12.4, 28.0, 4, 1.5, "13-40N 053-20E"), ("2026-09-26", 405.9, 11.0, 31.0, 6, 3.0, "12-10N 062-10E"),
            ("2026-09-28", 346.2, 10.6, 30.5, 6, 3.5, "10-45N 070-30E"), ("2026-09-30", 292.5, 12.5, 27.2, 4, 1.5, "09-10N 078-20E"), ("2026-10-02", 238.8, 12.5, 27.6, 3, 1.0, "11-30N 084-45E"),
            ("2026-10-03", 211.1, 12.3, 27.7, 4, 1.5, "15-20N 087-10E"), ("2026-10-04", 183.6, 12.4, 27.5, 3, 1.0, "19-50N 088-30E")]
    noons(b, "VSL-14", "V401", ms, [OP, ch], days, "eta_haldia", "2026-10-05 09:00", "V401-noon")
    good = [d for d in days if d[4] <= 4]
    g_spd, g_cons = round(sum(d[2] for d in good) / len(good), 2), round(sum(d[3] for d in good) / len(good), 2)
    a_spd, a_cons = round(sum(d[2] for d in days) / len(days), 2), round(sum(d[3] for d in days) / len(days), 2)
    arr = b.email("2026-10-05 08:40", T_REPORT, hal, [OP, ch], "V401-hal", "VSL-14 HALDIA ARRIVAL REPORT", "V401", note="arrival at Haldia pilot station", arrival_haldia="2026-10-05 08:30")
    b.email("2026-10-09 18:00", T_DISCH, hal, [OP, ch], "V401-hal", "VSL-14 HALDIA DISCHARGE COMPLETED", "V401", reply_to=arr, note="discharge completed", outturn_qty_mt=36791)
    cl = b.email("2026-10-08 11:00", T_SPEED, ch, [OP, own], "V401-perf", "VSL-14 V401 - SPEED AND CONSUMPTION PERFORMANCE CLAIM", "V401", scenario="S08",
                 note=f"charterer claims USD 21,500 for underperformance over the whole voyage: average {a_spd} kn and {a_cons} mt per day against the CP warranty of 12.5 kn on 28.0 mt per day",
                 claim_amount_usd=21500.0, avg_speed_all_days_kn=a_spd, avg_cons_all_days_mt=a_cons, warranty_speed_kn=12.5, warranty_cons_mt=28.0)
    rp = b.email("2026-10-10 10:30", T_SPEED, OP, [ch, own], "V401-perf", "RE: VSL-14 V401 - SPEED AND CONSUMPTION PERFORMANCE CLAIM", "V401", scenario="S08", reply_to=cl,
                 note=f"operator: the warranty applies in good weather only (wind up to force 4 and sea up to 2 m); on {len(good)} good-weather days the vessel averaged {g_spd} kn and {g_cons} mt per day, within the warranty; asks the charterer to withdraw the claim or send the weather analysis",
                 good_weather_days=len(good), avg_speed_good_kn=g_spd, avg_cons_good_mt=g_cons, good_weather_definition="wind up to BF4 and sea up to 2 m")
    b.email("2026-10-12 09:30", T_SPEED, ch, [OP], "V401-perf", "RE: VSL-14 V401 - SPEED AND CONSUMPTION PERFORMANCE CLAIM", "V401", scenario="S08", reply_to=rp,
            note="charterer will send an independent weather routing report; keeps the claim open", claim_amount_usd=21500.0)
    b.truth("S08", "Is the charterer's V401 speed and consumption claim valid?",
            f"Not on the figures so far. The charterer claims USD 21,500 using the whole-voyage averages ({a_spd} kn, {a_cons} mt per day) against the warranty of 12.5 kn on 28.0 mt per day. The warranty applies in good weather only "
            f"(wind up to force 4, sea up to 2 m): on the {len(good)} good-weather noon reports the vessel averaged {g_spd} kn and {g_cons} mt per day, within the warranty. The two force-6 days drag the whole-voyage average down. "
            "The charterer will send an independent weather routing report; the claim stays open.", [cl, rp])
    b.email("2026-10-01 10:00", T_HIRE, OP, [ch], "V401-hire", "VSL-14 HIRE STATEMENT NO. 9 (1 OCT - 15 OCT 2026)", "V401", note="hire statement", hire_rate_usd_day=11800, hire_next_due="2026-10-16")
    b.email("2026-10-05 10:20", T_VOY, nxt, [OP, BROKER], "V402-fix", "VSL-14 V402 - FIXTURE RECAP UREA KANDLA / MOMBASA", "V402", note="clean recap, 33,000 mt urea, laycan 22-28 Oct, freight USD 21.5 per mt",
            cargo_qty_mt=33000, freight_usd_mt=21.5, laycan="2026-10-22 to 2026-10-28", cp_date="2026-10-05")
    b.email("2026-10-11 15:00", T_VOY, hal, [OP], "V402-ballast", "VSL-14 HALDIA - SAILING AFTER DISCHARGE, BALLAST TO KANDLA", "V402", note="agent: sailed in ballast 10 Oct, ETA Kandla 21 Oct", eta_kandla="2026-10-21 10:00")
    return b.ledger()


# ------------------------------------------------------------------------------------------------------------------------------
def vsl15() -> Ledger:
    """S09: a demurrage claim; the figures differ on the rain stoppage."""
    b = Builder("VSL-15", "M15")
    operator(b)
    broker(b)
    own = party(b, "CPY-71", "Tidewater Orchid Navigation", "owner")
    ch = party(b, "CPY-72", "Formosa Salt and Minerals", "charterer")
    ms = party(b, "CPY-78", "Master, MV Tidewater Orchid", "master")
    es = party(b, "CPY-73", "Southern Ports Agency Esperance", "port_agent")
    kh = party(b, "CPY-74", "Kaohsiung Harbour Agency", "port_agent")
    party(b, "CPY-75", "Pacific Chemicals Receiving Terminal", "receiver")
    b.voyage("V501", "completed", "CPDD 08APR2026 (Formosa)", "Esperance", "Kaohsiung", "salt", 52000, sailed="2026-09-02 14:00")
    b.voyage("V502", "planned", "recap CPDD 02OCT2026 (Formosa)", "Port Lincoln", "Kaohsiung", "salt", 50000)
    b.discrepancies += ["rain_stoppage_hours", "demurrage_usd"]
    b.email("2026-09-02 14:40", T_REPORT, ms, [OP, es], "V501-sail", "VSL-15 / V501 SAILING REPORT ESPERANCE", "V501", note="sailed Esperance, salt loaded", cargo_qty_mt=52000, rob_vlsfo=702.1)
    noons(b, "VSL-15", "V501", ms, [OP, ch], [("2026-09-06", 640.0, 12.0, 24.8, 4, 1.5, "28-10S 108-30E"), ("2026-09-10", 560.3, 12.2, 24.6, 3, 1.0, "12-40S 112-10E"),
                                              ("2026-09-14", 480.2, 12.1, 24.9, 4, 1.5, "05-20N 115-30E")], "eta_kaohsiung", "2026-09-14 08:00", "V501-noon")
    nor = b.email("2026-09-14 08:00", T_LAYTIME, ms, [OP, kh, ch], "V501-laytime", "VSL-15 NOTICE OF READINESS - KAOHSIUNG", "V501", scenario="S09",
                  note="NOR tendered at the pilot station; laytime commences 6 hours after NOR per CP", nor_tendered="2026-09-14 08:00", laytime_commences="2026-09-14 14:00")
    sof = b.email("2026-09-21 09:30", T_LAYTIME, kh, [OP, ch], "V501-laytime", "VSL-15 KAOHSIUNG - STATEMENT OF FACTS", "V501", scenario="S09", reply_to=nor,
                  note="SOF: discharge started 14 Sep 18:00 and completed 21 Sep 06:00; rain stoppages recorded as 11.0 hours; one shifting of 2.0 hours", discharge_completed="2026-09-21 06:00",
                  rain_stoppage_hours=11.0, shifting_hours=2.0, rate_mt_day=10000, laytime_allowed_hours=124.8)
    rate, used, allowed = 14000, 160.0, 124.8
    ch_calc = b.email("2026-09-28 11:10", T_LAYTIME, ch, [OP, own], "V501-laytime", "VSL-15 DEMURRAGE STATEMENT / LAYTIME CALCULATION", "V501", scenario="S09", reply_to=sof,
                      note="charterer's calculation excepts 18.0 hours of rain and 2.0 hours of shifting: excess 15.2 hours, demurrage USD 8,866.67 at USD 14,000 per day",
                      rain_stoppage_hours=18.0, demurrage_usd=round((used - allowed - 20.0) / 24 * rate, 2), laytime_used_hours=used, laytime_allowed_hours=allowed, demurrage_rate_usd_day=rate)
    ow = b.email("2026-10-05 10:50", T_LAYTIME, OP, [ch, own], "V501-laytime", "RE: VSL-15 DEMURRAGE STATEMENT / LAYTIME CALCULATION", "V501", scenario="S09", reply_to=ch_calc,
                 note="operator: the SOF records only 11.0 hours of rain; with 11.0 + 2.0 hours excepted the excess is 22.2 hours, demurrage USD 12,950.00; asks the charterer to correct the statement and pay within 30 days of the documents",
                 rain_stoppage_hours=11.0, demurrage_usd=round((used - allowed - 13.0) / 24 * rate, 2), demurrage_rate_usd_day=rate)
    b.email("2026-10-10 14:30", T_LAYTIME, ch, [OP], "V501-laytime", "RE: VSL-15 DEMURRAGE STATEMENT / LAYTIME CALCULATION", "V501", scenario="S09", reply_to=ow,
            note="charterer will check the weather records with the receivers and revert; notes the CP time bar of 90 days from discharge for demurrage documents; documents were sent on 28 Sep by owners' side", time_bar_days=90)
    b.truth("S09", "What demurrage is claimed on V501 and why do the figures differ?",
            "Laytime allowed 124.8 hours (52,000 mt at 10,000 mt per day), used 160.0 hours from 14 Sep 14:00 to 21 Sep 06:00; demurrage USD 14,000 per day. The charterer excepts 18.0 hours of rain plus 2.0 hours shifting and gets 15.2 hours, "
            "USD 8,866.67. The SOF records only 11.0 hours of rain, so the operator's figure is 22.2 hours, USD 12,950.00. The charterer will check weather records; the CP time bar is 90 days from discharge.", [sof, ch_calc, ow])
    b.email("2026-10-02 10:15", T_VOY, BROKER, [OP, ch], "V502-fix", "VSL-15 - RECAP SALT PORT LINCOLN / KAOHSIUNG", "V502", note="recap, 50,000 mt salt, freight USD 15.9 per mt, laycan 20-30 Oct",
            cargo_qty_mt=50000, freight_usd_mt=15.9, laycan="2026-10-20 to 2026-10-30", cp_date="2026-10-02")
    b.email("2026-10-01 10:00", T_HIRE, OP, [ch], "V501-hire", "VSL-15 HIRE STATEMENT NO. 8 (1 OCT - 15 OCT 2026)", "V501", note="hire statement", hire_rate_usd_day=12900, hire_next_due="2026-10-16")
    b.email("2026-10-11 12:00", T_REPORT, ms, [OP, ch], "V502-ballast", "VSL-15 NOON REPORT 2026-10-11 (BALLAST TO PORT LINCOLN)", "V502", note="ballast passage", rob_vlsfo=611.3, speed_log_kn=12.4,
            speed_avg_kn=12.3, pos_text="22-10S 112-40E", wind_force=4, sea_m=1.5, eta_port_lincoln="2026-10-19 08:00")
    return b.ledger()


# ------------------------------------------------------------------------------------------------------------------------------
def vsl16() -> Ledger:
    """S10: holds rejected for grain loading; re-cleaning delay."""
    b = Builder("VSL-16", "M16")
    operator(b)
    broker(b)
    own = party(b, "CPY-81", "Gannet Crest Maritime", "owner")
    ch = party(b, "CPY-82", "Rioplata Grain Exports", "charterer")
    ms = party(b, "CPY-88", "Master, MV Gannet Crest", "master")
    ro = party(b, "CPY-83", "Parana River Agency", "port_agent")
    party(b, "CPY-86", "Hanbit Steel Raw Materials", "charterer")
    ins = party(b, "CPY-84", "Cargo Inspection Services Rosario", "surveyor")
    b.party("CPY-47", "Anchor Point Club Correspondents", "pni_correspondent", "anchorpoint.example")
    pni = "CPY-47"
    b.voyage("V601", "completed", "CPDD 17FEB2026 (Hanbit)", "Hay Point", "Gwangyang", "coking coal", 71500, sailed="2026-08-02 09:00")
    b.voyage("V602", "in_progress", "CPDD 17FEB2026 (Rioplata)", "Rosario", "Chittagong", "wheat", 68000, eta="2026-12-02 12:00")
    b.discrepancies += ["reclean_hours"]
    b.email("2026-08-28 20:00", T_DISCH, ms, [OP], "V601-disch", "VSL-16 GWANGYANG DISCHARGE COMPLETED - HOLDS SWEPT", "V601", note="discharge completed; holds swept and washed for the next cargo", outturn_qty_mt=71488)
    b.email("2026-09-14 12:10", T_REPORT, ms, [OP, ch], "V602-noon", "VSL-16 NOON REPORT 2026-09-14 (BALLAST)", "V602", note="ballast passage towards the River Plate", rob_vlsfo=902.4, speed_log_kn=12.1, speed_avg_kn=12.0,
            pos_text="22-40S 040-10E", wind_force=4, sea_m=1.5)
    noons(b, "VSL-16", "V602", ms, [OP, ch], [("2026-09-24", 801.0, 12.2, 33.0, 4, 1.5, "35-10S 018-40E"), ("2026-10-02", 640.3, 12.0, 32.6, 5, 2.0, "33-20S 044-10W")], "eta_rosario", "2026-10-06 07:00", "V602-noon")
    b.email("2026-10-06 09:30", T_REPORT, ro, [OP, ch], "V602-ros", "VSL-16 ROSARIO ANCHORAGE - ARRIVAL AND INSPECTION PLAN", "V602", note="arrived at the anchorage; hold inspection by the cargo inspector on 8 Oct", arrival_rosario="2026-10-06 07:00")
    nr = b.email("2026-10-08 16:40", T_HOLD, ins, [OP, ch, ro], "V602-holds", "VSL-16 HOLD INSPECTION REPORT - NOT ACCEPTED", "V602", scenario="S10",
                 note="inspector rejects holds no.2 and no.5: coal dust and rust scale in the corners; holds 1, 3, 4, 6, 7 accepted", rejected_holds="2, 5", accepted_holds="1, 3, 4, 6, 7", inspection_time="2026-10-08 14:00")
    rc = b.email("2026-10-08 18:05", T_HOLD, OP, [ms, ch], "V602-holds", "RE: VSL-16 HOLD INSPECTION REPORT - NOT ACCEPTED", "V602", scenario="S10", reply_to=nr,
                 note="operator instructs the master to re-clean holds 2 and 5 at anchorage with the crew; estimate 30 hours; asks the charterer to confirm the delay is for the account of the CP clause 28 (cleaning to the inspector's satisfaction)",
                 reclean_hours=30.0, cp_clause="clause 28")
    ok = b.email("2026-10-10 02:30", T_HOLD, ins, [OP, ch, ro], "V602-holds", "VSL-16 HOLD RE-INSPECTION REPORT - ACCEPTED", "V602", scenario="S10", reply_to=rc,
                 note="holds 2 and 5 pass the re-inspection at 02:00 on 10 Oct; vessel may berth", reinspection_passed="2026-10-10 02:00", reclean_hours=33.5)
    cl = b.email("2026-10-10 11:20", T_HOLD, ch, [OP, own], "V602-holds", "VSL-16 - TIME LOST HOLD CLEANING - OFF-HIRE", "V602", scenario="S10", reply_to=ok,
                 note="charterer asks to treat the 33.5 hours from the failed inspection (8 Oct 14:00) to the pass (10 Oct 02:00) as off-hire and to bear the cost of the hold washing chemicals USD 2,300",
                 reclean_hours=33.5, claim_offhire_hours=33.5, chemicals_usd=2300.0)
    b.email("2026-10-12 10:00", T_HOLD, OP, [ch, own], "V602-holds", "RE: VSL-16 - TIME LOST HOLD CLEANING - OFF-HIRE", "V602", scenario="S10", reply_to=cl,
            note="operator: cleaning on charterers' orders is for charterers' time unless the CP says otherwise; the CP clause 28 requires cleaning at owners' expense but the time stays on hire; the chemicals are owners' cost; proposes the time as on-hire and owners paying the chemicals",
            cp_clause="clause 28", chemicals_usd=2300.0)
    b.truth("S10", "Who bears the time lost on the V602 hold re-cleaning?",
            "Holds 2 and 5 were rejected on 8 Oct (14:00) and passed on 10 Oct (02:00), 33.5 hours later (30 hours was the estimate). The charterer asks for the 33.5 hours as off-hire and the chemicals (USD 2,300) for owners. "
            "The operator's position: cleaning is at owners' expense under CP clause 28 but the time stays on hire, so owners pay the chemicals only. Not agreed yet; it needs OP and chartering review of clause 28.", [nr, ok, cl])
    b.email("2026-10-11 12:00", T_CARGO, ro, [OP, ch], "V602-load", "VSL-16 ROSARIO - LOADING COMMENCED", "V602", note="berthed 10 Oct 08:00, loading started 10 Oct 12:00, 68,000 mt wheat, completion about 14 Oct", cargo_qty_mt=68000)
    b.email("2026-10-01 10:00", T_HIRE, OP, [ch], "V602-hire", "VSL-16 HIRE STATEMENT NO. 17 (1 OCT - 15 OCT 2026)", "V602", note="hire statement", hire_rate_usd_day=14300, hire_next_due="2026-10-16")
    b.email("2026-10-04 11:00", T_PNI, pni, [OP, own], "V602-pni", "VSL-16 P&I - GRAIN CARGO HOLD CONDITION GUIDANCE", "V602", note="club circular summarising grain hold cleanliness standards before loading",
            guidance="residues, odours, rust scale and insect infestation are the usual rejection causes")
    return b.ledger()


# ------------------------------------------------------------------------------------------------------------------------------
def vsl17() -> Ledger:
    """S14: port congestion at the discharge port, ETA to berth moves."""
    b = Builder("VSL-17", "M17")
    operator(b)
    broker(b)
    party(b, "CPY-91", "Mistral Quay Ship Owning", "owner")
    ch = party(b, "CPY-92", "Meghna Cement Industries", "charterer")
    ms = party(b, "CPY-98", "Master, MV Mistral Quay", "master")
    vz = party(b, "CPY-93", "Coromandel Port Agency", "port_agent")
    ct = party(b, "CPY-94", "Karnaphuli Shipping Agency", "port_agent")
    b.voyage("V701", "in_progress", "CPDD 22JUL2026 (Meghna)", "Visakhapatnam", "Chittagong", "limestone", 33800, sailed="2026-10-03 06:15", eta="2026-10-07 10:00")
    b.email("2026-10-03 07:00", T_REPORT, ms, [OP, vz], "V701-sail", "VSL-17 / V701 SAILING REPORT VISAKHAPATNAM", "V701", note="sailed, limestone loaded", cargo_qty_mt=33800, rob_vlsfo=318.5)
    noons(b, "VSL-17", "V701", ms, [OP, ch], [("2026-10-04", 296.7, 11.2, 21.8, 4, 1.5, "16-50N 084-10E"), ("2026-10-05", 275.4, 11.0, 21.3, 4, 1.5, "18-30N 086-40E")], "eta_chittagong", "2026-10-07 10:00", "V701-noon")
    ar = b.email("2026-10-07 09:20", T_REPORT, ms, [OP, ct], "V701-ctg", "VSL-17 ARRIVAL CHITTAGONG OUTER ANCHORAGE - NOR TENDERED", "V701", note="arrived at the outer anchorage, NOR tendered", nor_tendered="2026-10-07 09:00")
    cg = b.email("2026-10-07 14:30", T_DELAY, ct, [OP, ch], "V701-ctg", "VSL-17 CHITTAGONG - CONGESTION, EXPECTED WAITING TIME", "V701", scenario="S14", reply_to=ar,
                 note="agent: 17 vessels waiting, berth expected in about 9 days (16 Oct) because of a terminal crane breakdown and high water discharge limits", expected_berth="2026-10-16", waiting_vessels=17)
    b.email("2026-10-08 10:10", T_DELAY, OP, [ch], "V701-ctg", "RE: VSL-17 CHITTAGONG - CONGESTION, EXPECTED WAITING TIME", "V701", scenario="S14", reply_to=cg,
            note="operator reminds the charterer that waiting for a berth is on charterers' time under the CP and asks for the discharge port's alternative berth or a lightening plan", cp_waiting_clause="waiting for berth for charterers' account")
    b.email("2026-10-11 16:00", T_DELAY, ct, [OP, ch], "V701-ctg", "VSL-17 CHITTAGONG - UPDATE BERTHING 19 OCT", "V701", scenario="S14",
            note="agent updates: the terminal crane is still out, berth now expected 19 Oct", expected_berth="2026-10-19", waiting_vessels=19)
    b.truth("S14", "How long will VSL-17 wait at Chittagong and whose time is it?",
            "NOR was tendered on 7 Oct 09:00 at the outer anchorage. The agent first expected a berth about 16 Oct and on 11 Oct moved it to 19 Oct (19 vessels waiting, a crane breakdown at the terminal). "
            "Under the CP the waiting for a berth is for charterers' account, as the operator reminded the charterer on 8 Oct; no alternative berth has been offered.", [cg])
    b.email("2026-10-01 10:00", T_HIRE, OP, [ch], "V701-hire", "VSL-17 HIRE STATEMENT NO. 6 (1 OCT - 15 OCT 2026)", "V701", note="hire statement", hire_rate_usd_day=10400, hire_next_due="2026-10-16")
    return b.ledger()


def vsl18() -> Ledger:
    """S15: a medical case at sea, the vessel calls to land the seafarer; deviation time."""
    b = Builder("VSL-18", "M18")
    operator(b)
    broker(b)
    own = party(b, "CPY-101", "Pinewood Star Shipping", "owner")
    ch = party(b, "CPY-102", "Zhanjiang Pulp and Paper Co", "charterer")
    ms = party(b, "CPY-108", "Master, MV Pinewood Star", "master")
    ag = party(b, "CPY-103", "Benoa Shipping Services", "port_agent")
    pni = party(b, "CPY-104", "Archipelago Club Correspondents", "pni_correspondent")
    b.voyage("V801", "in_progress", "CPDD 30JUN2026 (Zhanjiang)", "Bunbury", "Zhanjiang", "wood chips", 54200, sailed="2026-10-02 13:00", eta="2026-10-19 08:00")
    b.email("2026-10-02 13:40", T_REPORT, ms, [OP], "V801-sail", "VSL-18 / V801 SAILING REPORT BUNBURY", "V801", note="sailed Bunbury, wood chips loaded", cargo_qty_mt=54200, rob_vlsfo=870.2)
    md = b.email("2026-10-08 05:50", T_CREW, ms, [OP, pni], "V801-medical", "VSL-18 MEDICAL - CREW MEMBER ABDOMINAL PAIN, REQUEST ADVICE", "V801", scenario="S15",
                 note="the master reports an able seaman with severe abdominal pain since last night, no improvement after treatment; asks for medical advice and a nearby port", position="Lombok Strait approaches, 120 nm from Benoa")
    ad = b.email("2026-10-08 08:10", T_CREW, pni, [OP, ms], "V801-medical", "RE: VSL-18 MEDICAL - CREW MEMBER ABDOMINAL PAIN", "V801", scenario="S15", reply_to=md,
                 note="the doctor advises hospital examination within 12 hours; the correspondent proposes landing at Benoa; cost of the hospital and repatriation is for the P&I club", advice="landing at Benoa, within 12 hours")
    dv = b.email("2026-10-08 14:20", T_VOY, ag, [OP, pni, ms], "V801-medical", "VSL-18 BENOA - MEDEVAC AT ANCHORAGE", "V801", scenario="S15", reply_to=ad,
                 note="agent arranged the medevac at Benoa anchorage: launch alongside 15:30, hospital admitted the seafarer at 17:10; vessel resumed passage at 17:40; deviation 6.5 hours", deviation_hours=6.5,
                 medevac_launch="2026-10-08 15:30", resumed="2026-10-08 17:40")
    b.email("2026-10-09 09:30", T_CREW, OP, [ch, own], "V801-medical", "VSL-18 - DEVIATION FOR MEDEVAC 6.5 HOURS", "V801", scenario="S15", reply_to=dv,
            note="operator informs the charterer of the medical deviation and that the time is not off-hire as it was to save life; the replacement is planned at Zhanjiang", deviation_hours=6.5, replacement_port="Zhanjiang")
    b.email("2026-10-10 11:00", T_CREW, ch, [OP], "V801-medical", "RE: VSL-18 - DEVIATION FOR MEDEVAC 6.5 HOURS", "V801", scenario="S15",
            note="charterer notes the information, keeps the right to claim time under the off-hire clause, and asks for the hospital certificate", asks="hospital certificate")
    b.truth("S15", "What happened on VSL-18 V801 with the medical case and who pays?",
            "On 8 Oct an able seaman was landed at Benoa after medical advice (within 12 hours); deviation 6.5 hours (launch 15:30, resumed 17:40). The P&I correspondent states the hospital and repatriation costs are for the club. "
            "The operator told the charterer the time is not off-hire (saving life); the charterer keeps the right to claim and asked for the hospital certificate. A replacement is planned at Zhanjiang.", [md, ad, dv])
    noons(b, "VSL-18", "V801", ms, [OP, ch], [("2026-10-04", 840.1, 12.0, 30.2, 4, 1.5, "30-10S 112-50E"), ("2026-10-12", 600.4, 12.1, 30.3, 3, 1.0, "08-30N 112-20E")], "eta_zhanjiang", "2026-10-19 08:00", "V801-noon")
    b.email("2026-10-01 10:00", T_HIRE, OP, [ch], "V801-hire", "VSL-18 HIRE STATEMENT NO. 7 (1 OCT - 15 OCT 2026)", "V801", note="hire statement", hire_rate_usd_day=13200, hire_next_due="2026-10-16")
    return b.ledger()


def vsl19() -> Ledger:
    """S16: sanctions / KYC on a proposed sub-charterer."""
    b = Builder("VSL-19", "M19")
    operator(b)
    broker(b)
    own = party(b, "CPY-111", "Harrow Spirit Shipholding", "owner")
    ch = party(b, "CPY-112", "Cavendish Cement Trading", "charterer")
    party(b, "CPY-113", "Altai Trade FZE", "sub_charterer")
    party(b, "CPY-118", "Master, MV Harrow Spirit", "master")
    ag = party(b, "CPY-114", "Cai Lan Shipping Agency", "port_agent")
    b.voyage("V901", "planned", "CPDD 12MAY2026 (Cavendish)", "Cai Lan", "Mormugao", "clinker", 60000)
    b.email("2026-10-08 09:00", T_VOY, ch, [OP, own], "V901-sub", "VSL-19 V901 - REQUEST FOR OWNERS' CONSENT TO SUB-CHARTER", "V901", scenario="S16",
            note="the charterer asks for consent to sub-let V901 to Altai Trade FZE; a free-zone company; laycan 20-25 Oct", laycan="2026-10-20 to 2026-10-25", proposed_subcharterer="Altai Trade FZE")
    kq = b.email("2026-10-09 10:40", T_SANC, OP, [ch], "V901-sub", "RE: VSL-19 V901 - KYC DOCUMENTS FOR PROPOSED SUB-CHARTERER", "V901", scenario="S16",
                 note="operator's compliance team asks for the certificate of incorporation, the beneficial owner chart, a 12-month trading record and the cargo origin documents", asks="incorporation, ownership chart, trading record, origin")
    sc = b.email("2026-10-10 15:30", T_SANC, OP, [own], "V901-sub", "VSL-19 - SCREENING RESULT ALTAI TRADE FZE", "V901", scenario="S16", reply_to=kq,
                 note="internal screening: the entity name has a partial match (84%) to a person on a screening list; the ownership chart is missing so the match cannot be cleared; recommends not consenting until cleared", screening_match_pct=84,
                 screening_status="pending, not cleared")
    b.email("2026-10-11 17:10", T_SANC, ch, [OP], "V901-sub", "RE: VSL-19 V901 - KYC DOCUMENTS FOR PROPOSED SUB-CHARTERER", "V901", scenario="S16", reply_to=kq,
            note="the charterer sends the incorporation certificate only; says the ownership chart will follow on 14 Oct; asks for consent by 13 Oct to keep the laycan", consent_requested_by="2026-10-13")
    b.truth("S16", "Can owners consent to Altai Trade FZE as sub-charterer for V901?",
            "Not yet. The charterer asked for consent on 8 Oct (laycan 20–25 Oct) and wants an answer by 13 Oct, but sent only the incorporation certificate; the ownership chart is promised for 14 Oct. "
            "Screening found an 84% name match to a listed person that cannot be cleared without the ownership chart, so the recommendation is no consent until cleared (needs compliance sign-off).", [sc, kq])
    b.email("2026-10-06 10:00", T_HIRE, OP, [ch], "V901-hire", "VSL-19 HIRE STATEMENT NO. 5 (1 OCT - 15 OCT 2026)", "V901", note="hire statement", hire_rate_usd_day=14900, hire_next_due="2026-10-16")
    b.email("2026-10-09 15:00", T_REPORT, ag, [OP, ch], "V901-cai", "VSL-19 CAI LAN - ETA NOTICE AND LOADING PLAN", "V901", note="agent: ETA 19 Oct, loading 20-22 Oct", eta_cai_lan="2026-10-19 10:00")
    return b.ledger()


def vsl20() -> Ledger:
    """S12: port state control detention at the discharge port."""
    b = Builder("VSL-20", "M20")
    operator(b)
    broker(b)
    own = party(b, "CPY-121", "Lumen Ridge Marine", "owner")
    ch = party(b, "CPY-122", "Yuxing Iron Ore Importers", "charterer")
    ms = party(b, "CPY-128", "Master, MV Lumen Ridge", "master")
    ag = party(b, "CPY-123", "Qingdao Harbour Agents", "port_agent")
    cls = party(b, "CPY-124", "Maritime Classification Register", "surveyor")
    b.party("CPY-47", "Anchor Point Club Correspondents", "pni_correspondent", "anchorpoint.example")
    pni = "CPY-47"
    b.voyage("V1001", "in_progress", "CPDD 19JAN2026 (Yuxing)", "Tubarao", "Qingdao", "iron ore", 80200, sailed="2026-08-22 19:00", eta="2026-10-09 06:00")
    b.email("2026-10-09 07:20", T_REPORT, ms, [OP, ag], "V1001-arr", "VSL-20 ARRIVAL REPORT QINGDAO", "V1001", note="arrived Qingdao, berthed 17:00, discharge started 19:00", arrival_qingdao="2026-10-09 06:30")
    pc = b.email("2026-10-10 16:00", T_INSP, ag, [OP, ms], "V1001-psc", "VSL-20 PORT STATE CONTROL INSPECTION - DETENTION", "V1001", scenario="S12",
                 note="the port state control inspection found 3 deficiencies: the oily water separator alarm not working, one fire damper seized in the engine room, and the emergency generator start failing once; vessel detained until rectified",
                 deficiencies=3, detained_from="2026-10-10 15:30")
    cr = b.email("2026-10-10 20:20", T_INSP, OP, [cls, ms, pni], "V1001-psc", "RE: VSL-20 PORT STATE CONTROL - DETENTION - CLASS ATTENDANCE", "V1001", scenario="S12", reply_to=pc,
                 note="operator requests class attendance tomorrow and spare parts by courier; informs the P&I correspondent")
    rl = b.email("2026-10-12 09:00", T_INSP, ag, [OP, ms], "V1001-psc", "RE: VSL-20 PORT STATE CONTROL - DETENTION RELEASED", "V1001", scenario="S12", reply_to=cr,
                 note="the detention was released at 08:20 on 12 Oct after class confirmed rectification of the three deficiencies; 40.8 hours from the detention", detained_hours=40.8, released="2026-10-12 08:20")
    b.email("2026-10-12 14:00", T_INSP, ch, [OP, own], "V1001-psc", "VSL-20 - OFF-HIRE NOTICE DETENTION QINGDAO", "V1001", scenario="S12", reply_to=rl,
            note="charterer notifies off-hire for the detention period (40.8 hours) under the off-hire clause and asks for the inspection report and the class certificate", offhire_claimed_hours=40.8)
    b.truth("S12", "What happened on the VSL-20 port state control inspection at Qingdao?",
            "The PSC inspection on 10 Oct found 3 deficiencies (oily water separator alarm, a seized fire damper, one emergency generator start failure) and detained the vessel from 15:30. "
            "Class attended and the detention was released at 08:20 on 12 Oct, after 40.8 hours. The charterer gave off-hire notice for the 40.8 hours on 12 Oct and asked for the inspection report and the class certificate.", [pc, rl])
    noons(b, "VSL-20", "V1001", ms, [OP, ch], [("2026-10-03", 410.2, 12.2, 31.0, 4, 1.5, "21-30N 125-10E"), ("2026-10-06", 322.8, 12.0, 30.6, 5, 2.0, "28-40N 124-30E")], "eta_qingdao", "2026-10-09 06:00", "V1001-noon")
    b.email("2026-10-01 10:00", T_HIRE, OP, [ch], "V1001-hire", "VSL-20 HIRE STATEMENT NO. 10 (1 OCT - 15 OCT 2026)", "V1001", note="hire statement", hire_rate_usd_day=18600, hire_next_due="2026-10-16")
    return b.ledger()


ALL = {"VSL-14": vsl14, "VSL-15": vsl15, "VSL-16": vsl16, "VSL-17": vsl17, "VSL-18": vsl18, "VSL-19": vsl19, "VSL-20": vsl20}
