"""HTTP API. A turn is POSTed as timestamped transcript chunks and the response is a
Server-Sent-Events stream of pipeline events (one JSON object per ``data:`` line).
SSE over a plain StreamingResponse keeps the dependency list to FastAPI alone."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")


class ChunkIn(BaseModel):
    t: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=2000)


class TurnIn(BaseModel):
    chunks: list[ChunkIn] = Field(min_length=1, max_length=100)
    end_t: float | None = None
    speed: float = Field(default=1.0, gt=0, le=50)
    system: str = Field(default="proposed", pattern="^(proposed|baseline)$")


def _rt(request: Request):
    return request.app.state.runtime


@router.get("/health")
def health(request: Request):
    rt = _rt(request)
    return {"status": "ok", "index": rt.index.meta, "reranker": rt.reranker.name,
            "controller": rt.controller().train_report, "sufficiency_gate": rt.calibration,
            "corpus": json.loads((rt.settings.processed_dir / "corpus_manifest.json").read_text(encoding="utf-8")),
            "active_sessions": len(rt.sessions)}


@router.get("/scenarios")
def scenarios(request: Request):
    return json.loads((_rt(request).settings.configs_dir / "demo_scenarios.json").read_text(encoding="utf-8"))


@router.post("/sessions")
def create_session(request: Request):
    s = _rt(request).sessions.create()
    request.app.state.session_events[s.session_id] = []
    return {"session_id": s.session_id}


@router.delete("/sessions/{sid}")
def end_session(sid: str, request: Request):
    request.app.state.session_events.pop(sid, None)
    return {"ended": _rt(request).sessions.end(sid)}


@router.get("/sessions/{sid}")
def get_session(sid: str, request: Request):
    s = _rt(request).sessions.get(sid)
    if not s:
        raise HTTPException(404, "session not found or expired")
    return {"session_id": sid, "topic": s.topic_utterance, "turns": s.turns,
            "versions": [{"version": v.version, "text": v.text, "uncertainty": v.uncertainty,
                          "change_log": v.change_log} for v in s.versions]}


@router.get("/sessions/{sid}/telemetry", response_class=PlainTextResponse)
def telemetry(sid: str, request: Request):
    evs = request.app.state.session_events.get(sid)
    if evs is None:
        raise HTTPException(404, "session not found")
    return "\n".join(json.dumps(e, default=str) for e in evs) + "\n"


@router.get("/chunks/{chunk_id}")
def chunk(chunk_id: str, request: Request):
    c = _rt(request).index.by_id.get(chunk_id)
    if not c:
        raise HTTPException(404, "unknown chunk id")
    return c.to_dict()


@router.post("/sessions/{sid}/turns")
async def run_turn(sid: str, body: TurnIn, request: Request):
    rt = _rt(request)
    session = rt.sessions.get(sid)
    if not session:
        raise HTTPException(404, "session not found or expired")
    engine = request.app.state.engines[body.system]
    queue: asyncio.Queue = asyncio.Queue()
    store = request.app.state.session_events.setdefault(sid, [])

    def sink(ev: dict) -> None:
        store.append(ev)
        queue.put_nowait(ev)

    chunks = [c.model_dump() for c in body.chunks]
    task = asyncio.create_task(engine.run_turn(session, chunks, body.end_t, body.speed, sink))

    async def stream():
        while True:
            get = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({get, task}, return_when=asyncio.FIRST_COMPLETED)
            if get in done:
                ev = get.result()
                yield f"data: {json.dumps(ev, default=str)}\n\n"
                if ev["type"] == "TURN_SUMMARY":
                    break
            else:
                get.cancel()
                if task.exception():
                    yield f"data: {json.dumps({'type': 'ERROR', 'message': str(task.exception())})}\n\n"
                while not queue.empty():
                    yield f"data: {json.dumps(queue.get_nowait(), default=str)}\n\n"
                break

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
