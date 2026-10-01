# The demo fleet

Everything in `datasets/mock/` is generated and fictional: ten dry-bulk vessels (VSL-01 … VSL-10) run by one operator,
with invented owners, charterers, agents, surveyors, correspondents, ports of call and cargoes (bauxite, iron ore, coal,
grain, fertiliser, salt, limestone, wood chips, clinker). About 170 emails, dated up to 12 Oct 2026 (the app's clock for this dataset).

| Depth | Vessels | Content |
|---|---|---|
| Deep | 3 | three voyages each, long threads, 3–4 disputes or procedures per vessel |
| Medium | 3 | two voyages, one open issue |
| Light | 4 | one voyage, routine mail and one small matter |

## Scenarios

Underwater inspection or cleaning window · B/L, mate's receipt and letter of indemnity quantities that disagree · ECA fuel
cost under a silent charter party · hire statement with a disputed off-hire deduction · redelivery notice and bunkers on
redelivery · cash to master and a corrected port invoice · P&I letter about cargo wetting · speed and consumption
performance claim · demurrage with different rain-stoppage figures · rejected holds and re-cleaning time · main-engine stoppage
and off-hire · port state control detention · bunker quality at the sulphur limit · port congestion · crew medical case ·
sub-charterer screening · fixture enquiry to recap · cargo shortage claim and time bar.

## How it is made (`mockdata/`)

1. **Fact ledger** (`vsl01.py` … `minor.py`): one Python module per vessel writes parties, voyages and a timeline of events.
   Every number appears once; each scenario also states its *ground truth* (the correct answer and the events that prove it).
2. **Validator** (`ledger.py`): refuses a ledger with a number that changes without a scenario saying so, a reply that
   is earlier than its parent, an ETA before sailing, an unknown party, or a mailbox outside the reserved `.example` domain.
3. **Renderer** (`render.py`): turns each event into an email in the layout the parser reads: header, body, signature and quoted
   history. Noon, sailing and arrival reports use the fixed form the report reader understands; other mail is a plain statement
   of the event, which a model can later rewrite in a human voice while code checks that no figure changed.
4. **Knowledge base** (`kbgen.py`), **golden questions** (`golden.py`) and the pipeline run (`load.py`) are derived from the same ledger.

```
python -m mockdata.build     # emails, knowledge base, truths
python -m mockdata.golden    # golden questions
python -m mockdata.load      # run the pipeline (recorded model answers; `--live` records new ones)
```
