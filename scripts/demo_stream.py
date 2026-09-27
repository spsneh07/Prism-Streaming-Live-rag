"""Run the demo scenarios in the terminal and print the live event trace.

    python scripts/demo_stream.py                              # all scenarios, real-time pacing
    python scripts/demo_stream.py --scenario early_retrieval   # one scenario
    python scripts/demo_stream.py --list                       # scenario names
    python scripts/demo_stream.py --scenario suppression --speed 4

Scenarios: early_retrieval, multi_intent, late_constraint, suppression, abstention (+ abstention_full).
"""
import argparse
import asyncio
import json

import _bootstrap  # noqa: F401
from app.config import get_settings
from app.runtime import Runtime

SHOW = {"SYNTHESIS_PREPARED", "TRANSCRIPT_CHUNK", "RETRIEVAL_DECISION", "QUERY_CREATED", "RETRIEVAL_STARTED", "RETRIEVAL_REUSED",
        "UTTERANCE_END", "EVIDENCE_FUSED", "CITATION_VALIDATED", "ANSWER_VERSION_UPDATED", "RETRIEVAL_SUPPRESSED",
        "FINAL_RESPONSE"}


def show(ev: dict) -> None:
    t, ty = ev["t"], ev["type"]
    if ty not in SHOW:
        return
    if ty == "TRANSCRIPT_CHUNK":
        msg = f'"{ev["text"]}"'
    elif ty == "RETRIEVAL_DECISION":
        msg = f'{ev["action"]:8} intent={ev["intent"]:12} {"[final] " if ev["final"] else ""}{ev["reason"]}'
    elif ty == "QUERY_CREATED":
        msg = f'{ev["sub_query_id"]}: "{ev["query"]}"{" (provisional)" if ev["provisional"] else ""}'
    elif ty == "RETRIEVAL_STARTED":
        msg = f'{ev["trigger"]} {ev["sub_query_ids"]}'
    elif ty == "RETRIEVAL_REUSED":
        msg = f'{ev["sub_query_id"]} reuses provisional results of "{ev["provisional_query"]}"'
    elif ty == "EVIDENCE_FUSED":
        msg = (f'{len(ev["evidence"])} chunks; dupes={len(ev["duplicates"])} superseded={len(ev["superseded"])} '
               f'conflicts={len(ev["conflicts"])}')
    elif ty == "CITATION_VALIDATED":
        msg = f'{ev["num_supported"]}/{ev["num_claims"]} claims supported, fabricated={ev["fabricated_citations"]}'
    elif ty == "ANSWER_VERSION_UPDATED":
        msg = f'v{ev["answer_version"]}: ' + "; ".join(ev["change_log"])
    elif ty == "SYNTHESIS_PREPARED":
        msg = ev["note"]
    elif ty == "RETRIEVAL_SUPPRESSED":
        msg = ev["reason"]
    elif ty == "FINAL_RESPONSE":
        msg = "\n      " + ev["answer"].replace("\n", "\n      ")
        if ev.get("uncertainty"):
            msg += "\n      uncertainty: " + " | ".join(ev["uncertainty"])
    else:
        msg = ""
    print(f"  {t:6.3f}s  {ty:22} {msg}")


async def main(names: list[str], speed: float) -> None:
    scen = json.loads((get_settings().configs_dir / "demo_scenarios.json").read_text(encoding="utf-8"))
    unknown = [n for n in names if n not in scen]
    if unknown:
        raise SystemExit(f"unknown scenario(s) {unknown}; choose from {list(scen)}")
    rt = Runtime.load()
    if rt.index.meta and json.loads((get_settings().processed_dir / "corpus_manifest.json").read_text()).get("synthetic"):
        print("NOTE: running on the DEVELOPMENT / DEMONSTRATION corpus (synthetic), not the official Theme 4 corpus.")
    eng = rt.engine()
    for name in names or list(scen):
        sc = scen[name]
        print(f"\n=== {sc['title']} ===\n    {sc.get('narration', '')}")
        session = rt.sessions.create()
        for turn in sc["turns"]:
            print("  --- turn ---")
            res = await eng.run_turn(session, turn["chunks"], turn.get("end_t"), speed=speed, sink=show)
            s = res.summary
            proof = ""
            if s["early_retrieval"]:
                proof = (f"PROOF retrieval_start {s['first_retrieval_t']:.2f}s < utterance_end {s['utterance_end_t']:.2f}s "
                         f"(lead {s['retrieval_lead_s']:.2f}s)")
            elif s["suppressed"]:
                proof = "PROOF retrieval suppressed: 0 retrieval calls"
            print(f"  summary: intent={s['intent']} v{s['answer_version']} calls={s['retrieval_calls_total']} "
                  f"reused={s['reused_subqueries']} ttft={s['ttft_s']}s  {proof}")
        rt.sessions.end(session.session_id)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="scenario names (same as --scenario)")
    ap.add_argument("--scenario", action="append", default=[], help="scenario name; repeatable")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, v in json.loads((get_settings().configs_dir / "demo_scenarios.json").read_text(encoding="utf-8")).items():
            print(f"{k:18} {v['title']}")
    else:
        asyncio.run(main(a.names + a.scenario, a.speed))
