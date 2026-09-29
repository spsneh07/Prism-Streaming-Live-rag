"""TURN_SUMMARY.output_record follows the Theme 4 guide's structured output (§4)."""
import asyncio


def _turn(rt, s, chunks, end_t):
    res = asyncio.run(rt.engine().run_turn(s, [{"t": t, "text": x} for t, x in chunks], end_t, speed=20))
    return next(e for e in res.log.events if e["type"] == "TURN_SUMMARY")["output_record"]


def test_example1_record_shape(rt):
    s = rt.sessions.create()
    rec = _turn(rt, s, [(0.0, "I need to plan a customer"), (0.8, "workshop in Pune for 30 people,"),
                        (1.6, "and I need the cancellation policy and the catering options.")], 2.1)
    assert set(rec) >= {"retrieval_events", "sub_queries", "answer", "citations", "uncertainty"}
    trig = [e["trigger"] for e in rec["retrieval_events"]]
    assert trig[0] == "provisional" and "multi_intent" in trig
    assert len(rec["sub_queries"]) == 3 and rec["retrieval_required"] is True
    assert rec["citations"] and all(" §S" in c for c in rec["citations"])


def test_example3_record_is_suppressed(rt):
    s = rt.sessions.create()
    _turn(rt, s, [(0.0, "What are the cancellation terms for an external venue?")], 0.6)
    rec = _turn(rt, s, [(0.0, "Please repeat your last answer in two bullets.")], 0.6)
    assert rec["retrieval_required"] is False and rec["reason"] == "presentation_restructure"
    assert rec["retrieval_events"] == [] and rec["citations"]
