"""Knowledge-base tables of the mock dataset, derived from the ledgers (docs/design_mock_data.md 6): vessels, voyages, parties,
contacts, charter links. The taxonomy, action rules, glossary and event families are method assets shared with the
desanitized set and are copied as they are."""

import csv
import re
import shutil
from pathlib import Path

from mockdata.ledger import Ledger, Party

ROOT = Path(__file__).resolve().parents[1]
SHARED = ("taxonomy.csv", "action_rules.csv", "event_families.csv", "glossary.csv")
ROLE = {"operator": "Operator (internal)", "owner": "Owner / Manager", "charterer": "Charterer", "sub_charterer": "Charterer", "master": "Master / Vessel",
        "port_agent": "Port Agent", "pni_correspondent": "P&I Club / Correspondent", "surveyor": "Surveyor / Survey Company", "broker": "Broker",
        "receiver": "Shipper / Receiver", "supplier": "Other"}
TYPE = {"operator": "operator / manager", "owner": "owner", "charterer": "charterer (head)", "sub_charterer": "charterer (sub)", "master": "vessel mailbox",
        "port_agent": "port agent", "pni_correspondent": "P&I correspondent", "surveyor": "surveyor", "broker": "broker", "receiver": "receiver", "supplier": "service supplier"}
STATUS = {"completed": "completed", "in_progress": "in progress", "planned": "planned"}


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _head(lg: Ledger, cp_ref: str) -> Party | None:
    token = re.search(r"\(([^)]+)\)", cp_ref)
    return next((p for p in lg.parties if token and p.role in ("charterer",) and p.name.lower().startswith(token.group(1).lower())), None)


def build_kb(ledgers: list[Ledger], out: Path, used_codes: set[str]) -> None:
    kb = out / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    for name in SHARED:
        shutil.copyfile(ROOT / "kb" / name, kb / name)
    parties: dict[str, Party] = {}
    vessel_rows, voyage_rows, link_rows, party_rows = [], [], [], []
    seen_parties: dict[str, set[str]] = {}
    for lg in ledgers:
        owner = next(p for p in lg.parties if p.role == "owner")
        master = next(p for p in lg.parties if p.role == "master")
        vessel_rows.append([lg.vessel, "mock ledger", ";".join(v.no for v in lg.voyages), owner.code, "OPR-01", master.code])
        for v in lg.voyages:
            facts = f"{v.cargo}, {v.qty_mt:,.0f} mt" + (f", sailed {v.sailed[:16].replace('T', ' ')} LT" if v.sailed else "") + (f", ETA {v.eta[:16].replace('T', ' ')} LT" if v.eta else "")
            voyage_rows.append([lg.vessel, v.no, STATUS[v.status], f"{v.load_port} -> {v.disch_port}", v.sailed[:10] if v.sailed else "", "", facts, "mock ledger"])
            head = _head(lg, v.cp_ref)
            if head:
                used_codes.add(head.code)
                link_rows.append([lg.vessel, v.no, "Owner-Head", owner.code, head.code, v.cp_ref.split(" (")[0].replace("recap ", "").replace(" pending", ""), "stated", "charter recap"])
        for p in lg.parties:
            parties[p.code] = p
            seen_parties.setdefault(p.code, set()).add(lg.vessel)
    used = used_codes | {"OPR-01"} | {r[3] for r in vessel_rows} | {r[5] for r in vessel_rows}
    for code in sorted(used):
        p = parties[code]
        party_rows.append([code, TYPE[p.role], ROLE[p.role], p.name, ";".join(sorted(seen_parties[code])), "stated", "mock ledger"])
    _write(kb / "vessels.csv", ["vessel_code", "source_document", "voyages", "owner_party", "manager_party", "vessel_mailbox_party"], vessel_rows)
    _write(kb / "voyages.csv", ["vessel_code", "voyage_no", "status", "route", "start", "end", "facts", "source"], voyage_rows)
    _write(kb / "parties.csv", ["party_code", "party_type", "role", "description", "vessel_codes", "confidence", "evidence"], party_rows)
    _write(kb / "contacts.csv", ["contact_code", "party_code", "party_type"], [[f"mail01@{parties[c].domain}", c, TYPE[parties[c].role]] for c in sorted(used)])
    # one link per (vessel, charter party): voyages of the same charter party are joined
    merged: dict[tuple, list] = {}
    for vessel, vno, level, owner, head, cp, conf, ev in link_rows:
        key = (vessel, level, owner, head, cp)
        merged.setdefault(key, [vessel, [], level, owner, head, cp, conf, ev])[1].append(vno)
    rows = [[f"L{i + 1:02d}", r[0], ";".join(r[1]), r[2], r[3], r[4], r[5], "", "", r[6], r[7]] for i, r in enumerate(merged.values())]
    for lg in ledgers:  # management link: owner to our side
        owner = next(p for p in lg.parties if p.role == "owner")
        rows.append([f"M{len(rows) + 1:02d}", lg.vessel, ";".join(v.no for v in lg.voyages), "Management", owner.code, "OPR-01", "", "", "", "stated", "management agreement"])
    _write(kb / "charter_links.csv", ["link_id", "vessel_code", "voyage_no", "level", "from_party", "to_party", "cp_reference", "start", "end", "confidence", "evidence"], rows)
