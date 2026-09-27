"""Cross-sub-query evidence fusion.

Pipeline position: per-sub-query hybrid retrieval (dense+BM25 RRF) -> per-sub-query
rerank -> **this module** -> synthesis.

Steps
1. Coverage quota: the top ``quota`` chunks of every sub-query are admitted first
   (round-robin), so one strong intent cannot crowd the others out.
2. The remaining slots are filled by cross-list RRF.
3. Exact duplicates merge provenance; near-duplicates (token Jaccard >= 0.8) from a
   different document are dropped and recorded.
4. Superseded documents (``superseded_by`` front matter) are dropped when the
   superseding document is also in the evidence set; otherwise they are kept but
   flagged. Chunks with high semantic overlap from different documents that state
   different numbers are flagged as potential conflicts (never silently merged).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.models.schemas import ScoredChunk
from app.retrieval.text import content_tokens, numbers

NEAR_DUP_JACCARD = 0.8      # shingle overlap above which two chunks say the same thing
CONFLICT_SIM = 0.75         # dense cosine above which two chunks discuss the same topic


@dataclass
class FusionReport:
    duplicates: list[dict] = field(default_factory=list)
    superseded: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    per_subquery_admitted: dict[str, list[str]] = field(default_factory=dict)


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1, len(a | b))


def fuse(results: dict[str, list[ScoredChunk]], index, k: int, quota: int = 2, rrf_k: int = 60
         ) -> tuple[list[ScoredChunk], FusionReport]:
    report = FusionReport()
    rrf: dict[str, float] = {}
    prov: dict[str, list[str]] = {}
    best: dict[str, ScoredChunk] = {}
    for sq_id, lst in results.items():
        for rank, sc in enumerate(lst, start=1):
            rrf[sc.chunk_id] = rrf.get(sc.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            prov.setdefault(sc.chunk_id, [])
            if sq_id not in prov[sc.chunk_id]:
                prov[sc.chunk_id].append(sq_id)
            if sc.chunk_id not in best or sc.score > best[sc.chunk_id].score:
                best[sc.chunk_id] = sc

    order: list[str] = []
    for r in range(quota):  # coverage quota, round-robin over sub-queries
        for sq_id, lst in results.items():
            if r < len(lst) and lst[r].chunk_id not in order:
                order.append(lst[r].chunk_id)
                report.per_subquery_admitted.setdefault(sq_id, []).append(lst[r].chunk_id)
    order += [cid for cid, _ in sorted(rrf.items(), key=lambda x: -x[1]) if cid not in order]

    kept: list[str] = []
    toks: dict[str, set[str]] = {}
    for cid in order:
        t = set(content_tokens(index.by_id[cid].text))
        dup_of = next((kc for kc in kept if _jaccard(t, toks[kc]) >= NEAR_DUP_JACCARD), None)
        if dup_of is not None:
            report.duplicates.append({"kept": dup_of, "dropped": cid})
            for sq in prov[cid]:  # the kept chunk inherits the provenance
                if sq not in prov[dup_of]:
                    prov[dup_of].append(sq)
            continue
        kept.append(cid)
        toks[cid] = t

    docs_present = {index.by_id[c].document_id for c in kept}
    final: list[str] = []
    for cid in kept:
        newer = index.by_id[cid].metadata.get("superseded_by")
        if newer and newer in docs_present:
            report.superseded.append({"dropped": cid, "superseded_by": newer})
            continue
        if newer:
            report.superseded.append({"kept_with_warning": cid, "superseded_by": newer})
        final.append(cid)
    final = final[:k]

    rows = {c.chunk_id: i for i, c in enumerate(index.chunks)}
    for i, a in enumerate(final):
        for b in final[i + 1:]:
            ca, cb = index.by_id[a], index.by_id[b]
            if ca.document_id == cb.document_id:
                continue
            sim = float(np.dot(index.chunk_emb[rows[a]], index.chunk_emb[rows[b]]))
            na, nb = numbers(ca.text), numbers(cb.text)
            if sim >= CONFLICT_SIM and na and nb and na != nb:
                report.conflicts.append({"a": a, "b": b, "similarity": round(sim, 3),
                                         "numbers_a": sorted(na), "numbers_b": sorted(nb)})

    fused = []
    for cid in final:
        sc = best[cid]
        fused.append(ScoredChunk(cid, rrf[cid], {**sc.signals, "fusion_rrf": rrf[cid]}, prov[cid]))
    return fused, report
