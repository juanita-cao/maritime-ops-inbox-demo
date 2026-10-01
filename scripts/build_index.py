"""Build the semantic index for hybrid retrieval (docs/design_agent_e16_v7.md 5.1).

An external call: the text of every E4-clean email is sent to the embeddings API once. Nothing is
sent without --yes; the estimate is printed first. Re-run it after any email text changes (the
service checks a SHA-1 per chunk and falls back to keywords for a changed one).

  conda run -n somr python scripts/build_index.py            # estimate only, no call
  conda run -n somr python scripts/build_index.py --yes      # real call, writes data/index/
  conda run -n somr python scripts/build_index.py --check    # offline: chunks and how many have a usable vector

DATASET=mock builds the index of the mock dataset (datasets/mock/data/index/).
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src import api, e_nodes, retrieval  # noqa: E402
from src.settings import DATASET_ROOT  # noqa: E402
from src.store import Store  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(api.state.db_path))
    p.add_argument("--out", default=str(DATASET_ROOT / "data" / "index"))
    p.add_argument("--model", default=retrieval.EMBED_MODEL, help="embedding model (an experiment: write it to its own --out folder)")
    p.add_argument("--yes", action="store_true", help="make the real embeddings call")
    p.add_argument("--check", action="store_true", help="offline: report coverage of the existing index")
    args = p.parse_args()

    store = Store.open(Path(args.db))
    rows = []
    for eid in sorted(store.email_ids()):
        email = store.get_email(eid)
        if email is not None and e_nodes.chat_email_view(email, api.kb) is not None:  # the E4 gate
            rows.append((eid, email.subject, email.new_text, email.quoted_text))
    store.close()
    out = Path(args.out)
    chunks = [c for e in rows for c in retrieval.email_chunks(*e)]

    if args.check:
        idx = retrieval.HybridIndex.from_emails(rows, out)
        print(f"{len(rows)} emails, {len(chunks)} chunks, {len(chunks) - idx.stale} with a usable vector, {idx.stale} without (model {idx.model})")
        return 0

    tokens, usd = retrieval.estimate_embedding_cost(chunks, retrieval.EMBED_PRICE.get(args.model, 0.13))
    print(f"{len(rows)} E4-clean emails -> {len(chunks)} chunks, about {tokens:,} tokens, about US${usd:.4f} with {args.model}")
    if not args.yes:
        print("Nothing sent. Add --yes to build the index.")
        return 1
    key = api.os.getenv("LLM_API_KEY") or api.os.getenv("OPENAI_API_KEY")
    if not key:
        print("No LLM_API_KEY in the environment.")
        return 2
    vectors = retrieval.openai_embedder(key, api.settings.llm_base_url, args.model)([c.text for c in chunks])
    retrieval.save_vectors(out, chunks, vectors, args.model)
    print(f"Wrote {len(chunks)} vectors to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
