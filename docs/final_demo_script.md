# Final demo script (≤ 5 minutes)

_Numbers quoted here are read from `results/` by `scripts/report.py` (2026-09-28 02:09:21). Rehearse with the dashboard at real-time pace._

**Setup, before recording:**
1. `python -m uvicorn app.main:app --app-dir backend --port 8000`, then open http://localhost:8000.
2. Leave System on **Streaming Live RAG**, Pace **real time**.
3. The note under the scenario buttons states that this is the development corpus. Say so out loud once.

| Time | Screen | What to say |
|---|---|---|
| 0:00–0:25 | Header, proof banner | "Voice users speak one natural sentence, not a search query. Conventional RAG waits for silence, searches once, restarts on every follow-up and searches even when nothing needs searching. We built retrieval that runs *while the user is speaking*." |
| 0:25–1:15 | **Demo 1, Early retrieval** | Point at the timeline: the first chunk is **WAIT** (amber), then **RETRIEVE** (green) as soon as the request is specific. Hatched bars are provisional retrievals, refined as more words arrive. The red dashed line is utterance end. The banner states retrieval began *N seconds before the user finished*. "Across the held-out set this happens on 90% of eligible turns, with a mean lead of 4.387 s." |
| 1:15–2:05 | **Demo 2, Multi-intent** (the guide's own example) | Sub-queries card: one sentence became three searches, and "Pune" was carried into each. Evidence card: parallel retrieval, then fusion; the duplicate catering FAQ was dropped. Answer card: every sentence has a clickable citation, so click one to show the source lines. "Compound requests correctly split: 78% vs 0% for conventional RAG." |
| 2:05–2:55 | **Demo 3, Late-arriving detail** | Turn 2, "the trip was international and the booking was made after travel", is classified as a **refinement**. The sub-queries card shows *delta* queries only. The answer goes v1 → v2: grey claims are kept, green claims are new, and the version history shows the change log. "No restart: prior sub-queries re-searched = 0. State continuity 100% on held-out refinements vs 0% for the baseline." |
| 2:55–3:30 | **Demo 4, Suppression** | "Make your previous answer shorter" gives a purple **SUPPRESS** and the banner says *no corpus search*. The answer is reshaped from session memory with the same citations. "Searches on turns that need none: 1 vs 8." |
| 3:30–4:05 | **Demo 5, Insufficient evidence** | The projector part is answered with a citation. The wifi password is flagged, naming the missing terms. "We would rather abstain than guess: 0 fabricated citations, citation support 100%." |
| 4:05–4:40 | Switch System to **Baseline**, re-run Demo 2 | The banner says it waited for the utterance end, then searched once with the whole sentence. Compare the answer and the timeline. |
| 4:40–5:00 | `docs/evaluation.md` gates table | Read the gates: G1 NOT VERIFIED, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS. "The limitations are listed in the repo, starting with the synthetic development corpus." |

**Do not claim:** results on the official corpus, user studies, production latency, or LLM-quality answers. The answers are extractive.
