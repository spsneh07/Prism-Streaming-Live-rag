"""Index build/load and the three retrieval modes (dense / bm25 / hybrid).

Dense search is an exact matrix product over L2-normalised embeddings. For a
corpus of a few thousand chunks this is faster than building an ANN index and
has no recall loss; swapping in FAISS only requires replacing ``_dense``.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.ingestion.loader import read_chunks
from app.models.schemas import Chunk, ScoredChunk
from app.retrieval.bm25 import BM25
from app.retrieval.embedder import Embedder
from app.retrieval.text import split_sentences


@dataclass
class Sentence:
    chunk_id: str
    text: str


def build_index(chunks: list[Chunk], embedder: Embedder, out_dir: Path, corpus_sha: str) -> dict:
    t0 = time.perf_counter()
    # Title + section heading are prepended for embedding only (not for display):
    # they carry topic words ("Cancellation", "Pune") that body text often omits.
    chunk_emb = embedder.encode([f"{c.source_title}. {c.section_title}. {c.text}" for c in chunks])
    sentences = [Sentence(c.chunk_id, s) for c in chunks for s in split_sentences(c.text)]
    sent_emb = embedder.encode([s.text for s in sentences])
    elapsed = time.perf_counter() - t0

    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "chunk_emb.npy", chunk_emb)
    np.save(out_dir / "sent_emb.npy", sent_emb)
    with (out_dir / "sentences.jsonl").open("w", encoding="utf-8") as fh:
        for s in sentences:
            fh.write(json.dumps({"chunk_id": s.chunk_id, "text": s.text}, ensure_ascii=False) + "\n")
    meta = {
        "embedding_model": embedder.model_name,
        "dim": embedder.dim,
        "num_chunks": len(chunks),
        "num_sentences": len(sentences),
        "corpus_sha256": corpus_sha,
        "embedding_seconds": round(elapsed, 3),
    }
    (out_dir / "index_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["index_bytes"] = sum(p.stat().st_size for p in out_dir.iterdir() if p.is_file())
    (out_dir / "index_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


class CorpusIndex:
    """In-memory hybrid index. Read-only after load, so safe to share across sessions."""

    def __init__(self, processed_dir: Path, embedder: Embedder, k1: float = 1.5, b: float = 0.75, rrf_k: int = 60):
        idx_dir = processed_dir / "index"
        if not (idx_dir / "chunk_emb.npy").exists():
            raise FileNotFoundError("index not built - run `python scripts/build_index.py` first")
        self.chunks = read_chunks(processed_dir)
        self.by_id = {c.chunk_id: c for c in self.chunks}
        self.meta = json.loads((idx_dir / "index_meta.json").read_text(encoding="utf-8"))
        if self.meta["embedding_model"] != embedder.model_name:
            raise ValueError("index was built with a different embedding model; rebuild it")
        self.chunk_emb = np.load(idx_dir / "chunk_emb.npy")
        self.sent_emb = np.load(idx_dir / "sent_emb.npy")
        with (idx_dir / "sentences.jsonl").open(encoding="utf-8") as fh:
            self.sentences = [Sentence(**json.loads(l)) for l in fh if l.strip()]
        self.sent_rows: dict[str, list[int]] = {}
        for i, s in enumerate(self.sentences):
            self.sent_rows.setdefault(s.chunk_id, []).append(i)
        self.embedder = embedder
        self.bm25 = BM25([f"{c.source_title} {c.section_title} {c.text}" for c in self.chunks], k1, b)
        self.rrf_k = rrf_k
        self._search_cache: dict[tuple, list[ScoredChunk]] = {}

    # -- primitive rankers ---------------------------------------------------
    def _dense(self, query: str) -> np.ndarray:
        return self.chunk_emb @ self.embedder.encode_one(query)

    def search(self, query: str, mode: str = "hybrid", k: int = 8) -> list[ScoredChunk]:
        """Memoised: provisional retrieval and the final decomposition often issue the
        same query. Copies are returned because callers annotate the results."""
        key = (query, mode, k)
        hit = self._search_cache.get(key)
        if hit is None:
            hit = self._search(query, mode, k)
            if len(self._search_cache) > 4096:
                self._search_cache.clear()
            self._search_cache[key] = hit
        return [ScoredChunk(c.chunk_id, c.score, dict(c.signals), list(c.sub_query_ids)) for c in hit]

    def clear_cache(self) -> None:
        self._search_cache.clear()

    def _search(self, query: str, mode: str, k: int) -> list[ScoredChunk]:
        if mode == "dense":
            s = self._dense(query)
            order = np.argsort(-s)[:k]
            return [ScoredChunk(self.chunks[i].chunk_id, float(s[i]), {"dense": float(s[i])}) for i in order]
        if mode == "bm25":
            s = self.bm25.scores(query)
            order = [i for i in np.argsort(-s)[:k] if s[i] > 0]
            return [ScoredChunk(self.chunks[i].chunk_id, float(s[i]), {"bm25": float(s[i])}) for i in order]
        if mode != "hybrid":
            raise ValueError(f"unknown retrieval mode {mode!r}")
        dense = self._dense(query)
        sparse = self.bm25.scores(query)
        d_rank = np.empty(len(dense), dtype=np.int64)
        d_rank[np.argsort(-dense)] = np.arange(1, len(dense) + 1)
        s_rank = np.empty(len(sparse), dtype=np.int64)
        s_rank[np.argsort(-sparse)] = np.arange(1, len(sparse) + 1)
        # Chunks with zero BM25 score get no sparse vote (they did not match at all).
        rrf = 1.0 / (self.rrf_k + d_rank) + np.where(sparse > 0, 1.0 / (self.rrf_k + s_rank), 0.0)
        order = np.argsort(-rrf)[:k]
        return [
            ScoredChunk(
                self.chunks[i].chunk_id,
                float(rrf[i]),
                {"dense": float(dense[i]), "bm25": float(sparse[i]), "dense_rank": int(d_rank[i]),
                 "bm25_rank": int(s_rank[i]) if sparse[i] > 0 else -1, "rrf": float(rrf[i])},
            )
            for i in order
        ]

    # -- helpers used by synthesis/grounding --------------------------------
    def sentences_of(self, chunk_id: str) -> list[tuple[str, np.ndarray]]:
        return [(self.sentences[i].text, self.sent_emb[i]) for i in self.sent_rows.get(chunk_id, [])]

    def dense_sim(self, query: str, chunk_id: str) -> float:
        i = self.chunks.index(self.by_id[chunk_id])
        return float(self.chunk_emb[i] @ self.embedder.encode_one(query))
