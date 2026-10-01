"""Hybrid retrieval (docs/design_agent_e16_v7.md 5): chunks, keyword score, semantic score, fusion,
the vector store, and staleness. The embedder is a fake: concept words map to fixed dimensions, so
a Chinese query and an English email can be close without any network."""

from src import retrieval as r

CONCEPTS = [("berth", "anchorage", "码头", "锚地"), ("crane", "gear", "吊"), ("invoice", "hire", "发票", "租金"),
            ("distance", "nm", "海里", "距离")]  # fmt: skip


def fake_embed(texts: list[str]) -> list[list[float]]:
    out = []
    for t in texts:
        low = t.lower()
        out.append(r._normalise([10.0 if any(w in low for w in words) else 0.0 for words in CONCEPTS] + [0.01]))
    return out


EMAILS = [
    ("E046", "M/V VSL-02//ROB", "ROB calculation. Arrival Discharge Port Distance 1400nm including 80nm ECA. Stay in berth 2 days.", ""),
    ("E051", "M/V VSL-02//CTM - NEWCASTLE", "Thanks for your kind support, handling fee USD400 base on CTM USD80000.", ""),
    ("E060", "MV VSL-01 / CPY-02 30TH HIRE", "Please find attached the hire statement with bank confirmation.", ""),
    ("E049", "M/V VSL-02 DAILY REPORT", "Daily running hours of ship crane numbers: NO.1(7H) NO.2(3H). Weather Cloudy.", "earlier mail"),
]


def vectors_for(chunks):
    return {c.key: (c.sha, v) for c, v in zip(chunks, fake_embed([c.text for c in chunks]), strict=True)}


def test_chunking_is_deterministic_overlapping_and_cut_at_whitespace():
    text = " ".join(f"word{i}" for i in range(400))  # ~2.7k chars
    chunks = r.chunk_text(text)
    assert len(chunks) >= 3 and chunks == r.chunk_text(text)
    assert all(len(c) <= r.CHUNK_CHARS for c in chunks)
    assert chunks[0].split()[-1] in chunks[1]  # the overlap repeats the end of the previous chunk
    assert r.chunk_text("   ") == [] and r.chunk_text("short") == ["short"]


def test_email_chunks_separate_the_body_from_the_quoted_thread():
    chunks = r.email_chunks("E1", "Subject", "new text", "quoted history")
    assert [(c.part, c.idx) for c in chunks] == [("body", 0), ("quoted", 0)]
    assert chunks[0].text.startswith("Subject\n") and chunks[0].key == "E1:body:0"


def test_tokens_keep_codes_and_make_cjk_bigrams():
    t = r.tokens("Distance 1400nm, B/L v202 E046 码头还是锚地")
    assert {"distance", "1400nm", "b/l", "v202", "e046", "码头", "头还", "锚地"} <= set(t)


def test_keyword_score_ranks_the_email_with_the_exact_terms_first():
    idx = r.HybridIndex.from_emails(EMAILS, None)
    hits = idx.search("1400nm distance", None)
    assert hits[0].email_id == "E046" and hits[0].via == "keyword"
    assert "1400nm" in hits[0].snippet


def test_a_chinese_question_finds_the_english_email_only_through_the_semantic_side():
    chunks = [c for e in EMAILS for c in r.email_chunks(*e)]
    idx = r.HybridIndex(chunks, vectors_for(chunks), "fake")
    assert idx.search("码头还是锚地", None) == []  # no shared tokens: keyword search finds nothing
    hits = idx.search("码头还是锚地", fake_embed(["码头还是锚地"])[0])
    assert hits[0].email_id == "E046" and hits[0].via == "semantic"


def test_fusion_combines_both_rankings_and_respects_the_allowed_set():
    chunks = [c for e in EMAILS for c in r.email_chunks(*e)]
    idx = r.HybridIndex(chunks, vectors_for(chunks), "fake")
    q = "crane 吊 running hours"
    hits = idx.search(q, fake_embed([q])[0])
    assert hits[0].email_id == "E049" and hits[0].via == "hybrid"
    only = idx.search(q, fake_embed([q])[0], allowed={"E051"})
    assert {h.email_id for h in only} == {"E051"}
    assert len(idx.search(q, fake_embed([q])[0], limit=2)) == 2


def test_vectors_round_trip_and_a_changed_chunk_loses_its_vector(tmp_path):
    chunks = [c for e in EMAILS for c in r.email_chunks(*e)]
    r.save_vectors(tmp_path, chunks, fake_embed([c.text for c in chunks]), "fake")
    loaded, model = r.load_vectors(tmp_path)
    assert model == "fake" and set(loaded) == {c.key for c in chunks}
    idx = r.HybridIndex.from_emails(EMAILS, tmp_path)
    assert idx.stale == 0 and idx.model == "fake"
    changed = [(e, s, t + " (fixed)" if e == "E060" else t, q) for e, s, t, q in EMAILS]
    stale = r.HybridIndex.from_emails(changed, tmp_path)
    assert stale.stale == 1 and "E060:body:0" not in stale.vec  # found by keywords only
    assert stale.search("hire statement", None)[0].email_id == "E060"


def test_no_index_means_keyword_only_and_the_cost_estimate_is_tiny():
    idx = r.HybridIndex.from_emails(EMAILS, None)
    assert idx.vec == {} and idx.stale == len(idx.chunks)
    tokens_, usd = r.estimate_embedding_cost(idx.chunks)
    assert tokens_ > 0 and usd < 0.001
