"""VSL-11 Aurelia Bay (deep): scenarios S01 (UWI / UWC), S02 (document cross-check), S11 (engine stoppage and
off-hire), S17 (fixture and delivery notice), plus reports, hire and bunkers. Invented throughout.
Clock of the dataset: 2026-10-12 18:00 +08:00; V101 is done, V102 is at sea, V103 is a planned fixture."""

from mockdata.builder import T_REPORT, Builder
from mockdata.ledger import Ledger

OP, OWN, HEAD, MSTR = "OPR-01", "CPY-01", "CPY-02", "CPY-08"
AG_KAM, AG_QD, AG_HED, AG_RZ, AG_NEW = "CPY-04", "CPY-05", "CPY-09", "CPY-10", "CPY-15"
PNI, SURV, BROKER, NEWCH, ENGSVC = "CPY-06", "CPY-07", "CPY-14", "CPY-13", "CPY-12"
RECEIVER = "CPY-16"


def build() -> Ledger:
    b = Builder("VSL-11", "M11")
    for code, name, role, dom in [
        (OP, "Meridian Fleet Management", "operator", "meridianfleet.example"),
        (OWN, "Aurelia Bay Shipping Ltd", "owner", "aureliabay.example"),
        (HEAD, "Corvane Bulk Trading", "charterer", "corvane.example"),
        (MSTR, "Master, MV Aurelia Bay", "master", "vsl11.example"),
        (AG_KAM, "Boke Coast Agency", "port_agent", "bokecoast.example"),
        (AG_QD, "Yellow Gulf Shipping Agency", "port_agent", "yellowgulf.example"),
        (AG_HED, "Pilbara Marine Agencies", "port_agent", "pilbaramarine.example"),
        (AG_RZ, "Eastern Shore Agency Rizhao", "port_agent", "easternshore.example"),
        (AG_NEW, "Hunter Harbour Agencies", "port_agent", "hunterharbour.example"),
        (PNI, "Lantern Club Correspondents", "pni_correspondent", "lanterncorr.example"),
        (SURV, "Seacrest Marine Surveyors", "surveyor", "seacrestsurvey.example"),
        (BROKER, "Pelham Shipbrokers", "broker", "pelhambrokers.example"),
        (NEWCH, "Ostrander Coal Logistics", "charterer", "ostrander.example"),
        (ENGSVC, "Norvik Engine Service", "supplier", "norvikservice.example"),
        (RECEIVER, "Shandong Bauxite Terminal", "receiver", "sdbauxite.example"),
    ]:
        b.party(code, name, role, dom)

    b.voyage("V101", "completed", "CPDD 14JUN2026 (Corvane)", "Kamsar", "Qingdao", "bauxite", 78420, sailed="2026-08-14 16:20")
    b.voyage("V102", "in_progress", "CPDD 14JUN2026 (Corvane)", "Port Hedland", "Rizhao", "iron ore fines", 81000,
             sailed="2026-10-08 04:30", eta="2026-10-22 08:00")
    b.voyage("V103", "planned", "CPDD 09OCT2026 (Ostrander)", "Newcastle", "Krishnapatnam", "thermal coal", 79500)
    b.discrepancies += ["loi_qty_mt", "freight_usd_mt"]  # the LOI differs on purpose (S02); freight is negotiated (S17)

    # ---- V101 (completed): S02 document cross-check -------------------------------------------------------------
    b.email("2026-08-14 17:05", T_REPORT, MSTR, [OP, AG_KAM], "V101-sail", "VSL-11 / V101 SAILING REPORT KAMSAR", "V101",
            note="sailing report, bauxite loaded", cargo_qty_mt=78420, bl_qty_mt=78420, draft_sailing="F 13.82 / A 14.05 m", rob_vlsfo=1241.6)
    mr = b.email("2026-08-14 18:30", "Loading / Cargo Operations", AG_KAM, [OP, HEAD], "V101-docs", "VSL-11 BAUXITE KAMSAR - BLS AND MATES RECEIPT",
                 "V101", scenario="S02", note="agent sends B/L and mate's receipt copies", bl_qty_mt=78420, mr_qty_mt=78420, bl_date="2026-08-14", bl_numbers="KAM-01, KAM-02")
    loi = b.email("2026-09-17 10:12", "LOI (Letter of Indemnity)", HEAD, [OP], "V101-docs", "RE: VSL-11 BAUXITE KAMSAR - BLS AND MATES RECEIPT", "V101",
                  reply_to=mr, scenario="S02", note="charterer asks owners to accept an LOI for a short-landing difference (receiver's draft survey)",
                  loi_qty_mt=78050, receiver_survey_qty_mt=78050, difference_mt=370)
    chk = b.email("2026-09-17 15:40", "LOI (Letter of Indemnity)", OP, [HEAD, OWN], "V101-docs", "RE: VSL-11 BAUXITE KAMSAR - BLS AND MATES RECEIPT",
                  "V101", reply_to=loi, scenario="S02", note="operator notes the quantities differ and asks for the LOI wording and the receiver's survey report",
                  bl_qty_mt=78420, loi_qty_mt=78050)
    b.email("2026-09-18 09:20", "LOI (Letter of Indemnity)", HEAD, [OP], "V101-docs", "RE: VSL-11 BAUXITE KAMSAR - BLS AND MATES RECEIPT", "V101",
            reply_to=chk, scenario="S02", note="charterer sends the receiver's survey report and the LOI draft; LOI covers 370 mt, signed by charterer only",
            loi_qty_mt=78050, difference_mt=370, loi_signed_by="charterer")
    arr = b.email("2026-09-18 21:40", T_REPORT, MSTR, [OP, AG_QD], "V101-qd", "VSL-11 ARRIVAL REPORT QINGDAO", "V101",
                  note="arrival report; notice of readiness tendered", nor_tendered="2026-09-18 21:30")
    b.email("2026-09-23 22:10", "Discharging", AG_QD, [OP, HEAD], "V101-qd", "VSL-11 QINGDAO - DISCHARGE COMPLETED", "V101", reply_to=arr,
            note="discharge completed; outturn per receiver's shore scale", outturn_qty_mt=78052)
    b.truth("S02", "Do the B/L, mate's receipt and LOI quantities for the Kamsar bauxite agree?",
            "No. The B/L and the mate's receipt both state 78,420 mt (14 Aug 2026), but the LOI covers 78,050 mt, which is the receiver's survey figure, a difference of 370 mt. "
            "The LOI is signed by the charterer only. The Qingdao outturn was 78,052 mt, in line with the receiver's survey.", [mr, loi, chk])

    b.email("2026-09-14 08:30", T_REPORT, AG_QD, [OP, HEAD], "V101-qd", "VSL-11 QINGDAO ETA NOTICE AND BERTHING PLAN", "V101",
            note="agent gives ETA and the berth plan; berthing expected after a 2 day wait", eta_qingdao="2026-09-18 20:00", expected_wait_days=2)
    b.email("2026-09-16 12:15", T_REPORT, MSTR, [OP, HEAD], "V101-noon", "VSL-11 NOON REPORT 2026-09-16", "V101", note="daily noon report near Qingdao",
            rob_vlsfo=412.8, speed_log_kn=11.6, speed_avg_kn=11.4, pos_text="30-45N 124-10E", wind_dir="NE", wind_force=5, sea_m=2.0, eta_qingdao="2026-09-18 20:00")
    b.email("2026-10-06 17:20", T_REPORT, AG_HED, [OP, HEAD], "V102-hed", "VSL-11 PORT HEDLAND - BERTHING AND LOADING STARTED", "V102",
            note="agent reports berthed and loading commenced, rate 3,200 mt/h", loading_rate_mt_h=3200, berthed="2026-10-06 13:40")

    # ---- V102: bunkers, sailing, noon reports ---------------------------------------------------------------------
    b.email("2026-10-02 11:05", "Bunker (Stem / Quote / ROB / Quality)", OP, [OWN], "V102-bunker", "VSL-11 BUNKER STEM PORT HEDLAND OCT 2026", "V102",
            note="stem of 640 MT VLSFO at Port Hedland", stem_vlsfo_mt=640, stem_price_usd_mt=612.5)
    b.email("2026-10-08 05:10", T_REPORT, MSTR, [OP, AG_HED], "V102-sail", "VSL-11 / V102 SAILING REPORT PORT HEDLAND", "V102",
            note="sailed Port Hedland, iron ore fines loaded", cargo_qty_mt=81000, draft_sailing="F 14.02 / A 14.35 m", rob_vlsfo=1368.4, eta_rizhao="2026-10-22 08:00")
    noons = [("2026-10-09 12:20", 1241.9, 12.1, "SE", 4, 1.5, "20-10S 112-35E", 11.9),
             ("2026-10-10 12:15", 1180.2, 10.8, "E", 5, 2.0, "16-05S 111-50E", 10.6),
             ("2026-10-11 12:10", 1131.0, 11.4, "ESE", 4, 1.5, "11-40S 112-20E", 11.2),
             ("2026-10-12 12:10", 1069.5, 11.9, "SE", 3, 1.0, "07-10S 113-05E", 11.7)]
    for when, rob, spd, wd, force, sea, pos, avg in noons:
        b.email(when, T_REPORT, MSTR, [OP, HEAD], "V102-noon", f"VSL-11 NOON REPORT {when[:10]}", "V102", note="daily noon report",
                rob_vlsfo=rob, speed_log_kn=spd, speed_avg_kn=avg, pos_text=pos, wind_dir=wd, wind_force=force, sea_m=sea,
                eta_rizhao="2026-10-22 08:00" if when < "2026-10-10" else "2026-10-22 20:00")

    # ---- S11: main engine stoppage and an off-hire claim ---------------------------------------------------------------
    st = b.email("2026-10-10 08:40", "Vessel Defect / Repair / Breakdown", MSTR, [OP, ENGSVC], "V102-engine", "VSL-11 M/E NO.4 CYL EXHAUST VALVE - REDUCED SPEED", "V102",
                 scenario="S11", note="master reports a stoppage to change the no.4 exhaust valve; engine stopped 02:10 to 08:10", stop_from="2026-10-10 02:10",
                 stop_to="2026-10-10 08:10", stop_hours=6.0, cause="exhaust valve no.4 spindle seat leak")
    b.email("2026-10-10 11:15", "Vessel Defect / Repair / Breakdown", ENGSVC, [OP], "V102-engine", "RE: VSL-11 M/E NO.4 CYL EXHAUST VALVE - REDUCED SPEED", "V102",
                 reply_to=st, scenario="S11", note="engine service advises the valve was replaced from spares on board; sea trial normal; spare to be replenished at Rizhao",
                 spare_valve_replaced="yes")
    cl = b.email("2026-10-10 16:30", "Off-hire", HEAD, [OP, OWN], "V102-engine", "VSL-11 OFF-HIRE NOTICE 10 OCT 2026", "V102", reply_to=st, scenario="S11",
                 note="charterer notifies off-hire for the whole stoppage and a speed shortfall afterwards, citing the CP off-hire clause",
                 offhire_claimed_hours=6.0, offhire_clause="clause 17")
    rp = b.email("2026-10-11 09:50", "Off-hire", OP, [HEAD, OWN], "V102-engine", "RE: VSL-11 OFF-HIRE NOTICE 10 OCT 2026", "V102", reply_to=cl, scenario="S11",
                 note="operator accepts the 6.0 h stoppage as off-hire time but disputes the speed claim: the vessel regained 11.8 kn within 3 h and the reduced-speed period is net loss of 3.5 h only if the warranty is 12.0 kn; asks for the speed log extract",
                 offhire_accepted_hours=6.0, speed_warranty_kn=12.0, net_speed_loss_hours=3.5)
    b.email("2026-10-12 10:05", "Off-hire", HEAD, [OP], "V102-engine", "RE: VSL-11 OFF-HIRE NOTICE 10 OCT 2026", "V102", reply_to=rp, scenario="S11",
            note="charterer agrees to the 6.0 h and asks for the log extract before agreeing the speed part", offhire_accepted_hours=6.0)
    b.truth("S11", "What off-hire is claimed for the V102 engine stoppage, and what has the operator accepted?",
            "The charterer claimed off-hire for the 6.0 h stoppage (10 Oct 02:10 to 08:10 LT, clause 17) plus a speed shortfall afterwards. The operator accepted the 6.0 h but disputes the speed part "
            "(warranty 12.0 kn, vessel regained 11.8 kn within 3 h, net loss at most 3.5 h) and asked for the speed log extract; the charterer agreed the 6.0 h and awaits the extract.",
            [st, cl, rp])

    # ---- hire --------------------------------------------------------------------------------------------------
    b.email("2026-10-01 10:00", "Hire / SOA / Payment", OP, [HEAD], "V102-hire", "VSL-11 HIRE STATEMENT NO. 14 (16 OCT - 31 OCT 2026)", "V102",
            note="hire statement for the next period; payment due 16 Oct", hire_rate_usd_day=17250, hire_next_due="2026-10-16", hire_amount_usd=258750)
    b.email("2026-10-12 09:15", "Hire / SOA / Payment", HEAD, [OP], "V102-hire", "RE: VSL-11 HIRE STATEMENT NO. 14", "V102",
            note="charterer confirms payment will be made on 15 Oct and asks to deduct the 6.0 h off-hire in the following statement", hire_next_due="2026-10-16")

    # ---- S01: underwater inspection / cleaning before the next fixture --------------------------------------------------------
    rq = b.email("2026-10-05 14:20", "Voyage Instructions / Port Nomination", NEWCH, [OP, BROKER], "V103-hull", "VSL-11 / NEWCASTLE - BIOFOULING AND HULL CLEANLINESS REQUIREMENT", "V103",
                 scenario="S01", note="the Newcastle charterer requires a recent underwater hull inspection report before arrival for biofouling reasons; inspection within 30 days before arrival",
                 inspect_within_days=30, required_before="Newcastle arrival", laycan="2026-11-20 to 2026-11-30")
    ag = b.email("2026-10-09 10:30", "Survey Arrangement / Quotation", OP, [AG_RZ, SURV], "V103-hull", "VSL-11 RIZHAO - UNDERWATER INSPECTION AND CLEANING WINDOW", "V103",
                 reply_to=rq, scenario="S01", note="operator asks the Rizhao agent for a diver permit and quote for UWI and UWC after discharge")
    rp1 = b.email("2026-10-10 15:45", "Survey Arrangement / Quotation", AG_RZ, [OP], "V103-hull", "RE: VSL-11 RIZHAO - UNDERWATER INSPECTION AND CLEANING WINDOW", "V103",
                  reply_to=ag, scenario="S01", note="agent: in-water cleaning is not permitted inside port limits; inspection only, at anchorage, after discharge completes, with a 3 working days permit; quote USD 3,800",
                  uwc_allowed="no", uwi_allowed="yes, anchorage, after discharge", permit_lead_working_days=3, uwi_quote_usd=3800)
    pc = b.email("2026-10-11 11:20", "P&I / Insurance", PNI, [OP, OWN], "V103-hull", "VSL-11 NEWCASTLE - PRE-ARRIVAL HULL INSPECTION AT BERTH", "V103", reply_to=rq,
                 scenario="S01", note="the Newcastle correspondent says the authority accepts an in-water inspection report from the previous 30 days, or an inspection at Newcastle anchorage by an approved diver booked by the correspondent",
                 alt_window="Newcastle anchorage by approved diver", alt_quote_usd=5200)
    b.email("2026-10-12 08:55", "Voyage Instructions / Port Nomination", OP, [HEAD], "V103-hull", "RE: VSL-11 V103 - HULL INSPECTION PLAN", "V103",
            scenario="S01", note="operator internal-style note to the charterer: V102 has no time for diving at sea or at Hedland; the plan is an inspection at Rizhao anchorage after discharge, or Newcastle anchorage; cleaning only if the report shows fouling",
            reply_to=rp1)
    b.truth("S01", "Can an underwater inspection or cleaning for VSL-11 be arranged during V102?",
            "Not during V102 itself: the vessel is at sea from Port Hedland (sailed 8 Oct) to Rizhao (ETA 22 Oct, moved from 08:00 to 20:00 after the engine stoppage). The first realistic window is Rizhao anchorage after discharge: inspection only "
            "(in-water cleaning is not permitted in port limits), 3 working days' permit, quote USD 3,800. The alternative is an inspection at Newcastle anchorage by an approved diver booked by the P&I correspondent "
            "(USD 5,200). The charterer needs a report within 30 days before Newcastle arrival (laycan 20–30 Nov).", [rq, rp1, pc])

    # ---- S17: fixture enquiry, firm offer, recap, delivery notice -------------------------------------------------------------
    f1 = b.email("2026-10-06 09:40", "Fixture Enquiry / Offer / Counter", BROKER, [OP], "V103-fix", "VSL-11 - ENQUIRY: 79,500 MT THERMAL COAL NEWCASTLE / KRISHNAPATNAM", "V103",
                 scenario="S17", note="broker's enquiry for a coal voyage, laycan 20-30 Nov", laycan="2026-11-20 to 2026-11-30", cargo_qty_mt=79500, freight_usd_mt=17.8)
    f2 = b.email("2026-10-07 16:10", "Fixture Enquiry / Offer / Counter", OP, [BROKER], "V103-fix", "RE: VSL-11 - ENQUIRY: 79,500 MT THERMAL COAL", "V103", reply_to=f1,
                 scenario="S17", note="counter offer: freight USD 19.2 per mt, 3 days demurrage free, hull inspection at charterer's time", freight_usd_mt=19.2, demurrage_usd_day=19500)
    f3 = b.email("2026-10-09 12:00", "CP Terms / Recap / Addendum", BROKER, [OP, NEWCH], "V103-fix", "VSL-11 / OSTRANDER - FIXTURE RECAP", "V103", reply_to=f2,
                 scenario="S17", note="clean recap: freight USD 18.6 per mt, laycan 20-30 Nov, load Newcastle, discharge Krishnapatnam, demurrage USD 19,500 per day, CP date 9 Oct 2026",
                 freight_usd_mt=18.6, demurrage_usd_day=19500, laycan="2026-11-20 to 2026-11-30", cp_date="2026-10-09")
    b.email("2026-10-11 14:25", "Delivery Notice", NEWCH, [OP], "V103-fix", "VSL-11 V103 - LAYCAN AND NOMINATION NOTICE", "V103", reply_to=f3, scenario="S17",
            note="charterer gives laycan and nominates Newcastle berth agents; 10 days notice of arrival required", notice_days=10, laycan="2026-11-20 to 2026-11-30")
    b.truth("S17", "What are the agreed terms for the V103 Newcastle coal fixture?",
            "Recap of 9 Oct 2026: freight USD 18.6 per mt (the counter offer was 19.2 and the enquiry 17.8), 79,500 mt thermal coal, Newcastle to Krishnapatnam, laycan 20–30 Nov 2026, demurrage USD 19,500 per day; "
            "the charterer asks for 10 days' notice of arrival.", [f1, f2, f3])
    return b.ledger()
