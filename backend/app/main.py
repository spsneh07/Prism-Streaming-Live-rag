"""FastAPI entry point: ``uvicorn app.main:app`` (run from backend/)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import REPO_ROOT
from app.runtime import Runtime

FRONTEND = REPO_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    rt = Runtime.load()
    app.state.runtime = rt
    app.state.engines = {"proposed": rt.engine(), "baseline": rt.baseline("dense")}
    app.state.session_events = {}
    yield


app = FastAPI(title="Streaming Live RAG", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")
