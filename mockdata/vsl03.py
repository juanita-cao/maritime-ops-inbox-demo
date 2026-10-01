"""VSL-03 Kestrel Harbor (deep): S01 (UWI / UWC, here a window while waiting at anchorage), S06 (CTM and a
disputed port invoice), S07 (cargo wetting claim via P&I), S18 (cargo shortage claim, time bar). Invented
throughout. Clock: 2026-10-12 18:00 +08:00. V301 done, V302 at sea (Aqaba to Paradip), V303 planned."""

from mockdata.builder import T_REPORT, Builder
from mockdata.ledger import Ledger

OP, OWN, HEAD, MSTR = "OPR-01", "CPY-41", "CPY-42", "CPY-48"
AG_RB, AG_MUN, AG_AQ, AG_PAR = "CPY-43", "CPY-44", "CPY-45", "CPY-46"
PNI, SURV, RECV, BROKER = "CPY-47", "CPY-49", "CPY-50", "CPY-14"
NEXTCH, DIVER = "CPY-51", "CPY-52"


def build() -> Ledger:
    b = Builder("VSL-03", "M13")
    for code, name, role, dom in [
        (OP, "Meridian Fleet Management", "operator", "meridianfleet.example"),
        (OWN, "Kestrel Harbor Maritime Inc", "owner", "kestrelharbor.example"),
        (HEAD, "Ravenscar Commodities", "charterer", "ravenscar.example"),
        (MSTR, "Master, MV Kestrel Harbor", "master", "vsl03.example"),
        (AG_RB, "Zulu Coast Agencies", "port_agent", "zulucoast.example"),
        (AG_MUN, "Kutch Gulf Port Services", "port_agent", "kutchgulf.example"),
        (AG_AQ, "Red Sea Maritime Agency", "port_agent", "redseamaritime.example"),
        (AG_PAR, "Mahanadi Shipping Agency", "port_agent", "mahanadiagency.example"),
        (PNI, "Anchor Point Club Correspondents", "pni_correspondent", "anchorpoint.example"),
        (SURV, "Gulf of Kutch Marine Surveyors", "surveyor", "kutchsurvey.example"),
        (RECV, "Mundra Power Fuels Ltd", "receiver", "mundrapower.example"),
        (BROKER, "Pelham Shipbrokers", "broker", "pelhambrokers.example"),
        (NEXTCH, "Calder Bulk Carriers Pool", "charterer", "calderbulk.example"),
        (DIVER, "Paradeep Divers and Hull Services", "supplier", "paradeepdivers.example"),
    ]:
        b.party(code, name, role, dom)
    b.voyage("V301", "completed", "CPDD 02MAY2026 (Ravenscar)", "Richards Bay", "Mundra", "thermal coal", 61200, sailed="2026-08-30 20:40")
    b.voyage("V302", "in_progress", "CPDD 02MAY2026 (Ravenscar)", "Aqaba", "Paradip", "urea", 55300, sailed="2026-10-04 11:30", eta="2026-10-21 14:00")
    b.voyage("V303", "planned", "recap CPDD 06OCT2026 (Calder)", "Visakhapatnam", "Chittagong", "limestone", 58000)
    b.discrepancies += ["dues_invoice_total_usd"]  # the reminder repeats the invoice number with a different total (S06)

    # ---- V301: loading and discharge, S18 shortage ----------------------------------------------------------------------------------------
    b.email("2026-08-30 21:15", T_REPORT, MSTR, [OP, AG_RB], "V301-sail", "VSL-03 / V301 SAILING REPORT RICHARDS BAY", "V301", note="sailed Richards Bay, coal loaded",
            cargo_qty_mt=61200, bl_qty_mt=61200, load_moisture_pct=9.0, rob_vlsfo=1004.5)
    b.email("2026-09-17 15:20", T_REPORT, AG_MUN, [OP, HEAD], "V301-disch", "VSL-03 MUNDRA ARRIVAL AND BERTHING PLAN", "V301", note="agent: arrival 17 Sep, discharge to start on berthing, receivers Mundra Power Fuels", arrival_mundra="2026-09-17 12:00")
    for when, rob, spd, wd, force, sea, pos in [("2026-09-02 12:20", 960.2, 11.6, "SE", 5, 2.0, "32-10S 034-40E"), ("2026-09-05 12:25", 880.0, 11.4, "ESE", 4, 1.5, "25-50S 042-10E"),
                                               ("2026-09-10 12:15", 744.8, 11.5, "E", 5, 2.0, "08-20S 055-10E"), ("2026-09-14 12:20", 640.5, 11.3, "ENE", 4, 1.5, "13-40N 066-45E")]:
        b.email(when, T_REPORT, MSTR, [OP, HEAD], "V301-noon", f"VSL-03 NOON REPORT {when[:10]}", "V301", note="daily noon report", rob_vlsfo=rob, speed_log_kn=spd, speed_avg_kn=spd - 0.1,
                pos_text=pos, wind_dir=wd, wind_force=force, sea_m=sea, eta_mundra="2026-09-17 12:00")
    b.email("2026-08-29 18:00", T_REPORT, AG_RB, [OP, HEAD], "V301-load", "VSL-03 RICHARDS BAY - LOADING COMPLETED", "V301", note="agent: loading finished 29 Aug 17:30, documents on board", cargo_qty_mt=61200, bl_qty_mt=61200)
    b.email("2026-10-03 10:00", T_REPORT, AG_AQ, [OP, HEAD], "V302-load", "VSL-03 AQABA - LOADING COMPLETED", "V302", note="agent: urea loading finished 3 Oct", cargo_qty_mt=55300)
    ds = b.email("2026-09-23 06:30", "Discharging", AG_MUN, [OP, HEAD], "V301-disch", "VSL-03 MUNDRA DISCHARGE COMPLETED - OUTTURN", "V301", scenario="S18",
                 note="discharge completed; outturn per shore weighbridge 60,790 mt against B/L 61,200 mt", outturn_qty_mt=60790, bl_qty_mt=61200)
    sc = b.email("2026-10-01 11:40", "Claim", RECV, [PNI, OP], "V301-short", "VSL-03 / MUNDRA - CARGO SHORTAGE CLAIM", "V301", scenario="S18", reply_to=ds,
                 note="receiver claims for 410 mt shortage (0.67%) at USD 100 per mt = USD 41,000; mentions the CP 0.5% tolerance and the 12-month time bar", shortage_mt=410, shortage_pct=0.67,
                 claim_amount_usd=41000.0, tolerance_pct=0.5, time_bar_months=12, claim_clause="clause 45")
    sr = b.email("2026-10-05 10:15", "Claim", PNI, [OP, OWN], "V301-short", "RE: VSL-03 / MUNDRA - CARGO SHORTAGE CLAIM", "V301", scenario="S18", reply_to=sc,
                 note="the correspondent asks for the draft survey at load and discharge, the weighbridge certificates and the cargo documents; advises no admission and holding replies until documents are checked",
                 asks="draft surveys, weighbridge certificates, B/L")
    b.email("2026-10-09 17:30", "Claim", OP, [PNI], "V301-short", "RE: VSL-03 / MUNDRA - CARGO SHORTAGE CLAIM", "V301", scenario="S18", reply_to=sr,
            note="operator sends the load draft survey (61,170 mt) and the discharge draft survey (61,070 mt); the weighbridge figure differs from the draft survey at discharge by 280 mt; asks the correspondent to request the receiver's weighbridge calibration certificate",
            load_draft_survey_mt=61170, discharge_draft_survey_mt=61070)
    b.truth("S18", "What is the V301 cargo shortage claim and its position?",
            "The receiver claims a 410 mt shortage (0.67%, USD 100 per mt = USD 41,000) based on B/L 61,200 mt against the shore weighbridge outturn 60,790 mt, which is above the 0.5% CP tolerance. "
            "The 12-month time bar (clause 45) is running. The load draft survey was 61,170 mt and the discharge draft survey 61,070 mt, so the weighbridge is 280 mt below the discharge draft survey; the operator has "
            "asked the correspondent to request the weighbridge calibration certificate. No admission has been made.", [ds, sc, sr])

    # ---- S07: wetting claim ------------------------------------------------------------------------------------------------------------------
    wl = b.email("2026-09-29 09:10", "P&I / Insurance", PNI, [OP, OWN], "V301-wet", "VSL-03 MUNDRA - RECEIVER'S LETTER ALLEGING SEAWATER IN HOLD NO.4", "V301", scenario="S07",
                 note="the correspondent forwards the receiver's letter: coal from hold no.4 arrived with moisture 11.2% against 9.0% at load; receiver alleges seawater ingress and reserves rights; no amount claimed yet",
                 hold_no=4, discharge_moisture_pct=11.2, load_moisture_pct=9.0)
    sq = b.email("2026-10-03 15:00", "Survey Arrangement / Quotation", SURV, [PNI, OP], "V301-wet", "RE: VSL-03 - SURVEY QUOTATION HOLD NO.4 HATCH COVER HOSE TEST", "V301", scenario="S07", reply_to=wl,
                 note="surveyor quotes USD 2,950 for a hatch cover hose test and inspection of hold no.4 coamings at the next port; proposes attendance on 14 Oct", survey_quote_usd=2950, survey_date="2026-10-14")
    b.email("2026-10-08 10:45", "P&I / Insurance", PNI, [OP, OWN], "V301-wet", "RE: VSL-03 - SURVEY QUOTATION HOLD NO.4 HATCH COVER HOSE TEST", "V301", scenario="S07", reply_to=sq,
            note="the correspondent: appoint the surveyor; do not comment to the receiver; the master's rain and weather log for the voyage is needed", asks="master's rain and weather log")
    b.truth("S07", "What is the position on the V301 hold no.4 wetting allegation?",
            "The receiver alleges seawater ingress in hold no.4 (moisture 11.2% at discharge against 9.0% at load, rights reserved, no amount claimed). The P&I correspondent advised not to comment to the receiver "
            "and to appoint Gulf of Kutch Marine Surveyors for a hatch cover hose test and coaming inspection (USD 2,950, planned 14 Oct); the master's rain and weather log is still needed.", [wl, sq])

    # ---- V302: sea passage + S06 CTM and the port invoice ------------------------------------------------------------------------------------
    b.email("2026-10-04 12:10", T_REPORT, MSTR, [OP, AG_AQ], "V302-sail", "VSL-03 / V302 SAILING REPORT AQABA", "V302", note="sailed Aqaba, urea loaded", cargo_qty_mt=55300, rob_vlsfo=1102.8,
            draft_sailing="F 12.55 / A 12.95 m", eta_paradip="2026-10-21 14:00")
    for when, rob, spd, avg, wd, force, sea, pos in [("2026-10-09 12:25", 1038.0, 11.2, 11.3, "NW", 4, 1.5, "15-20N 053-30E"), ("2026-10-10 12:20", 984.6, 10.9, 11.1, "W", 5, 2.0, "13-10N 057-15E"),
                                                    ("2026-10-11 12:20", 932.0, 10.6, 10.9, "WSW", 4, 1.5, "11-05N 061-00E"), ("2026-10-12 12:25", 880.4, 10.4, 10.7, "SW", 5, 2.0, "09-20N 064-40E")]:
        b.email(when, T_REPORT, MSTR, [OP, HEAD], "V302-noon", f"VSL-03 NOON REPORT {when[:10]}", "V302", note="daily noon report; speed and consumption", rob_vlsfo=rob, speed_log_kn=spd,
                speed_avg_kn=avg, pos_text=pos, wind_dir=wd, wind_force=force, sea_m=sea, eta_paradip="2026-10-21 14:00" if when < "2026-10-12" else "2026-10-21 20:00")
    cq = b.email("2026-10-02 09:20", "Cash to Master / Supply (CTM, Fresh Water, Provisions)", MSTR, [OP], "V302-ctm", "VSL-03 CTM REQUEST AQABA", "V302", scenario="S06",
                 note="master asks for cash to master USD 15,000 for wages, victualling and the Aqaba port cash items", ctm_usd=15000)
    b.email("2026-10-02 15:30", "Cash to Master / Supply (CTM, Fresh Water, Provisions)", AG_AQ, [OP, MSTR], "V302-ctm", "RE: VSL-03 CTM REQUEST AQABA - FEE INVOICE", "V302", scenario="S06", reply_to=cq,
                 note="agent will deliver the cash on board on 3 Oct; the cash handling fee is USD 450 and is invoiced to the owners", ctm_usd=15000, ctm_fee_usd=450)
    d1 = b.email("2026-09-08 11:00", "Port Agency / Port Costs (DA)", AG_RB, [OP, HEAD], "V301-da", "VSL-03 RICHARDS BAY - FINAL DISBURSEMENT ACCOUNT INV. ZC-2291", "V301", scenario="S06",
                 note="final DA for Richards Bay, invoice ZC-2291, total USD 31,870; includes the pre-loading survey and tallying lines", dues_invoice_no="ZC-2291", dues_invoice_total_usd=31870.0,
                 includes="pre-loading survey USD 1,800; tally USD 2,150; port dues; pilotage; tugs")
    d2 = b.email("2026-10-01 10:05", "Port Agency / Port Costs (DA)", AG_RB, [OP], "V301-da", "REMINDER: VSL-03 RICHARDS BAY - FINAL DA INV. ZC-2291 OUTSTANDING", "V301", scenario="S06", reply_to=d1,
                 note="payment reminder repeating invoice ZC-2291 with a total of USD 31,780", dues_invoice_no="ZC-2291", dues_invoice_total_usd=31780.0)
    d3 = b.email("2026-10-07 09:00", "Port Agency / Port Costs (DA)", OP, [AG_RB, HEAD], "V301-da", "RE: REMINDER: VSL-03 RICHARDS BAY - FINAL DA INV. ZC-2291 OUTSTANDING", "V301", scenario="S06", reply_to=d2,
                 note="operator asks which total is right (31,870 or 31,780) and asks who the pre-loading survey and tally lines belong to under the CP, since charterers appointed the survey",
                 dues_invoice_no="ZC-2291")
    b.email("2026-10-10 14:10", "Port Agency / Port Costs (DA)", AG_RB, [OP], "V301-da", "RE: REMINDER: VSL-03 RICHARDS BAY - FINAL DA INV. ZC-2291 OUTSTANDING", "V301", scenario="S06", reply_to=d3,
            note="agent: USD 31,780 is correct, the first total had a typing error; the pre-loading survey and tally were ordered by the charterers' receiver", dues_invoice_no="ZC-2291", dues_invoice_total_usd=31780.0)
    b.truth("S06", "How much is the Richards Bay final DA and which lines are disputed?",
            "Invoice ZC-2291 was first issued at USD 31,870 and the reminder says USD 31,780; on 10 Oct the agent confirmed USD 31,780 (typing error in the first total). It includes a pre-loading survey (USD 1,800) and "
            "tallying (USD 2,150) ordered by the charterers' side, which the operator has asked to be allocated per the CP. The Aqaba CTM of USD 15,000 was delivered on 3 Oct with a USD 450 handling fee invoiced to owners.",
            [d1, d2, d3, cq])

    # ---- S01: speed loss, hull fouling suspicion, a window at anchorage while waiting ---------------------------------------------------------------
    sp = b.email("2026-10-11 13:00", "Weather Routing / Speed & Consumption", OP, [MSTR], "V302-hull", "VSL-03 SPEED LOSS - POSSIBLE HULL FOULING", "V302", scenario="S01",
                 note="operator asks the master to confirm the speed loss: 10.4 kn at the same rpm and weather where 11.4 kn was normal; suspects fouling after the long stay at Mundra", speed_loss_kn=1.0)
    ag = b.email("2026-10-11 16:40", "Survey Arrangement / Quotation", OP, [AG_PAR, DIVER], "V302-hull", "VSL-03 PARADIP - UNDERWATER INSPECTION AND CLEANING AT ANCHORAGE", "V302", scenario="S01", reply_to=sp,
                 note="operator asks the Paradip agent and the diving contractor for a permit and quote for an inspection and cleaning at anchorage while the vessel waits for a berth")
    ar = b.email("2026-10-12 10:10", "Survey Arrangement / Quotation", AG_PAR, [OP], "V302-hull", "RE: VSL-03 PARADIP - UNDERWATER INSPECTION AND CLEANING AT ANCHORAGE", "V302", scenario="S01", reply_to=ag,
                 note="agent: UWI and UWC are allowed at the anchorage with port permission, 5 working days' notice, daylight, not during cargo operations; the berth wait is currently about 3 days; quote USD 7,400 for inspection and cleaning, USD 2,600 for inspection only",
                 uwc_allowed="yes, anchorage", uwi_allowed="yes, anchorage", permit_lead_working_days=5, berth_wait_days=3, uwc_quote_usd=7400, uwi_quote_usd=2600)
    b.email("2026-10-12 14:20", "Voyage Instructions / Port Nomination", HEAD, [OP], "V302-hull", "RE: VSL-03 PARADIP - ANY DELAY AT ANCHORAGE", "V302", scenario="S01", reply_to=ar,
            note="charterer says no objection to diving while the vessel waits for a berth, as long as it does not delay berthing or cause off-hire claims; asks to be told the diving time", charterer_objection="no, if it does not delay berthing")
    b.truth("S01", "Can an underwater inspection or cleaning be arranged for VSL-03 on V302?",
            "Yes, but only at Paradip anchorage while waiting for a berth (expected wait about 3 days from the ETA of 21 Oct). The agent allows UWI and UWC at anchorage with 5 working days' notice, not during cargo operations: "
            "USD 7,400 for inspection and cleaning or USD 2,600 for inspection only. The charterer has no objection provided berthing is not delayed. Today is 12 Oct, so the permit request should go in now. "
            "The reason is a speed loss of about 1 kn at the same rpm.", [sp, ar])

    # ---- V303 fixture ------------------------------------------------------------------------------------------------------------------------------
    b.email("2026-10-06 10:30", "CP Terms / Recap / Addendum", BROKER, [OP, NEXTCH], "V303-fix", "VSL-03 / CALDER - FIXTURE RECAP LIMESTONE VISAKHAPATNAM / CHITTAGONG", "V303",
            note="clean recap: 58,000 mt limestone, load Visakhapatnam discharge Chittagong, freight USD 14.2 per mt, laycan 28 Oct - 6 Nov", cargo_qty_mt=58000, freight_usd_mt=14.2, laycan="2026-10-28 to 2026-11-06", cp_date="2026-10-06")
    return b.ledger()
