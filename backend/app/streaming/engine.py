"""Streaming Live RAG turn engine.

One call to ``run_turn`` consumes a stream of timestamped transcript chunks and
emits the full event trace. The three things conventional RAG cannot do happen
here:

* **Early retrieval** - on every chunk the controller may launch a *provisional*
  retrieval in the background while the user keeps talking. At utterance end,
  sub-queries whose content was already retrieved are reused, so only the
  remainder is searched.
* **Refinement, not restart** - when the controller classifies a turn as a
  refinement, only the delta sub-queries are retrieved; prior claims and their
  citations are carried into the next answer version.
* **Suppression** - presentation-only turns never touch the corpus.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.controller.retrieval_controller import RetrievalController, StreamState
from app.decomposition.decomposer import Decomposer, Decomposition
from app.grounding.validator import GroundingValidator
from app.models.schemas import AnswerVersion, Claim, ScoredChunk, SubQuery
from app.retrieval.fusion import fuse
from app.retrieval.service import RetrievalResult, RetrievalService
from app.retrieval.text import content_tokens
from app.sessions.store import Session
from app.synthesis.restructure import render, restructure
from app.telemetry.events import EventLog

INSUFFICIENT_MSG = "The provided corpus does not contain enough information to verify this."


@dataclass
class EngineOptions:
    retrieval_mode: str = "hybrid"      # hybrid | dense | bm25
    rerank: bool = True
    decompose: bool = True
    early_retrieval: bool = True
    facet_filter: bool = True
    final_evidence_k: int = 8
    endpoint_delay_s: float = 0.5       # VAD hang-over when a scenario gives no explicit end time


@dataclass
class TurnResult:
    request_id: str
    log: EventLog
    summary: dict = field(default_factory=dict)


class StreamingEngine:
    def __init__(self, index, controller: RetrievalController, decomposer: Decomposer, service: RetrievalService,
                 synthesizer, validator: GroundingValidator, options: EngineOptions | None = None):
        self.index = index
        self.controller = controller
        self.decomposer = decomposer
        self.service = service
        self.synth = synthesizer
        self.validator = validator
        self.opt = options or EngineOptions()

    # ------------------------------------------------------------------ helpers
    def _key(self, text: str) -> frozenset[str]:
        """Retrieval-equivalence key: the set of in-vocabulary content stems."""
        return frozenset(t for t in content_tokens(text) if self.index.bm25.vocab_idf(t) is not None)

    def _anchor_terms(self, topic: str, k: int = 3) -> list[str]:
        """Highest-idf words of the topic utterance, used to scope refinement queries."""
        seen, out = set(), []
        for w in topic.replace("?", " ").replace(".", " ").replace(",", " ").split():
            st = content_tokens(w)
            if st and st[0] not in seen and self.index.bm25.vocab_idf(st[0]) is not None:
                seen.add(st[0])
                out.append((self.index.bm25.vocab_idf(st[0]), w.lower()))
        return [w for _, w in sorted(out, reverse=True)[:k]]

    def plan_queries(self, text: str, id_prefix: str, refinement_topic: str | None = None) -> Decomposition:
        if not self.opt.decompose:
            sq = SubQuery(f"{id_prefix}1", text.strip(), "", text.strip())
            return Decomposition(False, [sq], {}, ["decomposition disabled"])
        dec = self.decomposer.decompose(text, id_prefix, context_hint=refinement_topic or "")
        if refinement_topic:
            anchors = self._anchor_terms(refinement_topic)
            for sq in dec.sub_queries:
                have = self._key(sq.text)
                # Only under-specified clauses ("the trip was international") need the topic
                # anchor; specific ones ("booking made after travel") would be diluted by it.
                need = max(0, 3 - len(have))
                add = [a for a in anchors if not (self._key(a) <= have)][:need]
                if add:
                    sq.text = f"{sq.text} {' '.join(add)}"
                    sq.carried_context += add
                    dec.probe_results[sq.id] = self.index.search(sq.text, "hybrid", self.service.top_k)
            dec.trace.append(f"refinement anchors from topic: {anchors}")
        if self.opt.retrieval_mode != "hybrid":
            dec.probe_results = {}
        return dec

    async def _retrieve(self, log: EventLog, sqs: list[SubQuery], probes: dict, provisional: bool
                        ) -> list[RetrievalResult]:
        for sq in sqs:
            log.emit("QUERY_CREATED", sub_query_id=sq.id, query=sq.text, intent=sq.intent,
                     provisional=provisional, carried_context=sq.carried_context)
        log.emit("RETRIEVAL_STARTED", sub_query_ids=[q.id for q in sqs], provisional=provisional,
                 trigger="provisional" if provisional else "final")
        t0 = time.perf_counter()
        res = await self.service.retrieve_many(sqs, self.opt.retrieval_mode, self.opt.rerank, probes)
        for r in res:
            log.emit("RETRIEVAL_COMPLETED", provisional=provisional, **r.summary())
        log.emit("RETRIEVAL_COMPLETED", batch=True, provisional=provisional, sub_query_ids=[q.id for q in sqs],
                 wall_ms=round((time.perf_counter() - t0) * 1e3, 2))
        return res

    # ------------------------------------------------------------------ main entry
    async def run_turn(self, session: Session, chunks: list[dict], end_t: float | None = None,
                       speed: float = 1.0, sink=None) -> TurnResult:
        req = uuid.uuid4().hex[:8]
        log = EventLog(session.session_id, req, sink)
        end_t = end_t if end_t is not None else chunks[-1]["t"] + self.opt.endpoint_delay_s
        log.emit("TURN_STARTED", num_chunks=len(chunks), scheduled_end_t=end_t, speed=speed,
                 answer_version=session.current.version if session.current else 0)
        state = StreamState()
        prev_topic = session.topic_utterance if session.current else None
        cache: dict[frozenset, RetrievalResult] = {}
        prepared: dict[frozenset, tuple] = {}      # sentence scoring done during speech
        chain: asyncio.Task | None = None
        loop = asyncio.get_running_loop()
        counters = {"retrieval_calls": 0, "provisional_calls": 0, "reused": 0, "decisions": {}}

        async def provisional(prefix: str, prior: asyncio.Task | None, refinement: bool) -> None:
            if prior:
                await prior        # keep provisional searches ordered; never duplicate work
            tp = time.perf_counter()
            dec = await loop.run_in_executor(None, self.plan_queries, prefix, "p",
                                             prev_topic if refinement else None)
            log.emit("DECOMPOSITION", ms=round((time.perf_counter() - tp) * 1e3, 2), provisional=True,
                     **dec.to_dict())
            todo = [sq for sq in dec.sub_queries if self._key(sq.text) not in cache and self._key(sq.text)]
            if not todo:
                return
            res = await self._retrieve(log, todo, dec.probe_results, provisional=True)
            counters["provisional_calls"] += len(res)
            for r in res:
                cache[self._key(r.sub_query.text)] = r
            if hasattr(self.synth, "candidates"):
                # Speculative synthesis prep: score sentences now, while the user is still talking.
                tp = time.perf_counter()
                for r in res:
                    top = r.candidates[:3]
                    cands, suff = await loop.run_in_executor(None, self.synth.candidates, r.sub_query, top)
                    prepared[self._key(r.sub_query.text)] = ([c.chunk_id for c in top], cands, suff)
                n = len(res)
                log.emit("SYNTHESIS_PREPARED", sub_query_ids=[r.sub_query.id for r in res],
                         ms=round((time.perf_counter() - tp) * 1e3, 2),
                         note=f"pre-scored evidence sentences for {n} sub-quer{'ies' if n > 1 else 'y'} during speech")

        prefix = ""
        for i, ch in enumerate(chunks):
            delay = ch["t"] / speed - log.now()
            if delay > 0:
                await asyncio.sleep(delay)
            prefix = f"{prefix} {ch['text']}".strip()
            log.emit("TRANSCRIPT_CHUNK", index=i, text=ch["text"], scheduled_t=ch["t"], prefix=prefix)
            d = self.controller.decide(prefix, state, is_final=False, prev_answer_topic=prev_topic)
            counters["decisions"][d.action] = counters["decisions"].get(d.action, 0) + 1
            log.emit("RETRIEVAL_DECISION", final=False, action=d.action, reason=d.reason,
                     confidence=round(d.confidence, 3), intent=d.intent, features=d.features, chunk_index=i)
            state.prev_prefix = prefix
            if d.action == "RETRIEVE" and self.opt.early_retrieval:
                self.controller.mark_retrieved(state, set(self._key(prefix)))
                chain = asyncio.create_task(provisional(prefix, chain, d.intent == "refinement"))

        delay = end_t / speed - log.now()
        if delay > 0:
            await asyncio.sleep(delay)
        log.emit("UTTERANCE_END", utterance=prefix)
        d = self.controller.decide(prefix, state, is_final=True, prev_answer_topic=prev_topic)
        log.emit("RETRIEVAL_DECISION", final=True, action=d.action, reason=d.reason,
                 confidence=round(d.confidence, 3), intent=d.intent, features=d.features)
        if chain:
            await chain

        if d.action == "SUPPRESS":
            out = self._suppressed(session, log, prefix, d.intent, d.reason)
        elif d.intent == "refinement" and session.current:
            out = await self._refine(session, log, prefix, cache, counters, prepared)
        else:
            out = await self._answer(session, log, prefix, cache, counters, prepared)

        summary = self._summarise(log, session, d, counters, out)
        log.emit("TURN_SUMMARY", **summary)
        session.turns.append(summary)
        return TurnResult(req, log, summary)

    # ------------------------------------------------------------------ branches
    def _suppressed(self, session: Session, log: EventLog, utterance: str, intent: str, reason: str) -> dict:
        log.emit("RETRIEVAL_SUPPRESSED", intent=intent, reason=reason)
        if intent == "presentation" and session.current:
            claims, fmt = restructure(session.current, utterance)
            text = render(claims, fmt["bullets"])
            for line in text.split("\n"):
                log.emit("ANSWER_DELTA", text=line)
            log.emit("FINAL_RESPONSE", answer=text, suppressed=True, format=fmt,
                     answer_version=session.current.version,
                     citations=sorted({c for cl in claims for c in cl.citations}), uncertainty=[])
            return {"kind": "presentation", "citations": sorted({c for cl in claims for c in cl.citations})}
        msg = ("There is no previous answer in this session to reformat." if intent == "presentation"
               else "No corpus lookup needed for this turn.")
        log.emit("ANSWER_DELTA", text=msg)
        log.emit("FINAL_RESPONSE", answer=msg, suppressed=True,
                 answer_version=session.current.version if session.current else 0, citations=[], uncertainty=[])
        return {"kind": intent, "citations": []}

    async def _collect(self, log: EventLog, dec: Decomposition, cache: dict, counters: dict,
                       prepared: dict | None = None, prep_out: dict | None = None) -> dict[str, list[ScoredChunk]]:
        results: dict[str, list[ScoredChunk]] = {}
        todo: list[SubQuery] = []
        for sq in dec.sub_queries:
            hit = cache.get(self._key(sq.text)) if self.opt.early_retrieval else None
            if hit:
                counters["reused"] += 1
                log.emit("RETRIEVAL_REUSED", sub_query_id=sq.id, query=sq.text,
                         provisional_query=hit.sub_query.text, retrieved_at_t=round(hit.finished_at - log.t0, 4),
                         top_chunks=[c.chunk_id for c in hit.candidates[:3]])
                results[sq.id] = [ScoredChunk(c.chunk_id, c.score, dict(c.signals), [sq.id]) for c in hit.candidates]
                if prepared is not None and prep_out is not None and self._key(sq.text) in prepared:
                    prep_out[sq.id] = prepared[self._key(sq.text)]
            else:
                todo.append(sq)
        if todo:
            res = await self._retrieve(log, todo, dec.probe_results, provisional=False)
            counters["retrieval_calls"] += len(res)
            for r in res:
                results[r.sub_query.id] = r.candidates
        return results

    def _synthesize(self, sqs, fused, exclude, rankings, prep):
        if hasattr(self.synth, "candidates"):
            return self.synth.synthesize(sqs, fused, exclude, rankings, prep)
        return self.synth.synthesize(sqs, fused, exclude, rankings)

    def _emit_answer(self, log: EventLog, session: Session, version: AnswerVersion, report) -> None:
        for c in version.claims:
            if c.supported and c.status != "removed":
                log.emit("ANSWER_DELTA", text=c.text, citations=c.citations, sub_query_id=c.sub_query_id,
                         status=c.status)
        log.emit("CITATION_VALIDATED", **report.to_dict())
        log.emit("ANSWER_VERSION_UPDATED", answer_version=version.version, change_log=version.change_log,
                 claims=[{"text": c.text, "citations": c.citations, "status": c.status, "supported": c.supported,
                          "support": c.support_score, "sub_query_id": c.sub_query_id} for c in version.claims])
        answer = version.text or INSUFFICIENT_MSG
        cites = []
        for c in version.claims:
            if c.supported and c.status != "removed":
                for cid in c.citations:
                    ch = self.index.by_id[cid]
                    cites.append({"chunk_id": cid, "document_id": ch.document_id, "section_id": ch.section_id,
                                  "section_title": ch.section_title, "source_title": ch.source_title})
        log.emit("FINAL_RESPONSE", answer=answer, suppressed=False, answer_version=version.version,
                 citations=list({c["chunk_id"]: c for c in cites}.values()), uncertainty=version.uncertainty,
                 sub_queries=[{"id": q.id, "text": q.text, "intent": q.intent} for q in version.sub_queries])

    async def _answer(self, session: Session, log: EventLog, utterance: str, cache: dict, counters: dict,
                      prepared: dict | None = None) -> dict:
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        dec = await loop.run_in_executor(None, self.plan_queries, utterance, "q", None)
        log.emit("DECOMPOSITION", ms=round((time.perf_counter() - t0) * 1e3, 2), **dec.to_dict())
        prep: dict[str, tuple] = {}
        results = await self._collect(log, dec, cache, counters, prepared, prep)
        fused, frep = fuse(results, self.index, self.opt.final_evidence_k)
        log.emit("EVIDENCE_FUSED", evidence=[{"chunk_id": e.chunk_id, "sub_query_ids": e.sub_query_ids,
                                              "signals": {k: round(v, 3) for k, v in e.signals.items()}}
                                             for e in fused],
                 duplicates=frep.duplicates, superseded=frep.superseded, conflicts=frep.conflicts)
        t1 = time.perf_counter()
        syn = self._synthesize(dec.sub_queries, fused, None,
                               {k: [c.chunk_id for c in v] for k, v in results.items()}, prep)
        evidence_ids = {e.chunk_id for e in fused}
        claims, rep = self.validator.validate(syn.claims, evidence_ids)
        uncertainty = list(syn.uncertainty) + [f"Unsupported claim removed: {u['claim']} ({u['reason']})"
                                               for u in rep.unsupported_claims]
        uncertainty += [f"{s['kept_with_warning']} comes from a superseded document ({s['superseded_by']} replaces it)."
                        for s in frep.superseded if "kept_with_warning" in s]
        synth_ms = (time.perf_counter() - t1) * 1e3
        session.start_topic(utterance)
        session.results_by_sq = results
        version = AnswerVersion(len(session.versions) + 1, claims, uncertainty, dec.sub_queries,
                                sorted(evidence_ids), [f"new topic: {len(dec.sub_queries)} sub-quer"
                                                       f"{'ies' if len(dec.sub_queries) > 1 else 'y'}"])
        session.versions.append(version)
        self._emit_answer(log, session, version, rep)
        return {"kind": "answer", "synth_ms": synth_ms, "grounding": rep.to_dict(), "decomposition": dec.to_dict(),
                "sufficiency": syn.sufficiency, "fusion": frep.__dict__, "usage": getattr(self.synth, "last_usage", {})}

    async def _refine(self, session: Session, log: EventLog, utterance: str, cache: dict, counters: dict,
                      prepared: dict | None = None) -> dict:
        prev = session.current
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        prefix = f"v{prev.version + 1}q"
        dec = await loop.run_in_executor(None, self.plan_queries, utterance, prefix, session.topic_utterance)
        log.emit("DECOMPOSITION", ms=round((time.perf_counter() - t0) * 1e3, 2), refinement=True, **dec.to_dict())
        prep: dict[str, tuple] = {}
        delta = await self._collect(log, dec, cache, counters, prepared, prep)
        all_results = {**session.results_by_sq, **delta}
        k = self.opt.final_evidence_k + 2 * len(delta)
        fused, frep = fuse(all_results, self.index, k)
        log.emit("EVIDENCE_FUSED", evidence=[{"chunk_id": e.chunk_id, "sub_query_ids": e.sub_query_ids,
                                              "signals": {kk: round(v, 3) for kk, v in e.signals.items()}}
                                             for e in fused],
                 duplicates=frep.duplicates, superseded=frep.superseded, conflicts=frep.conflicts, refinement=True)
        dropped = {s["dropped"]: s["superseded_by"] for s in frep.superseded if "dropped" in s}
        change_log = [f"refinement of v{prev.version}: +{len(dec.sub_queries)} delta sub-quer"
                      f"{'ies' if len(dec.sub_queries) > 1 else 'y'}, prior sub-queries not re-searched"]
        kept: list[Claim] = []
        for c in prev.claims:
            if not c.supported or c.status == "removed":
                continue
            nc = Claim(c.text, list(c.citations), c.sub_query_id, True, c.support_score, "retained")
            gone = [cid for cid in c.citations if cid in dropped]
            if gone:
                nc.status = "removed"
                change_log.append(f"removed claim citing {gone[0]}: superseded by {dropped[gone[0]]}")
            kept.append(nc)
        t1 = time.perf_counter()
        delta_fused = [e for e in fused if any(s in delta for s in e.sub_query_ids)]
        syn = self._synthesize(dec.sub_queries, delta_fused, {c.text for c in kept},
                               {k: [c.chunk_id for c in v] for k, v in delta.items()}, prep)
        added = syn.claims
        for sq in dec.sub_queries:
            cites = sorted({cid for c in added if c.sub_query_id == sq.id for cid in c.citations})
            change_log.append(f"{sq.id} '{sq.source_span}': " +
                              (f"added {sum(c.sub_query_id == sq.id for c in added)} claim(s) citing {cites}"
                               if cites else "no new verifiable claim"))
        evidence_ids = set(prev.evidence_ids) | {e.chunk_id for e in fused}
        claims, rep = self.validator.validate(kept + added, evidence_ids)
        uncertainty = [u for u in prev.uncertainty] + list(syn.uncertainty)
        uncertainty += [f"Unsupported claim removed: {u['claim']} ({u['reason']})" for u in rep.unsupported_claims]
        synth_ms = (time.perf_counter() - t1) * 1e3
        session.results_by_sq = all_results
        version = AnswerVersion(prev.version + 1, claims, uncertainty, prev.sub_queries + dec.sub_queries,
                                sorted(evidence_ids), change_log)
        session.versions.append(version)
        self._emit_answer(log, session, version, rep)
        prev_cites = {cid for c in prev.claims if c.supported for cid in c.citations}
        new_cites = {cid for c in claims if c.supported and c.status != "removed" for cid in c.citations}
        return {"kind": "refinement", "synth_ms": synth_ms, "grounding": rep.to_dict(), "decomposition": dec.to_dict(),
                "retained_citations": sorted(prev_cites & new_cites), "added_citations": sorted(new_cites - prev_cites),
                "prior_subqueries_researched": 0, "sufficiency": syn.sufficiency, "fusion": frep.__dict__,
                "usage": getattr(self.synth, "last_usage", {})}

    # ------------------------------------------------------------------ telemetry
    def _summarise(self, log: EventLog, session: Session, d, counters: dict, out: dict) -> dict:
        ev = log.events
        end = log.first("UTTERANCE_END")["t"]
        first_ret = next((e["t"] for e in ev if e["type"] == "RETRIEVAL_STARTED"), None)
        # First response output: a claim, or the abstention / no-lookup message. Counting the
        # final response when no claim is streamed keeps abstaining turns in the latency stats.
        first_tok = next((e["t"] for e in ev if e["type"] in ("ANSWER_DELTA", "FINAL_RESPONSE")), None)
        started = log.first("TURN_STARTED")
        end_lag = end - started["scheduled_end_t"] / started.get("speed", 1.0)
        final = log.first("FINAL_RESPONSE")
        comp = [e for e in ev if e["type"] == "RETRIEVAL_COMPLETED" and not e.get("batch")]
        return {
            "request_id": log.request_id,
            "session_id": session.session_id,
            "utterance": log.first("UTTERANCE_END")["utterance"],
            "final_action": d.action,
            "intent": d.intent,
            "answer_version": final.get("answer_version"),
            "utterance_end_t": end,
            "first_retrieval_t": first_ret,
            "early_retrieval": first_ret is not None and first_ret < end,
            "retrieval_lead_s": round(end - first_ret, 4) if first_ret is not None else None,
            "ttft_s": round(first_tok - end, 4) if first_tok is not None else None,
            "utterance_end_lag_s": round(end_lag, 4),
            "turn_latency_s": round(final["t"] - end, 4),
            "retrieval_calls_total": sum(1 for _ in comp),
            "retrieval_calls_after_end": counters["retrieval_calls"],
            "provisional_calls": counters["provisional_calls"],
            "reused_subqueries": counters["reused"],
            "retrieval_ms_total": round(sum(e["retrieval_ms"] for e in comp), 2),
            "rerank_ms_total": round(sum(e["rerank_ms"] for e in comp), 2),
            # decomposition includes the probe searches whose results retrieval reuses
            "planning_ms_total": round(sum(e["ms"] for e in ev if e["type"] == "DECOMPOSITION"), 2),
            "synth_ms": round(out.get("synth_ms", 0.0), 2),
            "suppressed": d.action == "SUPPRESS",
            "citations": [c["chunk_id"] if isinstance(c, dict) else c for c in final.get("citations", [])],
            "uncertainty": final.get("uncertainty", []),
            "sub_queries": [q["text"] for q in out.get("decomposition", {}).get("sub_queries", [])],
            "grounding": out.get("grounding"),
            "retained_citations": out.get("retained_citations"),
            "added_citations": out.get("added_citations"),
            "llm_usage": out.get("usage") or {},
            "controller_decisions": counters["decisions"],
        }
