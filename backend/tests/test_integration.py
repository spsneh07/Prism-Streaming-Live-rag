"""End-to-end behaviour of the streaming engine (the seven required integration cases)."""
import asyncio
import json

from app.config import get_settings

GUIDE = ([(0.0, "I need to plan a customer"), (0.8, "workshop in Pune for 30 people,"),
          (1.6, "and I need the cancellation policy and the catering options.")], 2.1)
TRAVEL_V1 = ([(0.0, "Summarize the travel"), (0.7, "reimbursement rule for an employee trip.")], 1.2)
TRAVEL_LATE = ([(0.0, "The trip was international"), (0.8, "and the booking was made after travel.")], 1.3)


def ev(res, type_):
    return [e for e in res.log.events if e["type"] == type_]


def test_complete_streaming_request_emits_full_trace(run):
    _, (r,) = run([GUIDE])
    kinds = {e["type"] for e in r.log.events}
    assert {"TRANSCRIPT_CHUNK", "RETRIEVAL_DECISION", "QUERY_CREATED", "RETRIEVAL_STARTED", "RETRIEVAL_COMPLETED",
            "UTTERANCE_END", "EVIDENCE_FUSED", "ANSWER_DELTA", "CITATION_VALIDATED", "ANSWER_VERSION_UPDATED",
            "FINAL_RESPONSE", "TURN_SUMMARY"} <= kinds
    ts = [e["t"] for e in r.log.events]
    assert ts == sorted(ts)                                    # one monotonic clock
    assert all(e["session_id"] and e["request_id"] for e in r.log.events)


def test_early_retrieval_starts_before_utterance_end(rt):
    s = rt.sessions.create()
    chunks = [{"t": t, "text": x} for t, x in GUIDE[0]]
    r = asyncio.run(rt.engine().run_turn(s, chunks, GUIDE[1], speed=4.0))
    first = ev(r, "RETRIEVAL_STARTED")[0]["t"]
    end = ev(r, "UTTERANCE_END")[0]["t"]
    assert first < end and r.summary["early_retrieval"] and r.summary["retrieval_lead_s"] > 0
    assert ev(r, "RETRIEVAL_DECISION")[0]["action"] == "WAIT"   # "I need to plan a customer" is not specific yet


def test_multi_intent_parallel_retrieval_and_fusion(run):
    _, (r,) = run([GUIDE])
    dec = [e for e in ev(r, "DECOMPOSITION") if not e.get("provisional")][-1]
    assert dec["is_multi_intent"] and len(dec["sub_queries"]) == 3
    batches = [e for e in ev(r, "RETRIEVAL_STARTED")]
    assert any(len(b["sub_query_ids"]) >= 2 for b in batches)   # sub-queries dispatched together
    fused = ev(r, "EVIDENCE_FUSED")[-1]
    covered = {sq for e in fused["evidence"] for sq in e["sub_query_ids"]}
    assert {"q1", "q2", "q3"} <= covered
    assert fused["duplicates"]                                   # DOC_07 duplicates DOC_06


def test_late_detail_refines_instead_of_restarting(run):
    session, (r1, r2) = run([TRAVEL_V1, TRAVEL_LATE])
    assert r2.summary["intent"] == "refinement" and r2.summary["answer_version"] == 2
    v1, v2 = session.versions
    v1_cites = {c for cl in v1.claims if cl.supported for c in cl.citations}
    v2_cites = {c for cl in v2.claims if cl.supported and cl.status != "removed" for c in cl.citations}
    assert v1_cites <= v2_cites                                  # established facts preserved
    assert v2_cites - v1_cites                                   # delta evidence added
    assert {cl.status for cl in v2.claims} >= {"retained", "added"}
    queried = [e["sub_query_id"] for e in ev(r2, "QUERY_CREATED")]
    assert not any(q.startswith("q") for q in queried)           # prior sub-queries were not re-searched
    assert any("refinement of v1" in line for line in v2.change_log)
    added = " ".join(cl.text for cl in v2.claims if cl.status == "added")
    assert "senior director" in added or "late booking" in added.lower()


def test_presentation_turn_suppresses_retrieval(run):
    session, (r1, r2) = run([TRAVEL_V1, ([(0.0, "Make your previous"), (0.6, "answer shorter.")], 1.0)])
    assert r2.summary["final_action"] == "SUPPRESS" and r2.summary["retrieval_calls_total"] == 0
    assert not ev(r2, "RETRIEVAL_STARTED") and ev(r2, "RETRIEVAL_SUPPRESSED")
    assert set(r2.summary["citations"]) <= {c for cl in session.versions[0].claims for c in cl.citations}
    assert len(session.versions) == 1                            # no new content version


def test_insufficient_evidence_is_explicit(run):
    _, (r,) = run([([(0.0, "Does the company offer"), (0.8, "a gym membership?")], 1.8)])
    final = ev(r, "FINAL_RESPONSE")[0]
    assert final["citations"] == []
    assert "does not contain enough information" in final["answer"]
    assert final["uncertainty"]


def test_citations_are_valid_corpus_ids_from_this_turns_evidence(run, rt):
    _, (r,) = run([GUIDE])
    evidence = {e["chunk_id"] for e in ev(r, "EVIDENCE_FUSED")[-1]["evidence"]}
    cites = [c["chunk_id"] for c in ev(r, "FINAL_RESPONSE")[0]["citations"]]
    assert cites and all(c in rt.index.by_id and c in evidence for c in cites)
    val = ev(r, "CITATION_VALIDATED")[0]
    assert val["fabricated_citations"] == [] and val["citation_support_rate"] == 1.0


def test_baseline_runs_same_trace_schema(rt, run):
    _, (r,) = run([GUIDE], engine=rt.baseline())
    assert r.summary["early_retrieval"] is False and r.summary["retrieval_calls_total"] == 1
    assert ev(r, "FINAL_RESPONSE") and ev(r, "EVIDENCE_FUSED")


def test_all_demo_scenarios_run_end_to_end(rt, run):
    scen = json.loads((get_settings().configs_dir / "demo_scenarios.json").read_text(encoding="utf-8"))
    for name, sc in scen.items():
        turns = [([(c["t"], c["text"]) for c in t["chunks"]], t.get("end_t")) for t in sc["turns"]]
        _, results = run(turns)
        assert all(ev(r, "FINAL_RESPONSE") for r in results), name
