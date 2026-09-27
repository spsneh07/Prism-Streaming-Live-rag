"""Sentence embeddings with plain ``transformers`` (mean pooling + L2 norm).

This reproduces sentence-transformers' all-MiniLM-L6-v2 output without adding the
sentence-transformers dependency. Runs on CPU.
"""
from __future__ import annotations

from app.models.hf import load_pretrained as _load

import os
from functools import lru_cache

import numpy as np


class Embedder:
    def __init__(self, model_name: str, batch_size: int = 64):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        self.tokenizer = _load(AutoTokenizer, model_name)
        self.model = _load(AutoModel, model_name).eval().to("cpu")
        self.batch_size = batch_size
        self.dim = int(self.model.config.hidden_size)
        self.model_name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = []
        with self._torch.inference_mode():
            for i in range(0, len(texts), self.batch_size):
                batch = self.tokenizer(
                    texts[i : i + self.batch_size], padding=True, truncation=True, max_length=256, return_tensors="pt"
                )
                hidden = self.model(**batch).last_hidden_state
                mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                pooled = self._torch.nn.functional.normalize(pooled, p=2, dim=1)
                out.append(pooled.numpy().astype(np.float32))
        return np.vstack(out)

    def encode_one(self, text: str) -> np.ndarray:
        return self._cached(text)

    @lru_cache(maxsize=4096)
    def _cached(self, text: str) -> np.ndarray:
        # Streaming prefixes are re-embedded often; caching keeps the controller cheap.
        return self.encode([text])[0]
