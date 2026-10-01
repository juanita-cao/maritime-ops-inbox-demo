"""Record the demo conversation the chat page opens on (datasets/<name>/demo_chat.json).

An external action: every question is a real chat call (router, reasoning, verifier). Nothing is sent
without --yes; the plan is printed first. The answers go through the same v7 route and output scan as
a live question, so what the page shows is what the assistant said.

  DATASET=mock python scripts/record_demo_chat.py                         # plan only
  DATASET=mock python scripts/record_demo_chat.py --yes --model hybrid    # real calls (model = a picker id)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from src import api  # noqa: E402
from src.settings import DATASET, DATASET_ROOT  # noqa: E402

QUESTIONS = {
    "mock": [
        "我还有哪些邮件没有看？",
        "VSL-01 能不能在这个航次内安排水下检查或清洗？",
        "VSL-02 在北海 ECA 烧的低硫油费用应该谁承担？",
        "VSL-05 的滞期费双方各自怎么算？",
        "VSL-09 能不能同意转租给 Altai Trade FZE？",
        "从天津到新加坡，航速 12 节要几天？",
    ],
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--yes", action="store_true")
    p.add_argument("--only", type=int, nargs="*", help="re-record only these question numbers (1-based); the others stay as recorded")
    p.add_argument("--model", default="hybrid", help="a chat picker id: hybrid, gpt-4o-mini or gpt-5.5")
    args = p.parse_args()
    questions = QUESTIONS.get(DATASET)
    if not questions:
        print(f"no demo questions for dataset {DATASET}")
        return 2
    print(f"dataset {DATASET}: {len(questions)} questions, model {args.model}, chat mode {api.settings.chat_llm_mode}")
    for q in questions:
        print(" -", q)
    if not args.yes:
        print("Nothing sent. Add --yes to record.")
        return 1
    if api.settings.chat_llm_mode != "live":
        print("CHAT_LLM_MODE is not live: set CHAT_LLM_MODE=live (and the key) in the environment.")
        return 2
    client = TestClient(api.app)
    path = DATASET_ROOT / "demo_chat.json"
    old = {i["question"]: i for i in json.loads(path.read_text(encoding="utf-8"))} if args.only and path.exists() else {}
    items = []
    for n, q in enumerate(questions, start=1):
        if args.only and n not in args.only and q in old:
            items.append(old[q])
            continue
        r = client.post("/api/chat/v7", json={"question": q, "history": [], "model": args.model})
        r.raise_for_status()
        items.append({"question": q, "answer": r.json(), "recorded_at": datetime.now(api.now().tzinfo).isoformat(timespec="seconds"), "model": args.model})
        print(f"recorded: {q[:30]}… ({r.json().get('execution_mode')})")
    (DATASET_ROOT / "demo_chat.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", DATASET_ROOT / "demo_chat.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
