"""Calibrate the evidence-sufficiency gate on configs/calibration_queries.jsonl.

The calibration queries are disjoint from the held-out benchmark (enforced by
tests/test_eval_sets.py). Each query goes through the production path exactly as
at runtime - decomposer (cleaned clause as focus) -> hybrid + facet filter +
rerank - and three signals are recorded for its top-3 chunks:

    logit     best sentence-level cross-encoder score
    coverage  idf-weighted share of the question's key terms present (grounding/coverage.py)
    cos       best sentence cosine similarity (MiniLM)

A class-balanced logistic regression over the standardised signals is the gate
(P(sufficient) >= 0.5). Generalisation is reported with leave-one-out balanced
accuracy, not training accuracy. The gate is written to
data/processed/calibration.json with the corpus hash, so it is never applied to a
different corpus.
"""
import json

import numpy as np
from sklearn.linear_model import LogisticRegression

import _bootstrap  # noqa: F401
from app.config import get_settings
from app.models.schemas import SubQuery
from app.retrieval.service import RetrievalService
from app.runtime import Runtime

FEATURES = ["logit", "coverage", "cos"]


def features(rt, svc, syn, query: str) -> dict:
    dec = rt.decomposer.decompose(query, "c")
    sq = dec.sub_queries[0] if len(dec.sub_queries) == 1 else SubQuery("c1", query, "", query, focus=query)
    res = svc.retrieve_sync(sq)
    _, suff = syn.candidates(sq, res.candidates[:3])
    return {"logit": suff["best"], "coverage": suff["coverage"], "cos": suff["best_cos"],
            "missing": suff["missing_terms"], "focus": sq.focus}


def fit(X, y):
    mean, scale = X.mean(0), X.std(0) + 1e-9
    clf = LogisticRegression(class_weight="balanced", C=1.0, max_iter=1000).fit((X - mean) / scale, y)
    return clf, mean, scale


def balanced(pred, y):
    pos, neg = y == 1, y == 0
    tpr = float((pred[pos] == 1).mean())
    tnr = float((pred[neg] == 0).mean())
    return (tpr + tnr) / 2, tpr, tnr


def main() -> dict:
    s = get_settings()
    rt = Runtime.load()
    if rt.reranker.name == "none":
        raise SystemExit("reranker unavailable; this gate applies to the cross-encoder path only")
    svc = RetrievalService(rt.index, rt.reranker, s.top_k, rt.facets)
    syn = rt.synthesizer(True)
    rows = [json.loads(l) for l in (s.configs_dir / "calibration_queries.jsonl").read_text().splitlines() if l.strip()]
    scored = [{"query": r["query"], "answerable": r["answerable"], **features(rt, svc, syn, r["query"])} for r in rows]
    X = np.array([[x[f] for f in FEATURES] for x in scored], dtype=float)
    y = np.array([int(x["answerable"]) for x in scored])

    loo = np.zeros(len(y), dtype=int)
    for i in range(len(y)):
        m = np.arange(len(y)) != i
        clf, mean, scale = fit(X[m], y[m])
        loo[i] = int(clf.predict(((X[i] - mean) / scale)[None, :])[0])
    loo_bal, loo_tpr, loo_tnr = balanced(loo, y)

    clf, mean, scale = fit(X, y)
    train_pred = clf.predict((X - mean) / scale)
    tr_bal, _, _ = balanced(train_pred, y)
    gate = {"type": "logreg", "features": FEATURES, "coef": clf.coef_[0].round(4).tolist(),
            "intercept": round(float(clf.intercept_[0]), 4), "mean": mean.round(4).tolist(),
            "scale": scale.round(4).tolist(), "threshold": 0.5}
    for x, p in sorted(zip(scored, loo), key=lambda t: t[0]["logit"]):
        flag = "" if p == int(x["answerable"]) else "   <-- LOO error"
        print(f"{x['logit']:7.2f} cov={x['coverage']:.2f} cos={x['cos']:.2f} {'ANS' if x['answerable'] else '---'} "
              f"{x['query']}{flag}")
    summary = {"n": len(y), "loo_balanced_accuracy": round(loo_bal, 3), "loo_tpr": round(loo_tpr, 3),
               "loo_tnr": round(loo_tnr, 3), "train_balanced_accuracy": round(tr_bal, 3)}
    out = {"corpus_sha256": rt.index.meta["corpus_sha256"], "gate": gate, "summary": summary, "scores": scored}
    (s.processed_dir / "calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    s.results_dir.mkdir(parents=True, exist_ok=True)
    (s.results_dir / "calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"gate_coef": dict(zip(FEATURES, gate["coef"])), **summary}))
    return out


if __name__ == "__main__":
    main()
