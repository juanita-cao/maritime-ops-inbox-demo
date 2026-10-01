from src import eval_tools as t


def test_recall_and_mrr():
    assert t.recall_at(["E1", "E2", "E3"], {"E2", "E9"}, 2) == 0.5 and t.recall_at(["E1"], set(), 5) == 0.0
    assert t.mrr(["E1", "E2", "E3"], {"E3", "E2"}) == 0.5 and t.mrr(["E1"], {"E9"}) == 0.0


def test_missing_quotes_are_found_by_squashed_text_and_ellipsis():
    cases = [{"id": "G1", "source_id": "E1", "quote": "hire  statement ... bank confirmation"},
             {"id": "B1", "source_id": "E1", "quote": "invoice was paid"}, {"id": "B2", "source_id": "E9", "quote": "x"}]  # fmt: skip
    assert t.missing_quotes(cases, {"E1": "Please find the hire statement\nwith bank confirmation."}) == ["B1", "B2"]


def test_only_thumbs_down_become_candidates_with_empty_checks():
    recs = [{"thumbs": "up", "question": "a", "answer": {"text": "x"}},
            {"thumbs": "down", "question": "太长了吗", "tag": "too_long", "comment": "废话多",
             "history": [{"role": "user", "text": "q"}, {"role": "assistant", "text": "a"}],
             "answer": {"text": "长答案", "version": "v7", "model": "gpt-4o-mini"}}]  # fmt: skip
    got = t.feedback_candidates(recs, start=7)
    assert got == [{"id": "FB-007", "question": "太长了吗", "history": [{"role": "user", "text": "q"}, {"role": "assistant", "text": "a"}],
                    "checks": {}, "note": "too_long | 废话多", "answer_seen": {"text": "长答案", "version": "v7", "model": "gpt-4o-mini"}}]  # fmt: skip
