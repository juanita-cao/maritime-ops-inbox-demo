# Maritime Operations Inbox: demo

An AI assistant for a ship operator's inbox. It reads operations emails (reports, charterer and agent mail, claims, hire and
port notices), proposes what to do next for a person to confirm, and answers questions in a chat that cites the emails it used.
**Every vessel, company, person, port call and email in this repository is invented.** The data is a generated fleet of ten ships
(`datasets/mock/`), built from a fact ledger by the generator in `mockdata/`.

What to look at: `docs/architecture.md` (the chat assistant: routing, evidence contract, verifier, operation guides),
`docs/mock_data.md` (how the demo fleet is made), `kb/playbooks/` (operation
guides), and `datasets/mock/eval/golden_e16.json` (questions with expected facts).

## Run it

```
pip install -r backend/requirements.txt
python -m mockdata.build && python -m mockdata.load    # recorded model answers: no key and no network needed
cd frontend && npm install && npm run build            # or `npm run dev`
scripts/run_local.sh mock                              # backend on :8000
```

Live chat answers need `LLM_API_KEY` and `LLM_MODEL` (an OpenAI key); without them the chat page still opens on a recorded
conversation. Add `?debug=1` to the page URL to see which model produced an answer.
