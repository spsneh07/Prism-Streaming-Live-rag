# Streaming Live RAG

**Samsung PRISM Generative AI Hackathon 2026–27 · Theme 4: Streaming Live RAG**

Real-time incremental retrieval, multi-intent decomposition and state-preserving answer refinement for full-duplex conversations. It runs entirely on CPU and makes no LLM calls by default.

> **Corpus status.** The official Theme 4 corpus was **not available** in this repository. Everything here runs on a **development / demonstration corpus**: 16 synthetic policy documents, each marked `synthetic: true`. That corpus mirrors the guide's scenarios and was written by the same author as the system. Every reported number describes that corpus only. The system is corpus-agnostic; see [§6](#6-using-the-official-corpus) for how to use the official corpus.

---

## 1. The problem

A voice user says one natural sentence, for example *"I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy and the catering options."* That sentence hides three searches. The user adds details later ("the trip was international") and sometimes only wants the last answer reformatted.

Conventional RAG handles this poorly:
- It waits for silence before doing anything.
- It sends the whole sentence as one query.
- It restarts on every follow-up.
- It searches even when a turn doesn't need it.

## 2. What this system does differently

| Capability | How | Evidence |
|---|---|---|
| **Retrieves while the user is speaking** | A per-chunk controller (two small logistic regressions plus guardrails) decides WAIT / RETRIEVE / SUPPRESS. Provisional retrieval, and even answer-sentence scoring, run during speech. | G2 in `docs/evaluation.md`; timeline in the dashboard |
| **One utterance → several searches** | Segmentation, constraint re-attachment, leading-context merge, corpus-arbitrated merge of near-duplicate intents, entity carry-over | G3 |
| **Hybrid retrieval and fusion** | MiniLM dense + BM25 → RRF → facet filter (families discovered from titles) → cross-encoder rerank → cross-sub-query fusion (coverage quota, dedup, superseded versions dropped) | Retrieval ablation |
| **Refines instead of restarting** | Refinement intent → delta-only sub-queries; prior claims and citations are kept; answer v1 → v2 with a change log | G5 |
| **Suppresses unnecessary retrieval** | Presentation-only and chit-chat turns never touch the corpus | False-trigger rate |
| **Grounded, or abstains** | Extractive claims; a validator checks that the id exists, was retrieved, and that text and numbers match; a calibrated abstention gate names the missing terms | G4, abstention accuracy |
| **Observable** | One monotonic clock for every event, delivered over SSE, in the dashboard, as JSONL and to the benchmark | G6 |

Architecture: [docs/architecture.md](docs/architecture.md) · decisions: [docs/design_decisions.md](docs/design_decisions.md).

## 3. Quick start (exact commands, verified on Windows 11 / Python 3.13)

Install:

```bash
pip install -r backend/requirements.txt
```

Optional configuration (defaults work; see `.env.example`):

```bash
cp .env.example .env
```

Model weights (~180 MB, into `data/models/`):

```bash
python scripts/download_models.py
```

Ingest the corpus and build the index:

```bash
python scripts/build_index.py
```

Calibrate the per-corpus abstention gate:

```bash
python scripts/calibrate_sufficiency.py
```

Start the backend. It also serves the dashboard at http://localhost:8000, so there is no separate frontend process:

```bash
python -m uvicorn app.main:app --app-dir backend --port 8000
```

### Demos (one command each)

| Demo | Command |
|---|---|
| 1 Early retrieval | `python scripts/demo_stream.py --scenario early_retrieval` |
| 2 Multi-intent | `python scripts/demo_stream.py --scenario multi_intent` |
| 3 Late-arriving constraint | `python scripts/demo_stream.py --scenario late_constraint` |
| 4 Retrieval suppression | `python scripts/demo_stream.py --scenario suppression` |
| 5 Insufficient evidence | `python scripts/demo_stream.py --scenario abstention` (and `abstention_full`) |
| All | `python scripts/demo_stream.py` |

The same scenarios are the numbered buttons in the dashboard. Each run prints a `PROOF retrieval_start … < utterance_end …` line.

### Tests, benchmark, reproducibility

```bash
cd backend && python -m pytest -q
```

```bash
python scripts/benchmark.py
```

```bash
python scripts/report.py
```

```bash
python scripts/reproduce.py
```

- **Tests:** 58, of which 2 are strict expected failures documenting known limitations.
- **`benchmark.py`:** runs the held-out set at real-time pacing (about 25 minutes) and writes `results/`. Use `--set dev` for the development set and `--quick` for 5× pacing.
- **`report.py`:** regenerates `docs/evaluation.md`, `docs/presentation_facts.md` and `docs/final_demo_script.md` from `results/`.
- **`reproduce.py`:** the G1 replay. It clones into an empty directory and runs index → calibration → tests → benchmark → demo.

### Docker

```bash
docker compose up --build
```

Tests and the benchmark in containers:

```bash
docker compose --profile eval run --rm tests
```

> Docker was **not available** in the development environment, so the image has **not** been built. `scripts/reproduce.py` validates it statically instead:
> - every COPY source exists;
> - the CMD target exists;
> - `.dockerignore` is present;
> - a CPU torch 2.6.0 wheel is published for cp313 / linux x86_64.
>
> G1 is therefore reported as **NOT VERIFIED**, not PASS.

## 4. Evaluation

| Set | File | Purpose |
|---|---|---|
| Controller development | `configs/controller_train.jsonl` | Trains the intent and readiness models |
| Calibration | `configs/calibration_queries.jsonl` | Fits the abstention gate (leave-one-out accuracy reported) |
| Retrieval evaluation | `data/eval/retrieval_eval.jsonl` | Dense vs BM25 vs hybrid vs hybrid + rerank |
| Development streams | `data/eval/dev_streams.jsonl` | Failure diagnosis (**not held-out**) |
| **Held-out benchmark** | `data/benchmark/heldout_streams.jsonl` | Frozen before the fixes (hash-checked, overlap-checked); all headline numbers |

Results, the six Theme 4 gates with PASS/FAIL, the ablations and every failing held-out turn are in [docs/evaluation.md](docs/evaluation.md). Slide-ready facts are in [docs/presentation_facts.md](docs/presentation_facts.md). All of it is generated from `results/`, and no number is typed by hand.

## 5. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | Create an ephemeral session |
| POST | `/api/sessions/{id}/turns` | Body `{chunks:[{t,text}], end_t?, speed?, system: proposed\|baseline}` → **SSE** stream of pipeline events |
| GET | `/api/sessions/{id}` | Answer versions and turn summaries |
| GET | `/api/sessions/{id}/telemetry` | JSONL of every event in the session |
| DELETE | `/api/sessions/{id}` | End session (memory dropped) |
| GET | `/api/chunks/{chunk_id}` | Source text, file and line range of a citation |
| GET | `/api/health` | Corpus manifest, index, reranker, controller report, gate status |

## 6. Using the official corpus

1. Put the files in `data/raw/`; subfolders are fine. Supported formats:
   - `.md`: front matter plus `#` headings; source section numbers like `## 4.2 …` or `{#id}` are kept.
   - `.txt`: headings are detected automatically.
   - `.json` / `.jsonl`: `{doc_id, title, text}` or `{doc_id, title, sections:[{section_id, title, text}]}`; ids are kept verbatim.
   - `.pdf`: one section per page (`p3`); needs PyMuPDF.
   - `.docx`: headings from paragraph styles; needs python-docx.
2. Optionally declare version relations in the source (`supersedes: ID` or `superseded_by: ID`).
3. Run `python scripts/build_index.py`.
4. Rewrite `configs/calibration_queries.jsonl` for the new corpus, then run `python scripts/calibrate_sufficiency.py`. The gate is bound to the corpus hash and is never reused across corpora.
5. Write new gold labels (`scripts/make_heldout.py`, `scripts/make_dev_set.py`, `data/eval/retrieval_eval.jsonl`), because they reference section ids. Also rewrite `configs/demo_scenarios.json`.

No controller, retrieval, synthesis or grounding code changes are needed; `backend/tests/test_corpus_agnostic.py` verifies this on a fresh JSON + TXT + PDF corpus. The controller's intent training data is conversational (speech acts), not corpus facts, but it should be spot-checked against the new domain.

## 7. Configuration

Every field in `backend/app/config.py` can be overridden as `SLRAG_<FIELD>`; see `.env.example`. No secrets are needed.

`SLRAG_LLM_PROVIDER=anthropic` (plus `ANTHROPIC_API_KEY`) switches synthesis to an LLM whose output still goes through the validator. It is off by default and was not used for any reported result.

## 8. Repository layout

```
backend/app/        controller/ decomposition/ retrieval/ reranking/ synthesis/ grounding/
                    sessions/ streaming/ telemetry/ api/ ingestion/ models/ config.py runtime.py main.py
backend/tests/      unit, integration, API, end-to-end demo, regression, corpus-agnostic, eval-set hygiene
frontend/           dashboard (index.html, app.js, style.css): served by the backend
data/raw/           development corpus        data/benchmark/  held-out set + FROZEN.md
data/eval/          dev streams, retrieval eval set
configs/            controller_train.jsonl, calibration_queries.jsonl, demo_scenarios.json
scripts/            build_index, calibrate_sufficiency, demo_stream, benchmark, report, reproduce,
                    make_heldout, make_dev_set, download_models
docs/               architecture, evaluation, design_decisions, limitations, presentation_facts,
                    final_demo_script, ai_usage_log
results/            benchmark.json/csv, latency.json, calibration.json, reproducibility.json, plots/, dev/
```

## 9. Limitations and next steps

See [docs/limitations.md](docs/limitations.md). In short:
- a synthetic, same-author corpus and benchmark;
- residual abstention-gate errors in both directions;
- a decomposer that relies on surface cues;
- extractive (not fluent) answers;
- simulated speech;
- Docker not built here.

## 10. Submission checklist

- [ ] Public GitHub repository with this README (the official reference PDFs are git-ignored; the Theme 4 guide carries a personal watermark)
- [ ] `python scripts/benchmark.py && python scripts/report.py` re-run on the final commit
- [ ] Demo video (≤ 5 min), following `docs/final_demo_script.md`
- [ ] Deck `CollegeName_TeamName.pptx` from the provided template, using `docs/presentation_facts.md`
- [ ] AI Usage Disclosure Form completed from `docs/ai_usage_log.md` (team fields filled in by the team)
- [ ] Release tag **`PRISM_GENAI_HACKATHON_Y2026`** on the final commit, created only once everything above is in that commit
