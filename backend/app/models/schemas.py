"""Plain dataclasses shared across the pipeline (kept dependency-free)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Chunk:
    chunk_id: str          # e.g. "DOC_03:S2:c1"
    document_id: str       # e.g. "DOC_03"
    section_id: str        # e.g. "S2"
    section_title: str
    source_title: str
    text: str
    line_start: int        # 1-based line numbers in the raw file
    line_end: int
    source_file: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        return f"{self.document_id} §{self.section_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredChunk:
    chunk_id: str
    score: float
    # Per-signal scores/ranks kept for observability ("why was this retrieved?").
    signals: dict[str, float] = field(default_factory=dict)
    # Which sub-queries retrieved this chunk (provenance after fusion).
    sub_query_ids: list[str] = field(default_factory=list)


@dataclass
class SubQuery:
    id: str
    text: str
    intent: str = ""                 # grounded label: top section title
    source_span: str = ""            # the utterance fragment it came from
    carried_context: list[str] = field(default_factory=list)
    focus: str = ""                  # cleaned clause without carried context (answer selection)


@dataclass
class Decision:
    action: str                      # WAIT | RETRIEVE | SUPPRESS
    reason: str
    confidence: float
    intent: str = "new_request"      # new_request | refinement | presentation | chitchat
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class Claim:
    text: str
    citations: list[str]             # chunk_ids
    sub_query_id: str = ""
    supported: bool = True
    support_score: float = 1.0
    status: str = "added"            # added | retained | removed


@dataclass
class AnswerVersion:
    version: int
    claims: list[Claim]
    uncertainty: list[str]
    sub_queries: list[SubQuery]
    evidence_ids: list[str]
    change_log: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = []
        for c in self.claims:
            if not c.supported:
                continue
            cites = " ".join(f"[{cid.rsplit(':', 1)[0].replace(':', ' §')}]" for cid in dict.fromkeys(c.citations))
            parts.append(f"{c.text} {cites}".strip())
        return " ".join(parts)
