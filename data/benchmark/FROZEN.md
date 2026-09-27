# Held-out benchmark: frozen

| File | Cases / turns | sha256 | Frozen on |
|---|---|---|---|
| `heldout_streams.jsonl` | 63 / 77 | `97f6cc37b5640ba14fd7fd43f424a9cd1ad19aa5dfaf52e1f20e7be6dc81b546` | 2026-09-28 |

## Rules
- **When it was written:** after the first development run, and *before* any of the failure-mode fixes were implemented. None of those fixes were tried against this file.
- **When it is run:** once, after the fixes are complete. Whatever it reports is published, including failures.
- **No edits after results:** cases and labels are never changed after seeing results. New cases go into the development set (`scripts/make_dev_set.py`).
- **Enforcement:** `backend/tests/test_eval_sets.py` fails if the file's hash changes or if it overlaps with the controller training, calibration or development sets.

## Caveat
The same author (the AI agent) wrote the corpus, the system and this set. That makes it held-out from tuning, but not independent. The official Samsung held-out replay set remains the real test.

## Change made at freeze time (before any results)
The overlap test flagged five utterances with cosine ≥ 0.87 to the development or controller training sets; the closest was 0.95. They were rephrased, and the file was re-hashed with LF line endings. No benchmark run had been made on this file at that point.
