# Presentation facts (auto-generated; measured or implemented facts only)

_Source: `results/benchmark.json` (2026-09-28 18:38:33); held-out set `data/benchmark/heldout_streams.jsonl` (63 cases / 77 turns); same CPU machine for every system. Regenerate with `python scripts/report.py`._

> **What these numbers are:** a *development benchmark on a 16-document synthetic corpus*, built by the team for development.
>
> **What they are not:** an official Samsung / hackathon evaluation. No official Theme 4 corpus or official benchmark was available or run. Use this wording on slides.

> **DEVELOPMENT / DEMONSTRATION corpus.** Synthetic, written by the system's author, not the official Theme 4 corpus, which was not available. All numbers below describe this corpus only.

## Theme
Theme 4, Streaming Live RAG: retrieve the right context mid-conversation from one natural command.

## Existing solutions and their gap (measured on the conventional baseline)
- It waits for the end of speech before searching: early retrieval 0%.
- It treats a compound request as one query: multi-intent identification 0%.
- It searches when nothing needs searching: 8 retrieval calls across 8 presentation or chit-chat turns.
- It restarts on late details: refinement state continuity 0%, and 29% of v1 citations kept.

## Our solution (implemented)
- **Controller:** runs on every transcript chunk and decides WAIT / RETRIEVE / SUPPRESS. Two logistic-regression models plus guardrails; no LLM on the hot path.
- **Provisional retrieval:** starts during speech, and the answer's sentence scoring is prepared before the user stops. Results are reused at utterance end.
- **Decomposition and retrieval:** one utterance becomes N sub-queries, with context entities carried across and leading context merged into the question. Each is retrieved in parallel: dense + BM25 with RRF, a facet filter derived from titles, then a cross-encoder rerank.
- **Fusion:** a coverage quota per sub-query, de-duplication, and superseded-version handling.
- **Refinement:** late details trigger delta-only retrieval and a new answer version; prior claims and citations are kept.
- **Grounding:** extractive claims plus a validator (the id exists, was retrieved, and text and numbers match), plus a calibrated abstention gate that names the missing terms.
- **Telemetry:** one monotonic clock for every event. It is shown live in the dashboard and exported as JSONL.

## Evaluation gates (held-out)
| Gate | Measured | Target | Status |
|---|---|---|---|
| G1 Reproducibility | local replay: PASS; docker: NOT VERIFIED | container launches with one command on a clean machine; replay completes unattended | NOT VERIFIED |
| G2 Early retrieval | 0.903 | >= 0.80 (low false-trigger rate on no-retrieval turns) | PASS |
| G3 Multi-intent identification | 0.778 | >= 0.70 | PASS |
| G4 Factual grounding | 1.0 support, 0 fabricated | >= 0.85 support and 0 fabricated | PASS |
| G5 Session refinement | 1.000 | 1.00 (every late constraint updates, never restarts) | PASS |
| G6 Telemetry & observability | 1.000 | 1.00 | PASS |

## Headline results: development benchmark on a 16-document synthetic corpus (held-out split): conventional RAG vs Streaming Live RAG
| Metric | Conventional | Streaming Live RAG |
|---|---|---|
| Retrieval starts before the user finishes | 0% | **90%** (mean lead 4.422 s) |
| Compound requests correctly split | 0% | **78%** |
| Answer cites a correct section | 73% | 73% |
| Retrieval recall@3 | 95% | 96% |
| Late details handled without restart | 0% | **100%** |
| Searches on turns that need none | 8 | **1** |
| Correct abstention on unanswerable turns | 33% | 83% |
| Citation support / fabricated ids | 100% / 0 | 100% / 0 |
| Time to first answer token after speech ends (mean) | 17 ms | 32 ms |
| LLM cost per turn | $0 | $0 |

## Ablations (held-out)
- **Early retrieval on vs off** (same pipeline, real time): TTFT 206 ms → 32 ms.
- **Model-based vs rule-based controller:**
  - intent accuracy 99% vs 81%;
  - refinement continuity 100% vs 0%;
  - early retrieval 90% vs 76%;
  - premature retrieval 8% vs 2%.
- **Hybrid vs dense-only** (end-to-end citation hit): hybrid + rerank 73%, hybrid without rerank 84%, dense-only 88%.
- **Retrieval-only eval, recall@1:** dense 1.0, bm25 0.9737, hybrid 1.0, hybrid+facet+rerank 0.9737.
- **Decomposition on vs off:** multi-intent 78% vs 0%; citation hit 73% vs 66%.

## Innovation highlights (implemented and demonstrated)
- Retrieval timing is a learned per-chunk decision, and each decision is logged with its reason and feature vector.
- Speculative synthesis prep: evidence sentences are scored while the user is still speaking.
- The corpus arbitrates decomposition: clauses merge only when they share the same best section.
- Delta-only refinement with versioned answers, and a change log of retained, added and removed claims.
- Presentation-only turns never touch the corpus and cannot add citations.
- Facet (e.g. city) families are discovered automatically from document titles.
- Abstention is a calibrated gate that names the concepts missing from the evidence.

## Limitations (say them on the slide)
- The corpus is a synthetic development corpus; the official Theme 4 corpus and held-out replay were not available. All sets were written by the same author as the system.
- Failing held-out turns: 26 of 77. See `docs/evaluation.md` §8.
- **Abstention trade-off.**
  - The gate refused 12 of 63 answerable held-out turns.
  - Citation hit rate is 73%: the conventional baseline scores 73%, and the same pipeline without the gate 84%.
  - Correct abstention is 83%, against 33% for the baseline.
- The proposed pipeline costs more compute per turn than bare RAG; early retrieval hides most of it.
- Answers are extractive (grounded, not fluent). Speech is simulated from transcripts.
- G1: Docker is NOT VERIFIED in the development environment.

## Tech stack
Python 3.13 · FastAPI + Server-Sent Events · asyncio · PyTorch (CPU) + Hugging Face transformers (all-MiniLM-L6-v2 embeddings, ms-marco-MiniLM-L6-v2 cross-encoder) · scikit-learn · numpy · in-house BM25 / RRF · vanilla JS dashboard · pytest · matplotlib · Docker.
