"""VSL-02 Northern Linden (deep): S03 (ECA fuel cost, clause silent), S04 (hire statement with a disputed
off-hire deduction), S05 (redelivery notice and bunkers on redelivery), S13 (bunker quality dispute).
Invented throughout. Clock: 2026-10-12 18:00 +08:00. V201 done, V202 at sea (Rouen to Casablanca), V203 planned."""

from mockdata.builder import T_REPORT, Builder
from mockdata.ledger import Ledger

OP, OWN, HEAD, MSTR = "OPR-01", "CPY-21", "CPY-22", "CPY-28"
AG_PAR, AG_RTM, AG_ROU, AG_CAS = "CPY-23", "CPY-24", "CPY-25", "CPY-26"
SUPPLIER, SURV, BROKER, NEXTCH = "CPY-27", "CPY-29", "CPY-14", "CPY-31"


def build() -> Ledger:
    b = Builder("VSL-02", "M12")
    for code, name, role, dom in [
        (OP, "Meridian Fleet Management", "operator", "meridianfleet.example"),
        (OWN, "Linden Maritime Holdings", "owner", "lindenmaritime.example"),
        (HEAD, "Brannock Agri Trading", "charterer", "brannock.example"),
        (MSTR, "Master, MV Northern Linden", "master", "vsl02.example"),
        (AG_PAR, "Atlantic Sul Agency", "port_agent", "atlanticsul.example"),
        (AG_RTM, "Maasmond Agency", "port_agent", "maasmond.example"),
        (AG_ROU, "Seine Maritime Agency", "port_agent", "seinemaritime.example"),
        (AG_CAS, "Atlas Port Agency", "port_agent", "atlasport.example"),
        (SUPPLIER, "Rhine Bunker Supply", "supplier", "rhinebunker.example"),
        (SURV, "Vanguard Marine Surveyors", "surveyor", "vanguardsurvey.example"),
        (BROKER, "Pelham Shipbrokers", "broker", "pelhambrokers.example"),
        (NEXTCH, "Solano Grain Company", "charterer", "solanograin.example"),
    ]:
        b.party(code, name, role, dom)
    b.voyage("V201", "completed", "CPDD 20JUN2026 (Brannock)", "Paranagua", "Rotterdam", "soybean meal", 52300, sailed="2026-09-01 18:10")
    b.voyage("V202", "in_progress", "CPDD 20JUN2026 (Brannock)", "Rouen", "Casablanca", "wheat", 49800, sailed="2026-10-09 06:20", eta="2026-10-14 18:00")
    b.voyage("V203", "planned", "recap pending (Solano)", "Santos", "Antwerp", "soybean meal", 51000)
    b.discrepancies += ["offhire_hours", "offhire_amount_usd"]  # claimed and accepted figures differ on purpose (S04)

    # ---- V201: loading, sailing, ECA fuel (S03) ---------------------------------------------------------------------
    b.email("2026-09-01 18:50", T_REPORT, MSTR, [OP, AG_PAR], "V201-sail", "VSL-02 / V201 SAILING REPORT PARANAGUA", "V201", note="sailed Paranagua, soybean meal loaded",
            cargo_qty_mt=52300, rob_vlsfo=902.4, rob_lsmgo=161.8, draft_sailing="F 12.20 / A 12.65 m")
    b.email("2026-09-12 12:30", T_REPORT, MSTR, [OP, HEAD], "V201-noon", "VSL-02 NOON REPORT 2026-09-12", "V201", note="noon report in the Atlantic",
            rob_vlsfo=711.0, rob_lsmgo=161.8, speed_log_kn=12.4, speed_avg_kn=12.3, pos_text="14-20N 028-10W", wind_dir="NE", wind_force=4, sea_m=1.5, eta_rotterdam="2026-09-22 10:00")
    for when, rob, spd, wd, force, sea, pos in [("2026-09-05 12:25", 842.3, 12.5, "SE", 4, 1.5, "25-10S 044-20W"), ("2026-09-08 12:20", 778.9, 12.2, "ESE", 5, 2.0, "08-30S 034-50W"),
                                               ("2026-09-15 12:30", 646.5, 12.5, "N", 3, 1.0, "29-50N 021-30W"), ("2026-09-18 12:20", 585.2, 12.6, "NNW", 5, 2.0, "44-30N 009-10W")]:
        b.email(when, T_REPORT, MSTR, [OP, HEAD], "V201-noon", f"VSL-02 NOON REPORT {when[:10]}", "V201", note="daily noon report", rob_vlsfo=rob, rob_lsmgo=161.8, speed_log_kn=spd,
                speed_avg_kn=spd - 0.1, pos_text=pos, wind_dir=wd, wind_force=force, sea_m=sea, eta_rotterdam="2026-09-22 10:00")
    b.email("2026-08-30 09:00", T_REPORT, AG_PAR, [OP, HEAD], "V201-load", "VSL-02 PARANAGUA - LOADING COMMENCED", "V201", note="agent: berthed 29 Aug, loading started, rate 1,900 mt/h", loading_rate_mt_h=1900)
    b.email("2026-10-07 11:30", T_REPORT, AG_ROU, [OP, HEAD], "V202-rou", "VSL-02 ROUEN - ETA NOTICE AND LOADING PLAN", "V202", note="agent: berth confirmed, loading 7-8 Oct, 49,800 mt wheat", cargo_qty_mt=49800)
    sec = b.email("2026-09-20 11:40", "Bunker (Stem / Quote / ROB / Quality)", MSTR, [OP, HEAD], "V201-eca", "VSL-02 ENTERING NORTH SEA SECA - CHANGEOVER TO LSMGO", "V201", scenario="S03",
                  note="master reports the changeover to LSMGO at the Channel SECA entry; LSMGO burned in the SECA until Rotterdam was 38.6 mt", lsmgo_consumed_seca_mt=38.6,
                  changeover_time="2026-09-20 09:30", rob_lsmgo=123.2)
    b.email("2026-09-22 10:05", T_REPORT, AG_RTM, [OP, HEAD], "V201-rtm", "VSL-02 ROTTERDAM ARRIVAL AND BERTHING PLAN", "V201", note="agent: pilot on board 10:00, berthing 14:30 at the grain terminal", arrival_rotterdam="2026-09-22 10:00")
    b.email("2026-09-27 02:30", "Discharging", AG_RTM, [OP, HEAD], "V201-rtm", "VSL-02 ROTTERDAM DISCHARGE COMPLETED", "V201", note="discharge completed, outturn 52,284 mt", outturn_qty_mt=52284)
    ec = b.email("2026-10-02 10:30", "Hire / SOA / Payment", HEAD, [OP, OWN], "V201-eca", "VSL-02 - LSMGO CONSUMED IN SECA - CHARGE TO OWNERS", "V201", reply_to=sec, scenario="S03",
                 note="charterer will deduct the cost of the 38.6 mt LSMGO from hire as an owners' cost, saying CP clause 32 is silent and the recap does not give ECA fuel to charterers",
                 lsmgo_consumed_seca_mt=38.6, lsmgo_price_usd_mt=810.0, claim_amount_usd=31266.0, cp_clause_cited="clause 32")
    er = b.email("2026-10-05 09:50", "CP Terms / Recap / Addendum", OP, [HEAD, OWN], "V201-eca", "RE: VSL-02 - LSMGO CONSUMED IN SECA - CHARGE TO OWNERS", "V201", reply_to=ec, scenario="S03",
                 note="operator replies: clause 12 makes charterers provide and pay for all bunkers used; clause 32 (cleaning) does not mention ECA; the route to Rotterdam was charterers' order; asks the charterer to withdraw the claim",
                 cp_clause_fuel="clause 12", cp_clause_eca="none (clause 32 does not mention ECA)")
    b.email("2026-10-08 15:20", "CP Terms / Recap / Addendum", HEAD, [OP], "V201-eca", "RE: VSL-02 - LSMGO CONSUMED IN SECA - CHARGE TO OWNERS", "V201", reply_to=er, scenario="S03",
            note="charterer keeps the claim 'pending legal review' and will hold USD 31,266 from the next hire", claim_amount_usd=31266.0)
    b.truth("S03", "Who should bear the LSMGO consumed in the North Sea SECA on V201?",
            "Proposal for review: charterers. The 38.6 mt LSMGO (USD 31,266 at USD 810 per mt) was burned entering Rotterdam on the charterer's voyage orders; CP clause 12 puts all bunkers on charterers, "
            "clause 32 (the one the charterer cites) is silent on ECA fuel, and the recap does not shift it to owners. The charterer has not withdrawn the claim and will hold the amount from the next hire.",
            [sec, ec, er])

    # ---- S13: bunker quality ---------------------------------------------------------------------------------------
    bk = b.email("2026-09-26 16:20", "Bunker (Stem / Quote / ROB / Quality)", SUPPLIER, [OP, MSTR], "V201-bunker", "VSL-02 BUNKER DELIVERY NOTE ROTTERDAM 26 SEP", "V201", scenario="S13",
                 note="bunker delivery note for 600 mt VLSFO, sulphur 0.49% per supplier's analysis; MARPOL sample sealed", bdn_qty_mt=600, bdn_sulphur_pct=0.49, marpol_sample_no="RBS-26-0917")
    lab = b.email("2026-10-06 11:10", "Bunker (Stem / Quote / ROB / Quality)", SURV, [OP, HEAD], "V201-bunker", "VSL-02 FUEL ANALYSIS RESULT - SAMPLE RBS-26-0917", "V201", reply_to=bk, scenario="S13",
                  note="independent lab result for the retained sample: sulphur 0.54%; the report states a test tolerance of 0.05 on the 0.50% limit; viscosity and density in spec", lab_sulphur_pct=0.54, sulphur_limit_pct=0.50, test_tolerance_pct=0.05)
    b.email("2026-10-07 09:30", "Bunker (Stem / Quote / ROB / Quality)", HEAD, [OP, OWN], "V201-bunker", "RE: VSL-02 FUEL ANALYSIS RESULT - SAMPLE RBS-26-0917", "V201", reply_to=lab, scenario="S13",
            note="charterer says the fuel is non-compliant at 0.54% and asks owners to declassify and de-bunker, holding owners liable for any port state action", lab_sulphur_pct=0.54)
    b.email("2026-10-09 10:40", "Bunker (Stem / Quote / ROB / Quality)", OP, [HEAD, OWN], "V201-bunker", "RE: VSL-02 FUEL ANALYSIS RESULT - SAMPLE RBS-26-0917", "V201", scenario="S13",
            note="operator: 0.54 is within the 0.05 tolerance of the 0.50 limit so the fuel is treated as compliant; bunkers were charterers' supply under clause 12; suggests a fresh test of the ship's own sample and a letter of protest to the supplier",
            reply_to=lab, lab_sulphur_pct=0.54, test_tolerance_pct=0.05)
    b.truth("S13", "Is the Rotterdam bunker delivery non-compliant on sulphur?",
            "Not on the evidence so far. The delivery note says 0.49%, the independent lab found 0.54% against the 0.50% limit with a stated test tolerance of 0.05, so 0.54 is within tolerance (0.55). "
            "The charterer calls it non-compliant and asks owners to de-bunker; the operator disagrees (bunkers were the charterers' supply, clause 12) and proposes a retest and a letter of protest to the supplier.", [bk, lab])

    # ---- S04: hire statement and a disputed deduction ---------------------------------------------------------------------
    hs = b.email("2026-10-01 10:00", "Hire / SOA / Payment", OP, [HEAD], "V202-hire", "VSL-02 HIRE STATEMENT NO. 11 (1 OCT - 15 OCT 2026)", "V202", scenario="S04",
                 note="hire statement, 15 days in advance at USD 15,400 per day; payment due 1 Oct, includes an off-hire deduction for the Rotterdam delay as notified by charterer", hire_rate_usd_day=15400, hire_period="1 Oct - 15 Oct 2026")
    ds = b.email("2026-10-03 14:00", "Hire / SOA / Payment", HEAD, [OP], "V202-hire", "VSL-02 - OFF-HIRE DEDUCTION 11.5 HOURS ROTTERDAM", "V202", scenario="S04", reply_to=hs,
                 note="charterer deducts 11.5 hours (USD 7,379.17) for berthing delay at Rotterdam, alleging a ballast water management certificate query",
                 offhire_hours=11.5, offhire_amount_usd=7379.17, alleged_cause="ballast water certificate query")
    rj = b.email("2026-10-06 10:20", "Hire / SOA / Payment", OP, [HEAD, OWN], "V202-hire", "RE: VSL-02 - OFF-HIRE DEDUCTION 11.5 HOURS ROTTERDAM", "V202", scenario="S04", reply_to=ds,
                 note="operator rejects: the certificate was valid and checked; the delay was the terminal berth being occupied; asks to reinstate the 11.5 hours",
                 offhire_hours=11.5, delay_cause="terminal berth occupied")
    ac = b.email("2026-10-11 16:15", "Hire / SOA / Payment", HEAD, [OP], "V202-hire", "RE: VSL-02 - OFF-HIRE DEDUCTION 11.5 HOURS ROTTERDAM", "V202", scenario="S04", reply_to=rj,
                 note="charterer accepts the certificate was valid but keeps 4.0 hours for pilot boarding delayed by the vessel's late notice; will reinstate 7.5 hours (USD 4,812.50) in the next statement",
                 offhire_hours=4.0, offhire_amount_usd=2566.67, reinstated_hours=7.5, reinstated_usd=4812.5)
    b.email("2026-10-12 09:40", "Hire / SOA / Payment", OP, [HEAD], "V202-hire", "VSL-02 HIRE STATEMENT NO. 12 (16 OCT - 31 OCT 2026)", "V202", scenario="S04",
            note="next statement: due 16 Oct, includes the 7.5 hours reinstated; the 4.0 hours still deducted and the SECA claim of USD 31,266 is held by the charterer (disputed)",
            hire_rate_usd_day=15400, hire_next_due="2026-10-16", hire_period="16 Oct - 31 Oct 2026", reinstated_hours=7.5)
    b.truth("S04", "What hire deduction is disputed and when is the next hire due for VSL-02?",
            "The charterer deducted 11.5 hours (USD 7,379.17 at USD 15,400 per day) for the Rotterdam berthing delay. The operator rejected it (valid certificate, berth occupied). On 11 Oct the charterer agreed to "
            "reinstate 7.5 hours (USD 4,812.50) but keeps 4.0 hours (USD 2,566.67). The next hire (statement no. 12, 16–31 Oct) is due 16 Oct; the separate SECA claim of USD 31,266 is still held and disputed.",
            [ds, rj, ac])

    # ---- V202: loading and sea passage -----------------------------------------------------------------------------------
    b.email("2026-10-09 07:10", T_REPORT, MSTR, [OP, AG_ROU], "V202-sail", "VSL-02 / V202 SAILING REPORT ROUEN", "V202", note="sailed Rouen, wheat loaded", cargo_qty_mt=49800,
            rob_vlsfo=618.7, rob_lsmgo=121.0, draft_sailing="F 11.40 / A 11.95 m", eta_casablanca="2026-10-14 18:00")
    for when, rob, spd, wd, force, sea, pos in [("2026-10-10 12:20", 600.2, 12.3, "NW", 4, 1.5, "47-10N 005-50W"), ("2026-10-11 12:15", 582.5, 12.6, "N", 5, 2.0, "42-30N 009-45W"),
                                               ("2026-10-12 12:20", 565.1, 12.5, "NNE", 4, 1.5, "37-45N 010-30W")]:
        b.email(when, T_REPORT, MSTR, [OP, HEAD], "V202-noon", f"VSL-02 NOON REPORT {when[:10]}", "V202", note="daily noon report", rob_vlsfo=rob, rob_lsmgo=120.6, speed_log_kn=spd,
                speed_avg_kn=spd - 0.1, pos_text=pos, wind_dir=wd, wind_force=force, sea_m=sea, eta_casablanca="2026-10-14 18:00")

    b.email("2026-10-12 15:00", T_REPORT, AG_CAS, [OP, HEAD], "V202-cas", "VSL-02 CASABLANCA - ETA NOTICE AND BERTHING", "V202", note="agent: pilot 18:00 on 14 Oct, berth 20:30, discharge 15-16 Oct", eta_casablanca="2026-10-14 18:00")

    # ---- S05: redelivery -----------------------------------------------------------------------------------------------------
    rd = b.email("2026-10-10 13:30", "Redelivery Notice", HEAD, [OP, OWN], "V202-redel", "VSL-02 - REDELIVERY NOTICE (5 DAYS APPROX)", "V202", scenario="S05",
                 note="5 days approximate notice: redelivery on dropping outward pilot Casablanca about 17 Oct 2026, bunkers on redelivery per CP", redelivery_place="Casablanca", redelivery_date_est="2026-10-17",
                 notice_days=5)
    rq = b.email("2026-10-11 10:00", "Redelivery Notice", OP, [HEAD], "V202-redel", "RE: VSL-02 - REDELIVERY NOTICE (5 DAYS APPROX)", "V202", scenario="S05", reply_to=rd,
                 note="operator acknowledges and asks for the 3 day and 2 day notices, the bunker survey arrangement and confirmation that the final cargo discharge ends by 16 Oct",
                 bunkers_on_delivery_vlsfo_mt=905.0, bunkers_on_delivery_price_usd_mt=585.0)
    rb = b.email("2026-10-12 11:20", "Redelivery Notice", HEAD, [OP], "V202-redel", "RE: VSL-02 - REDELIVERY NOTICE - BUNKERS ON REDELIVERY", "V202", scenario="S05", reply_to=rq,
                 note="charterer: joint on/off survey at Casablanca by Vanguard; bunkers on redelivery bought at USD 598 per mt VLSFO; estimated 318 mt VLSFO on redelivery against 905 mt on delivery",
                 redelivery_bunker_price_usd_mt=598.0, redelivery_vlsfo_est_mt=318.0, redelivery_survey="joint on/off survey Vanguard")
    b.truth("S05", "What is the VSL-02 redelivery plan and what bunker figures apply?",
            "Redelivery is on dropping outward pilot at Casablanca around 17 Oct 2026 (5 days' notice given 10 Oct). Bunkers on delivery were 905 mt VLSFO at USD 585; the charterer will buy "
            "the bunkers on redelivery at USD 598 per mt, estimated 318 mt VLSFO, after a joint on/off survey by Vanguard. The operator has asked for the 3-day and 2-day notices.", [rd, rq, rb])

    # ---- V203: fixture ----------------------------------------------------------------------------------------------------------------
    b.email("2026-10-08 11:00", "Fixture Enquiry / Offer / Counter", BROKER, [OP], "V203-fix", "VSL-02 - ENQUIRY: SOYBEAN MEAL SANTOS / ANTWERP 51,000 MT", "V203",
            note="broker enquiry for a voyage after redelivery, open Casablanca late October", laycan="2026-11-05 to 2026-11-15", cargo_qty_mt=51000, freight_usd_mt=29.5)
    return b.ledger()
