"""Pre-demo check against a RUNNING server (read-only apart from creating and ending
throw-away sessions). Run it right before the jury session:

    python scripts/predemo_check.py                 # http://localhost:8000, real-time pacing
    python scripts/predemo_check.py --speed 5       # faster rehearsal
    python scripts/predemo_check.py --url http://localhost:8000

For every demo scenario in configs/demo_scenarios.json it checks the property the
demo is meant to show and prints PASS / FAIL with the observed values. Exit code 1
if anything fails. It never modifies files, the index or the calibration.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def events(client: httpx.Client, sid: str, turn: dict, speed: float) -> list[dict]:
    body = {"chunks": turn["chunks"], "end_t": turn.get("end_t"), "speed": speed, "system": "proposed"}
    r = client.post(f"/api/sessions/{sid}/turns", json=body, timeout=120)
    r.raise_for_status()
    return [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]


def summary(evs: list[dict]) -> dict:
    return next((e for e in evs if e["type"] == "TURN_SUMMARY"), {})


CHECKS = {
    "early_retrieval": lambda S: (S[0]["early_retrieval"] and bool(S[0]["citations"]),
                                  f"early={S[0]['early_retrieval']} lead={S[0]['retrieval_lead_s']}s "
                                  f"ttft={S[0]['ttft_s']}s cites={S[0]['citations']}"),
    "multi_intent": lambda S: (len(S[0]["sub_queries"]) >= 3 and len({c.split(':')[0] for c in S[0]["citations"]}) >= 3,
                               f"sub_queries={S[0]['sub_queries']} cites={S[0]['citations']}"),
    "refinement": lambda S: (S[1]["intent"] == "refinement" and S[1]["answer_version"] == 2
                             and bool(S[1]["retained_citations"]) and bool(S[1]["added_citations"]),
                             f"intent={S[1]['intent']} v={S[1]['answer_version']} retained={S[1]['retained_citations']} "
                             f"added={S[1]['added_citations']}"),
    "suppression": lambda S: (S[1]["suppressed"] and S[1]["retrieval_calls_total"] == 0 and bool(S[1]["citations"]),
                              f"suppressed={S[1]['suppressed']} calls={S[1]['retrieval_calls_total']} cites={S[1]['citations']}"),
    "insufficient_evidence": lambda S: (bool(S[0]["citations"]) and bool(S[0]["uncertainty"]),
                                        f"cites={S[0]['citations']} uncertainty={len(S[0]['uncertainty'])}"),
    "insufficient_evidence_full": lambda S: (not S[0]["citations"] and bool(S[0]["uncertainty"]),
                                             f"cites={S[0]['citations']} uncertainty={len(S[0]['uncertainty'])}"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()
    ok = True
    with httpx.Client(base_url=a.url) as c:
        try:
            h = c.get("/api/health", timeout=10).json()
        except httpx.HTTPError as e:
            print(f"FAIL server not reachable at {a.url}: {e}\n     start it with: "
                  "python -m uvicorn app.main:app --app-dir backend --port 8000")
            return 1
        print(f"server ok: {h['index']['num_chunks']} chunks, reranker={h['reranker']}, gate: {h['sufficiency_gate']['status']}")
        scenarios = c.get("/api/scenarios").json()
        for name, sc in scenarios.items():
            sid = c.post("/api/sessions").json()["session_id"]
            t0 = time.perf_counter()
            try:
                S = []
                for turn in sc["turns"]:
                    evs = events(c, sid, turn, a.speed)
                    err = [e for e in evs if e["type"] == "ERROR"]
                    if err:
                        raise RuntimeError(err[0].get("message"))
                    S.append(summary(evs))
                passed, detail = CHECKS[name](S) if name in CHECKS else (True, "no check defined")
            except Exception as e:  # report and continue with the next scenario
                passed, detail = False, f"error: {e}"
            finally:
                c.delete(f"/api/sessions/{sid}")
            ok &= passed
            print(f"{'PASS' if passed else 'FAIL'} {name:28} {time.perf_counter() - t0:5.1f}s  {detail}")
    print("ALL PASS" if ok else "SOME CHECKS FAILED - see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
