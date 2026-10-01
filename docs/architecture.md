# Architecture of the chat assistant

The assistant answers an operator's questions about a fleet from the fleet's own emails, and says where each statement
comes from. Its design rule is that **code decides what a model may not**: routing guards, arithmetic, quoting and the
output scan are code; the model reads, reasons and words.

## The path of a question

1. **Input scan.** A question that contains an e-mail address, a phone number, an identity number or a street address is refused.
2. **Reference answers in code.** A passage-time question naming two ports of `kb/distances.csv` and a speed is answered
   from the table and by arithmetic: no model call, the same answer every time, with the source and the date of the lookup.
3. **Router** (small model, three samples, majority vote). Chooses an *execution mode*: `deterministic` (queries over the
   operational data, rendered in code), `evidence_reasoning` (read and cross-check emails), `proposal_reasoning` (a
   recommendation a person must review), `domain_knowledge`, `hybrid`, `follow_up`, `out_of_scope`. Code guards correct
   known router mistakes. It may also select an **operation guide** (below).
4. **Retrieval.** Hybrid: keyword ranking and embeddings over email chunks, fused by reciprocal rank. The model reads
   emails through tools; a report-field question (wind, speed, consumption, draft) is answered from fields extracted by code.
5. **Reasoning** (stronger model, only for the modes that need it). Strict structured output: an answer, the *evidence*
   (claim + a verbatim quote + the record it came from), a proposal where the mode allows one, and the steps of the guide.
6. **Checks in code.** Every quote must occur in the text actually read; every number and id in the answer must occur in
   something the model was given; passage times are computed, not stated; emails about another vessel are dropped from the sources.
7. **Verifier** (small model, only for proposals, long answers and payment or cross-check questions). For each quoted claim:
   supports / contradicts / unrelated / insufficient. It **flags, it never rewrites**.
8. **Output scan.** Anything the input scan would refuse is replaced by `[hidden]` before the answer leaves.

## What the user sees

The conclusion first, short; the basis behind "Show basis"; claims as numbered citations `[1]`, `[2]` that open the email with
the quoted passage marked; one reference list; recommendations labelled as proposals for review; drafts that are never sent.
Nothing is saved until a person confirms it in the review flow, which is the only write path (the chat reuses the same
confirm call as the Email page; conflicts are decided by the backend).

## Operation guides

`kb/playbooks/*.md`: an operator's procedure for a kind of question (arrange an underwater inspection or cleaning, cross-check
cargo documents, allocate a cost, find the next hire due, a port-arrival checklist). A guide has steps; the answer reports each
step as done, missing or not applicable, and a step counts as done only if the evidence was actually read.

## The demo data

`datasets/mock/` is a generated fleet: a fact ledger (`mockdata/`) holds every number once; emails, the knowledge base, labels
and the golden questions are derived from it, so the expected answers are known by construction. See `docs/design_mock_data.md`.

## Tests and evaluation

`backend/tests/` (unit tests of the layers), `datasets/mock/eval/golden_e16.json` (questions with expected facts, run by
`scripts/eval_e16.py`). Model calls are recorded and replayed, so the suite runs offline.
