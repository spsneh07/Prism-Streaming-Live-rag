# Final submission deck: notes

**File:** `SRM_Univ_Fantastic_4_Submission.pptx` (repo root) · 15 slides · 16:9 · built from the Samsung PRISM template `CollegeName_TeamName_Submission.pptx`. The template itself is left unchanged.

**Rebuild:**

```bash
python scripts/build_presentation.py
```

- The script reads every benchmark number from `results/benchmark.json`.
- It checks those numbers against `docs/presentation_facts.md`. If they disagree it stops without writing the deck.
- It needs the template file in the repo root. That file is git-ignored, so it is only present locally.
- Speaker notes are included on every slide.

**Label used for every number:** "Development benchmark · 16-document synthetic corpus". Where the space allows, the footnote adds: "held-out split, 63 cases / 77 turns · written by the system's author; not an official Samsung evaluation".

## Slide map and sources

| # | Slide | Content source |
|---|---|---|
| 1 | Title | Team details as supplied by the team; template title layout |
| 2 | Theme 4 — Streaming Live RAG | README §1, `presentation_facts.md` "Theme" |
| 3 | Existing Solutions & Gaps | `architecture.md` §1. Baseline row: `presentation_facts.md` "Existing solutions and their gap" |
| 4 | Our Solution | `architecture.md` §2. The timeline is the real Demo 2 trace from `python scripts/demo_stream.py --scenario multi_intent`: WAIT 0.00 s, RETRIEVE 0.81 s and 1.62 s, utterance end 2.11 s, lead 1.29 s |
| 5 | System Architecture | `architecture.md` §2–§10 (controller, decomposer, parallel dense + BM25, RRF, cross-encoder, validator, session store, telemetry) |
| 6 | Demo & Product Walkthrough | Real Demo 2 trace, plus the screenshot `docs/screenshots/dashboard_demo2_multi_intent.png` captured from the running app |
| 7 | From First Answer to Refined Answer | Real Demo 1 trace (retrieval at 2.83 s, utterance end at 10.30 s, lead 7.47 s) and real Demo 3 trace (v1 has 2 claims; v2 keeps those 2 and adds 4; 2 delta sub-queries). Screenshot: `dashboard_demo3_answer_v2.png` |
| 8 | Tools & Technology | `backend/requirements.txt`, `frontend/` (vanilla HTML/CSS/JS), `docker-compose.yml`. The 61 tests come from `pytest --collect-only` |
| 9 | Impact & Use Cases | Use cases are labelled "potential" and "prototype only". Metrics come from `benchmark.json` |
| 10 | Results & Evaluation | Native bar chart plus latency and trade-off cards, all from `benchmark.json`. Gate statuses come from `benchmark.json` `gates` |
| 11 | Innovation Highlights & Limitations | `presentation_facts.md` "Innovation highlights"; limitations from `docs/limitations.md` |
| 12 | What's Next | `docs/limitations.md` "Future work". Marked as planned, not implemented |
| 13 | Why Streaming Live RAG? | Conceptual sequence, not a time-to-answer claim (see the note below the metrics table) |
| 14 | Checklist | Real status. The demo video is **PENDING** |
| 15 | Thank you | Template closing slide, plus team, GitHub link and contact |

## Metrics used (all from `results/benchmark.json`, run 2026-09-29 22:05:20)

| Metric | Conventional | Streaming Live RAG |
|---|---|---|
| Early retrieval (G2) | 0% | 90% (mean lead 4.4 s) |
| Multi-intent identification (G3) | 0% | 78% |
| Refinement state continuity (G5) | 0% | 100% |
| Correct abstention on unanswerable turns | 33% | 83% |
| Citation hit rate | 73% | 73% (84% for the same pipeline without the gate) |
| Citation support (G4) / fabricated citations | 100% / 0 | 100% / 0 |
| Searches on turns that need none | 8 | 1 |
| Time to first token after speech ends, mean | 14 ms | 21 ms (187 ms without early retrieval) |
| Gates G1–G6 | | all PASS (G1 Docker verified on the development machine only) |
| Answerable held-out turns refused by the gate | | 12 of 63 |

**Trade-offs shown on the slides:**
- The baseline's time to first token is lower than ours.
- Our citation hit rate only equals the baseline's.

Slide 13 does not claim a faster answer. It shows *where* the work happens: during speech.

## Placeholders remaining
- **Demo video link** (slide 14): `[ DEMO VIDEO LINK — TO BE ADDED BY THE TEAM ]`. Replace it with the YouTube or Drive URL and change the status from PENDING to Y.

## Visual QA
- **Rendering:** every slide was rendered through PowerPoint (COM export, 1600 px) and inspected.
- **First pass:** found overflow, clipping and label collisions on slides 1, 3, 4, 5, 6, 10, 11, 13 and 14. All were fixed.
- **Second pass:** a full re-render found no remaining issues.
- **Package check:** `validate.py --original` reports PASS.
- **Placeholder check:** a text search found no template placeholders ("(Y/N)", "Member Name & Email").

## Before submitting
1. Add the demo video link on slide 14.
2. Open the deck once in PowerPoint and check that the fonts (Calibri, Arial) render as expected on the presenting machine.
3. Optionally export a PDF copy (File → Export → PDF).
