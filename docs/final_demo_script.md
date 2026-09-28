# Final demo script (≤ 5 minutes)

_Numbers quoted here are read from `results/` by `scripts/report.py` (2026-09-28 23:46:37). Rehearse with the dashboard at real-time pace._

**Terminal alternative (deterministic, no browser):**
- `python scripts/demo_stream.py --scenario early_retrieval`
- `python scripts/demo_stream.py --scenario multi_intent`
- `python scripts/demo_stream.py --scenario refinement`
- `python scripts/demo_stream.py --scenario suppression`
- `python scripts/demo_stream.py --scenario insufficient_evidence`

No external API is called.

**Setup, before recording:**
1. `python -m uvicorn app.main:app --app-dir backend --port 8000`, then open http://localhost:8000.
2. Leave System on **Streaming Live RAG**, Pace **real time**.
3. The note under the scenario buttons states that this is the development corpus. Say so out loud once.

**Central message (say it at 0:00 and again at 4:50):** "Retrieval begins before utterance completion, natural requests are decomposed into multiple searches, evidence is fused, and late details refine the answer without restarting the session."

| Time | Screen | What to say |
|---|---|---|
| 0:00–0:30 | **Problem**: header, empty dashboard | "Voice users speak one natural sentence, not a search query. Conventional RAG waits for silence, sends the whole sentence as one query, restarts on every follow-up, and searches even when nothing needs searching." Then the central message. Say once: "All numbers today are from a development benchmark on a 16-document synthetic corpus." |
| 0:30–1:15 | **Live partial transcript**: click **Demo 1**, watch the Live stream card | Transcript chunks arrive one at a time, as from speech recognition. After each chunk the controller decides: the first is **WAIT** (amber, not specific yet); once the request is specific it switches to **RETRIEVE** (green) and a provisional query appears. |
| 1:15–2:00 | **Early retrieval**: timeline and proof banner | The hatched bars are provisional retrievals, made while the user is still talking; the red dashed line is the utterance end. Read the banner: retrieval began *N seconds before the user finished*. "On the held-out split this happens on 90% of eligible turns, with a mean lead of 4.418 s; conventional RAG: 0%." |
| 2:00–2:45 | **Multi-intent decomposition**: **Demo 2** (the guide's own example) | Sub-queries card: one sentence became three searches, and "Pune" was carried into each. Evidence card: retrieved in parallel, then fused, with the duplicate catering FAQ dropped. Click one citation to show its source lines. "Compound requests split correctly: 78% vs 0% for conventional RAG." |
| 2:45–3:30 | **Late-arriving detail**: **Demo 3** | Turn 2 ("the trip was international and the booking was made after travel") is classified as a **refinement**. Only *delta* queries are searched. The answer goes v1 → v2: grey claims are kept, green claims are new, and the version history shows the change log. "No restart: prior sub-queries re-searched = 0. State continuity 100% vs 0% for the baseline." |
| 3:30–4:00 | **Suppression**: **Demo 4** | "Make your previous answer shorter" gives a purple **SUPPRESS**, and the banner says *no corpus search*. The answer is reshaped from session memory. "Searches on turns that need none: 1 vs 8." |
| 4:00–4:30 | **Grounding / abstention**: **Demo 5** | The projector question is answered with a citation; the wifi password is flagged, naming the missing terms. "Every claim is checked against its cited text: support 100%, 0 fabricated citations. We would rather abstain than guess." |
| 4:30–4:50 | **Metrics / telemetry**: Telemetry card (session events as JSONL), then the gates table in `docs/evaluation.md` | "Every event is on one clock and exported." Read the gates: G1 PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS. Say the trade-off: "Abstention is conservative. Correct abstention 83% vs 33%, but citation hit rate 73% vs 73% for the baseline." |
| 4:50–5:00 | **Conclusion** | Repeat the central message. "Limitations, starting with the synthetic corpus, are listed in the repository." |

**Do not claim:** results on the official corpus, official Samsung benchmark scores, user studies, production latency, or LLM-quality answers. The answers are extractive: Demo 5 also shows a second, on-topic sentence about a different room; do not present it as part of the answer. No code is shown in the video.
