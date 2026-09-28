# Final runbook

Exact commands to set up, run, demo, test, benchmark and publish the Streaming Live RAG prototype.

- **Run location:** every command runs from the repository root unless it says otherwise.
- **Shells:** commands work in PowerShell, Command Prompt and bash unless a variant is given.
- **Verified on:** Windows 11, Python 3.13.7, CPU only, and Docker Desktop 29.8.1.

> All results are from a **development benchmark on a 16-document synthetic corpus**, not an official Samsung benchmark.

## A. Setup

Requirements:
- Python 3.13 (the only version verified; the pins target it);
- Git;
- about 3 GB of disk space;
- network access for the first model download.

Clone the repository:

```bash
git clone <REPOSITORY_URL> streaming-live-rag
cd streaming-live-rag
```

Optional virtual environment. On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the pinned dependencies:

```bash
pip install -r backend/requirements.txt
```

Optional configuration: copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`). The defaults work, no secrets are needed, and no LLM is called.

## B. Model preparation

Downloads the MiniLM embedder and the MiniLM cross-encoder (about 180 MB) into `data/models/`, which is git-ignored:

```bash
python scripts/download_models.py
```

## C. Corpus and index preparation

Ingest `data/raw/` and build the dense and BM25 index (into `data/processed/`):

```bash
python scripts/build_index.py
```

Fit the per-corpus abstention gate (writes `data/processed/calibration.json` and `results/calibration.json`):

```bash
python scripts/calibrate_sufficiency.py
```

To use a different corpus, see README §6. You must rebuild, recalibrate and rewrite the gold labels.

## D. Starting the backend

```bash
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Health check, from a second terminal:

```bash
curl http://localhost:8000/api/health
```

In Windows PowerShell, use `Invoke-RestMethod http://localhost:8000/api/health`.

Docker alternative (builds the models, index and calibration into the image; the first build takes several minutes):

```bash
docker compose up --build
```

## E. Running the dashboard

1. Start the backend (section D) and open http://localhost:8000.
2. Leave **System** set to *Streaming Live RAG* and **Pace** set to *real time*.
3. The buttons run demos 1 to 5 and 5b. **Baseline** in the System menu runs conventional RAG for comparison.
4. To stop the server, press Ctrl+C in its terminal. With Docker, run `docker compose down`.

## F. Running each demo (terminal, no browser needed)

Each command prints the event stream, the answer with citations and a `PROOF` line. Add `--speed 4` to run faster than real time.

```bash
python scripts/demo_stream.py --scenario early_retrieval
```

```bash
python scripts/demo_stream.py --scenario multi_intent
```

```bash
python scripts/demo_stream.py --scenario refinement
```

```bash
python scripts/demo_stream.py --scenario suppression
```

```bash
python scripts/demo_stream.py --scenario insufficient_evidence
```

To run all scenarios, including `insufficient_evidence_full`:

```bash
python scripts/demo_stream.py
```

On Windows, if the console shows garbled `§` or arrow characters, set UTF-8 output first. In PowerShell:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

## G. Running tests

```bash
cd backend
python -m pytest -q
cd ..
```

Expected result: **60 passed, 1 xfailed**. The expected failure is strict and documents a known intent-classifier near-miss.

In Docker, after `docker compose build`:

```bash
docker compose --profile eval run --rm tests
```

## H. Running the benchmark

The held-out benchmark takes about 25–30 minutes at real-time pacing. Do not run other CPU-heavy work at the same time, because latencies are measured.

```bash
python scripts/benchmark.py
```

The development set only, at 5× pacing:

```bash
python scripts/benchmark.py --set dev --quick
```

Regenerate `docs/evaluation.md`, `docs/presentation_facts.md` and `docs/final_demo_script.md` from `results/`:

```bash
python scripts/report.py
```

Full clean-copy reproducibility replay (G1): it runs the local replay, then builds and starts the Docker image when the docker CLI is present. It takes about 20 minutes.

```bash
python scripts/reproduce.py --pip-dry-run
```

> The held-out set `data/benchmark/heldout_streams.jsonl` is frozen (see `data/benchmark/FROZEN.md`). Do not edit it or tune anything on it.

## I. Checking git status

```bash
git status
```

```bash
git log --oneline -5
```

The working tree must be clean before pushing. Check that no secrets, `.env`, models or reference PDFs are tracked:

```bash
git ls-files
```

## J. Final GitHub push

1. Create an **empty public** repository on GitHub, with no README or licence, so there is no initial commit to merge.
2. Add it as the remote. This repository has no remote yet.

```bash
git remote add origin https://github.com/<OWNER>/<REPOSITORY>.git
```

3. Push `main`:

```bash
git push -u origin main
```

## K. Release tag

Create the tag only once the deck, the demo video link and the AI disclosure form are final and committed:

```bash
git tag -a PRISM_GENAI_HACKATHON_Y2026 -m "PRISM GenAI Hackathon 2026 final submission"
```

```bash
git push origin PRISM_GENAI_HACKATHON_Y2026
```

To check that the tag points at the final commit:

```bash
git show --no-patch PRISM_GENAI_HACKATHON_Y2026
```
