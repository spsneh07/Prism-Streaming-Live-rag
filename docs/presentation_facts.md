# Presentation facts (auto-generated; only measured or implemented facts)

_Source: `results/benchmark.json` (2026-09-28 00:14:41), same CPU laptop, same 49-case / 61-turn benchmark for every system. Regenerate with `python scripts/report.py`._

## Theme
Theme 4, Streaming Live RAG: retrieve the right context mid-conversation from one natural command.

## Existing solutions and their gap (what the baseline measurably does)
- It waits for the end of speech before searching: early retrieval rate 0%.
- It treats a compound request as one query: multi-intent identification 0%.
- It searches on turns that don't need it: 7 retrieval calls on 7 presentation or chit-chat turns.
- It restarts on late details: only 17% of v1 citations survive into the follow-up answer.

## Our solution (implemented)
- A controller runs on every transcript chunk and decides WAIT / RETRIEVE / SUPPRESS. It uses two logistic-regression models plus guardrails; no LLM call.
- Provisional retrieval runs in the background while the user speaks, and results are reused at utterance end.
- The decomposer turns one utterance into N sub-queries, which are retrieved in parallel (hybrid dense + BM25, RRF, facet filter, cross-encoder rerank) and fused with a coverage quota, de-duplication and superseded-version handling.
- Answers are versioned: late details trigger delta-only retrieval, and prior citations are retained.
- A grounding validator checks every claim: the citation exists, was retrieved, and the text and numbers match. Unsupported claims are removed and reported as uncertainty.
- Every step emits a telemetry event on one clock, shown live in the dashboard and exported as JSONL.

## Measured results (proposed vs baseline)
| Metric | Baseline | Proposed |
|---|---|---|
| Early retrieval rate | 0% | **89%** |
| Mean retrieval start before utterance end | n/a | **3.972 s** |
| Multi-intent identification | 0% | **78%** |
| Retrieval recall@3 | 92% | **97%** |
| Answer cites a gold section | 79% | **89%** |
| Retrieval calls on no-retrieval turns | 7 | **1** |
| v1 citations kept after a late detail | 17% | **100%** |
| Citation support / fabricated citations | 100% / 0 | 100% / 0 |
| Abstention on unanswerable turns | 60% | 60% |
| TTFT after utterance end (mean) | 15 ms | 185 ms |
| LLM cost per turn | $0 | $0 |

- **Early retrieval ablation** (same pipeline, early retrieval off, 5× pacing): TTFT 411 ms → 185 ms with early retrieval.
- **Controller ablation** (rule-based controller):
  - refinement detection 0% vs 100%;
  - intent accuracy 85% vs 98%;
  - early retrieval 75% vs 89%.
- **Decomposition ablation:** multi-intent identification 0% vs 78%; citation hit 81% vs 89%.
- **Retrieval ablation** (citation hit rate): dense-only 89%, hybrid without rerank 87%, hybrid + rerank 89%.

## Innovation highlights (implemented and demonstrated)
- Retrieval timing is a learned decision per transcript chunk, with an observable reason and feature vector for every decision.
- The corpus itself arbitrates decomposition: clauses merge only when they hit the same best section, which prevents over-fragmentation.
- Delta-only refinement with answer versioning: the change log records added, retained and removed claims and why.
- Presentation-only turns never touch the corpus and cannot introduce new citations.
- Document families and facet values (e.g. city) are discovered from titles, with no hard-coded domain lists.
- An evidence-sufficiency gate calibrated on held-out queries (balanced accuracy 1.0) produces explicit "corpus does not contain enough information".

## Limitations (state these on the slide)
- The corpus and benchmark are synthetic, small and written by the same (AI) author as the system. This is a development benchmark, not the official held-out set.
- Recall@8 saturates on 57 chunks; recall@3 and citation hit rate are the discriminating metrics.
- The proposed pipeline's per-turn compute is higher than the bare baseline's, so its TTFT is higher; early retrieval is what hides it.
- Answers are extractive (grounded, not fluent). Speech input is simulated. Docker was not verified in the dev environment.

## Tech stack
Python 3.13 · FastAPI + SSE · asyncio · PyTorch CPU + Hugging Face transformers (all-MiniLM-L6-v2, ms-marco-MiniLM-L6-v2 cross-encoder) · scikit-learn · numpy · in-house BM25 / RRF · vanilla JS dashboard · pytest · matplotlib · Docker.
