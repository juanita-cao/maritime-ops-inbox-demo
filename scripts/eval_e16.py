"""E16 golden eval (docs/design_agent_e16_v6.md 3): run eval/golden_e16.json against a chat version
and a model, score every case with code checks, and report pass rate, latency, tokens and cost.

Free by default: answers replay from eval/recordings/<version>/<model>/ (made by an earlier live
run), so code-only changes re-score at no cost. --live makes real calls: it prints an estimate
and stops unless --yes is also given.

Run from the repository root:
  conda run -n somr python scripts/eval_e16.py --version v6 --model gpt-4o-mini            # replay
  conda run -n somr python scripts/eval_e16.py --version v6 --model gpt-5.5 --effort low --live --yes
  conda run -n somr python scripts/eval_e16.py --version v6 --model gpt-5.5 --cases R18,F1-too-long --live --yes
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src import api, e16_v5, e16_v6, e16_v7, retrieval  # noqa: E402
from src.llm_client import LiveLlm, RecordedLlm  # noqa: E402
from src.schemas import ChatRequest, ChatTurn  # noqa: E402
from src.settings import DATASET_ROOT  # noqa: E402
from src.store import Store  # noqa: E402

GOLDEN = DATASET_ROOT / "eval" / "golden_e16.json"  # DATASET=mock reads datasets/mock/eval/
RECORDINGS = DATASET_ROOT / "eval" / "recordings"
RESULTS = DATASET_ROOT / "eval" / "results"
# USD per 1M tokens (input, output). None = not known here: fill in from the provider's price page.
PRICES: dict[str, tuple[float, float] | None] = {
    "gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00), "gpt-4.1-mini": (0.40, 1.60), "gpt-4.1-nano": (0.10, 0.40),
    "o4-mini": (1.10, 4.40), "o3": (2.00, 8.00),
    "gpt-5": (1.25, 10.00), "gpt-5-mini": (0.25, 2.00), "gpt-5-nano": (0.05, 0.40),
    "gpt-5.4": None, "gpt-5.4-mini": None, "gpt-5.5": None,
}  # fmt: skip
EST_TOKENS_PER_CASE = (30_000, 1_500)  # from the v5.1 runs: ~30k input, ~1.5k output per question


def cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    price = PRICES.get(model)
    return None if price is None else (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


def check(case: dict, answer, version: str = "v6") -> list[str]:
    """Every failed check, as a short reason; [] = pass."""
    c, text, fails = case["checks"], answer.text, []
    lines = [ln for ln in text.split("\n") if ln.strip()]
    for s in c.get("contains", []):
        if s not in text:
            fails.append(f"missing '{s}'")
    for group in c.get("contains_any", []):
        if not any(s in text for s in group):
            fails.append(f"none of {group}")
    for s in c.get("not_contains", []):
        if s in text:
            fails.append(f"contains '{s}'")
    ids = {s.id for s in answer.sources}
    for i in c.get("cites", []):
        if i not in ids and i not in text:
            fails.append(f"does not cite {i}")
    if "max_lines" in c and len(lines) > c["max_lines"]:
        fails.append(f"{len(lines)} lines > {c['max_lines']}")
    if "mode" in c and answer.execution_mode not in c["mode"]:
        fails.append(f"mode {answer.execution_mode} not in {c['mode']}")
    if answer.execution_mode in c.get("not_mode", []):
        fails.append(f"mode {answer.execution_mode}")
    if c.get("has_draft") and not answer.draft:
        fails.append("no draft")
    if c.get("shorter_than_previous") and len(text) >= len(case["history"][-1]["text"]):
        fails.append("not shorter than the previous answer")
    if answer.llm_status == "failed":
        fails.append("llm_status failed")
    # every shown part must be free of identity / contact data (the v7 output scan, checked for all versions)
    for part in (answer.text, answer.details, answer.draft):
        if part and e16_v7.scrub(part)[1]:
            fails.append("output contains identity or contact data")
            break
    if version == "v7" and "playbook" in c and not (answer.playbook and answer.playbook.id == c["playbook"]):
        fails.append(f"playbook is {answer.playbook.id if answer.playbook else None}, wanted {c['playbook']}")
    if version == "v7" and len(answer.steps) < c.get("steps_min", 0):
        fails.append(f"{len(answer.steps)} playbook step(s) < {c['steps_min']}")
    if version == "v7" and any(s not in (answer.draft or "") for s in c.get("draft_contains", [])):
        fails.append(f"draft lacks one of {c['draft_contains']}")
    if version == "v7" and "min_verified_evidence" in c:
        verified = sum(1 for e in answer.evidence if e.status == "verified")
        if verified < c["min_verified_evidence"]:
            fails.append(f"{verified} verified evidence quote(s) < {c['min_verified_evidence']}")
    return fails


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--version", choices=["v5.1", "v6", "v7"], default="v6")
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--effort", choices=["none", "minimal", "low", "medium", "high"], help="reasoning models only")
    p.add_argument("--router-model", help="v6: run the router on another (fast) model")
    p.add_argument("--fast-model", help="v6: router, deterministic wording and follow-ups on this model")
    p.add_argument("--cases", help="comma-separated case ids (default: all)")
    p.add_argument("--db", default=str(api.state.db_path))
    p.add_argument("--live", action="store_true", help="real calls (costs money)")
    p.add_argument("--yes", action="store_true", help="confirm a live run")
    args = p.parse_args()

    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    tag = args.model + (f"@{args.effort}" if args.effort else "") + (f"+router-{args.router_model}" if args.router_model else "") \
        + (f"+fast-{args.fast_model}" if args.fast_model else "")
    folder = RECORDINGS / args.version / tag

    if args.live and not args.yes:
        est_in, est_out = (len(cases) * n for n in EST_TOKENS_PER_CASE)
        usd = cost(args.model, est_in, est_out)
        print(f"Live run: {len(cases)} cases × {args.version} × {tag}")
        print(f"Estimate: ~{est_in:,} input + ~{est_out:,} output tokens"
              + (f" ≈ US${usd:.2f}" if usd is not None else " (price not in PRICES — check the provider's page)"))
        print("Add --yes to run it.")
        return 1

    def client(model: str, sub: Path, effort: str | None = None):
        if not args.live:
            return RecordedLlm(sub)
        settings = api.settings.model_copy(update={"llm_mode": "live", "llm_model": model})
        return LiveLlm(settings, folder=sub, reasoning_effort=effort)

    llm = client(args.model, folder, args.effort)
    router = client(args.router_model, folder / "router") if args.router_model else None
    fast = client(args.fast_model, folder / "fast") if args.fast_model else None
    usages = [(folder / "usage.jsonl", args.model), (folder / "fast" / "usage.jsonl", args.fast_model),
              (folder / "router" / "usage.jsonl", args.router_model)]
    before = {u: len(u.read_text().splitlines()) if u.exists() else 0 for u, _ in usages}

    store = Store.open(Path(args.db))
    kb = api.kb
    at = api.now()
    context = api.build_chat_context(store, at)

    backend = None
    if args.version == "v7":
        os.environ.setdefault("E16_INCLUDE_DRAFT_PLAYBOOKS", "1")  # the owner's review runs use the draft playbooks
        key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        embedder = retrieval.openai_embedder(key, api.settings.llm_base_url) if args.live and key else None
        backend = e16_v7.RetrievalBackend(DATASET_ROOT / "data" / "index", embedder)

    def run_tool(name: str, a: dict):
        if backend is not None:
            return e16_v7.run_tool_v7(name, a, store, kb, backend)
        return e16_v5.run_tool_v5(name, a, store, kb)

    rows, latencies = [], []
    for case in cases:
        req = ChatRequest(question=case["question"], history=[ChatTurn(**h) for h in case.get("history", [])])
        t0 = time.perf_counter()
        if args.version == "v7":
            answer = e16_v7.e16v7_answer_chat(req, context, llm, at, run_tool, kb.taxonomy.get("event_types", []),
                                              router_llm=router, fast_llm=fast, playbooks=api.PLAYBOOKS)  # fmt: skip
        elif args.version == "v6":
            answer = e16_v6.e16v6_answer_chat(req, context, llm, at, run_tool, kb.taxonomy.get("event_types", []),
                                              router_llm=router, fast_llm=fast)  # fmt: skip
        else:
            answer = e16_v5.e16v5_answer_chat(req, context, llm, at, run_tool, kb.taxonomy.get("event_types", []),
                                              revision="5.1")  # fmt: skip
        seconds = time.perf_counter() - t0
        latencies.append(seconds)
        fails = check(case, answer, args.version)
        rows.append({"id": case["id"], "pass": not fails, "fails": fails, "seconds": round(seconds, 1),
                     "mode": answer.execution_mode, "text": answer.text, "details": answer.details,
                     "draft": answer.draft, "sources": [s.id for s in answer.sources],
                     "trace": answer.reasoning_trace,
                     "evidence": [e.model_dump() for e in answer.evidence]})  # fmt: skip
        print(f"{'PASS' if not fails else 'FAIL'} {case['id']:<16} {seconds:5.1f}s  {'; '.join(fails)}", flush=True)
    store.close()

    t_in = t_out = 0
    usd: float | None = 0.0
    for u, model in usages:
        if not u.exists() or not model:
            continue
        new = [json.loads(ln) for ln in u.read_text().splitlines()[before[u]:]]
        i, o = sum(r.get("input_tokens") or 0 for r in new), sum(r.get("output_tokens") or 0 for r in new)
        t_in, t_out = t_in + i, t_out + o
        c = cost(model, i, o)
        usd = None if usd is None or c is None else usd + c
    if not args.live:
        usd = 0.0
    passed = sum(r["pass"] for r in rows)
    p90 = sorted(latencies)[max(0, int(len(latencies) * 0.9) - 1)] if latencies else 0
    summary = {"time": datetime.now().isoformat(timespec="seconds"), "version": args.version, "model": tag,
               "mode": "live" if args.live else "replay", "passed": passed, "total": len(rows),
               "avg_seconds": round(statistics.mean(latencies), 1) if latencies else 0, "p90_seconds": round(p90, 1),
               "input_tokens": t_in, "output_tokens": t_out, "usd": None if usd is None else round(usd, 3)}  # fmt: skip
    print(f"\n{passed}/{len(rows)} passed · avg {summary['avg_seconds']}s · p90 {summary['p90_seconds']}s · "
          f"{t_in:,} in / {t_out:,} out tokens · " + ("price unknown" if usd is None else f"US${usd:.3f}"))

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS / f"{stamp}_{args.version}_{tag}.json").write_text(
        json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    table = RESULTS / "summary.csv"
    new_file = not table.exists()
    with table.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary))
        if new_file:
            w.writeheader()
        w.writerow(summary)
    return 0 if passed == len(rows) else 2


if __name__ == "__main__":
    sys.exit(main())
