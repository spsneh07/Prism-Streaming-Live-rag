"""Pluggable rerankers.

``Reranker.rerank(query, candidates)`` returns candidates re-ordered with a
``rerank`` signal attached. ``NoopReranker`` lets the benchmark ablate the stage.
"""
from __future__ import annotations

from app.models.hf import load_pretrained as _load

from typing import Protocol

from app.models.schemas import ScoredChunk


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, candidates: list[ScoredChunk], texts: dict[str, str]) -> list[ScoredChunk]: ...


class NoopReranker:
    name = "none"

    def rerank(self, query, candidates, texts):
        return list(candidates)


class CrossEncoderReranker:
    """MS MARCO MiniLM cross-encoder: scores (query, passage) jointly; output is a logit."""

    def __init__(self, model_name: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.tokenizer = _load(AutoTokenizer, model_name)
        self.model = _load(AutoModelForSequenceClassification, model_name).eval()
        self.name = model_name

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        with self._torch.inference_mode():
            enc = self.tokenizer([query] * len(passages), passages, padding=True, truncation=True,
                                 max_length=320, return_tensors="pt")
            return self.model(**enc).logits.view(-1).tolist()

    def rerank(self, query, candidates, texts):
        scores = self.score(query, [texts[c.chunk_id] for c in candidates])
        out = []
        for c, s in zip(candidates, scores):
            out.append(ScoredChunk(c.chunk_id, float(s), {**c.signals, "rerank": float(s)}, list(c.sub_query_ids)))
        return sorted(out, key=lambda c: -c.score)


def load_reranker(enabled: bool, model_name: str) -> Reranker:
    if not enabled:
        return NoopReranker()
    try:
        return CrossEncoderReranker(model_name)
    except Exception as exc:  # model not downloaded / offline
        print(f"[reranker] disabled: could not load {model_name}: {exc}")
        return NoopReranker()
