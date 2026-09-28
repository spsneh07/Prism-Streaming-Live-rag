"""Benchmark: Streaming Live RAG vs conventional RAG, ablations, retrieval eval, gates.

    python scripts/benchmark.py                 # held-out set, real-time pacing  -> results/
    python scripts/benchmark.py --set dev       # development set                 -> results/dev/
    python scripts/benchmark.py --quick         # 5x pacing everywhere (smoke test)

Every number written to results/ is computed from event traces of this run;
nothing is hand-entered. Metric definitions: docs/evaluation.md.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import _bootstrap  # noqa: F401
from app.config import get_settings
from app.models.schemas import SubQuery
from app.reranking.rerankers import NoopReranker
from app.retrieval.service import RetrievalService
from app.runtime import Runtime
from app.streaming.engine import EngineOptions

ROOT = Path(__file__).resolve().parents[1]
SETS = {"heldout": ROOT / "data" / "benchmark" / "heldout_streams.jsonl",
        "dev": ROOT / "data" / "eval" / "dev_streams.jsonl"}
REQUIRED_EVENTS = {"TURN_STARTED", "TRANSCRIPT_CHUNK", "RETRIEVAL_DECISION", "UTTERANCE_END", "FINAL_RESPONSE",
                   "TURN_SUMMARY"}
REQUIRED_SUMMARY = {"request_id", "session_id", "utterance_end_t", "first_retrieval_t", "ttft_s", "turn_latency_s",
                    "retrieval_calls_total", "citations", "uncertainty", "answer_version", "llm_usage",
                    "final_action", "intent"}


def section(cid: str) -> str:
    return cid.rsplit(":", 1)[0]


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 4)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def rate(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def ratio(num, den):
    return round(num / den, 4) if den else None


# ----------------------------------------------------------------------------- per-turn scoring
def turn_row(case, ti, turn, res, system, index, prev_sq_ids):
    ev = res.log.events
    s = res.summary
    exp = turn["expect"]
    fused = [e for e in ev if e["type"] == "EVIDENCE_FUSED"]
    evidence = [section(x["chunk_id"]) for x in fused[-1]["evidence"]] if fused else []
    final = next(e for e in ev if e["type"] == "FINAL_RESPONSE")
    cited_ids = [c["chunk_id"] if isinstance(c, dict) else c for c in final.get("citations", [])]
    cited = [section(c) for c in cited_ids]
    sq_tops = {}
    for e in ev:
        if e["type"] in ("RETRIEVAL_COMPLETED", "RETRIEVAL_REUSED") and e.get("sub_query_id") and not e.get("batch"):
            if e["type"] == "RETRIEVAL_COMPLETED" and e.get("provisional"):
                continue
            sq_tops[e["sub_query_id"]] = [section(c) for c in e.get("top_chunks", [])]
    gold = exp["gold"]
    recall_hits = [any(g in evidence for g in intent) for intent in gold]
    recall3_hits = [any(g in evidence[:3] for g in intent) for intent in gold]
    cite_hits = [any(g in cited for g in intent) for intent in gold]
    distinct_cover = None
    if len(gold) >= 2:
        free, ok = dict(sq_tops), True
        for intent in gold:     # each gold intent matched by the top-3 of a *different* sub-query
            m = next((k for k, v in free.items() if any(g in v for g in intent)), None)
            if m is None:
                ok = False
                break
            free.pop(m)
        distinct_cover = ok and len(sq_tops) >= 2
    grounding = s.get("grounding") or {}
    supported_claims = grounding.get("num_supported", 0) if not s["suppressed"] else None
    abstained = None
    if exp["unanswerable"]:
        if gold:   # partially answerable: the missing part must be flagged
            abstained = any("not contain enough information" in u or "not verified" in u for u in s["uncertainty"])
        else:      # fully unanswerable: nothing may be asserted
            abstained = (supported_claims or 0) == 0
    # WAIT behaviour: chunk index of the first provisional RETRIEVE decision
    first_ret_chunk = next((e["chunk_index"] for e in ev if e["type"] == "RETRIEVAL_DECISION" and not e["final"]
                            and e["action"] == "RETRIEVE"), None)
    eok = exp.get("earliest_ok_chunk")
    premature = None if eok is None or s["intent"] == "n/a" else (first_ret_chunk is not None and first_ret_chunk < eok)
    # G6 trace completeness
    kinds = {e["type"] for e in ev}
    decisions = sum(1 for e in ev if e["type"] == "RETRIEVAL_DECISION" and not e.get("final"))
    trace_ok = (REQUIRED_EVENTS - ({"RETRIEVAL_DECISION"} if s["intent"] == "n/a" else set())) <= kinds \
        and REQUIRED_SUMMARY <= set(s) \
        and all("t" in e and e["session_id"] and e["request_id"] for e in ev) \
        and (s["intent"] == "n/a" or decisions == len(turn["chunks"])) \
        and (s["suppressed"] or "CITATION_VALIDATED" in kinds)
    # G5: refinement must not re-search the previous turn's sub-queries
    queried = {e["sub_query_id"] for e in ev if e["type"] == "QUERY_CREATED"}
    researched_prior = len(queried & prev_sq_ids)
    return {
        "system": system, "case": case["id"], "category": case["category"], "turn": ti,
        "expected_intent": exp["intent"], "predicted_intent": s["intent"],
        "needs_retrieval": exp["needs_retrieval"], "final_action": s["final_action"],
        "num_chunks": len(turn["chunks"]), "end_t": turn["end_t"],
        "early_retrieval": s["early_retrieval"], "retrieval_lead_s": s["retrieval_lead_s"],
        "first_retrieve_chunk": first_ret_chunk, "earliest_ok_chunk": eok, "premature_retrieval": premature,
        "ttft_s": s["ttft_s"], "turn_latency_s": s["turn_latency_s"], "utterance_end_lag_s": s["utterance_end_lag_s"],
        "retrieval_calls": s["retrieval_calls_total"], "provisional_calls": s["provisional_calls"],
        "reused_subqueries": s["reused_subqueries"], "retrieval_ms": s["retrieval_ms_total"],
        "rerank_ms": s["rerank_ms_total"], "synth_ms": s["synth_ms"],
        "search_ms": round(s["planning_ms_total"] + s["retrieval_ms_total"], 2),
        "num_subqueries": len(s["sub_queries"]), "sub_queries": " | ".join(s["sub_queries"]),
        "gold_intents": len(gold), "recall_hits": sum(recall_hits), "recall3_hits": sum(recall3_hits),
        "cite_hits": sum(cite_hits), "distinct_cover": distinct_cover, "claims": grounding.get("num_claims"),
        "supported_claims": supported_claims, "fabricated": len(grounding.get("fabricated_citations", [])),
        "superseded_cited": sum(1 for c in cited_ids if c in index.by_id and index.by_id[c].metadata.get("superseded_by")),
        "abstained": abstained, "answer_version": s["answer_version"],
        "researched_prior_subqueries": researched_prior, "trace_complete": trace_ok,
        "llm_tokens": sum(v for k, v in (s.get("llm_usage") or {}).items() if k.endswith("tokens")),
        "citations": " ".join(cited), "_sq_ids": sorted(queried),
    }


async def run_system(rt, name, engine, cases, speed, tel_dir):
    rows, prev_cites = [], {}
    for case in cases:
        session = rt.sessions.create()
        prev_ids: set[str] = set()
        for ti, turn in enumerate(case["turns"]):
            res = await engine.run_turn(session, turn["chunks"], turn["end_t"], speed=speed)
            res.log.export_jsonl(tel_dir / f"{name}.jsonl")
            row = turn_row(case, ti, turn, res, name, rt.index, prev_ids)
            final_ids = {e["sub_query_id"] for e in res.log.events if e["type"] == "QUERY_CREATED"}
            final_ids |= {e["sub_query_id"] for e in res.log.events if e["type"] == "RETRIEVAL_REUSED"}
            prev_ids = {i for i in final_ids if not i.startswith("p")} or prev_ids
            if ti > 0 and turn["expect"]["intent"] == "refinement":
                before = prev_cites.get(case["id"], set())
                after = set(row["citations"].split())
                row["citation_retention"] = round(len(before & after) / len(before), 4) if before else None
                row["prev_version"] = rows[-1]["answer_version"] if rows else None
            prev_cites[case["id"]] = set(row["citations"].split())
            row.pop("_sq_ids")
            rows.append(row)
        rt.sessions.end(session.session_id)
    return rows


def aggregate(rows):
    R = [r for r in rows if r["needs_retrieval"]]
    NR = [r for r in rows if not r["needs_retrieval"]]
    gold_rows = [r for r in R if r["gold_intents"]]
    g_total = sum(r["gold_intents"] for r in gold_rows)
    compound = [r for r in rows if r["gold_intents"] >= 2 and r["expected_intent"] == "new_request"]
    single = [r for r in rows if r["gold_intents"] == 1 and r["expected_intent"] == "new_request"
              and r["category"] in ("single", "single_short", "single_long", "paraphrase", "contradictory", "duplicate")]
    refine = [r for r in rows if r["expected_intent"] == "refinement"]
    answer_rows = [r for r in rows if r["claims"] is not None and r["final_action"] == "RETRIEVE"]
    claims = sum(r["claims"] or 0 for r in answer_rows)
    supported = sum(r["supported_claims"] or 0 for r in answer_rows)
    eligible = [r for r in R if r["num_chunks"] >= 2]
    unans = [r for r in rows if r["abstained"] is not None]
    streaming = rows and rows[0]["predicted_intent"] != "n/a"
    continuity = [r["predicted_intent"] == "refinement" and r["answer_version"] == (r.get("prev_version") or 0) + 1
                  and r["researched_prior_subqueries"] == 0 and (r.get("citation_retention") in (None, 1.0))
                  for r in refine] if streaming else [False for _ in refine]
    return {
        "turns": len(rows),
        "retrieval_recall@3": ratio(sum(r["recall3_hits"] for r in gold_rows), g_total),
        "retrieval_recall@8": ratio(sum(r["recall_hits"] for r in gold_rows), g_total),
        "citation_hit_rate": ratio(sum(r["cite_hits"] for r in gold_rows), g_total),
        "early_retrieval_rate": rate([r["early_retrieval"] for r in eligible]),
        "eligible_turns": len(eligible),
        "mean_retrieval_lead_s": mean([r["retrieval_lead_s"] for r in eligible if r["early_retrieval"]]),
        "premature_retrieval_rate": rate([r["premature_retrieval"] for r in rows]),
        "wait_labelled_turns": sum(1 for r in rows if r["premature_retrieval"] is not None),
        "false_trigger_rate_no_retrieval_turns": rate([r["retrieval_calls"] > 0 for r in NR]),
        "unnecessary_retrieval_calls": sum(r["retrieval_calls"] for r in NR),
        "no_retrieval_turns": len(NR),
        "multi_intent_identification": rate([r["distinct_cover"] for r in compound]),
        "compound_turns": len(compound),
        "single_intent_not_fragmented": rate([r["num_subqueries"] == 1 for r in single]),
        "intent_accuracy": rate([r["predicted_intent"] == r["expected_intent"] for r in rows]) if streaming else None,
        "citation_support_rate": ratio(supported, claims),
        "claims_total": claims,
        "fabricated_citations": sum(r["fabricated"] for r in rows),
        "superseded_doc_citations": sum(r["superseded_cited"] for r in rows),
        "abstention_accuracy": rate([r["abstained"] for r in unans]),
        "unanswerable_turns": len(unans),
        "refinement_turns": len(refine),
        "refinement_detected": rate([r["predicted_intent"] == "refinement" for r in refine]) if streaming else None,
        "refinement_state_continuity": rate(continuity),
        "refinement_delta_recall": ratio(sum(r["recall_hits"] for r in refine), sum(r["gold_intents"] for r in refine)),
        "refinement_citation_retention": mean([r.get("citation_retention") for r in refine]),
        "refinement_retrieval_calls_mean": mean([r["retrieval_calls"] for r in refine]),
        "trace_coverage": rate([r["trace_complete"] for r in rows]),
        "ttft_s_mean": mean([r["ttft_s"] for r in R]),
        "ttft_s_p50": pct([r["ttft_s"] for r in R], 0.5),
        "ttft_s_p95": pct([r["ttft_s"] for r in R], 0.95),
        "turn_latency_s_mean": mean([r["turn_latency_s"] for r in R]),
        "ttft_turns": sum(1 for r in R if r["ttft_s"] is not None),
        # CPU-contention check: how late the simulated utterance end fired vs its schedule
        "utterance_end_lag_s_max": pct([r["utterance_end_lag_s"] for r in rows], 1.0),
        "turn_latency_s_p95": pct([r["turn_latency_s"] for r in R], 0.95),
        "retrieval_calls_per_turn": mean([r["retrieval_calls"] for r in rows]),
        "search_ms_per_turn": mean([r["search_ms"] for r in rows]),
        "rerank_ms_per_turn": mean([r["rerank_ms"] for r in rows]),
        "llm_tokens_per_turn": mean([r["llm_tokens"] for r in rows]),
        "llm_cost_usd_per_turn": 0.0 if all(r["llm_tokens"] == 0 for r in rows) else None,
    }


# ----------------------------------------------------------------------------- retrieval-only eval
def retrieval_eval(rt, path: Path) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    configs = {
        "dense": ("dense", NoopReranker(), None),
        "bm25": ("bm25", NoopReranker(), None),
        "hybrid": ("hybrid", NoopReranker(), None),
        "hybrid+facet+rerank": ("hybrid", rt.reranker, rt.facets),
    }
    out = {}
    for name, (mode, rr, facets) in configs.items():
        rt.index.clear_cache()
        svc = RetrievalService(rt.index, rr, 8, facets)
        r1 = r3 = r5 = mrr = 0.0
        ms = []
        for r in rows:
            res = svc.retrieve_sync(SubQuery("e", r["query"], "", r["query"]), mode, rerank=rr.name != "none")
            ms.append(res.retrieval_ms + res.rerank_ms)
            secs = [section(c.chunk_id) for c in res.candidates]
            rank = next((i + 1 for i, s_ in enumerate(secs) if s_ in r["gold"]), None)
            r1 += rank == 1
            r3 += rank is not None and rank <= 3
            r5 += rank is not None and rank <= 5
            mrr += 1 / rank if rank else 0
        n = len(rows)
        out[name] = {"recall@1": round(r1 / n, 4), "recall@3": round(r3 / n, 4), "recall@5": round(r5 / n, 4),
                     "mrr@8": round(mrr / n, 4), "latency_ms_mean": round(statistics.fmean(ms), 2), "queries": n}
    return out


# ----------------------------------------------------------------------------- gates
def gates(S, repro) -> list[dict]:
    p = S["proposed"]

    def g(gid, name, metric, value, target, passed, method):
        return {"gate": gid, "name": name, "metric": metric, "measured": value, "target": target,
                "status": "PASS" if passed is True else ("FAIL" if passed is False else passed), "method": method}

    if repro is None:
        g1 = g("G1", "Reproducibility", "clean-copy replay + container launch", "not run",
               "container launches with one command on a clean machine; replay completes unattended",
               "NOT RUN", "scripts/reproduce.py")
    else:
        local_ok = repro.get("local_replay") == "PASS"
        docker_ok = repro.get("docker") == "PASS"
        status = True if (local_ok and docker_ok) else ("NOT VERIFIED" if local_ok else False)
        g1 = g("G1", "Reproducibility", "clean-copy replay (local) / container build",
               f"local replay: {repro.get('local_replay')}; docker: {repro.get('docker')}",
               "container launches with one command on a clean machine; replay completes unattended", status,
               "scripts/reproduce.py copies the repo without derived files into an empty directory and runs "
               "ingest -> index -> calibration -> tests -> quick benchmark; Docker checked statically when the "
               "docker CLI is unavailable")
    return [
        g1,
        g("G2", "Early retrieval", "share of eligible turns whose first retrieval starts before utterance end",
          p["early_retrieval_rate"], ">= 0.80 (low false-trigger rate on no-retrieval turns)",
          p["early_retrieval_rate"] is not None and p["early_retrieval_rate"] >= 0.80,
          f"{p['eligible_turns']} held-out turns that need retrieval and have >= 2 chunks; timestamps from "
          f"RETRIEVAL_STARTED vs UTTERANCE_END on one monotonic clock. Also reported: false-trigger rate "
          f"{p['false_trigger_rate_no_retrieval_turns']} on {p['no_retrieval_turns']} no-retrieval turns, premature "
          f"retrieval rate {p['premature_retrieval_rate']} on {p['wait_labelled_turns']} WAIT-labelled turns"),
        g("G3", "Multi-intent identification", "compound turns where >= 2 distinct sub-queries each retrieve a gold section",
          p["multi_intent_identification"], ">= 0.70", p["multi_intent_identification"] is not None
          and p["multi_intent_identification"] >= 0.70,
          f"{p['compound_turns']} compound held-out turns; each gold intent must be in the top-3 of a different sub-query"),
        g("G4", "Factual grounding", "claims supported by their cited chunk; fabricated citation ids",
          f"{p['citation_support_rate']} support, {p['fabricated_citations']} fabricated",
          ">= 0.85 support and 0 fabricated", p["citation_support_rate"] is not None
          and p["citation_support_rate"] >= 0.85 and p["fabricated_citations"] == 0,
          f"validator on all {p['claims_total']} claims: id exists, id was retrieved this turn, >= 60% term "
          f"containment, numbers match. Answer-level quality reported separately: citation hit rate "
          f"{p['citation_hit_rate']}, abstention accuracy {p['abstention_accuracy']}"),
        g("G5", "Session refinement", "refinement turns with verified state continuity",
          p["refinement_state_continuity"], "1.00 (every late constraint updates, never restarts)",
          p["refinement_state_continuity"] == 1.0,
          f"{p['refinement_turns']} refinement turns; continuity = detected as refinement AND version +1 AND 0 prior "
          f"sub-queries re-searched AND all prior citations retained"),
        g("G6", "Telemetry & observability", "turns with a complete trace", p["trace_coverage"], "1.00",
          p["trace_coverage"] == 1.0,
          "every turn must emit TURN_STARTED, one RETRIEVAL_DECISION per chunk, UTTERANCE_END, CITATION_VALIDATED "
          "(unless suppressed), FINAL_RESPONSE and a TURN_SUMMARY with timestamps, retrieval calls, citations, "
          "version and token usage"),
    ]


# ----------------------------------------------------------------------------- plots
def plots(S, rows, out: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out.mkdir(parents=True, exist_ok=True)
    made = []
    colors = {"baseline": "#8a8f98", "proposed": "#2a6fdb", "ablation_no_early_retrieval": "#c9a227"}

    def bar(systems, metrics, labels, fname, title, ylim=None, fmt="{:.2f}"):
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        w = 0.8 / len(systems)
        for j, sysname in enumerate(systems):
            vals = [S[sysname][m] if S[sysname][m] is not None else 0 for m in metrics]
            xs = [i + (j - (len(systems) - 1) / 2) * w for i in range(len(metrics))]
            ax.bar(xs, vals, w, label=sysname.replace("ablation_", ""), color=colors.get(sysname, "#999"))
            for x, v in zip(xs, vals):
                ax.text(x, v, fmt.format(v), ha="center", va="bottom", fontsize=8)
        ax.set_xticks(range(len(metrics)))
        ax.set_xticklabels(labels, fontsize=9)
        if ylim:
            ax.set_ylim(*ylim)
        ax.set_title(title, fontsize=11)
        ax.legend(frameon=False, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(out / fname, dpi=150)
        plt.close(fig)
        made.append(fname)

    bar(["baseline", "proposed"], ["retrieval_recall@3", "citation_hit_rate", "multi_intent_identification",
                                   "abstention_accuracy", "refinement_state_continuity"],
        ["Recall@3", "Citation hit", "Multi-intent", "Abstention", "Refinement\ncontinuity"],
        "quality_comparison.png", "Held-out: conventional RAG vs Streaming Live RAG", (0, 1.15))
    bar(["baseline", "ablation_no_early_retrieval", "proposed"], ["ttft_s_mean", "ttft_s_p50", "ttft_s_p95"],
        ["TTFT mean", "TTFT p50", "TTFT p95"], "latency_comparison.png",
        "Seconds from utterance end to first answer (real-time pacing)", fmt="{:.3f}")
    bar(["baseline", "proposed"], ["unnecessary_retrieval_calls", "retrieval_calls_per_turn"],
        ["Retrievals on no-retrieval turns", "Retrieval calls / turn"], "retrieval_efficiency.png",
        "Retrieval efficiency", fmt="{:.1f}")

    pr = [r for r in rows if r["system"] == "proposed" and r["needs_retrieval"] and r["num_chunks"] >= 2]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    leads = sorted([r["retrieval_lead_s"] or 0 for r in pr])
    ax.bar(range(len(leads)), leads, color=["#2a6fdb" if v > 0 else "#b42318" for v in leads])
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_title("Seconds retrieval started BEFORE the utterance ended (per eligible turn)", fontsize=11)
    ax.set_xlabel("eligible held-out turns, sorted (red = no early retrieval)")
    ax.set_ylabel("lead (s)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "early_retrieval_lead.png", dpi=150)
    plt.close(fig)
    made.append("early_retrieval_lead.png")

    abl = ["baseline"] + [k for k in S if k.startswith("ablation")] + ["proposed"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    vals = [S[k]["citation_hit_rate"] for k in abl]
    ax.barh([k.replace("ablation_", "") for k in abl], vals,
            color=["#8a8f98"] * (len(abl) - 1) + ["#2a6fdb"])
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.2f}", va="center", fontsize=8)
    ax.set_xlim(0, 1.1)
    ax.set_title("Held-out citation hit rate by configuration", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "ablations_citation_hit.png", dpi=150)
    plt.close(fig)
    made.append("ablations_citation_hit.png")
    return made


# ----------------------------------------------------------------------------- main
async def main(set_name: str, quick: bool) -> None:
    s = get_settings()
    path = SETS[set_name]
    cases = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = ROOT / "results" if set_name == "heldout" else ROOT / "results" / set_name
    tel = ROOT / "results" / "telemetry" / set_name
    tel.mkdir(parents=True, exist_ok=True)
    for f in tel.glob("*.jsonl"):
        f.unlink()
    t_load = time.perf_counter()
    rt = Runtime.load()
    load_s = time.perf_counter() - t_load
    rt_speed = 5.0 if quick else 1.0
    abl_speed = 5.0
    k = s.final_evidence_k
    systems = [
        ("baseline", rt.baseline("dense"), rt_speed),
        ("proposed", rt.engine(EngineOptions(final_evidence_k=k)), rt_speed),
        ("ablation_no_early_retrieval", rt.engine(EngineOptions(early_retrieval=False, final_evidence_k=k)), rt_speed),
        ("ablation_dense_only", rt.engine(EngineOptions(retrieval_mode="dense", rerank=False, facet_filter=False,
                                                         final_evidence_k=k)), abl_speed),
        ("ablation_hybrid_no_rerank", rt.engine(EngineOptions(rerank=False, final_evidence_k=k)), abl_speed),
        ("ablation_no_decomposition", rt.engine(EngineOptions(decompose=False, final_evidence_k=k)), abl_speed),
        ("ablation_rule_controller", rt.engine(EngineOptions(final_evidence_k=k), controller_mode="rule"), abl_speed),
    ]
    warm = [json.loads(l) for l in SETS["dev"].read_text(encoding="utf-8").splitlines()[:3]]
    for _, eng, _ in systems[:3]:     # untimed warm-up on dev cases (torch first-call overhead)
        await run_system(rt, "warmup", eng, warm, 20.0, tel)
    for f in tel.glob("warmup.jsonl"):
        f.unlink()

    all_rows, S = [], {}
    for name, eng, speed in systems:
        rt.embedder._cached.cache_clear()   # no system benefits from another's caches
        rt.index.clear_cache()
        t0 = time.perf_counter()
        rows = await run_system(rt, name, eng, cases, speed, tel)
        S[name] = aggregate(rows)
        S[name]["pacing_speed"] = speed
        S[name]["wall_s"] = round(time.perf_counter() - t0, 1)
        all_rows += rows
        print(f"{name:30} cite_hit={S[name]['citation_hit_rate']} early={S[name]['early_retrieval_rate']} "
              f"ttft={S[name]['ttft_s_mean']} abst={S[name]['abstention_accuracy']}", flush=True)

    reval = retrieval_eval(rt, ROOT / "data" / "eval" / "retrieval_eval.jsonl")
    repro_path = ROOT / "results" / "reproducibility.json"
    repro = json.loads(repro_path.read_text()) if repro_path.exists() else None
    G = gates(S, repro)
    meta = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "set": set_name,
        "set_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "set_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "machine": {"platform": platform.platform(), "processor": platform.processor(), "python": platform.python_version()},
        "corpus": json.loads((s.processed_dir / "corpus_manifest.json").read_text()),
        "index": rt.index.meta,
        "reranker": rt.reranker.name,
        "synthesizer": type(rt.synthesizer(True)).__name__,
        "sufficiency_gate": rt.calibration,
        "model_load_s": round(load_s, 2),
        "num_cases": len(cases),
        "num_turns": sum(len(c["turns"]) for c in cases),
        "controller_training": rt.controller().train_report,
        "pacing": f"baseline, proposed and no_early_retrieval at {rt_speed}x; other ablations at {abl_speed}x "
                  "(their latency is not comparable, only their quality metrics)",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps({"meta": meta, "gates": G, "summary": S,
                                                    "retrieval_eval": reval}, indent=2), encoding="utf-8")
    with (out / "benchmark.csv").open("w", newline="", encoding="utf-8") as fh:
        keys = sorted({k for r in all_rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(all_rows)
    lat = {n: {k: v for k, v in S[n].items() if "ttft" in k or "latency" in k or "_ms_" in k or "lead" in k} for n in S}
    (out / "latency.json").write_text(json.dumps(lat, indent=2), encoding="utf-8")
    made = plots(S, all_rows, out / "plots")
    for gg in G:
        print(f"{gg['gate']} {gg['status']:13} {gg['measured']}")
    print(f"retrieval eval: {json.dumps(reval)}")
    print(f"wrote {out.relative_to(ROOT)}/benchmark.json, benchmark.csv, latency.json, plots: {made}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=sorted(SETS), default="heldout")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.set, a.quick))
