"""HELD-OUT benchmark: data/benchmark/heldout_streams.jsonl.

Written on 2026-09-28, BEFORE the failure-mode fixes of that day, and frozen:
its sha256 is recorded in data/benchmark/FROZEN.md and checked by
tests/test_eval_sets.py. Do not edit cases after seeing results; add new cases
to the development set (make_dev_set.py) instead.

Phrasings are new: none is copied from configs/controller_train.jsonl,
configs/calibration_queries.jsonl or data/eval/dev_streams.jsonl (checked by the
same test with a normalised-text and embedding-similarity check).

Labels per turn
- intent            new_request | refinement | presentation | chitchat
- needs_retrieval   False for presentation / chit-chat turns
- gold              list of intents; each intent = acceptable "DOC:SECTION" ids
- unanswerable      parts the corpus cannot answer (abstention expected)
- earliest_ok_chunk first chunk index after which retrieval is justified
                    (WAIT is expected before it); None = not scored
Timing: 150 wpm (2.5 words/s) + 0.5 s end-pointing, as in the dev set.
"""
import hashlib
import json
from pathlib import Path

WPS, ENDPOINT = 2.5, 0.5


def turn(chunks, intent="new_request", gold=None, needs_retrieval=True, unanswerable=None, earliest=None):
    t, out = 0.0, []
    for c in chunks:
        out.append({"t": round(t, 2), "text": c})
        t += len(c.split()) / WPS
    return {"chunks": out, "end_t": round(t + ENDPOINT, 2),
            "expect": {"intent": intent, "needs_retrieval": needs_retrieval, "gold": gold or [],
                       "unanswerable": unanswerable or [], "earliest_ok_chunk": earliest}}


T = turn
CASES = {
    # ---------------- single intent ----------------
    "h_economy_rule": ("single", [T(["I'm flying to Tokyo", "for a client meeting,", "what are the rules on economy class?"], gold=[["DOC_01:S2"]], earliest=2)]),
    "h_speeding_ticket": ("single", [T(["What happens", "if I get a speeding ticket", "on a business trip,", "will I be reimbursed?"], gold=[["DOC_01:S5"]], earliest=1)]),
    "h_minibar": ("single", [T(["Can someone", "reimburse the minibar", "charges from my hotel?"], gold=[["DOC_01:S5"]], earliest=1)]),
    "h_lost_taxi_receipt": ("single", [T(["I lost a taxi receipt", "worth about twenty dollars,", "what can I do?"], gold=[["DOC_01:S5"]], earliest=0)]),
    "h_baner_biggest_room": ("single", [T(["How big is", "the biggest room", "at the Baner centre?"], gold=[["DOC_03:S3"]], earliest=2)]),
    "h_koregaon_wheelchair": ("single", [T(["Is the Koregaon venue", "accessible for wheelchair users?"], gold=[["DOC_03:S2"]], earliest=0)]),
    "h_baner_deposit": ("single", [T(["Do we need to pay", "a deposit when booking", "Baner Conference Centre?"], gold=[["DOC_03:S3"]], earliest=1)]),
    "h_internal_food_budget": ("single", [T(["How much does the company", "spend on food", "per person for an internal team event?"], gold=[["DOC_06:S2"]], earliest=1)]),
    "h_vegetarian": ("single", [T(["Is vegetarian food", "always included", "in catering orders?"], gold=[["DOC_06:S3"]], earliest=0)]),
    "h_legal_review": ("single", [T(["Does a customer workshop", "that sponsors customer travel", "need legal to look at it?"], gold=[["DOC_08:S2"]], earliest=1)]),
    "h_feedback_survey": ("single", [T(["When should the feedback survey", "go out after a workshop?"], gold=[["DOC_08:S4"]], earliest=0)]),
    "h_rejected_claim": ("single", [T(["If my claim gets rejected,", "can I fix it", "and send it again?"], gold=[["DOC_09:S4"]], earliest=0)]),
    "h_audit_share": ("single", [T(["What percentage of claims", "does Finance audit", "every month?"], gold=[["DOC_09:S2"]], earliest=1)]),
    "h_unreconciled": ("single", [T(["What happens", "if my card transactions", "stay unreconciled for two months?"], gold=[["DOC_10:S3"]], earliest=1)]),
    "h_rollover_days": ("single", [T(["How many unused leave days", "roll over into next year?"], gold=[["DOC_11:S1"]], earliest=0)]),
    "h_non_eng_laptop": ("single", [T(["How much memory", "will my laptop have", "if I'm not in engineering?"], gold=[["DOC_12:S1"]], earliest=1)]),
    "h_stolen_phone": ("single", [T(["How soon do I need", "to tell IT", "that my device was stolen?"], gold=[["DOC_12:S3"]], earliest=1)]),
    "h_probation_wfh": ("single", [T(["Can new hires", "still on probation", "work from home?"], gold=[["DOC_13:S1"]], earliest=1)]),
    "h_personal_laptop": ("single", [T(["Is it okay to copy", "confidential files", "onto my personal laptop?"], gold=[["DOC_14:S2"]], earliest=1)]),
    "h_long_booking": ("single", [T(["How long can a meeting room", "be booked before", "facilities needs to approve it?"], gold=[["DOC_15:S1"]], earliest=0)]),
    "h_late_checkin": ("single", [T(["How long is a booked meeting room", "held if we're late", "to check in?"], gold=[["DOC_15:S3"]], earliest=0)]),
    "h_guest_accompany": ("single", [T(["Do customer guests", "have to be accompanied", "inside secure areas?"], gold=[["DOC_16:S3"]], earliest=1)]),
    "h_short_parental": ("single_short", [T(["Parental leave?"], gold=[["DOC_11:S3"]])]),
    "h_short_stolen": ("single_short", [T(["Laptop stolen?"], gold=[["DOC_12:S3"]])]),
    "h_long_rambling": ("single_long", [T(["Okay so my team lead is out this week and I'm covering,", "and there's this whole mess with the quarterly numbers,", "but what I actually need to know is", "how many days ahead I should book a domestic flight."], gold=[["DOC_01:S4"]], earliest=3)]),
    "h_ambiguous_approval": ("ambiguous", [T(["What's the approval", "I need?"], gold=[["DOC_08:S2", "DOC_09:S2", "DOC_01:S3", "DOC_01:S4", "DOC_15:S1", "DOC_13:S1"]])]),
    "h_para_venue_closes": ("paraphrase", [T(["If the venue itself closes down,", "do we still get our money back?"], gold=[["DOC_05:S4"]], earliest=0)]),
    "h_para_move_date": ("paraphrase", [T(["Can we move the event date", "instead of cancelling it outright?"], gold=[["DOC_05:S3"]], earliest=0)]),
    "h_conflict_filing_window": ("contradictory", [T(["How much time do I have", "to file expenses", "after coming back from a trip?"], gold=[["DOC_01:S2"]], earliest=1)]),
    "h_conflict_late_signoff": ("contradictory", [T(["Who signs off", "on a flight booked", "after the trip already happened?"], gold=[["DOC_01:S4"]], earliest=1)]),
    "h_duplicate_outside_caterer": ("duplicate", [T(["Can we hire an outside caterer,", "or must we use the venue's own kitchen?"], gold=[["DOC_06:S1", "DOC_07:S1", "DOC_07:S2", "DOC_03:S2", "DOC_03:S3"]], earliest=0)]),
    # ---------------- compound ----------------
    "h_c_training_day": ("compound", [T(["For a training day in Pune", "with about 50 people,", "which venue fits,", "and how early do I need to request it?"], gold=[["DOC_03:S2", "DOC_03:S3"], ["DOC_03:S5"]], earliest=0)]),
    "h_c_card": ("compound", [T(["Who qualifies for a company credit card,", "and is there a ceiling on money", "I can take out at ATMs on international trips?"], gold=[["DOC_10:S1"], ["DOC_10:S2"]], earliest=0)]),
    "h_c_claims_pay_fx": ("compound", [T(["When are expense claims paid out,", "and at what exchange rate", "are foreign purchases converted?"], gold=[["DOC_09:S4"], ["DOC_09:S3"]], earliest=0)]),
    "h_c_security": ("compound", [T(["How should confidential data be shared", "outside the company,", "and how fast must a breach be reported?"], gold=[["DOC_14:S2"], ["DOC_14:S3"]], earliest=0)]),
    "h_c_catering": ("compound", [T(["What's the lead time for catering", "for 60 guests,", "and what's the per head budget", "for a customer workshop?"], gold=[["DOC_06:S4"], ["DOC_06:S2"]], earliest=0)]),
    "h_c_hinjewadi": ("compound", [T(["I'm planning a design sprint in Hinjewadi;", "can we serve hot lunch there,", "and what's the refund", "if we cancel three days before?"], gold=[["DOC_03:S4"], ["DOC_05:S2"]], earliest=0)]),
    "h_c_leave": ("compound", [T(["How many weeks of leave", "does a secondary caregiver get,", "and how many annual leave days", "can I carry forward?"], gold=[["DOC_11:S3"], ["DOC_11:S1"]], earliest=1)]),
    "h_c_cross_doc": ("compound", [T(["Which Bengaluru venue seats 30,", "and do customer visitors", "need to be registered in advance?"], gold=[["DOC_04:S2"], ["DOC_16:S1"]], earliest=0)]),
    "h_c_partial": ("compound_partial", [T(["What's the international per diem,", "and which hotel chain", "do we have a discount with?"], gold=[["DOC_01:S3"]], unanswerable=["hotel chain discount"], earliest=0)]),
    "h_c_three": ("compound", [T(["How long do laptops last before replacement,", "how much is the home office allowance,", "and can I work from abroad for three weeks?"], gold=[["DOC_12:S2"], ["DOC_13:S2"], ["DOC_13:S3"]], earliest=0)]),
    # ---------------- late-arriving detail ----------------
    "h_r_flight_germany": ("refinement", [
        T(["What's the rule", "for booking flights?"], gold=[["DOC_01:S4", "DOC_01:S2"]], earliest=1),
        T(["Oh, it's a flight", "to Germany."], intent="refinement", gold=[["DOC_01:S3", "DOC_01:S4"]])]),
    "h_r_seventy_attendees": ("refinement", [
        T(["What venues can I use", "for an event in Pune?"], gold=[["DOC_03:S1", "DOC_03:S2", "DOC_03:S3", "DOC_03:S4"]], earliest=0),
        T(["We'll have around", "seventy attendees."], intent="refinement", gold=[["DOC_03:S3", "DOC_03:S5"]])]),
    "h_r_gluten": ("refinement", [
        T(["How does catering work", "for our events?"], gold=[["DOC_06:S1", "DOC_07:S1"]], earliest=0),
        T(["A few guests", "are gluten intolerant."], intent="refinement", gold=[["DOC_06:S3"]])]),
    "h_r_dollars": ("refinement", [
        T(["Who approves", "my expense claim?"], gold=[["DOC_09:S2"]], earliest=1),
        T(["Some of it", "was paid in dollars."], intent="refinement", gold=[["DOC_09:S3", "DOC_01:S3"]])]),
    "h_r_customer_data": ("refinement", [
        T(["How do I report", "a lost laptop?"], gold=[["DOC_12:S3"]], earliest=1),
        T(["It had customer data", "on it."], intent="refinement", gold=[["DOC_14:S1", "DOC_14:S2", "DOC_14:S3"]])]),
    "h_r_dubai": ("refinement", [
        T(["Can I work remotely?"], gold=[["DOC_13:S1"]]),
        T(["I'd be working", "from Dubai for a month."], intent="refinement", gold=[["DOC_13:S3"]])]),
    "h_r_twelve_days": ("refinement", [
        T(["Tell me what money we lose", "when a venue booking is called off."], gold=[["DOC_05:S2"]], earliest=1),
        T(["It would be", "just under two weeks out."], intent="refinement", gold=[["DOC_05:S2"]])]),
    # ---------------- suppression ----------------
    "h_s_one_line": ("suppression", [
        T(["What are the rules", "on customer attendee data?"], gold=[["DOC_08:S3"]], earliest=1),
        T(["Summarise that", "in one line."], intent="presentation", needs_retrieval=False)]),
    "h_s_list": ("suppression", [
        T(["What does the Koregaon hall offer?"], gold=[["DOC_03:S2"]]),
        T(["Give me the key points", "as a list."], intent="presentation", needs_retrieval=False)]),
    "h_s_briefly": ("suppression", [
        T(["How does the approval workflow", "for claims work?"], gold=[["DOC_09:S2"]], earliest=0),
        T(["Can you say that", "more briefly?"], intent="presentation", needs_retrieval=False)]),
    "h_s_reword_customer": ("suppression", [
        T(["What can't I claim", "on a business trip?"], gold=[["DOC_01:S5"]], earliest=1),
        T(["Reword that", "so a customer could understand it."], intent="presentation", needs_retrieval=False)]),
    "h_s_hear_again": ("suppression", [
        T(["What are the data classes?"], gold=[["DOC_14:S1"]]),
        T(["Could I hear that", "one more time?"], intent="presentation", needs_retrieval=False)]),
    "h_chitchat_thanks": ("chitchat", [T(["Awesome,", "thanks a lot!"], intent="chitchat", needs_retrieval=False)]),
    "h_chitchat_morning": ("chitchat", [T(["Morning!", "How's your day going?"], intent="chitchat", needs_retrieval=False)]),
    "h_presentation_no_prior": ("suppression", [T(["Turn your previous reply", "into a table."], intent="presentation", needs_retrieval=False)]),
    # ---------------- topic switch ----------------
    "h_switch_visitors": ("topic_switch", [
        T(["How much sick leave do I get?"], gold=[["DOC_11:S2"]]),
        T(["Different question,", "how early must visitors be registered?"], gold=[["DOC_16:S1"]], earliest=1)]),
    "h_switch_laptops": ("topic_switch", [
        T(["Which food vendors can we book in Pune?"], gold=[["DOC_06:S1", "DOC_07:S1"]]),
        T(["Unrelated,", "after how many years do we get new computers?"], gold=[["DOC_12:S2"]], earliest=1)]),
    # ---------------- insufficient evidence ----------------
    "h_i_salary": ("insufficient", [T(["What's the annual", "salary increment?"], unanswerable=["salary increment"])]),
    "h_i_coffee": ("insufficient", [T(["Is there free coffee", "in the Pune office?"], unanswerable=["free coffee"])]),
    "h_i_domestic_meals": ("insufficient", [T(["What is the meal allowance", "for domestic trips?"], unanswerable=["domestic meal allowance"])]),
    "h_i_events_head": ("insufficient", [T(["Who is the head", "of the Events desk?"], unanswerable=["head of events desk"])]),
    "h_i_baner_parking": ("insufficient", [T(["How many parking spots", "does Baner Conference Centre have?"], unanswerable=["parking spots"])]),
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "data" / "benchmark" / "heldout_streams.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps({"id": cid, "category": cat, "turns": turns}) + "\n" for cid, (cat, turns) in CASES.items())
    out.write_bytes(body.encode("utf-8"))   # LF endings on every OS so the frozen hash is stable
    print(f"wrote {len(CASES)} cases / {sum(len(t) for _, t in CASES.values())} turns -> {out}")
    print("sha256", hashlib.sha256(body.encode()).hexdigest())


if __name__ == "__main__":
    main()
