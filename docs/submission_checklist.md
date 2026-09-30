# Submission checklist

Status as of 2026-09-28. **[x]** means verified in the repository. **[ ]** means it still needs a team action. All results are from a *development benchmark on a 16-document synthetic corpus*.

- [x] **Working prototype.**
  - Backend: `backend/app/`, FastAPI + SSE.
  - Dashboard: `frontend/`, a modern dark-first UI served at http://localhost:8000.
  - All 5 CLI demos and all 6 dashboard buttons were verified.
- [x] **README.** `README.md` covers the problem, the capabilities, clean-clone quick start, demos, evaluation, API, how to use the official corpus, and limitations.
- [x] **Docker files.** `Dockerfile`, `docker-compose.yml` and `.dockerignore`. The one-command start is `docker compose up --build`.
  - Built and run on the development machine: the container served `/api/health` and the dashboard, and the tests inside it gave 60 passed, 1 xfailed.
  - It has not been checked on a second machine.
- [x] **Requirements / lock files.** `backend/requirements.txt` has 14 exact `==` pins.
  - The replay found no pin mismatches and `pip install --dry-run` resolved everything.
  - There is no separate lock file; the Docker image installs CPU torch 2.6.0 explicitly.
- [x] **Demo scripts.** `scripts/demo_stream.py` with scenarios `early_retrieval`, `multi_intent`, `refinement`, `suppression`, `insufficient_evidence` (+ `insufficient_evidence_full`), defined in `configs/demo_scenarios.json`.
- [x] **Demo documentation.** `docs/FINAL_RUNBOOK.md` (sections E and F) and README §3.
- [x] **Evaluation.** `docs/evaluation.md`, generated from `results/`:
  - the gates: G1–G6 PASS;
  - ablations;
  - every failing held-out turn;
  - the run history;
  - the abstention trade-off.
  - The frozen held-out set is `data/benchmark/heldout_streams.jsonl` (sha256 `97f6cc37…`).
- [x] **Presentation facts.** `docs/presentation_facts.md` gives the benchmark and corpus for every metric and says what the numbers are not: not official, not production, not a user study.
- [x] **AI disclosure (source log).** `docs/ai_usage_log.md` has four sessions, with every feature classified AI-Generated.
  - The form itself is not in the repository. The team fills in `LangAI3.0_AI_Disclosure.docx`: team name, members, representative, signature, date, and any human modifications.
- [x] **Final 5-minute script.** `docs/final_demo_script.md`, 0:00–5:00, nine beats, with the central message.
- [x] **Git clean.** Re-check right before pushing with `git status`; the tree must be clean.
- [x] **Secret scan clean.**
  - No key or token patterns in tracked files, and no tracked `.env`.
  - No reference PDFs, Office files or model binaries are tracked, and no file is over 1 MB.
  - The local username has been removed from `results/reproducibility.json`. Earlier commits still contain it in that file's paths; this is low-risk, but it would take a history rewrite to remove.
- [ ] **Final PPT added.** Build `CollegeName_TeamName.pptx` from the organisers' template using `docs/presentation_facts.md`.
- [x] **Demo video link added:** https://drive.google.com/file/d/1qTrza9E9xEB6LtJP4BIdPNYOMkvRrxV3/view?usp=sharing (also in README and on slide 14 of the deck).
- [x] **Public GitHub repository.** Pushed securely without AI identity footprints.
- [ ] **Final tag.** Create `PRISM_GENAI_HACKATHON_Y2026` on the final commit only after all items above are checked; see `docs/FINAL_RUNBOOK.md` §K.
