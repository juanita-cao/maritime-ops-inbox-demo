"""Hybrid retrieval over the company's emails (docs/design_agent_e16_v7.md 5).

Keyword (BM25-style) and semantic (embedding) rankings over email chunks, fused with reciprocal
rank fusion, so a Chinese question finds the English email that answers it. Standard library only
(no numpy): the corpus is a few hundred chunks.

The vectors are built offline (scripts/build_index.py) and committed under data/index/. Chunks are
derived from the email text by code, so the index stores only a SHA-1 per chunk: at load a chunk
whose text changed (an email was fixed) simply has no vector and is found by keywords only.
"""

import hashlib
import json
import math
import re
from array import array
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

CHUNK_CHARS = 900
OVERLAP_CHARS = 150
RRF_K = 60
SEM_WEIGHT = 0.4  # weight of the semantic ranking in the fusion (keyword = 1); 0.4 gave the best hybrid recall in eval/retrieval_gold.json
POOL = 50  # how deep each ranking goes before fusion
BM25_K1, BM25_B = 1.5, 0.75
EMBED_MODEL = "text-embedding-3-small"
EMBED_PRICE = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}  # USD per million tokens
EMBED_BATCH = 64
SNIPPET = 320

_LATIN = re.compile(r"[a-z0-9]+(?:[./\-][a-z0-9]+)*")
_CJK_RUN = re.compile(r"[一-鿿]+")


@dataclass(frozen=True)
class Chunk:
    email_id: str
    part: str  # "body" (subject + new text) or "quoted" (the earlier messages of the thread)
    idx: int
    text: str

    @property
    def key(self) -> str:
        return f"{self.email_id}:{self.part}:{self.idx}"

    @property
    def sha(self) -> str:
        return hashlib.sha1(self.text.encode("utf-8")).hexdigest()


def chunk_text(text: str) -> list[str]:
    """Sliding windows of CHUNK_CHARS with OVERLAP_CHARS, cut at whitespace where possible."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_CHARS:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + CHUNK_CHARS // 2, end)
            end = cut if cut > 0 else end
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return [c for c in out if c]


def email_chunks(email_id: str, subject: str, new_text: str, quoted_text: str) -> list[Chunk]:
    chunks = [Chunk(email_id, "body", i, t) for i, t in enumerate(chunk_text(f"{subject}\n{new_text}"))]
    chunks += [Chunk(email_id, "quoted", i, t) for i, t in enumerate(chunk_text(quoted_text))]
    return chunks


def tokens(text: str) -> list[str]:
    """Latin words (keeping codes such as 1400nm, v202, e046, b/l) and CJK character bigrams."""
    lower = text.lower()
    out = _LATIN.findall(lower)
    for run in _CJK_RUN.findall(lower):
        out += [run[i : i + 2] for i in range(len(run) - 1)] if len(run) > 1 else [run]
    return out


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


# --- embeddings ---------------------------------------------------------------------------------

Embedder = Callable[[list[str]], list[list[float]]]


def openai_embedder(api_key: str, base_url: str, model: str = EMBED_MODEL) -> Embedder:
    """An external call (design 2 amendment): texts leave the system, so only E4-clean email text and
    the officer's already-scanned question may be passed in."""
    from openai import OpenAI  # imported here so tests and offline use never need it

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=3)

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = [t[:8000] for t in texts[i : i + EMBED_BATCH]]
            data = client.embeddings.create(model=model, input=batch).data
            out += [_normalise(list(d.embedding)) for d in sorted(data, key=lambda d: d.index)]
        return out

    return embed


# --- vector store (data/index/) -------------------------------------------------------------------


def save_vectors(path: Path, chunks: list[Chunk], vectors: list[list[float]], model: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    dim = len(vectors[0]) if vectors else 0
    flat = array("f")
    for v in vectors:
        flat.extend(v)
    with (path / "vectors.f32").open("wb") as f:
        flat.tofile(f)
    meta = {"model": model, "dim": dim, "chunks": [{"key": c.key, "sha": c.sha} for c in chunks]}
    (path / "meta.json").write_text(json.dumps(meta, indent=0), encoding="utf-8")


def load_vectors(path: Path) -> tuple[dict[str, tuple[str, list[float]]], str | None]:
    """key -> (sha, vector); empty when there is no index."""
    meta_file, bin_file = path / "meta.json", path / "vectors.f32"
    if not (meta_file.exists() and bin_file.exists()):
        return {}, None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    dim, rows = meta["dim"], meta["chunks"]
    flat = array("f")
    with bin_file.open("rb") as f:
        flat.fromfile(f, dim * len(rows))
    out = {}
    for i, row in enumerate(rows):
        out[row["key"]] = (row["sha"], list(flat[i * dim : (i + 1) * dim]))
    return out, meta["model"]


# --- the index ------------------------------------------------------------------------------------


@dataclass
class Hit:
    email_id: str
    score: float
    snippet: str
    via: str  # "hybrid" | "keyword" | "semantic"


class HybridIndex:
    def __init__(self, chunks: list[Chunk], vectors: dict[str, tuple[str, list[float]]] | None = None,
                 model: str | None = None):  # fmt: skip
        self.chunks = chunks
        self.model = model
        self.vec: dict[str, list[float]] = {}
        for c in chunks:
            stored = (vectors or {}).get(c.key)
            if stored and stored[0] == c.sha:
                self.vec[c.key] = stored[1]
        self.stale = len(chunks) - len(self.vec)  # chunks without a usable vector
        self._tf = [Counter(tokens(c.text)) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(chunks)) if chunks else 0.0
        df: Counter = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    @property
    def email_ids(self) -> set[str]:
        return {c.email_id for c in self.chunks}

    @classmethod
    def from_emails(cls, emails: Iterable[tuple[str, str, str, str]], index_dir: Path | None) -> "HybridIndex":
        """emails: (email_id, subject, new_text, quoted_text), E4-clean ones only."""
        chunks = [c for e in emails for c in email_chunks(*e)]
        vectors, model = load_vectors(index_dir) if index_dir else ({}, None)
        return cls(chunks, vectors, model)

    def keyword_scores(self, query: str) -> dict[int, float]:
        q = [t for t in dict.fromkeys(tokens(query)) if t in self._idf]
        scores: dict[int, float] = {}
        for i, tf in enumerate(self._tf):
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self._idf[t] * f * (BM25_K1 + 1) / (f + BM25_K1 * (1 - BM25_B + BM25_B * self._len[i] / (self._avg or 1)))
            if s > 0:
                scores[i] = s
        return scores

    def semantic_scores(self, qvec: list[float]) -> dict[int, float]:
        return {i: _dot(qvec, self.vec[c.key]) for i, c in enumerate(self.chunks) if c.key in self.vec}

    def search(self, query: str, qvec: list[float] | None = None, allowed: set[str] | None = None,
               limit: int = 8, sem_weight: float = 1.0) -> list[Hit]:  # fmt: skip
        """Rank emails: reciprocal-rank fusion of the keyword and semantic chunk rankings, filtered
        to `allowed` email ids; an email scores by its best chunk."""
        ok = {i for i, c in enumerate(self.chunks) if allowed is None or c.email_id in allowed}
        kw = self.keyword_scores(query)
        sem = self.semantic_scores(qvec) if qvec else {}
        fused: dict[int, float] = {}
        for ranking, weight in ((kw, 1.0), (sem, sem_weight)):
            ranked = sorted((i for i in ranking if i in ok), key=lambda i: -ranking[i])[:POOL]
            for rank, i in enumerate(ranked):
                fused[i] = fused.get(i, 0.0) + weight / (RRF_K + rank + 1)
        via = "hybrid" if kw and sem else "semantic" if sem else "keyword"
        best: dict[str, tuple[float, int]] = {}
        for i, score in fused.items():
            e = self.chunks[i].email_id
            if e not in best or (score, kw.get(i, 0.0)) > (best[e][0], kw.get(best[e][1], 0.0)):
                best[e] = (score, i)
        ranked_emails = sorted(best.items(), key=lambda kv: -kv[1][0])[:limit]
        return [Hit(e, score, _snippet(self.chunks[i].text, query), via) for e, (score, i) in ranked_emails]


def _snippet(text: str, query: str) -> str:
    flat = " ".join(text.split())
    for t in sorted(tokens(query), key=len, reverse=True):
        at = flat.lower().find(t)
        if at >= 0 and len(t) >= 3:
            return flat[max(0, at - 100) : at + SNIPPET - 100]
    return flat[:SNIPPET]


def estimate_embedding_cost(chunks: list[Chunk], usd_per_million: float = 0.02) -> tuple[int, float]:
    """(approximate tokens, USD) for embedding every chunk: about 4 characters a token."""
    tokens_ = sum(len(c.text) for c in chunks) // 4
    return tokens_, tokens_ * usd_per_million / 1_000_000
