"""DEVELOPMENT set: data/eval/dev_streams.jsonl (formerly the first benchmark).

This set was used to find and diagnose failures, so it is NOT held-out any more.
The held-out benchmark is scripts/make_heldout.py -> data/benchmark/heldout_streams.jsonl.

Generated from the case list below.

Only the *timing* is generated: chunk timestamps follow a 150 words-per-minute
speaking rate (2.5 words/s) and the utterance end adds a 0.5 s end-pointing delay
(typical VAD hang-over). Utterance text, chunk boundaries and gold labels are
written by hand against the corpus in data/raw.

Gold labels are section ids ("DOC_05:S2"). ``gold`` is a list of intents; each
intent is a list of acceptable sections (any one counts as a hit).
Phrasings are deliberately different from configs/controller_train.jsonl so the
controller is evaluated on held-out utterances.
"""
import json
from pathlib import Path

WPS = 2.5
ENDPOINT = 0.5


def turn(chunks, intent="new_request", gold=None, needs_retrieval=True, unanswerable=None, earliest=None):
    t, out = 0.0, []
    for c in chunks:
        out.append({"t": round(t, 2), "text": c})
        t += len(c.split()) / WPS
    return {"chunks": out, "end_t": round(t + ENDPOINT, 2),
            "expect": {"intent": intent, "needs_retrieval": needs_retrieval, "gold": gold or [],
                       "unanswerable": unanswerable or [], "earliest_ok_chunk": earliest}}


def P(*turns):
    return list(turns)


CASES = {
    # ---------------- single intent ----------------
    "single_paraphrase_meal_allowance": ("single", P(turn(["Could you tell me", "how much the daily meal allowance", "is when travelling abroad?"], gold=[["DOC_01:S3"]]))),
    "single_intl_booking_lead": ("single", P(turn(["How far in advance", "do I have to book", "a flight to another country?"], gold=[["DOC_01:S4"]]))),
    "single_baner_rooms": ("single", P(turn(["Which rooms at", "Baner Conference Centre", "fit a group of 35?"], gold=[["DOC_03:S3"]]))),
    "single_refund_ten_days": ("single", P(turn(["What refund do we get", "if we cancel a venue", "ten days before the event?"], gold=[["DOC_05:S2"]]))),
    "single_claim_approver": ("single", P(turn(["Who has to approve", "an expense claim of", "sixty thousand rupees?"], gold=[["DOC_09:S2"]]))),
    "single_currency_conversion": ("single", P(turn(["How is money spent", "in euros converted", "when I file expenses?"], gold=[["DOC_09:S3"]]))),
    "single_cash_withdrawal": ("single", P(turn(["Is there a limit", "on how much cash", "I can withdraw with the company card abroad?"], gold=[["DOC_10:S2"]]))),
    "single_catering_lead": ("single", P(turn(["How many days", "before an event", "must catering be ordered?"], gold=[["DOC_06:S4"]]))),
    "single_vegan": ("single", P(turn(["Can we get vegan", "meals for the workshop?"], gold=[["DOC_06:S3"]]))),
    "single_after_workshop": ("single", P(turn(["What do I need to do", "after a customer workshop is over?"], gold=[["DOC_08:S4"]]))),
    "single_attendee_data": ("single", P(turn(["How long can customer", "attendee data be kept?"], gold=[["DOC_08:S3"]]))),
    "single_exec_briefing": ("single", P(turn(["Which venue in Hinjewadi", "is suitable for an executive briefing?"], gold=[["DOC_03:S4"]]))),
    "single_very_short": ("single_short", P(turn(["Sick leave?"], gold=[["DOC_11:S2"]]))),
    "single_long_irrelevant_details": ("single_long", P(turn(["So yesterday I was chatting with my manager", "over coffee, which was terrible by the way,", "and she mentioned that I could maybe", "get a new laptop, so how often", "do laptops actually get replaced here?"], gold=[["DOC_12:S2"]]))),
    "single_ambiguous_event_policy": ("ambiguous", P(turn(["What's the policy", "for the event?"], gold=[["DOC_03:S1", "DOC_05:S1", "DOC_06:S1", "DOC_08:S1", "DOC_03:S5"]]))),
    "single_paraphrase_force_majeure": ("single", P(turn(["If a hurricane shuts the venue", "do we lose our deposit?"], gold=[["DOC_05:S4"]]))),
    "single_koregaon_own_caterer": ("single", P(turn(["Does the Koregaon hall", "let us bring in", "our own caterer?"], gold=[["DOC_03:S2", "DOC_07:S2"]]))),
    "single_conflict_intl_daily_allowance": ("contradictory", P(turn(["What's the daily allowance", "under the travel policy", "for overseas trips?"], gold=[["DOC_01:S3"]]))),
    "single_conflict_claim_deadline": ("contradictory", P(turn(["What's the deadline", "to submit travel expense claims?"], gold=[["DOC_01:S2"]]))),
    "single_duplicate_vendors": ("duplicate", P(turn(["Who are the outside catering vendors", "we're allowed to use in Pune?"], gold=[["DOC_06:S1", "DOC_07:S1"]]))),
    # ---------------- compound ----------------
    "compound_guide_workshop": ("compound", P(turn(["I need to plan a customer", "workshop in Pune for 30 people,", "and I need the cancellation policy", "and the catering options."], gold=[["DOC_03:S2", "DOC_03:S3", "DOC_03:S5"], ["DOC_05:S2"], ["DOC_06:S1", "DOC_07:S1", "DOC_03:S3"]]))),
    "compound_leave": ("compound", P(turn(["How many annual leave days", "do I get, and how many", "sick days?"], gold=[["DOC_11:S1"], ["DOC_11:S2"]]))),
    "compound_laptops": ("compound", P(turn(["How often do we get new laptops", "and what should I do", "if my laptop gets stolen?"], gold=[["DOC_12:S2"], ["DOC_12:S3"]]))),
    "compound_remote": ("compound", P(turn(["Tell me the home office allowance,", "and also whether I can work", "from another country for a month."], gold=[["DOC_13:S2"], ["DOC_13:S3"]]))),
    "compound_visitors": ("compound", P(turn(["We have customers visiting", "next week; how do I register them,", "and do they need to sign an NDA?"], gold=[["DOC_16:S1"], ["DOC_16:S2"]]))),
    "compound_whitefield_budget": ("compound", P(turn(["I want to book the Whitefield suite", "for a launch, what's the lead time,", "and how much is the catering budget per person?"], gold=[["DOC_04:S3"], ["DOC_06:S2"]]))),
    "compound_three_intents": ("compound", P(turn(["What's the cancellation refund", "if we cancel a week out,", "can we reschedule instead,", "and who approves a workshop budget of ten lakh?"], gold=[["DOC_05:S2"], ["DOC_05:S3"], ["DOC_08:S2"]]))),
    "compound_partially_unanswerable": ("compound_partial", P(turn(["Which Pune venue has", "a projector, and what is", "the wifi password there?"], gold=[["DOC_03:S2"]], unanswerable=["wifi password"]))),
    "compound_card_payment": ("compound", P(turn(["How do I reconcile", "my corporate card", "and when do approved claims get paid?"], gold=[["DOC_10:S3"], ["DOC_09:S4"]]))),
    "compound_security": ("compound", P(turn(["What is the security incident reporting deadline", "and how is customer personal data classified?"], gold=[["DOC_14:S3"], ["DOC_14:S1"]]))),
    # ---------------- late-arriving detail (refinement) ----------------
    "refine_guide_travel": ("refinement", P(
        turn(["Summarize the travel", "reimbursement rule", "for an employee trip."], gold=[["DOC_01:S2"]]),
        turn(["The trip was international", "and the booking was made", "after the travel."], intent="refinement", gold=[["DOC_01:S3"], ["DOC_01:S4"]]))),
    "refine_venue_hot_lunch": ("refinement", P(
        turn(["Which Pune venue", "works for a 40 person workshop?"], gold=[["DOC_03:S2", "DOC_03:S3"]]),
        turn(["Lunch has to be", "a hot buffet."], intent="refinement", gold=[["DOC_03:S2", "DOC_03:S4", "DOC_06:S1", "DOC_07:S1"]]))),
    "refine_leave_carry_over": ("refinement", P(
        turn(["How much annual leave", "do I get?"], gold=[["DOC_11:S1"]]),
        turn(["Some of those days", "are left over from last year."], intent="refinement", gold=[["DOC_11:S1"]]))),
    "refine_cancel_lockdown": ("refinement", P(
        turn(["What is the refund", "if we cancel the venue?"], gold=[["DOC_05:S2"]]),
        turn(["It's because the city", "issued a lockdown order."], intent="refinement", gold=[["DOC_05:S4"]]))),
    "refine_claim_amount": ("refinement", P(
        turn(["How do I submit", "an expense claim?"], gold=[["DOC_09:S1"]]),
        turn(["It's for seventy", "thousand rupees."], intent="refinement", gold=[["DOC_09:S2"]]))),
    "refine_laptop_engineer": ("refinement", P(
        turn(["Can I get", "a new laptop?"], gold=[["DOC_12:S1", "DOC_12:S2"]]),
        turn(["I work in", "the engineering team."], intent="refinement", gold=[["DOC_12:S1"]]))),
    # ---------------- suppression ----------------
    "suppress_two_bullets": ("suppression", P(
        turn(["What are the", "cancellation tiers for venues?"], gold=[["DOC_05:S2"]]),
        turn(["Could you list that", "as two quick bullets?"], intent="presentation", needs_retrieval=False))),
    "suppress_trim": ("suppression", P(
        turn(["What catering options", "exist in Pune?"], gold=[["DOC_06:S1", "DOC_07:S1"]]),
        turn(["Too long,", "trim it down please."], intent="presentation", needs_retrieval=False))),
    "suppress_single_sentence": ("suppression", P(
        turn(["How many sick days", "do we get?"], gold=[["DOC_11:S2"]]),
        turn(["Condense your answer", "into a single sentence."], intent="presentation", needs_retrieval=False))),
    "suppress_plain_words": ("suppression", P(
        turn(["Explain the", "late booking rule."], gold=[["DOC_01:S4"]]),
        turn(["Put that in plain words", "for a new joiner."], intent="presentation", needs_retrieval=False))),
    "chitchat_thanks": ("chitchat", P(turn(["Great,", "appreciate it!"], intent="chitchat", needs_retrieval=False))),
    "chitchat_greeting": ("chitchat", P(turn(["Hey,", "good afternoon."], intent="chitchat", needs_retrieval=False))),
    "presentation_without_prior": ("suppression", P(turn(["Put your last answer", "in bullet points."], intent="presentation", needs_retrieval=False))),
    # ---------------- topic switch (must NOT be treated as refinement) ----------------
    "switch_parental_leave": ("topic_switch", P(
        turn(["What's the per diem", "abroad?"], gold=[["DOC_01:S3"]]),
        turn(["How many parental leave weeks", "do secondary caregivers get?"], gold=[["DOC_11:S3"]]))),
    "switch_lost_device": ("topic_switch", P(
        turn(["What caterers", "can we hire?"], gold=[["DOC_06:S1", "DOC_07:S1"]]),
        turn(["Separately, how early must", "lost devices be reported?"], gold=[["DOC_12:S3"]]))),
    # ---------------- insufficient evidence ----------------
    "insufficient_parking": ("insufficient", P(turn(["What is the parking fee", "at the Pune venues?"], unanswerable=["parking fee"]))),
    "insufficient_stock": ("insufficient", P(turn(["What is the company's", "stock price today?"], unanswerable=["stock price"]))),
    "insufficient_gym": ("insufficient", P(turn(["Does the company offer", "a gym membership?"], unanswerable=["gym membership"]))),
    "insufficient_ceo": ("insufficient", P(turn(["Who is the CEO", "of Veltrix?"], unanswerable=["CEO"]))),
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "data" / "eval" / "dev_streams.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for cid, (cat, turns) in CASES.items():
            fh.write(json.dumps({"id": cid, "category": cat, "turns": turns}) + "\n")
    print(f"wrote {len(CASES)} cases -> {out}")


if __name__ == "__main__":
    main()
