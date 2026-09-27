"""Conventional (turn-based) RAG baseline used for the comparison.

* waits for the end of the utterance (no early retrieval)
* sends the whole utterance as ONE query (no decomposition)
* dense-only retrieval, no reranker
* stateless follow-ups: the previous utterance is concatenated to the new one and
  the full pipeline is re-run (restart, no answer versioning, no suppression)

Synthesis and grounding validation are identical to the proposed system, so the
comparison isolates the retrieval/orchestration differences.
"""
from __future__ import annotations

import asyncio
import time
import uuid

from app.grounding.validator import GroundingValidator
from app.models.schemas import AnswerVersion, SubQuery
from app.retrieval.fusion import fuse
from app.retrieval.service import RetrievalService
from app.sessions.store import Session
from app.streaming.engine import INSUFFICIENT_MSG, TurnResult
from app.telemetry.events import EventLog


class BaselineEngine:
    def __init__(self, index, service: RetrievalService, synthesizer, validator: GroundingValidator,
                 mode: str = "dense", final_evidence_k: int = 8, endpoint_delay_s: float = 0.5):
        self.index, self.service, self.synth, self.validator = index, service, synthesizer, validator
        self.mode = mode
        self.k = final_evidence_k
        self.endpoint_delay_s = endpoint_delay_s

    async def run_turn(self, session: Session, chunks: list[dict], end_t: float | None = None,
                       speed: float = 1.0, sink=None) -> TurnResult:
        log = EventLog(session.session_id, uuid.uuid4().hex[:8], sink)
        end_t = end_t if end_t is not None else chunks[-1]["t"] + self.endpoint_delay_s
        log.emit("TURN_STARTED", num_chunks=len(chunks), scheduled_end_t=end_t, baseline=True)
        text = ""
        for i, ch in enumerate(chunks):
            delay = ch["t"] / speed - log.now()
            if delay > 0:
                await asyncio.sleep(delay)
            text = f"{text} {ch['text']}".strip()
            log.emit("TRANSCRIPT_CHUNK", index=i, text=ch["text"], scheduled_t=ch["t"])
        delay = end_t / speed - log.now()
        if delay > 0:
            await asyncio.sleep(delay)
        log.emit("UTTERANCE_END", utterance=text)

        query = f"{session.topic_utterance} {text}" if session.topic_utterance else text
        sq = SubQuery("q1", query, "", text)
        log.emit("QUERY_CREATED", sub_query_id="q1", query=query, provisional=False)
        log.emit("RETRIEVAL_STARTED", sub_query_ids=["q1"], provisional=False, trigger="utterance_end")
        res = (await self.service.retrieve_many([sq], self.mode, rerank=False))[0]
        log.emit("RETRIEVAL_COMPLETED", provisional=False, **res.summary())
        fused, frep = fuse({"q1": res.candidates}, self.index, self.k)
        log.emit("EVIDENCE_FUSED", evidence=[{"chunk_id": e.chunk_id, "sub_query_ids": e.sub_query_ids}
                                             for e in fused],
                 duplicates=frep.duplicates, superseded=frep.superseded, conflicts=frep.conflicts)
        t1 = time.perf_counter()
        syn = self.synth.synthesize([sq], fused, rankings={"q1": [c.chunk_id for c in res.candidates]})
        claims, rep = self.validator.validate(syn.claims, {e.chunk_id for e in fused})
        synth_ms = (time.perf_counter() - t1) * 1e3
        version = AnswerVersion(len(session.versions) + 1, claims, list(syn.uncertainty), [sq],
                                [e.chunk_id for e in fused], ["baseline: full restart"])
        if session.topic_utterance is None:
            session.topic_utterance = text
        session.versions.append(version)
        for c in claims:
            if c.supported:
                log.emit("ANSWER_DELTA", text=c.text, citations=c.citations)
        log.emit("CITATION_VALIDATED", **rep.to_dict())
        cites = sorted({cid for c in claims if c.supported for cid in c.citations})
        log.emit("FINAL_RESPONSE", answer=version.text or INSUFFICIENT_MSG, answer_version=version.version,
                 citations=cites, uncertainty=version.uncertainty, suppressed=False)
        end = log.first("UTTERANCE_END")["t"]
        first_tok = next((e["t"] for e in log.events if e["type"] == "ANSWER_DELTA"), None)
        summary = {
            "request_id": log.request_id, "session_id": session.session_id, "utterance": text,
            "final_action": "RETRIEVE", "intent": "n/a", "answer_version": version.version,
            "utterance_end_t": end, "first_retrieval_t": log.first("RETRIEVAL_STARTED")["t"],
            "early_retrieval": False, "retrieval_lead_s": 0.0,
            "ttft_s": round(first_tok - end, 4) if first_tok is not None else None,
            "turn_latency_s": round(log.first("FINAL_RESPONSE")["t"] - end, 4),
            "retrieval_calls_total": 1, "retrieval_calls_after_end": 1, "provisional_calls": 0,
            "reused_subqueries": 0, "retrieval_ms_total": round(res.retrieval_ms, 2), "rerank_ms_total": 0.0, "planning_ms_total": 0.0,
            "synth_ms": round(synth_ms, 2), "suppressed": False, "citations": cites,
            "uncertainty": version.uncertainty, "sub_queries": [query], "grounding": rep.to_dict(),
            "retained_citations": None, "added_citations": None, "llm_usage": {}, "controller_decisions": {},
        }
        log.emit("TURN_SUMMARY", **summary)
        session.turns.append(summary)
        return TurnResult(log.request_id, log, summary)
