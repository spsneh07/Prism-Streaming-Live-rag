from app.controller.retrieval_controller import StreamState


def test_guide_example_decomposes_into_three(rt):
    d = rt.decomposer.decompose("I need to plan a customer workshop in Pune for 30 people, and I need the "
                                "cancellation policy and the catering options.")
    assert d.is_multi_intent and len(d.sub_queries) == 3
    assert "for 30 people" in d.sub_queries[0].text                  # constraint re-attached, not an intent
    assert all("Pune" in q.text for q in d.sub_queries)               # context carried to siblings
    assert d.sub_queries[1].carried_context == ["Pune"]
    assert d.to_dict()["sub_queries"][0]["id"] == "q1"               # structured JSON output


def test_single_intent_not_fragmented(rt):
    for u in ["What are the terms and conditions for cancelling a venue booking?",
              "What is the cancellation policy for venues?"]:
        assert len(rt.decomposer.decompose(u).sub_queries) == 1, u


def test_distinct_sections_stay_separate(rt):
    d = rt.decomposer.decompose("How many annual leave days do I get, and how many sick days?")
    assert len(d.sub_queries) == 2


def _decide(ctrl, prefix, prev=None, final=False, state=None):
    return ctrl.decide(prefix, state or StreamState(), is_final=final, prev_answer_topic=prev)


def test_controller_wait_retrieve_suppress(rt):
    c = rt.controller("learned")
    assert _decide(c, "I need to plan a customer").action == "WAIT"
    assert _decide(c, "I need to plan a customer workshop in Pune").action == "RETRIEVE"
    d = _decide(c, "Please repeat your last answer in two bullet points.", prev="travel reimbursement", final=True)
    assert d.action == "SUPPRESS" and d.intent == "presentation"
    assert "no corpus search" in d.reason


def test_controller_guardrails(rt):
    c = rt.controller("learned")
    d = _decide(c, "Make it shorter.", prev=None, final=True)
    assert d.action == "SUPPRESS" and "no prior answer" in d.reason
    st = StreamState()
    c.mark_retrieved(st, {"cancel", "policy", "venu"})
    d = _decide(c, "cancellation policy venue", state=st)
    assert d.action == "WAIT" and d.features["new_content"] == 0     # never retrieve the same content twice
    assert _decide(c, "Thanks, great.", final=True).action == "SUPPRESS"


def test_controller_is_observable(rt):
    d = _decide(rt.controller(), "What is the per diem for trips abroad?")
    assert {"n_content", "idf_mass", "dangling", "new_content", "p_ready"} <= set(d.features)
    assert rt.controller().train_report["intent_examples"] > 50


def test_rule_controller_ablation(rt):
    c = rt.controller("rule")
    assert _decide(c, "Make your previous answer shorter", prev="x", final=True).action == "SUPPRESS"
    assert _decide(c, "The trip was international", prev="x").intent == "new_request"   # no refinement notion
