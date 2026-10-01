"""Build the mock dataset's emails: python -m mockdata.build [--out datasets/mock]. Writes one JSON per email
({email_id, text, event_id, thread, scenario}) and the truths with their E### evidence ids."""

import argparse
import json
from pathlib import Path

import yaml

from mockdata import minor, vsl01, vsl02, vsl03
from mockdata.kbgen import build_kb
from mockdata.ledger import Ledger
from mockdata.render import assign_ids, render_all

ROOT = Path(__file__).resolve().parents[1]


def all_ledgers() -> list[Ledger]:
    return [vsl01.build(), vsl02.build(), vsl03.build(), *[f() for f in minor.ALL.values()]]


def fleet_names() -> dict[str, str]:
    fleet = yaml.safe_load((ROOT / "mockdata/fleet.yaml").read_text(encoding="utf-8"))
    return {v["code"]: v["name"] for v in fleet["vessels"]}


def build(out: Path, bodies: dict[str, str] | None = None) -> int:
    ledgers = all_ledgers()
    ids = assign_ids(ledgers)
    ev = [e for lg in ledgers for e in lg.events]
    build_kb(ledgers, out, {c for e in ev for c in [e.sender, *e.receivers]})
    texts = render_all(ledgers, fleet_names(), bodies)
    meta = {ids[e.id]: (e, lg.vessel) for lg in ledgers for e in lg.events}
    (out / "emails").mkdir(parents=True, exist_ok=True)
    for eid, text in texts.items():
        e, vessel = meta[eid]
        (out / "emails" / f"{eid}.json").write_text(json.dumps(
            {"email_id": eid, "text": text, "event_id": e.id, "vessel": vessel, "thread": e.thread, "scenario": e.scenario, "event_type": e.event_type},
            ensure_ascii=False, indent=1), encoding="utf-8")
    truths = [{"vessel": lg.vessel, "scenario": t.scenario, "question": t.question, "answer": t.answer, "evidence": [ids[x] for x in t.evidence]}
              for lg in ledgers for t in lg.truths]
    (out / "truths.json").write_text(json.dumps(truths, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(texts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "datasets" / "mock"))
    print(build(Path(ap.parse_args().out)), "emails written")
