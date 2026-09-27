"""Grounding / citation validator - runs on every answer before it is returned.

Checks per claim
1. every cited id exists in the corpus index      (else: fabricated citation)
2. every cited id was retrieved in this session   (else: citation outside evidence)
3. lexical support: >= ``min_support`` of the claim's content words appear in
   the cited chunk (containment, not overlap, so padding a claim with extra
   facts lowers its score)
4. numeric consistency: every number in the claim appears in the cited chunk
   (catches the most common hallucination: a wrong amount / day count)

Claims failing any check are marked unsupported, removed from the rendered answer
and listed in the uncertainty field. Nothing is ever "repaired" by inventing a
citation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.schemas import Claim
from app.retrieval.text import content_tokens, numbers


@dataclass
class GroundingReport:
    num_claims: int = 0
    num_supported: int = 0
    fabricated_citations: list[str] = field(default_factory=list)
    outside_evidence_citations: list[str] = field(default_factory=list)
    unsupported_claims: list[dict] = field(default_factory=list)

    @property
    def support_rate(self) -> float:
        return self.num_supported / self.num_claims if self.num_claims else 1.0

    def to_dict(self) -> dict:
        return {"num_claims": self.num_claims, "num_supported": self.num_supported,
                "citation_support_rate": round(self.support_rate, 4),
                "fabricated_citations": self.fabricated_citations,
                "outside_evidence_citations": self.outside_evidence_citations,
                "unsupported_claims": self.unsupported_claims}


class GroundingValidator:
    def __init__(self, index, min_support: float = 0.6):
        self.index = index
        self.min_support = min_support

    def support(self, claim_text: str, chunk_id: str) -> tuple[float, bool]:
        chunk = self.index.by_id[chunk_id]
        ctoks = set(content_tokens(claim_text))
        doc_toks = set(content_tokens(f"{chunk.source_title} {chunk.section_title} {chunk.text}"))
        containment = len(ctoks & doc_toks) / len(ctoks) if ctoks else 0.0
        nums_ok = numbers(claim_text) <= numbers(chunk.text)
        return containment, nums_ok

    def validate(self, claims: list[Claim], evidence_ids: set[str]) -> tuple[list[Claim], GroundingReport]:
        rep = GroundingReport()
        for c in claims:
            if c.status == "removed":
                continue
            rep.num_claims += 1
            valid = []
            for cid in c.citations:
                if cid not in self.index.by_id:
                    rep.fabricated_citations.append(cid)
                elif cid not in evidence_ids:
                    rep.outside_evidence_citations.append(cid)
                else:
                    valid.append(cid)
            best, reason = 0.0, "no valid citation"
            for cid in valid:
                score, nums_ok = self.support(c.text, cid)
                if not nums_ok:
                    reason = f"numbers not found in {cid}"
                    continue
                if score > best:
                    best = score
            c.support_score = round(best, 3)
            c.supported = bool(valid) and best >= self.min_support
            if c.supported:
                rep.num_supported += 1
            else:
                if valid and reason == "no valid citation":
                    reason = f"only {best:.0%} of claim terms found in cited text"
                rep.unsupported_claims.append({"claim": c.text, "citations": c.citations, "reason": reason})
        return claims, rep
