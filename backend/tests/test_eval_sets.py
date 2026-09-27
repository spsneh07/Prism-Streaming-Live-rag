"""Evaluation-set hygiene: the held-out benchmark is frozen and disjoint from
every set used for training, calibration or development."""
import hashlib
import json
import re

import numpy as np

from app.config import REPO_ROOT

FROZEN_SHA = "97f6cc37b5640ba14fd7fd43f424a9cd1ad19aa5dfaf52e1f20e7be6dc81b546"
NEAR_DUP_COSINE = 0.92


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _utterances(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            for t in json.loads(line)["turns"]:
                out.append(" ".join(c["text"] for c in t["chunks"]))
    return out


def _jsonl(path, key):
    return [json.loads(l)[key] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_heldout_is_frozen():
    body = (REPO_ROOT / "data" / "benchmark" / "heldout_streams.jsonl").read_bytes()
    assert hashlib.sha256(body).hexdigest() == FROZEN_SHA, "held-out set changed - see data/benchmark/FROZEN.md"


def test_heldout_disjoint_from_other_sets(rt):
    held = _utterances(REPO_ROOT / "data" / "benchmark" / "heldout_streams.jsonl")
    others = (
        [r["text"] for r in map(json.loads, (REPO_ROOT / "configs" / "controller_train.jsonl").read_text().splitlines())
         if r["kind"] == "intent"]
        + [" ".join(r["chunks"]) for r in map(json.loads, (REPO_ROOT / "configs" / "controller_train.jsonl").read_text().splitlines())
           if r["kind"] == "readiness"]
        + _jsonl(REPO_ROOT / "configs" / "calibration_queries.jsonl", "query")
        + _utterances(REPO_ROOT / "data" / "eval" / "dev_streams.jsonl")
        + _jsonl(REPO_ROOT / "data" / "eval" / "retrieval_eval.jsonl", "query")
    )
    assert not {_norm(h) for h in held} & {_norm(o) for o in others}
    H = rt.embedder.encode(held)
    O = rt.embedder.encode(others)
    sims = H @ O.T
    i, j = np.unravel_index(sims.argmax(), sims.shape)
    assert sims.max() < NEAR_DUP_COSINE, f"near-duplicate: {held[i]!r} ~ {others[j]!r} ({sims.max():.3f})"
