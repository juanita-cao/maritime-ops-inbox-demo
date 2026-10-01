"""Run the mock emails through the pipeline in time order into datasets/mock/data/app.sqlite.

  python -m mockdata.load            recorded answers only (needs datasets/mock/data/llm_recordings)
  python -m mockdata.load --live     real model calls for E5, E6, E7 (external action: the owner approves the cost first);
                                     every answer is saved as a recording, so the next run is free

Prints counts only. The model comes from .env (LLM_MODEL, LLM_BASE_URL)."""

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

os.environ["DATASET"] = "mock"  # before src.settings is imported
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("LLM_MODE", "recorded")

from src import e_nodes as e  # noqa: E402
from src import pipeline as pl  # noqa: E402
from src.kb_loader import load_kb, own_domains  # noqa: E402
from src.llm_client import LiveLlm, RecordedLlm  # noqa: E402
from src.schemas import RawEmail  # noqa: E402
from src.settings import DATASET_ROOT, load_settings  # noqa: E402
from src.store import Store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--db", default=str(DATASET_ROOT / "data" / "app.sqlite"))
    args = ap.parse_args()
    import json

    settings, kb = load_settings(), load_kb(DATASET_ROOT / "kb")
    llm = LiveLlm(settings) if args.live else RecordedLlm()
    raws = [RawEmail(email_id=d["email_id"], text=d["text"]) for d in (json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATASET_ROOT / "emails").glob("E*.json")))]
    parsed = {r.email_id: e.e1_parse_email(r, own_domains(kb), settings.default_utc_offset) for r in raws}
    order = sorted(raws, key=lambda r: (parsed[r.email_id].sent_time, r.email_id))
    path = Path(args.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    store = Store.open(path)
    count: Counter = Counter()
    for raw in order:
        result = pl.run_email(raw, store, kb, llm, parsed[raw.email_id].sent_time, settings.default_utc_offset)
        count[f"saved {result.saved.status}"] += 1
        if result.proposal:
            count[f"task {result.proposal.task.kind}"] += 1
            count[f"lane {result.proposal.lane.lane}"] += 1
        if result.applied:
            count[f"auto {result.applied.status}"] += 1
    store.close()
    for key in sorted(count):
        print(f"{count[key]:>4} {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
