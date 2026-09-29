# AI usage log

This log feeds the *LangAI 3.0 AI Usage Disclosure Form* (`LangAI3.0_AI_Disclosure.docx`, section 4). For each feature it records: feature name; Self-Generated / AI-Generated / Both; and a description covering the AI tool/platform, prompt used, output summary and modifications.

> **Status:** AI tools, primarily Claude Code, were used during development for coding assistance, debugging, documentation, testing and development support. The team provided the requirements and project direction, reviewed the outputs, tested the implementation and finalized the submitted system. The submitted prototype does not need AI as an external runtime service.

## Sessions
| # | Date | Tool / platform | Prompt used (keep a copy with the submission) | Scope |
|---|---|---|---|---|
| 1 | 2026-09-27 | Claude Code (Anthropic), model Claude Opus 5.5, desktop app | Team "master prompt": act as lead engineer; read the four reference files; build, test, benchmark and document a working Theme 4 prototype | Initial system, synthetic corpus, first benchmark, docs |
| 2 | 2026-09-28 | same | Team "hackathon-ready" prompt: official corpus first; remove synthetic-corpus assumptions; separate evaluation sets; six gates; ablations; fix failure modes generically; streaming demo polish; reproducibility; GitHub preparation; AI disclosure; presentation support | Everything marked "(s2)" below |
| 3 | 2026-09-28 | same | Team "final release / QA" prompt: freeze held-out; improve abstention using development data only; verify gates; Docker / clean-clone checks; line-ending and hash integrity; regression tests; demo verification; timing methodology; document consistency; release checklist; no tag | Everything marked "(s3)" below |
| 4 | 2026-09-28 | same | Team "final submission packaging" prompt: stop feature development; repository audit; document consistency; demo verification; Docker verification once Docker Desktop was installed; runbook, submission checklist, 5-minute demo script, judge-safe presentation facts | Docker build/run verification (G1), packaging documents; no change to system behaviour or the held-out set |
| 5 | 2026-09-29 – 2026-09-30 | same | Team prompts: build the final submission PPT from the Samsung template; check the system against the Theme 4 guide and fix the gaps; fill the AI disclosure form | Items marked "(s5)" below; one held-out re-run, published unchanged |

## Team-specific fields: TO BE FILLED BY THE TEAM
- **Team name:** Team Fantastic 4
- **Project name:** Streaming Live RAG
- **Institution:** SRM University / SRM Institute of Science & Technology
- **Team members (names, roles, contact):** Sneh Prasad (sp0701@srmist.edu.in), Purva Jain (pj8602@srmist.edu.in), Agadh Khanolkar (ak1920@srmist.edu.in), Srushti More (sm1436@srmist.edu.in)
- **Representative:** Sneh Prasad, Team Lead
- **Signature:** see signed disclosure form
- **Date:** 30 September 2026
- **Purpose of AI usage (form section 3):**
  - Code generation: yes, see the table below.
  - Idea generation, UI/UX, content creation, data analysis, testing/debugging: the team must confirm each one.

## Feature origin classification
| # | Feature | Classification | Output summary | Human modifications |
|---|---|---|---|---|
| 1 | Development corpus (`data/raw/`, 16 docs, marked synthetic) | Both | Fictional policy documents shaped after the Theme 4 guide's examples | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 2 | Format-agnostic ingestion (md/txt/json/jsonl/pdf/docx, source section ids) (s2) | Both | `ingestion/loader.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 3 | Hybrid retrieval (dense + BM25 + RRF), search cache (s2) | Both | `retrieval/index.py`, `bm25.py`, `embedder.py`, `text.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 4 | Cross-encoder reranker, facet filter | Both | `reranking/rerankers.py`, `retrieval/facets.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 5 | Retrieval controller, incl. new features (s2) | Both | Two logistic regressions + guardrails; training data `configs/controller_train.jsonl` written by the agent | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 6 | Multi-intent decomposer, incl. context merge and focus span (s2) | Both | `decomposition/decomposer.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 7 | Evidence fusion | Both | `retrieval/fusion.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 8 | Streaming engine, speculative synthesis prep (s2), refinement, suppression | Both | `streaming/engine.py`, `synthesis/restructure.py`, `sessions/store.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 9 | Extractive synthesis and calibrated abstention gate (coverage + LR) (s2) | Both | `synthesis/extractive.py`, `grounding/coverage.py`, `scripts/calibrate_sufficiency.py`, `configs/calibration_queries.jsonl` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 10 | Grounding / citation validator | Both | `grounding/validator.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 11 | Optional LLM synthesizer (not used for results) | AI-Generated | `synthesis/llm.py` | not used for submitted results |
| 12 | Telemetry, SSE API | Both | `telemetry/events.py`, `api/routes.py`, `main.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 13 | Dashboard (6 cards, timeline, proof banner) (s2) | Both | `frontend/` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 14 | Evaluation sets: held-out, dev, retrieval-eval (s2) | Both | `scripts/make_heldout.py`, `scripts/make_dev_set.py`, `data/eval/retrieval_eval.jsonl`, `data/benchmark/FROZEN.md` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 15 | Baseline, benchmark harness, gates, plots, reports (s2) | Both | `streaming/baseline.py`, `scripts/benchmark.py`, `scripts/report.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 16 | Reproducibility replay (s2) | Both | `scripts/reproduce.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 17 | Tests (61, incl. regression, corpus-agnostic, eval-set hygiene) | Both | `backend/tests/` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 18 | Packaging and documentation | Both | Dockerfile, compose, `.dockerignore`, README, `docs/*` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 19 | Abstention gate refit on development data, weak-evidence band (inactive) (s3) | Both | `scripts/calibrate_sufficiency.py`, `synthesis/extractive.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 20 | TTFT definition fix, utterance-end lag check, held-out run history (s3) | Both | `streaming/engine.py`, `streaming/baseline.py`, `scripts/benchmark.py`, `scripts/report.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 21 | Hardened clean-copy replay (offline, empty model cache, all demos, server smoke test) (s3) | Both | `scripts/reproduce.py`, `scripts/_smoke_server.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 22 | Release checklist, regression tests, `.gitattributes` (s3) | Both | `docs/release_checklist.md`, `backend/tests/test_regressions.py`, `.gitattributes` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 23 | Docker verification in the clean-copy replay; shared G1 gate rule; home-directory redaction in the replay report (s4) | Both | `scripts/reproduce.py`, `scripts/_gates.py`, `scripts/benchmark.py`, `scripts/report.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 24 | Final packaging documents: runbook, submission checklist, 5-minute demo script, judge-safe presentation facts (s4) | Both | `docs/FINAL_RUNBOOK.md`, `docs/submission_checklist.md`, `scripts/report.py` (generates `final_demo_script.md`, `presentation_facts.md`) | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 25 | Quantity-constraint check ("for 30 people"), ablation row, run-history labels (s5) | Both | `retrieval/constraints.py`, `retrieval/service.py`, `synthesis/extractive.py`, `scripts/benchmark.py`, `scripts/report.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 26 | Guide-format output record in `TURN_SUMMARY` (s5) | Both | `streaming/engine.py` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |
| 27 | Submission deck, dashboard screenshots, filled AI disclosure form (s5) | Both | `scripts/build_presentation.py`, `SRM_Univ_Fantastic_4_Submission.pptx`, `docs/screenshots/`, `docs/final_ppt_notes.md`, `SRM_Univ_Fantastic_4_AI_Disclosure.docx` | Reviewed and validated by the team through tests, benchmark runs and demo verification. |

## Disclosure notes for the jury
- **Evaluation independence:** the corpus, all evaluation sets and their gold labels were written by the same AI agent that built the system. The held-out set was frozen before the failure fixes, but it is not independent.
- **No hand-entered results:** every number in `results/` and in the generated docs (`evaluation.md`, `presentation_facts.md`, `final_demo_script.md`) comes from scripts.
- **No LLM API calls:** none were made during development or evaluation.
- **No outside knowledge in answers:** answers are sentences extracted from `data/raw/`. The models only embed, rank and classify.
- **Reference material not redistributed:** the official reference PDFs, the template and the form are git-ignored.
