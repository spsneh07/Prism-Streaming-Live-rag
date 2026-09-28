# Release checklist

Final-release QA for the Theme 4 Streaming Live RAG submission, run on 2026-09-28 on the development machine (Windows 11, Python 3.13.7, CPU only; see `results/environment.json`). Each item states what was run and what was observed. "NOT VERIFIED" means the check could not be run here, not that it passed.

| # | Item | How it was checked | Status |
|---|---|---|---|
| 1 | Held-out set unchanged | `backend/tests/test_eval_sets.py` checks sha256 `97f6cc37…81b546` (recorded in `data/benchmark/FROZEN.md`) and the overlap with the other sets | PASS |
| 2 | No tuning on the held-out set | Abstention gate refitted on 116 development examples only (56 calibration + 60 dev sub-queries); config frozen before the held-out run (D23, D24) | PASS |
| 3 | Held-out benchmark re-run on the final gate | `python scripts/benchmark.py` on commit `22820e4`, completed 18:38:33. G2–G6 PASS (G1 is recomputed from the latest replay, see 8). Later commits change only reporting, packaging and replay code, not system behaviour | PASS |
| 4 | Every completed held-out run published | Run history in `docs/evaluation.md` §5 reads commit `4b4a0ba` from git. One run was interrupted before writing results (its process was killed when a development session ended); this is disclosed there | PASS |
| 5 | Generated docs match `results/` | `python scripts/report.py` regenerates `evaluation.md`, `presentation_facts.md` and `final_demo_script.md` | PASS |
| 6 | Test suite | `cd backend && python -m pytest -q`: 61 collected, 60 passed, 1 strict expected failure (`test_plain_words_request_is_presentation`), 0 failed, 0 skipped | PASS |
| 7 | Clean-copy replay (G1, local part) | `python scripts/reproduce.py --pip-dry-run`, latest run started 20:52:54: every step ok (index, calibration, tests, quick dev benchmark, all 5 demos, backend smoke test), pip dry run PASS, no pin mismatches. Model weights copied from local `data/models/`, so the download step is not exercised | PASS |
| 8 | Docker image builds and starts (G1) | `python scripts/reproduce.py --pip-dry-run` on Docker Desktop 29.8.1 (Windows 11, Linux engine), run started 20:52:54: `docker compose build --no-cache` ok (models downloaded inside the image), `docker compose up -d app` ok, `/api/health` and the dashboard served by the container, `docker compose --profile eval run --rm tests` 60 passed / 1 xfailed, `docker compose down` ok. One machine only | PASS |
| 9 | Demos from the CLI | `python scripts/demo_stream.py --scenario <name>` for `early_retrieval`, `multi_intent`, `refinement`, `suppression`, `insufficient_evidence`, `insufficient_evidence_full`: all exit 0 and print a PROOF line; refinement reaches v2 with 0 prior sub-queries re-searched; suppression makes 0 retrieval calls; both insufficient-evidence scenarios name the missing terms | PASS |
| 10 | Demos in the dashboard | `python -m uvicorn app.main:app --app-dir backend --port 8000`; all six buttons run at real-time pace with the expected proof banner, 0 fabricated citation ids, and no browser-console or server errors | PASS |
| 11 | README | Scenario names, test count, clean-clone order (install → download models → build index → calibrate → run), Docker verified on one machine only, limitations (abstention trade-off, synthetic corpus) | PASS |
| 12 | Stale numbers | Searched README and `docs/` for old test counts, old scenario names and the old 56-query / 0.88 gate figures; fixed in README, `limitations.md`, `ai_usage_log.md` and a `config.py` comment | PASS |
| 13 | Secrets and large files | `git ls-files` scanned for key/token patterns and files > 5 MB before committing; `.env`, reference PDFs, `data/models`, `data/processed` and `results/telemetry` are git-ignored | PASS |
| 14 | Demo 5 off-target supporting sentence | Cross-encoder scores inspected (correct sentence 7.7, off-target 2.7, both positive). No corpus-independent rule separates them without a new tuned threshold, so behaviour was left unchanged and documented in `limitations.md` | Documented |
| 15 | Packaging documents | `docs/FINAL_RUNBOOK.md`, `docs/submission_checklist.md`, 5-minute `final_demo_script.md`, judge-safe `presentation_facts.md` (benchmark and corpus on every metric) | PASS |
| 16 | Personal data in tracked files | Local username removed from `results/reproducibility.json` (`reproduce.py` now writes `~`); still present in that file in earlier commits | PASS (history not rewritten) |
| 17 | Release tag | Not created. It is created by the team, on the final commit, only after the deck, video and disclosure form are done | Pending (team) |

## Known limitations carried into the release
- Synthetic, same-author 16-document development corpus; no official corpus or official held-out replay.
- Abstention trade-off: on the held-out set the gate raises correct abstention to 83% (baseline 33%) but refuses 12 of 63 answerable turns, so the citation hit rate (73%) only matches the baseline and is below the same pipeline without the gate (84%). Refitting on development data changed 0 of 77 held-out turns.
- Docker / G1 verified on the development machine only; not checked on a second machine.
- Full list: `docs/limitations.md`.
