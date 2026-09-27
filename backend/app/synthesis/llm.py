"""Optional LLM synthesizer behind a provider abstraction.

Disabled by default (``SLRAG_LLM_PROVIDER=none``). When enabled, the model only
sees retrieved evidence blocks and must tag every sentence with ``[DOC_ID §S]``.
Its output is parsed into claims and ALWAYS passes through the grounding
validator, which drops any sentence whose citation is missing, fabricated, or does
not contain the claimed facts.
"""
from __future__ import annotations

import os
import re
from typing import Protocol

from app.models.schemas import Claim, ScoredChunk, SubQuery
from app.retrieval.text import split_sentences
from app.synthesis.extractive import SynthesisResult

_CITE_RE = re.compile(r"\[(DOC_[A-Za-z0-9]+)\s*§\s*(S\d+)\]")

SYSTEM_PROMPT = (
    "You answer strictly from the EVIDENCE blocks. Every sentence must end with one or more citations "
    "in the form [DOC_ID §S#] copied from the evidence headers. Do not use outside knowledge. If the "
    "evidence does not answer a question, say 'The provided corpus does not contain enough information "
    "to verify this.' for that question, without a citation."
)


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> tuple[str, dict]: ...


class AnthropicProvider:
    """Minimal Messages API client over httpx (no SDK dependency)."""

    def __init__(self, model: str):
        import httpx

        self.key = os.environ["ANTHROPIC_API_KEY"]
        self.base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self.model = model
        self.http = httpx.Client(timeout=60)

    def complete(self, system: str, user: str) -> tuple[str, dict]:
        r = self.http.post(f"{self.base}/v1/messages",
                           headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                           json={"model": self.model, "max_tokens": 600, "system": system,
                                 "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        return text, data.get("usage", {})


class LLMSynthesizer:
    name = "llm"

    def __init__(self, index, provider: LLMProvider):
        self.index = index
        self.provider = provider
        self.last_usage: dict = {}

    def synthesize(self, sub_queries: list[SubQuery], fused: list[ScoredChunk],
                   exclude_sentences: set[str] | None = None) -> SynthesisResult:
        blocks = []
        for e in fused:
            c = self.index.by_id[e.chunk_id]
            blocks.append(f"[{c.document_id} §{c.section_id}] {c.source_title} - {c.section_title}\n{c.text}")
        questions = "\n".join(f"- ({q.id}) {q.source_span or q.text}" for q in sub_queries)
        user = f"QUESTIONS:\n{questions}\n\nEVIDENCE:\n\n" + "\n\n".join(blocks)
        text, usage = self.provider.complete(SYSTEM_PROMPT, user)
        self.last_usage = usage
        section_to_chunk = {f"{self.index.by_id[e.chunk_id].document_id} §{self.index.by_id[e.chunk_id].section_id}":
                            e.chunk_id for e in fused}
        claims, uncertainty = [], []
        for sent in split_sentences(text):
            cites = [f"{d} §{s}" for d, s in _CITE_RE.findall(sent)]
            body = _CITE_RE.sub("", sent).strip()
            if not cites:
                if "not contain enough information" in body:
                    uncertainty.append(body)
                continue
            # Unknown section markers are kept verbatim so the validator flags them as fabricated.
            ids = [section_to_chunk.get(c, c.replace(" §", ":") + ":c?") for c in cites]
            claims.append(Claim(text=body, citations=ids, sub_query_id=sub_queries[0].id if sub_queries else ""))
        return SynthesisResult(claims, uncertainty, {})
