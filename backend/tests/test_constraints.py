"""Quantity constraints ("for 30 people"): parsing, matching, promotion, end to end."""
import asyncio

from app.models.schemas import ScoredChunk
from app.retrieval.constraints import promote, quantity_constraints, satisfies


def test_parse_group_size_phrases():
    assert quantity_constraints("a customer workshop in Pune for 30 people") == [(30, "people")]
    assert quantity_constraints("a dinner for about 12 guests") == [(12, "guest")]
    assert quantity_constraints("how many days of leave do I get") == []
    assert quantity_constraints("claims within 30 days") == []   # deadlines are not group sizes


def test_minimum_semantics_and_number_lists():
    cons = [(30, "people")]
    assert satisfies("Koregaon Park Hall seats up to 40 people in classroom layout.", cons)
    assert satisfies("It offers three rooms with capacities of 20, 35 and 80 people.", cons)
    assert not satisfies("The largest internal room seats 12 people.", cons)
    assert not satisfies("Requests for events with more than 50 attendees need 20 days.", cons)  # other noun
    assert not satisfies("Customer workshops are planned in four steps.", cons)


def test_promote_keeps_top_result_and_only_acts_when_needed():
    texts = {"a": "workshops are planned in steps", "b": "internal rooms seat 12 people",
             "c": "agenda and invitations", "d": "rooms for 20, 35 and 80 people", "e": "hall seats 40 people"}
    cands = [ScoredChunk(k, 1.0) for k in "abcde"]
    out, promoted = promote(cands, [(30, "people")], texts)
    assert [c.chunk_id for c in out] == ["a", "d", "e", "b", "c"] and promoted == ["d", "e"]
    same, none = promote(cands, [(10, "people")], texts)          # "b" (12 people) already in the window
    assert same == cands and none == []


def test_guide_example_venue_reaches_the_answer(rt):
    """Theme 4 guide, Example 1: the capacity sub-intent is answered with a venue that fits 30."""
    s = rt.sessions.create()
    chunks = [(0.0, "I need to plan a customer"), (0.8, "workshop in Pune for 30 people,"),
              (1.6, "and I need the cancellation policy and the catering options.")]
    res = asyncio.run(rt.engine().run_turn(s, [{"t": t, "text": x} for t, x in chunks], 2.1, speed=20))
    fin = next(e for e in res.log.events if e["type"] == "FINAL_RESPONSE")
    cited = {c["chunk_id"].rsplit(":", 1)[0] if isinstance(c, dict) else c.rsplit(":", 1)[0] for c in fin["citations"]}
    assert "DOC_03:S3" in cited or "DOC_03:S2" in cited
    val = next(e for e in res.log.events if e["type"] == "CITATION_VALIDATED")
    assert val["fabricated_citations"] == [] and val["citation_support_rate"] == 1.0


def test_baseline_is_unchanged_by_constraints(rt):
    b = rt.baseline()
    assert b.service.quantity_constraints is False and b.synth.quantity_constraints is False
