"""Run the mock emails through the pipeline in time order into datasets/mock/data/app.sqlite.

  python -m mockdata.load            recorded answers only (needs datasets/mock/data/llm_recordings)
  python -m mockdata.load --leave-open 50   (default) the officer has already confirmed the oldest proposals, so the other pages
                                     (Overview, Vessel, Action) have data; the newest 50 stay to review. 0 confirms none.
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

from datetime import timedelta  # noqa: E402

from src import e_apply  # noqa: E402
from src import e_nodes as e  # noqa: E402
from src import pipeline as pl  # noqa: E402
from src.kb_loader import load_kb, own_domains  # noqa: E402
from src.llm_client import LiveLlm, RecordedLlm  # noqa: E402
from src.schemas import Decision, RawEmail  # noqa: E402
from src.settings import DATASET_ROOT, load_settings  # noqa: E402
from src.store import Store  # noqa: E402


def ingest(order, parsed, kb, settings, llm, path: Path, confirm_ids: set[str]) -> Counter:
    """Run the emails in time order into a fresh database; the officer approves the proposals of `confirm_ids` right after each
    is made (so a later email sees the task the earlier one created and proposes an update, as in real use)."""
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
        if raw.email_id in confirm_ids and result.saved.status == "open":
            decision = Decision(kind="approve", actor="officer", decided_at=parsed[raw.email_id].sent_time + timedelta(hours=3),
                                reason="Confirmed in the demo data (history)")
            try:
                applied = e_apply.e11_apply_changes(result.saved.proposal_id, decision, store)
                count[f"confirmed {applied.status}"] += 1
            except e_apply.InvalidDecision:
                count["confirmed refused"] += 1
    store.close()
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--leave-open", type=int, default=50, help="proposals left to review (the newest); the older ones are confirmed")
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
    if args.leave_open > 0:
        # pass 1 (nothing confirmed) tells which emails need a review; the oldest of them are confirmed in pass 2
        scratch = path.with_name("scratch.sqlite")
        ingest(order, parsed, kb, settings, llm, scratch, set())
        store = Store.open(scratch)
        open_ids = [r["email_id"] for r in store.proposal_rows(("open",))]
        store.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(scratch) + suffix).unlink(missing_ok=True)
        by_time = sorted(open_ids, key=lambda i: (parsed[i].sent_time, i))
        want = max(0, len(by_time) - args.leave_open)
        count = ingest(order, parsed, kb, settings, llm, path, set(by_time[:want]))
        # a proposal can conflict with an earlier confirmed task of the same key: confirm a few more of the oldest until the target is met
        for _ in range(5):
            left = len(by_time) - count["confirmed applied"]
            if left <= args.leave_open:
                break
            want += left - args.leave_open
            count = ingest(order, parsed, kb, settings, llm, path, set(by_time[:want]))
    else:
        count = ingest(order, parsed, kb, settings, llm, path, set())
    for key in sorted(count):
        print(f"{count[key]:>4} {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
