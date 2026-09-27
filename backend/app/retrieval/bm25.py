"""Okapi BM25 (in-house, ~40 lines, so every score is inspectable)."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from app.retrieval.text import content_tokens


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_tokens = [content_tokens(d) for d in docs]
        self.doc_len = np.array([len(t) for t in self.doc_tokens], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if len(docs) else 0.0
        self.tf = [Counter(t) for t in self.doc_tokens]
        df = Counter(tok for toks in self.doc_tokens for tok in set(toks))
        n = len(docs)
        # BM25+ style non-negative idf
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        q = content_tokens(query)
        out = np.zeros(len(self.tf), dtype=np.float32)
        for tok in q:
            idf = self.idf.get(tok)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(tok, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                    out[i] += idf * f * (self.k1 + 1) / denom
        return out

    def vocab_idf(self, token: str) -> float | None:
        return self.idf.get(token)
