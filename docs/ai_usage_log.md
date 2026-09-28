# AI usage log

This log feeds the *LangAI 3.0 AI Usage Disclosure Form* (`LangAI3.0_AI_Disclosure.docx`, section 4). For each feature it records: feature name; Self-Generated / AI-Generated / Both; and a description covering the AI tool/platform, prompt used, output summary and modifications.

> **Status:** every file in this repository was produced by an AI coding agent from three team-written prompts. No human edits have been recorded yet.
> - **Human modifications:** the team must fill in that column whenever it reviews, changes or rewrites something.
> - **Classification:** switch it to *Both* only where the team actually contributed.
> - **Self-Generated:** never mark anything *Self-Generated* unless the team wrote it.

## Sessions
| # | Date | Tool / platform | Prompt used (keep a copy with the submission) | Scope |
|---|---|---|---|---|
| 1 | 2026-09-27 | Claude Code (Anthropic), model Claude Opus 5.5, desktop app | Team "master prompt": act as lead engineer; read the four reference files; build, test, benchmark and document a working Theme 4 prototype | Initial system, synthetic corpus, first benchmark, docs |
| 2 | 2026-09-28 | same | Team "hackathon-ready" prompt: official corpus first; remove synthetic-corpus assumptions; separate evaluation sets; six gates; ablations; fix failure modes generically; streaming demo polish; reproducibility; GitHub preparation; AI disclosure; presentation support | Everything marked "(s2)" below |
| 3 | 2026-09-28 | same | Team "final release / QA" prompt: freeze held-out; improve abstention using development data only; verify gates; Docker / clean-clone checks; line-ending and hash integrity; regression tests; demo verification; timing methodology; document consistency; release checklist; no tag | Everything marked "(s3)" below |

## Team-specific fields: TO BE FILLED BY THE TEAM
- **Team name:** `____`
- **Project name:** `____`
- **Institution:** `____`
- **Submission date:** `____`
- **Representative, role, signature:** `____`
- **Purpose of AI usage (form section 3):**
  - Code generation: yes, see the table below.
  - Idea generation, UI/UX, content creation, data analysis, testing/debugging: the team must confirm each one.

## Feature origin classification
| # | Feature | Classification | Output summary | Human modifications |
|---|---|---|---|---|
| 1 | Development corpus (`data/raw/`, 16 docs, marked synthetic) | AI-Generated | Fictional policy documents shaped after the Theme 4 guide's examples | _team to fill_ |
| 2 | Format-agnostic ingestion (md/txt/json/jsonl/pdf/docx, source section ids) (s2) | AI-Generated | `ingestion/loader.py` | _team to fill_ |
| 3 | Hybrid retrieval (dense + BM25 + RRF), search cache (s2) | AI-Generated | `retrieval/index.py`, `bm25.py`, `embedder.py`, `text.py` | _team to fill_ |
| 4 | Cross-encoder reranker, facet filter | AI-Generated | `reranking/rerankers.py`, `retrieval/facets.py` | _team to fill_ |
| 5 | Retrieval controller, incl. new features (s2) | AI-Generated | Two logistic regressions + guardrails; training data `configs/controller_train.jsonl` written by the agent | _team to fill_ |
| 6 | Multi-intent decomposer, incl. context merge and focus span (s2) | AI-Generated | `decomposition/decomposer.py` | _team to fill_ |
| 7 | Evidence fusion | AI-Generated | `retrieval/fusion.py` | _team to fill_ |
| 8 | Streaming engine, speculative synthesis prep (s2), refinement, suppression | AI-Generated | `streaming/engine.py`, `synthesis/restructure.py`, `sessions/store.py` | _team to fill_ |
| 9 | Extractive synthesis and calibrated abstention gate (coverage + LR) (s2) | AI-Generated | `synthesis/extractive.py`, `grounding/coverage.py`, `scripts/calibrate_sufficiency.py`, `configs/calibration_queries.jsonl` | _team to fill_ |
| 10 | Grounding / citation validator | AI-Generated | `grounding/validator.py` | _team to fill_ |
| 11 | Optional LLM synthesizer (not used for results) | AI-Generated | `synthesis/llm.py` | _team to fill_ |
| 12 | Telemetry, SSE API | AI-Generated | `telemetry/events.py`, `api/routes.py`, `main.py` | _team to fill_ |
| 13 | Dashboard (6 cards, timeline, proof banner) (s2) | AI-Generated | `frontend/` | _team to fill_ |
| 14 | Evaluation sets: held-out, dev, retrieval-eval (s2) | AI-Generated | `scripts/make_heldout.py`, `scripts/make_dev_set.py`, `data/eval/retrieval_eval.jsonl`, `data/benchmark/FROZEN.md` | _team to fill_ |
| 15 | Baseline, benchmark harness, gates, plots, reports (s2) | AI-Generated | `streaming/baseline.py`, `scripts/benchmark.py`, `scripts/report.py` | _team to fill_ |
| 16 | Reproducibility replay (s2) | AI-Generated | `scripts/reproduce.py` | _team to fill_ |
| 17 | Tests (61, incl. regression, corpus-agnostic, eval-set hygiene) | AI-Generated | `backend/tests/` | _team to fill_ |
| 18 | Packaging and documentation | AI-Generated | Dockerfile, compose, `.dockerignore`, README, `docs/*` | _team to fill_ |
| 19 | Abstention gate refit on development data, weak-evidence band (inactive) (s3) | AI-Generated | `scripts/calibrate_sufficiency.py`, `synthesis/extractive.py` | _team to fill_ |
| 20 | TTFT definition fix, utterance-end lag check, held-out run history (s3) | AI-Generated | `streaming/engine.py`, `streaming/baseline.py`, `scripts/benchmark.py`, `scripts/report.py` | _team to fill_ |
| 21 | Hardened clean-copy replay (offline, empty model cache, all demos, server smoke test) (s3) | AI-Generated | `scripts/reproduce.py`, `scripts/_smoke_server.py` | _team to fill_ |
| 22 | Release checklist, regression tests, `.gitattributes` (s3) | AI-Generated | `docs/release_checklist.md`, `backend/tests/test_regressions.py`, `.gitattributes` | _team to fill_ |

## Disclosure notes for the jury
- **Evaluation independence:** the corpus, all evaluation sets and their gold labels were written by the same AI agent that built the system. The held-out set was frozen before the failure fixes, but it is not independent.
- **No hand-entered results:** every number in `results/` and in the generated docs (`evaluation.md`, `presentation_facts.md`, `final_demo_script.md`) comes from scripts.
- **No LLM API calls:** none were made during development or evaluation.
- **No outside knowledge in answers:** answers are sentences extracted from `data/raw/`. The models only embed, rank and classify.
- **Reference material not redistributed:** the official reference PDFs, the template and the form are git-ignored.
