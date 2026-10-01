"""Evidence verifier (docs/design_agent_e16_v7.md 6).

Layer 1 (the code check that a quote really occurs in the record read) lives in e16_v7. This is
layer 2: for a quote that does exist, does it support the claim it is attached to? A fast model
answers one narrow question per claim. The verifier only flags; it never rewrites an answer.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from src import llm_client
from src.llm_client import LlmClient, LlmError

NODE = "E16_V7_VERIFY"
_VERDICTS = ("supports", "contradicts", "unrelated", "insufficient")
MAX_CLAIMS = 6

VERIFY_SYSTEM = """ROLE
You check whether one quoted passage supports one claim. You judge only the quote: never use your own knowledge, and never assume anything the quote does not say.

INPUTS
- question: what the officer asked
- claim: a statement an assistant made in its answer
- source_id: the record the quote was copied from
- language: the language the reason must be written in
- quote: the passage copied from that record

VERDICTS
- supports: the quote states the claim, or directly entails it. Quantities, parties, ports, dates and negations must match.
- contradicts: the quote says the opposite, or a different fact (another quantity, another party).
- unrelated: the quote is about something else and does not bear on the claim.
- insufficient: the quote is related but does not establish the claim. A claim stronger than its quote is insufficient: for example "the invoice is unpaid" from a message that only attaches a hire statement; "a CP clause makes the charterers liable" from a message that only quotes a complaint; "the port works at a berth" from a message that only mentions the port.

READING RULES
- The claim and the quote may be in different languages (a Chinese claim about an English email): compare meaning, never wording.
- "unrelated" only when the quote is about a different matter than the claim. If the quote contains the figures, parties or facts the claim states, the verdict is supports, even when the claim is short or labels the quote's matter in its own words.
- A claim that names or summarises something (for example "the documents required for the check", "the operator's calculation") is supported when the quote lists or gives it; do not ask for more detail than the claim itself contains.

OUTPUT CONTRACT
Return JSON only: {"verdict": "supports|contradicts|unrelated|insufficient", "reason": ""}
"reason" is one short sentence in the language named by "language" (zh = Chinese, en = English), whatever language the quote is in."""


class VerdictOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    verdict: Literal[_VERDICTS]  # type: ignore[valid-type]
    reason: str = ""


VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": list(_VERDICTS)}, "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}
llm_client.register_schema(NODE, "e16_v7_verify", VERDICT_SCHEMA)

# A payment-status or cross-check question is high-stakes even when the answer is short.
_HIGH_STAKES = re.compile(r"待付|未付|已付|付款|付清|到账|核对|是否一致|一致吗|unpaid|outstanding|paid|cross-?check|consistent|match", re.I)


WEAK_QUOTE_CHARS = 25


def weak_quote(claim: str, quote: str) -> bool:
    """A very short quote that lacks a number the claim states: it cannot carry the claim, and asking
    the verifier would only produce a false "contradicts" (design 7.1 section 7)."""
    nums = set(re.findall(r"\d+(?:\.\d+)?", claim))
    return len(quote.strip()) < WEAK_QUOTE_CHARS and bool(nums - set(re.findall(r"\d+(?:\.\d+)?", quote)))


def needs_verification(mode: str, size: str, question: str) -> bool:
    """L2 modes, detailed answers, and payment-status / cross-check questions (design 6)."""
    return mode in ("proposal_reasoning", "hybrid") or size == "detailed" or bool(_HIGH_STAKES.search(question))


def verify_claims(llm: LlmClient, key: str, question: str, items: list[tuple[str, str, str]], zh: bool = False) -> list[VerdictOut | None]:
    """items: (claim, source_id, quote). One call each, in parallel; None where a call failed
    (a failed verifier never blocks or changes an answer)."""
    items = items[:MAX_CLAIMS]

    def one(i: int) -> VerdictOut | None:
        claim, source_id, quote = items[i]
        user = json.dumps({"question": question, "claim": claim, "source_id": source_id, "quote": quote,
                           "language": "zh" if zh else "en"}, ensure_ascii=False)
        try:
            return VerdictOut.model_validate(llm.complete_json(NODE, f"{key}-v{i}", VERIFY_SYSTEM, user))
        except (LlmError, ValidationError, AttributeError, TypeError):
            return None

    if not items:
        return []
    with ThreadPoolExecutor(len(items)) as pool:
        return list(pool.map(one, range(len(items))))
