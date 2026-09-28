"""Calibrate the evidence-sufficiency gate on DEVELOPMENT data only.

Never reads data/benchmark/ (the frozen held-out set).

Data (pipeline form: decomposer -> hybrid + facet filter + rerank -> sentence scoring):
  A. configs/calibration_queries.jsonl   labelled answerable / unanswerable
  B. data/eval/dev_streams.jsonl         new-request turns; each sub-query is labelled
       1  if its top-3 evidence contains a gold section of the turn,
       0  if the turn is fully unanswerable, if the sub-query names an annotated
          unanswerable span (e.g. "wifi password"), or if it misses gold in a turn that
          has unanswerable parts,
       skipped otherwise (a retrieval miss is not the gate's decision to make).

Models: class-balanced logistic regression over
  legacy : (best sentence logit, coverage, best cosine)
  full   : legacy + (mean of top-3 sentence logits, share of supporting sentences, best chunk rerank)
chosen by leave-one-GROUP-out balanced accuracy (a group = one query / one dev turn).

Three-way policy: P >= 0.5 answer; hedge <= P < 0.5 answer flagged as weak evidence;
P < hedge abstain. The hedge threshold is the lowest value on a 0.05 grid for which,
on the leave-one-group-out predictions, (a) at least 75% of the band is answerable and
(b) the band admits at most 10% of all unanswerable examples. These criteria were fixed
before looking at the result.
"""
import json

import numpy as np
from sklearn.linear_model import LogisticRegression

import _bootstrap  # noqa: F401
from app.config import REPO_ROOT, get_settings
from app.models.schemas import SubQuery
from app.retrieval.service import RetrievalService
from app.runtime import Runtime

LEGACY = ["logit", "coverage", "cos"]
FULL = ["logit", "logit_top3_mean", "n_support", "coverage", "cos", "rerank_max"]
HEDGE_MIN_PRECISION = 0.75
HEDGE_MAX_UNANSWERABLE_SHARE = 0.10


def sq_features(syn, svc, sq):
    res = svc.retrieve_sync(sq)
    top = res.candidates[:3]
    _, suff = syn.candidates(sq, top)
    return suff["features"], [c.chunk_id.rsplit(":", 1)[0] for c in top], suff["missing_terms"]


def collect(rt, svc, syn, s):
    ex = []
    for i, r in enumerate(json.loads(l) for l in (s.configs_dir / "calibration_queries.jsonl").read_text().splitlines() if l.strip()):
        dec = rt.decomposer.decompose(r["query"], "c")
        sq = dec.sub_queries[0] if len(dec.sub_queries) == 1 else SubQuery("c1", r["query"], "", r["query"], focus=r["query"])
        f, _, miss = sq_features(syn, svc, sq)
        ex.append({"group": f"cal{i}", "source": "calibration", "text": r["query"], "label": int(r["answerable"]),
                   "features": f, "missing": miss})
    dev = REPO_ROOT / "data" / "eval" / "dev_streams.jsonl"
    for case in (json.loads(l) for l in dev.read_text(encoding="utf-8").splitlines() if l.strip()):
        for ti, turn in enumerate(case["turns"]):
            e = turn["expect"]
            if e["intent"] != "new_request" or not e["needs_retrieval"]:
                continue
            utt = " ".join(c["text"] for c in turn["chunks"])
            gold = {g for intent in e["gold"] for g in intent}
            for sq in rt.decomposer.decompose(utt, "d").sub_queries:
                f, top, miss = sq_features(syn, svc, sq)
                text = (sq.focus or sq.text).lower()
                names_unanswerable = any(all(w in text for w in span.lower().split()) for span in e["unanswerable"])
                if (not gold and e["unanswerable"]) or names_unanswerable:
                    label = 0
                elif gold & set(top):
                    label = 1
                elif e["unanswerable"]:
                    label = 0
                else:
                    continue
                ex.append({"group": f"{case['id']}#{ti}", "source": "dev", "text": sq.focus or sq.text, "label": label,
                           "features": f, "missing": miss})
    return ex


def fit(X, y):
    mean, scale = X.mean(0), X.std(0) + 1e-9
    clf = LogisticRegression(class_weight="balanced", C=1.0, max_iter=2000).fit((X - mean) / scale, y)
    return clf, mean, scale


def logo_proba(X, y, groups):
    p = np.zeros(len(y))
    for g in sorted(set(groups)):
        m = np.array([gg != g for gg in groups])
        clf, mean, scale = fit(X[m], y[m])
        p[~m] = clf.predict_proba((X[~m] - mean) / scale)[:, 1]
    return p


def balanced(pred, y):
    tpr = float((pred[y == 1] == 1).mean())
    tnr = float((pred[y == 0] == 0).mean())
    return (tpr + tnr) / 2, tpr, tnr


def choose_hedge(p, y):
    n_unans = int((y == 0).sum())
    for h in [round(x, 2) for x in np.arange(0.05, 0.5, 0.05)]:
        band = (p >= h) & (p < 0.5)
        if band.sum() == 0:
            continue
        prec = float(y[band].mean())
        unans_share = float(((y == 0) & band).sum()) / max(1, n_unans)
        if prec >= HEDGE_MIN_PRECISION and unans_share <= HEDGE_MAX_UNANSWERABLE_SHARE:
            return h, prec, unans_share, int(band.sum())
    return None, None, None, 0


def main() -> dict:
    s = get_settings()
    rt = Runtime.load()
    if rt.reranker.name == "none":
        raise SystemExit("reranker unavailable; this gate applies to the cross-encoder path only")
    svc = RetrievalService(rt.index, rt.reranker, s.top_k, rt.facets)
    syn = rt.synthesizer(True)
    ex = collect(rt, svc, syn, s)
    y = np.array([e["label"] for e in ex])
    groups = [e["group"] for e in ex]
    report = {"n": len(ex), "n_answerable": int(y.sum()), "n_unanswerable": int((y == 0).sum()),
              "sources": {src: sum(1 for e in ex if e["source"] == src) for src in ("calibration", "dev")}}
    results = {}
    for name, feats in (("legacy", LEGACY), ("full", FULL)):
        X = np.array([[e["features"][f] for f in feats] for e in ex], dtype=float)
        p = logo_proba(X, y, groups)
        bal, tpr, tnr = balanced((p >= 0.5).astype(int), y)
        results[name] = {"feats": feats, "X": X, "p": p, "bal": bal, "tpr": tpr, "tnr": tnr}
        print(f"{name:7} leave-one-group-out balanced accuracy {bal:.3f} (TPR {tpr:.3f}, TNR {tnr:.3f})")
    best = max(results, key=lambda k: (round(results[k]["bal"], 3), k == "legacy"))   # tie -> simpler model
    R = results[best]
    h, h_prec, h_unans, h_n = choose_hedge(R["p"], y)
    clf, mean, scale = fit(R["X"], y)
    gate = {"type": "logreg", "features": R["feats"], "coef": clf.coef_[0].round(4).tolist(),
            "intercept": round(float(clf.intercept_[0]), 4), "mean": mean.round(4).tolist(),
            "scale": scale.round(4).tolist(), "threshold": 0.5}
    if h is not None:
        gate["hedge_threshold"] = h
    # three-way policy on the leave-one-group-out predictions
    p = R["p"]
    answered = p >= (h if h is not None else 0.5)
    report.update({
        "model": best,
        "loo_balanced_accuracy": round(R["bal"], 3), "loo_tpr": round(R["tpr"], 3), "loo_tnr": round(R["tnr"], 3),
        "legacy_loo_balanced_accuracy": round(results["legacy"]["bal"], 3),
        "full_loo_balanced_accuracy": round(results["full"]["bal"], 3),
        "hedge_threshold": h, "hedge_band_precision": None if h_prec is None else round(h_prec, 3),
        "hedge_band_unanswerable_share": None if h_unans is None else round(h_unans, 3), "hedge_band_n": h_n,
        "policy_loo_answer_rate_on_answerable": round(float(answered[y == 1].mean()), 3),
        "policy_loo_abstention_on_unanswerable": round(float((~answered)[y == 0].mean()), 3),
        "train_balanced_accuracy": round(balanced(clf.predict((R["X"] - mean) / scale), y)[0], 3),
        "criteria": {"hedge_min_precision": HEDGE_MIN_PRECISION,
                     "hedge_max_unanswerable_share": HEDGE_MAX_UNANSWERABLE_SHARE},
    })
    for e, pp in sorted(zip(ex, p), key=lambda t: t[1]):
        wrong = (pp >= 0.5) != bool(e["label"])
        print(f"{pp:5.2f} {'ANS' if e['label'] else '---'} {e['source']:11} {e['text'][:70]}{'   <-- LOO error' if wrong else ''}")
    scores = [{k: v for k, v in e.items()} | {"p_logo": round(float(pp), 4)} for e, pp in zip(ex, p)]
    out = {"corpus_sha256": rt.index.meta["corpus_sha256"], "gate": gate, "summary": report, "scores": scores}
    (s.processed_dir / "calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    s.results_dir.mkdir(parents=True, exist_ok=True)
    (s.results_dir / "calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return out


if __name__ == "__main__":
    main()
