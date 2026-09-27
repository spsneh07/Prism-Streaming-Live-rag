from app.models.schemas import AnswerVersion, Claim, ScoredChunk, SubQuery
from app.retrieval.service import RetrievalService
from app.synthesis.llm import LLMSynthesizer
from app.synthesis.restructure import parse_format, render, restructure


def test_validator_flags_fabrication_numbers_and_scope(rt):
    ok = Claim("Employees receive 10 days of paid sick leave per year.", ["DOC_11:S2:c1"])
    wrong_num = Claim("Employees receive 15 days of paid sick leave per year.", ["DOC_11:S2:c1"])
    fake = Claim("Employees receive 10 days of paid sick leave per year.", ["DOC_999:S1:c1"])
    outside = Claim("Primary caregivers receive 26 weeks of paid parental leave.", ["DOC_11:S3:c1"])
    unrelated = Claim("The office has a rooftop swimming pool and free parking.", ["DOC_11:S2:c1"])
    claims, rep = rt.validator.validate([ok, wrong_num, fake, outside, unrelated], {"DOC_11:S2:c1"})
    assert [c.supported for c in claims] == [True, False, False, False, False]
    assert rep.fabricated_citations == ["DOC_999:S1:c1"]
    assert rep.outside_evidence_citations == ["DOC_11:S3:c1"]
    assert "numbers not found" in rep.unsupported_claims[0]["reason"]
    assert rep.support_rate == 0.2


class FakeProvider:
    """Stands in for an API model; returns one grounded and one hallucinated sentence."""

    def complete(self, system, user):
        assert "EVIDENCE" in user and "[DOC_11 §S2]" in user
        return ("Employees get 10 days of paid sick leave per year [DOC_11 §S2]. "
                "Unused sick leave is paid out at year end [DOC_42 §S9].", {"input_tokens": 120, "output_tokens": 30})


def test_llm_output_always_passes_validator(rt):
    syn = LLMSynthesizer(rt.index, FakeProvider())
    ev = [ScoredChunk("DOC_11:S2:c1", 1.0, {}, ["q1"])]
    res = syn.synthesize([SubQuery("q1", "sick leave", "", "sick leave")], ev)
    claims, rep = rt.validator.validate(res.claims, {"DOC_11:S2:c1"})
    assert [c.supported for c in claims] == [True, False]
    assert rep.fabricated_citations and syn.last_usage["input_tokens"] == 120


def test_extractive_abstains_without_evidence(rt):
    syn = rt.synthesizer(rt.reranker.name != "none")
    svc = RetrievalService(rt.index, rt.reranker)
    sq = SubQuery("q1", "gym membership", "", "gym membership", focus="gym membership")
    r = svc.retrieve_sync(sq)
    out = syn.synthesize([sq], r.candidates)
    assert out.claims == [] and "does not contain enough information" in out.uncertainty[0]


def test_extractive_claims_are_verbatim_corpus_text(rt):
    syn = rt.synthesizer(rt.reranker.name != "none")
    svc = RetrievalService(rt.index, rt.reranker)
    sq = SubQuery("q1", "how many sick days", "", "how many sick days", focus="how many sick days")
    out = syn.synthesize([sq], svc.retrieve_sync(sq).candidates)
    assert out.claims
    for c in out.claims:
        body = c.text.split(": ", 1)[-1]
        assert body in rt.index.by_id[c.citations[0]].text


def test_restructure_uses_only_existing_claims():
    v = AnswerVersion(1, [Claim("A one.", ["D:S1:c1"], "q1"), Claim("A two.", ["D:S2:c1"], "q1"),
                          Claim("B one.", ["D:S3:c1"], "q2")], [], [], [])
    fmt = parse_format("Please repeat your last answer in two bullet points.")
    assert fmt == {"max_items": 2, "bullets": True, "shorter": False}
    claims, _ = restructure(v, "in two bullet points")
    assert [c.text for c in claims] == ["A one.", "B one."]            # one per sub-intent first
    assert render(claims, True).startswith("• A one. [D §S1]")
    short, _ = restructure(v, "make it shorter")
    assert len(short) == 2
