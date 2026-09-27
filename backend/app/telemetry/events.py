"""Structured event log for one turn. Every pipeline step emits exactly one event
type from ``EVENT_TYPES``; the same stream feeds SSE clients, the UI, JSONL export
and the benchmark, so the demo and the numbers can never disagree."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

EVENT_TYPES = (
    "TURN_STARTED", "TRANSCRIPT_CHUNK", "RETRIEVAL_DECISION", "QUERY_CREATED", "RETRIEVAL_STARTED",
    "RETRIEVAL_COMPLETED", "RETRIEVAL_REUSED", "SYNTHESIS_PREPARED", "UTTERANCE_END", "DECOMPOSITION", "EVIDENCE_FUSED",
    "ANSWER_DELTA", "CITATION_VALIDATED", "ANSWER_VERSION_UPDATED", "RETRIEVAL_SUPPRESSED", "FINAL_RESPONSE",
    "TURN_SUMMARY",
)


class EventLog:
    def __init__(self, session_id: str, request_id: str, sink: Callable[[dict], Any] | None = None):
        self.session_id = session_id
        self.request_id = request_id
        self.t0 = time.perf_counter()
        self.wall0 = time.time()
        self.events: list[dict] = []
        self.sink = sink

    def now(self) -> float:
        return time.perf_counter() - self.t0

    def emit(self, type_: str, **payload: Any) -> dict:
        assert type_ in EVENT_TYPES, type_
        ev = {"t": round(self.now(), 4), "type": type_, "session_id": self.session_id,
              "request_id": self.request_id, **payload}
        self.events.append(ev)
        if self.sink:
            self.sink(ev)
        return ev

    def first(self, type_: str, **match: Any) -> dict | None:
        for e in self.events:
            if e["type"] == type_ and all(e.get(k) == v for k, v in match.items()):
                return e
        return None

    def export_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for e in self.events:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
