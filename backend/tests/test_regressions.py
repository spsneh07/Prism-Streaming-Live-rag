"""Regression tests for every defect found during development.

Known, still-open failures are marked ``xfail(strict=True)``: they document the
limitation honestly and will flag loudly (XPASS -> failure) if behaviour changes.
"""
import asyncio

import pytest

from app.models.schemas import ScoredChunk, SubQuery
from app.retrieval.service import RetrievalService


def run_turn(rt, chunks, end_t, session=None, engine=None):
    s = session or rt.sessions.create()
    res = asyncio.run((engine or rt.engine()).run_turn(s, [{"t": t, "text": x} for t, x in chunks], end_t, speed=20))
    return s, res


def final(res):
    return next(e for e in res.log.events if e["type"] == "FINAL_RESPONSE")


# --- abstention ---------------------------------------------------------------------------
def test_unknown_entity_question_abstains(rt):
    """Bug: 'Who is the CEO of Veltrix?' was answered with an unrelated scope sentence."""
    _, r = run_turn(rt, [(0, "Who is the CEO"), (0.6, "of Veltrix?")], 1.3)
    assert final(r)["citations"] == [] and final(r)["uncertainty"]


def test_coverage_names_missing_concept(rt):
    cov, missing = rt.coverage.coverage("parking fee at the Pune venues", ["DOC_03:S2:c1", "DOC_03:S5:c1"])
    assert "parking" in missing and cov < 1.0          # stem "park" must NOT match "Koregaon Park Hall"


def test_parking_fee_abstains(rt):
    """Was a known failure (xfail) until the gate was refitted on development data.
    Caveat: this dev utterance is now part of the gate's fitting data, and under
    leave-one-group-out it is still misclassified (p=0.52), so this pass is regression
    protection, not independent evidence that the limitation is solved."""
    _, r = run_turn(rt, [(0, "What is the parking fee"), (0.8, "at the Pune venues?")], 1.3)
    assert final(r)["citations"] == []


def test_partially_answerable_flags_missing_part(rt):
    _, r = run_turn(rt, [(0, "Which Pune venue has a projector,"), (1.0, "and what is the wifi password there?")], 2.3)
    f = final(r)
    assert any(c["chunk_id"].startswith("DOC_03:S2") for c in f["citations"])      # projector answered
    assert any("wifi" in u for u in f["uncertainty"])                               # wifi flagged


# --- intent / controller ---------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="known near-miss: audience phrase pulls this presentation request toward "
                                       "refinement (p=0.51 vs 0.44)")
def test_plain_words_request_is_presentation(rt):
    intent, _ = rt.controller().classify_intent("Put that in plain words for a new joiner.",
                                                "Explain the late booking rule.")
    assert intent == "presentation"


def test_imperative_on_previous_answer_is_presentation(rt):
    for t in ["Put that in plain words", "Make it simpler for a beginner."]:
        assert rt.controller().classify_intent(t, "Explain the late booking rule.")[0] == "presentation", t


def test_refinement_without_corpus_words_is_not_suppressed(rt):
    """Bug: 'It's for seventy thousand rupees' was suppressed as 'no searchable content'."""
    s, _ = run_turn(rt, [(0, "How do I submit"), (0.6, "an expense claim?")], 1.1)
    _, r = run_turn(rt, [(0, "It's for seventy"), (0.6, "thousand rupees.")], 1.1, session=s)
    assert r.summary["final_action"] == "RETRIEVE" and r.summary["answer_version"] == 2


# --- decomposition / ranking -----------------------------------------------------------------
def test_short_questions_are_not_attached_as_constraints(rt):
    """Bug: 'how do I register them' was merged into the previous clause."""
    d = rt.decomposer.decompose("We have customers visiting next week; how do I register them, "
                                "and do they need to sign an NDA?")
    assert len(d.sub_queries) == 2
    assert "customers visiting" in d.sub_queries[0].text             # leading context merged forward


def test_shared_context_chunk_does_not_crowd_out_each_subquery(rt):
    """Bug: a chunk retrieved by every sub-query (via a carried city name) led each one's evidence."""
    _, r = run_turn(rt, [(0, "I need to plan a customer"), (0.8, "workshop in Pune for 30 people,"),
                         (1.6, "and I need the cancellation policy and the catering options.")], 2.1)
    cites = [c["chunk_id"] for c in final(r)["citations"]]
    assert any(c.startswith("DOC_05") for c in cites) and any(c.startswith("DOC_06") for c in cites)


def test_other_city_venue_not_used_for_pune_request(rt):
    svc = RetrievalService(rt.index, rt.reranker, 8, rt.facets)
    res = svc.retrieve_sync(SubQuery("q", "venue in Pune for 30 people"))
    assert not any(c.chunk_id.startswith("DOC_04") for c in res.candidates)


# --- infrastructure -------------------------------------------------------------------------
def test_search_cache_returns_independent_copies(rt):
    a = rt.index.search("sick leave", "hybrid", 3)
    a[0].sub_query_ids.append("mutated")
    a[0].signals["x"] = 1
    b = rt.index.search("sick leave", "hybrid", 3)
    assert b[0].sub_query_ids == [] and "x" not in b[0].signals


def test_calibration_is_bound_to_its_corpus(rt, tmp_path, monkeypatch):
    import json
    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"corpus_sha256": "other", "gate": {"type": "logreg"}, "summary": {}}))
    monkeypatch.setattr(rt.settings, "processed_dir", tmp_path)
    assert "different corpus" in rt._load_calibration()["status"]


def test_early_retrieval_prepares_synthesis_during_speech(rt):
    s = rt.sessions.create()
    chunks = [{"t": 0.0, "text": "How many days of"}, {"t": 0.8, "text": "paid sick leave do we get?"}]
    r = asyncio.run(rt.engine().run_turn(s, chunks, 3.0, speed=1.0))
    prepared = [e for e in r.log.events if e["type"] == "SYNTHESIS_PREPARED"]
    end = next(e["t"] for e in r.log.events if e["type"] == "UTTERANCE_END")
    assert prepared and prepared[0]["t"] < end


# --- context / pronoun handling ---------------------------------------------------------------
def test_pronoun_sentence_is_contextualised_with_its_heading(rt):
    """Bug: 'It includes a projector ...' was unusable out of context."""
    _, r = run_turn(rt, [(0, "Which Pune venue has a projector,"), (1.0, "and what is the wifi password there?")], 2.3)
    texts = [e["text"] for e in r.log.events if e["type"] == "ANSWER_DELTA"]
    assert any(t.startswith("Koregaon Park Hall: It includes a projector") for t in texts)


def test_rambling_context_merges_into_the_question_and_focus_is_the_need(rt):
    """Bug: context-only clauses became their own sub-queries and diluted the answer focus."""
    d = rt.decomposer.decompose("So yesterday I was chatting with my manager over coffee, and she said I could get "
                                "a new laptop, so how often do laptops actually get replaced here?")
    assert len(d.sub_queries) == 1
    assert d.sub_queries[0].focus.startswith("often do laptops")
    d2 = rt.decomposer.decompose("So I'm heading to Singapore next month to visit a customer, and before I book "
                                 "anything I'd like to know the daily meal allowance for international travel.")
    assert d2.sub_queries[0].focus == "daily meal allowance for international travel"


# --- answer versions across suppressed turns ---------------------------------------------------
def test_suppressed_turn_preserves_version_and_refinement_builds_on_it(rt):
    s, r1 = run_turn(rt, [(0, "Summarize the travel"), (0.7, "reimbursement rule for an employee trip.")], 1.2)
    v1 = {c for cl in s.versions[0].claims if cl.supported for c in cl.citations}
    _, r2 = run_turn(rt, [(0, "Make your previous"), (0.6, "answer shorter.")], 1.0, session=s)
    assert r2.summary["suppressed"] and len(s.versions) == 1 and r2.summary["retrieval_calls_total"] == 0
    _, r3 = run_turn(rt, [(0, "The trip was international"), (0.8, "and the booking was made after travel.")],
                     1.3, session=s)
    assert r3.summary["answer_version"] == 2 and r3.summary["intent"] == "refinement"
    v2 = {c for cl in s.versions[1].claims if cl.supported and cl.status != "removed" for c in cl.citations}
    assert v1 <= v2
