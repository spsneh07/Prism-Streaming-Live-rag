"""Async retrieval service: parallel per-sub-query retrieval + rerank with timings."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.models.schemas import ScoredChunk, SubQuery
from app.reranking.rerankers import Reranker
from app.retrieval.constraints import promote, quantity_constraints
from app.retrieval.index import CorpusIndex


@dataclass
class RetrievalResult:
    sub_query: SubQuery
    candidates: list[ScoredChunk]
    started_at: float
    finished_at: float
    retrieval_ms: float
    rerank_ms: float
    mode: str
    reranker: str
    top_scores: list[float] = field(default_factory=list)
    facet_dropped: list[str] = field(default_factory=list)
    constraint_promoted: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "sub_query_id": self.sub_query.id,
            "query": self.sub_query.text,
            "mode": self.mode,
            "reranker": self.reranker,
            "retrieval_ms": round(self.retrieval_ms, 2),
            "rerank_ms": round(self.rerank_ms, 2),
            "num_candidates": len(self.candidates),
            "top_chunks": [c.chunk_id for c in self.candidates[:3]],
            "top_scores": [round(s, 3) for s in self.top_scores[:3]],
            "facet_dropped": self.facet_dropped,
            "constraint_promoted": self.constraint_promoted,
        }


class RetrievalService:
    def __init__(self, index: CorpusIndex, reranker: Reranker, top_k: int = 8, facet_filter=None,
                 quantity_constraints: bool = False):
        self.index = index
        self.quantity_constraints = quantity_constraints
        self.reranker = reranker
        self.top_k = top_k
        self.facet_filter = facet_filter
        # Title + heading give the reranker context the body lacks ("Koregaon Park Hall" is in Pune
        # only according to the document title).
        self._texts = {c.chunk_id: f"{c.source_title} - {c.section_title}. {c.text}" for c in index.chunks}

    def retrieve_sync(self, sq: SubQuery, mode: str = "hybrid", rerank: bool = True,
                      precomputed: list[ScoredChunk] | None = None) -> RetrievalResult:
        """``precomputed`` = candidates already found by the decomposer's probe search
        (same query, same mode), so the corpus is not searched twice."""
        t0 = time.perf_counter()
        if precomputed is not None:
            cands = [ScoredChunk(c.chunk_id, c.score, dict(c.signals)) for c in precomputed[: self.top_k]]
        else:
            cands = self.index.search(sq.text, mode, self.top_k)
        dropped: list[str] = []
        if self.facet_filter is not None:
            cands, dropped = self.facet_filter.apply(sq.text, cands)
        t1 = time.perf_counter()
        rr_name = "none"
        if rerank and self.reranker.name != "none":
            cands = self.reranker.rerank(sq.text, cands, self._texts)
            rr_name = self.reranker.name
        promoted: list[str] = []
        if self.quantity_constraints:
            cons = sorted(set(quantity_constraints(f"{sq.source_span} {sq.text}")))
            cands, promoted = promote(cands, cons, self._texts)
        t2 = time.perf_counter()
        for c in cands:
            c.sub_query_ids = [sq.id]
        return RetrievalResult(sq, cands, t0, t2, (t1 - t0) * 1e3, (t2 - t1) * 1e3, mode, rr_name,
                               [c.score for c in cands], dropped, promoted)

    async def retrieve_many(self, sqs: list[SubQuery], mode: str = "hybrid", rerank: bool = True,
                            precomputed: dict[str, list[ScoredChunk]] | None = None) -> list[RetrievalResult]:
        """Sub-queries run concurrently in the default thread pool. torch and numpy
        release the GIL in their kernels, so this gives real overlap on CPU."""
        loop = asyncio.get_running_loop()
        return list(await asyncio.gather(
            *(loop.run_in_executor(None, self.retrieve_sync, sq, mode, rerank, (precomputed or {}).get(sq.id))
              for sq in sqs)))
