"""Extractive, citation-first answer synthesis (default, offline, $0 per turn).

For every sub-query the synthesizer
1. checks evidence sufficiency (cross-encoder logit + answer-coverage, or dense
   cosine when the reranker is disabled) - below the gate the sub-intent is
   reported as unverifiable instead of answered;
2. selects up to N sentences from that sub-query's evidence, ranked by cosine to
   the sub-query with MMR-style redundancy suppression;
3. attaches the source chunk id to each sentence.

Every sentence is copied verbatim from the corpus, so this path cannot introduce
outside knowledge. The optional LLM synthesizer (``llm.py``) produces more fluent
text and is therefore always passed through the grounding validator.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.models.schemas import Claim, ScoredChunk, SubQuery
from app.retrieval.constraints import quantity_constraints, satisfies

REDUNDANT_SIM = 0.85   # two sentences above this cosine say the same thing
_PRONOUNS = {"it", "this", "they", "these", "those", "each", "its", "their", "that"}


@dataclass
class SynthesisResult:
    claims: list[Claim]
    uncertainty: list[str]
    sufficiency: dict[str, dict]


class ExtractiveSynthesizer:
    name = "extractive"

    def __init__(self, index, reranker_enabled: bool, sentences_per_subquery: int = 2,
                 min_sentence_sim: float = 0.30, min_rerank_logit: float = -2.0, min_dense_sim: float = 0.40,
                 sentence_scorer=None, coverage=None, gate: dict | None = None, quantity_constraints: bool = False):
        self.index = index
        # Prefer sentences that satisfy a stated quantity ("for 30 people"): see retrieval/constraints.py.
        self.quantity_constraints = quantity_constraints
        self.reranker_enabled = reranker_enabled
        # Optional cross-encoder used to rank candidate sentences (``.score(query, texts)``).
        self.sentence_scorer = sentence_scorer
        self.n = sentences_per_subquery
        self.min_sentence_sim = min_sentence_sim
        self.min_rerank_logit = min_rerank_logit
        self.min_dense_sim = min_dense_sim
        self.coverage = coverage
        # Evidence-sufficiency gate, calibrated per corpus by scripts/calibrate_sufficiency.py:
        # logistic regression over named evidence features (see ``features``). Three outcomes:
        #   p >= threshold                  -> answer
        #   hedge_threshold <= p < threshold -> answer, flagged as weakly supported
        #   p <  hedge_threshold            -> abstain
        # Uncalibrated fallback: best-sentence logit threshold only.
        self.gate = gate or {"type": "threshold", "t_low": min_rerank_logit}

    @staticmethod
    def features(logits: list[float], cos_max: float, coverage: float, rerank_max: float | None) -> dict:
        """Evidence features for one sub-query. Aggregates over the top evidence, not only
        the single best sentence, so several consistent moderately-scored sentences count."""
        top = sorted(logits, reverse=True)[:3]
        best = top[0]
        return {
            "logit": best,                                        # best sentence (legacy name)
            "logit_top3_mean": sum(top) / len(top),
            "n_support": min(sum(1 for x in logits if x >= 0.0), 5) / 5.0,
            "coverage": coverage,
            "cos": cos_max,
            "rerank_max": best if rerank_max is None else rerank_max,
        }

    def p_sufficient(self, feats: dict) -> float | None:
        g = self.gate
        if g.get("type") != "logreg":
            return None
        names = g.get("features", ["logit", "coverage", "cos"])
        z = g["intercept"] + sum(c * (feats[n] - m) / sd for c, n, m, sd in zip(g["coef"], names, g["mean"], g["scale"]))
        return 1.0 / (1.0 + math.exp(-z))

    def support_level(self, feats: dict) -> tuple[str, float | None]:
        p = self.p_sufficient(feats)
        if p is None:
            return ("strong" if feats["logit"] >= self.gate["t_low"] else "none"), None
        if p >= self.gate.get("threshold", 0.5):
            return "strong", p
        if p >= self.gate.get("hedge_threshold", 1.1):
            return "weak", p
        return "none", p

    def candidates(self, sq: SubQuery, evidence: list[ScoredChunk]) -> tuple[list[tuple], dict]:
        """Score every sentence of the sub-query's evidence and decide sufficiency.

        Sentences are scored against the user's own clause (``focus``); the
        retrieval query additionally carries context words (e.g. a city name) that
        would bias selection toward sentences that merely mention the context.
        With a cross-encoder, sufficiency combines the best *sentence* logit with
        answer-coverage (calibrated by scripts/calibrate_sufficiency.py); without one
        it is the best chunk cosine.
        """
        if not evidence:
            return [], {"sufficient": False, "signal": "none", "best": None}
        focus = sq.focus or sq.source_span or sq.text
        q = self.index.embedder.encode_one(focus)
        cands = []
        for e in evidence:
            for text, emb in self.index.sentences_of(e.chunk_id):
                cos = float(emb @ q)
                cands.append((cos, cos, text, e.chunk_id, emb))
        cov, missing = (self.coverage.coverage(focus, [e.chunk_id for e in evidence])
                        if self.coverage is not None else (1.0, []))
        if self.sentence_scorer is not None and cands:
            # Score with title + heading as context: "It includes a projector" only answers
            # "which venue has a projector" once we know which section "It" refers to.
            logits = self.sentence_scorer.score(
                focus, [f"{self.index.by_id[c[3]].source_title} - {self.index.by_id[c[3]].section_title}. {c[2]}"
                        for c in cands])
            cands = [(lg, cos, t, cid, emb) for lg, (_, cos, t, cid, emb) in zip(logits, cands)]
            rr = [e.signals["rerank"] for e in evidence if "rerank" in e.signals]
            feats = self.features([c[0] for c in cands], max(c[1] for c in cands), cov, max(rr) if rr else None)
            level, p = self.support_level(feats)
            suff = {"sufficient": level != "none", "support": level, "signal": "sentence_ce_logit+coverage",
                    "best": round(feats["logit"], 3), "coverage": round(cov, 3), "best_cos": round(feats["cos"], 3),
                    "features": {k: round(v, 4) for k, v in feats.items()},
                    "p_sufficient": None if p is None else round(p, 3), "missing_terms": missing}
        else:
            best = max(self.index.dense_sim(sq.text, e.chunk_id) for e in evidence)
            suff = {"sufficient": best >= self.min_dense_sim, "signal": "dense_cosine", "best": round(best, 3),
                    "coverage": round(cov, 3), "missing_terms": missing, "threshold": self.min_dense_sim}
        cands.sort(key=lambda x: -x[0])
        return cands, suff

    def synthesize(self, sub_queries: list[SubQuery], fused: list[ScoredChunk],
                   exclude_sentences: set[str] | None = None,
                   rankings: dict[str, list[str]] | None = None,
                   prepared: dict[str, tuple] | None = None) -> SynthesisResult:
        """``rankings`` = each sub-query's own (reranked) chunk order. Evidence for a
        sub-query is taken in that order, restricted to chunks that survived fusion, so a
        chunk that many sub-queries weakly share cannot crowd out each one's best match."""
        used = set(exclude_sentences or ())
        claims: list[Claim] = []
        uncertainty: list[str] = []
        suff_report: dict[str, dict] = {}
        by_id = {e.chunk_id: e for e in fused}
        for sq in sub_queries:
            if rankings and sq.id in rankings:
                ev = [by_id[c] for c in rankings[sq.id] if c in by_id][:3]
            else:
                ev = [e for e in fused if sq.id in e.sub_query_ids][:3]
            pre = (prepared or {}).get(sq.id)
            if pre is not None and pre[0] == [e.chunk_id for e in ev]:
                cands, suff = pre[1], dict(pre[2], precomputed=True)   # scored while the user was speaking
            else:
                cands, suff = self.candidates(sq, ev)
            suff_report[sq.id] = suff
            if not suff["sufficient"]:
                miss = f" (not found in the retrieved evidence: {', '.join(suff['missing_terms'])})" if suff.get("missing_terms") else ""
                uncertainty.append(f"The provided corpus does not contain enough information to verify: "
                                   f"\"{sq.source_span or sq.text}\"{miss}.")
                continue
            if suff.get("support") == "weak":
                miss = f"; not found in the evidence: {', '.join(suff['missing_terms'])}" if suff.get("missing_terms") else ""
                uncertainty.append(f"Weak evidence for \"{sq.source_span or sq.text}\": the cited sections only partly "
                                   f"address it (P(sufficient)={suff['p_sufficient']}{miss}). Verify against the sources.")
            cons = quantity_constraints(f"{sq.source_span} {sq.text}") if self.quantity_constraints else []
            if cons:
                # stable: constraint-satisfying sentences first, each group still in score order
                cands = sorted(cands, key=lambda c: not satisfies(c[2], cons))
            picked: list[tuple[str, str, np.ndarray]] = []
            for score, cos, text, cid, emb in cands:
                if len(picked) >= self.n:
                    break
                # First sentence must clear the calibrated gate; supporting sentences only
                # need topical similarity (the gate already established the evidence is on-topic).
                if cos < self.min_sentence_sim:
                    continue
                if text in used or any(float(emb @ p[2]) >= REDUNDANT_SIM for p in picked):
                    continue
                picked.append((text, cid, emb))
                used.add(text)
            if not picked:
                uncertainty.append(f"Retrieved sections for \"{sq.source_span or sq.text}\" do not state an "
                                   f"answer directly; not verified.")
            claims += [Claim(text=self._contextualise(t, cid), citations=[cid], sub_query_id=sq.id)
                       for t, cid, _ in picked]
        return SynthesisResult(claims, uncertainty, suff_report)

    def _contextualise(self, sentence: str, chunk_id: str) -> str:
        """Prefix the section heading when a sentence opens with a pronoun ("It ...",
        "This ..."), so the claim stays meaningful out of context. The heading is part
        of the cited chunk, so the claim remains fully attributable."""
        first = sentence.split(" ", 1)[0].lower()
        if first in _PRONOUNS:
            return f"{self.index.by_id[chunk_id].section_title}: {sentence}"
        return sentence
