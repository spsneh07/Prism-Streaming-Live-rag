from app.models.schemas import ScoredChunk, SubQuery
from app.reranking.rerankers import NoopReranker
from app.retrieval.fusion import fuse
from app.retrieval.service import RetrievalService


def sec(cid):
    return cid.rsplit(":", 1)[0]


def test_three_retrieval_modes(rt):
    for mode in ("dense", "bm25", "hybrid"):
        hits = rt.index.search("refund if we cancel a venue", mode, 5)
        assert hits and any(sec(h.chunk_id).startswith("DOC_05") for h in hits[:3]), mode
    h = rt.index.search("international per diem", "hybrid", 3)[0]
    assert {"dense", "bm25", "rrf"} <= set(h.signals)          # observable per-signal scores


def test_reranker_is_modular(rt):
    r = RetrievalService(rt.index, NoopReranker()).retrieve_sync(SubQuery("q", "sick leave days"))
    assert r.reranker == "none" and r.rerank_ms < 5


def test_cross_encoder_reranks(rt):
    if rt.reranker.name == "none":
        return
    r = RetrievalService(rt.index, rt.reranker).retrieve_sync(SubQuery("q", "how many sick days do we get"))
    assert sec(r.candidates[0].chunk_id) == "DOC_11:S2" and "rerank" in r.candidates[0].signals


def test_facet_filter_keeps_city_consistent(rt):
    cands = rt.index.search("venue for 30 people in Pune", "hybrid", 8)
    kept, dropped = rt.facets.apply("venue for 30 people in Pune", cands)
    assert all(not c.chunk_id.startswith("DOC_04") for c in kept)
    assert any(d.startswith("DOC_04") for d in dropped)
    same, none = rt.facets.apply("annual leave", cands)      # no facet value named -> untouched
    assert len(same) == len(cands) and not none


def test_fusion_dedup_supersede_quota(rt):
    res = {
        "a": [ScoredChunk("DOC_06:S1:c1", 3.0), ScoredChunk("DOC_07:S1:c1", 2.9), ScoredChunk("DOC_06:S2:c1", 1)],
        "b": [ScoredChunk("DOC_02:S3:c1", 2.0), ScoredChunk("DOC_01:S3:c1", 1.9)],
        "c": [ScoredChunk("DOC_11:S2:c1", 0.5)],
    }
    fused, rep = fuse(res, rt.index, k=8)
    ids = [f.chunk_id for f in fused]
    assert "DOC_07:S1:c1" not in ids and rep.duplicates[0]["dropped"] == "DOC_07:S1:c1"   # verbatim duplicate
    assert "DOC_02:S3:c1" not in ids and rep.superseded[0]["superseded_by"] == "DOC_01"    # older policy version
    assert "DOC_11:S2:c1" in ids                                                            # weak intent still covered
    assert set(fused[ids.index("DOC_06:S1:c1")].sub_query_ids) == {"a"}


def test_superseded_kept_with_warning_when_alone(rt):
    fused, rep = fuse({"a": [ScoredChunk("DOC_02:S3:c1", 1.0)]}, rt.index, k=8)
    assert [f.chunk_id for f in fused] == ["DOC_02:S3:c1"]
    assert rep.superseded == [{"kept_with_warning": "DOC_02:S3:c1", "superseded_by": "DOC_01"}]
