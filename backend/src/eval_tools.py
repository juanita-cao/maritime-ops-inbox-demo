"""Small pure helpers for the v7 eval scripts (scripts/eval_retrieval.py, eval_verifier.py,
feedback_to_golden.py), kept here so they have tests."""

import re


def recall_at(ranked: list[str], gold: set[str], k: int) -> float:
    return len(set(ranked[:k]) & gold) / len(gold) if gold else 0.0


def mrr(ranked: list[str], gold: set[str]) -> float:
    for i, eid in enumerate(ranked, 1):
        if eid in gold:
            return 1 / i
    return 0.0


def _squash(s: str) -> str:
    s = s.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def missing_quotes(cases: list[dict], texts: dict[str, str]) -> list[str]:
    """Verifier cases whose quote does not occur in the named email (the eval must not rest on a typo)."""
    bad = []
    for c in cases:
        body = _squash(texts.get(c["source_id"], ""))
        parts = [_squash(p) for p in re.split(r"\.{3}|…", c["quote"]) if _squash(p)]
        if not body or not all(p in body for p in parts):
            bad.append(c["id"])
    return bad


def feedback_candidates(records: list[dict], start: int = 1) -> list[dict]:
    """Thumbs-down records as golden-case drafts for the owner to review. The checks stay empty:
    the owner writes what a good answer must contain."""
    out = []
    for r in records:
        if r.get("thumbs") != "down":
            continue
        out.append({
            "id": f"FB-{start + len(out):03d}",
            "question": r["question"],
            "history": [{"role": t["role"], "text": t["text"]} for t in r.get("history", [])][-4:],
            "checks": {},
            "note": " | ".join(x for x in (r.get("tag"), r.get("comment")) if x),
            "answer_seen": {"text": r["answer"]["text"], "version": r["answer"].get("version"), "model": r["answer"].get("model")},
        })  # fmt: skip
    return out
