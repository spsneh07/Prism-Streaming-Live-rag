"""Central configuration.

Every tunable constant lives here with a comment explaining where it came from,
so nothing in the pipeline is a silent magic number. Values can be overridden by
environment variables prefixed with ``SLRAG_`` (see ``.env.example``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default):
    raw = os.environ.get(f"SLRAG_{name.upper()}")
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return type(default)(raw)


@dataclass
class Settings:
    # --- paths -------------------------------------------------------------
    raw_dir: Path = REPO_ROOT / "data" / "raw"
    processed_dir: Path = REPO_ROOT / "data" / "processed"
    benchmark_dir: Path = REPO_ROOT / "data" / "benchmark"
    configs_dir: Path = REPO_ROOT / "configs"
    results_dir: Path = REPO_ROOT / "results"
    telemetry_dir: Path = REPO_ROOT / "results" / "telemetry"

    # --- models ------------------------------------------------------------
    # all-MiniLM-L6-v2: 22M params, 384-d, ~5 ms/sentence on CPU. Chosen for CPU
    # feasibility; any HF sentence-embedding model with mean pooling works.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # ms-marco-MiniLM-L6-v2 cross-encoder: 22M params, standard MS MARCO reranker.
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    use_reranker: bool = True

    # --- chunking ----------------------------------------------------------
    # Sections in the corpus are short (40-120 words), so a section is the
    # natural citation unit; only oversized sections are split.
    max_chunk_words: int = 160

    # --- retrieval ---------------------------------------------------------
    top_k: int = 8                 # candidates kept per sub-query after fusion
    rrf_k: int = 60                # RRF constant from Cormack et al. (2009)
    bm25_k1: float = 1.5           # standard Okapi defaults
    bm25_b: float = 0.75
    final_evidence_k: int = 8      # evidence passed to synthesis (same for baseline)

    # --- controller --------------------------------------------------------
    controller_mode: str = "learned"   # "learned" | "rule"
    retrieve_threshold: float = 0.5    # P(RETRIEVE) cut-off for learned controller
    rule_min_content_tokens: int = 3   # rule-based ablation: retrieve after N content words
    suppress_threshold: float = 0.5    # P(presentation|chitchat) cut-off

    # --- decomposition -----------------------------------------------------
    # Two adjacent segments whose top-3 retrieved sections overlap by at least
    # this Jaccard score are treated as the same intent and merged back
    # (guards against the "over-fragmenting sub-queries" pitfall).
    merge_overlap: float = 0.5

    # --- synthesis / grounding --------------------------------------------
    sentences_per_subquery: int = 2
    # Minimum cosine(sub-query, evidence sentence) for a sentence to be used.
    min_sentence_sim: float = 0.30
    # Evidence-sufficiency gate: best sentence-level cross-encoder logit below this =>
    # "corpus does not contain enough information". Calibrated with
    # scripts/calibrate_sufficiency.py on configs/calibration_queries.jsonl (32 queries,
    # disjoint from the benchmark): balanced accuracy 1.00 at -1.1 (results/calibration.json).
    min_rerank_logit: float = -1.1
    # Fallback gate when the reranker is disabled: dense cosine of best chunk.
    min_dense_sim: float = 0.40
    # Claim support: fraction of claim content tokens present in cited chunk.
    min_claim_support: float = 0.6

    # --- streaming demo ----------------------------------------------------
    chunk_interval_s: float = 0.8   # simulated gap between transcript chunks

    # --- optional LLM -------------------------------------------------------
    llm_provider: str = "none"      # "none" (extractive) | "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"

    def __post_init__(self) -> None:
        for f in fields(self):
            cur = getattr(self, f.name)
            if isinstance(cur, Path):
                raw = os.environ.get(f"SLRAG_{f.name.upper()}")
                if raw:
                    setattr(self, f.name, Path(raw))
            else:
                setattr(self, f.name, _env(f.name, cur))


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
