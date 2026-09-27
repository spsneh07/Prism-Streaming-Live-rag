"""Ephemeral, session-scoped memory.

Sessions live only in this process's memory, are keyed by a random id, expire
after ``ttl_s`` of inactivity and are never written to disk (telemetry export
contains events, not a user profile). There is no user identity field at all,
so cross-session personalisation is impossible by construction.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.models.schemas import AnswerVersion, ScoredChunk


@dataclass
class Session:
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    topic_utterance: str | None = None                     # utterance that opened the current topic
    versions: list[AnswerVersion] = field(default_factory=list)
    results_by_sq: dict[str, list[ScoredChunk]] = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)       # per-turn summaries (for UI / benchmark)

    @property
    def current(self) -> AnswerVersion | None:
        return self.versions[-1] if self.versions else None

    def start_topic(self, utterance: str) -> None:
        """A new request replaces the topic context (older versions stay for audit)."""
        self.topic_utterance = utterance
        self.results_by_sq = {}


class SessionStore:
    def __init__(self, ttl_s: float = 1800):
        self._sessions: dict[str, Session] = {}
        self.ttl_s = ttl_s

    def create(self) -> Session:
        self._gc()
        s = Session(session_id=uuid.uuid4().hex[:12])
        self._sessions[s.session_id] = s
        return s

    def get(self, session_id: str) -> Session | None:
        self._gc()
        s = self._sessions.get(session_id)
        if s:
            s.last_active = time.time()
        return s

    def end(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def __len__(self) -> int:
        return len(self._sessions)

    def _gc(self) -> None:
        cutoff = time.time() - self.ttl_s
        for sid in [k for k, v in self._sessions.items() if v.last_active < cutoff]:
            del self._sessions[sid]
