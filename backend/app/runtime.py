"""Builds every component once (models are loaded a single time and shared)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.controller.retrieval_controller import RetrievalController
from app.decomposition.decomposer import Decomposer
from app.grounding.coverage import TermCoverage
from app.grounding.validator import GroundingValidator
from app.reranking.rerankers import NoopReranker, load_reranker
from app.retrieval.embedder import Embedder
from app.retrieval.facets import FacetFilter
from app.retrieval.index import CorpusIndex
from app.retrieval.service import RetrievalService
from app.sessions.store import SessionStore
from app.streaming.baseline import BaselineEngine
from app.streaming.engine import EngineOptions, StreamingEngine
from app.synthesis.extractive import ExtractiveSynthesizer


@dataclass
class Runtime:
    settings: Settings
    embedder: Embedder
    index: CorpusIndex
    decomposer: Decomposer
    reranker: object
    validator: GroundingValidator
    sessions: SessionStore
    _controllers: dict
    facets: FacetFilter | None = None
    coverage: TermCoverage | None = None
    calibration: dict | None = None

    def __post_init__(self) -> None:
        self.facets = FacetFilter(self.index, self.decomposer.proper_nouns)
        self.coverage = TermCoverage(self.index)
        self.calibration = self._load_calibration()

    def _load_calibration(self) -> dict:
        """Per-corpus sufficiency gate written by scripts/calibrate_sufficiency.py.
        Ignored (with a visible status) if it was calibrated on a different corpus."""
        s = self.settings
        default = {"type": "threshold", "t_low": s.min_rerank_logit,
                   "status": "uncalibrated default (run scripts/calibrate_sufficiency.py)"}
        path = s.processed_dir / "calibration.json"
        if not path.exists():
            return default
        cal = json.loads(path.read_text(encoding="utf-8"))
        if cal.get("corpus_sha256") != self.index.meta.get("corpus_sha256"):
            return {**default, "status": "calibration file is for a different corpus; using default"}
        return {**cal["gate"], "status": f"calibrated on {cal['summary']['n']} queries (leave-one-out "
                                         f"balanced accuracy {cal['summary']['loo_balanced_accuracy']})"}

    @property
    def gate(self) -> dict:
        return {k: v for k, v in self.calibration.items() if k != "status"}

    @classmethod
    def load(cls, settings: Settings | None = None) -> "Runtime":
        s = settings or get_settings()
        emb = Embedder(s.embedding_model)
        idx = CorpusIndex(s.processed_dir, emb, s.bm25_k1, s.bm25_b, s.rrf_k)
        return cls(s, emb, idx, Decomposer(idx, s.merge_overlap), load_reranker(s.use_reranker, s.reranker_model),
                   GroundingValidator(idx, s.min_claim_support), SessionStore(), {})

    def controller(self, mode: str | None = None) -> RetrievalController:
        mode = mode or self.settings.controller_mode
        if mode not in self._controllers:
            s = self.settings
            self._controllers[mode] = RetrievalController(
                self.index, self.embedder, self.decomposer.proper_nouns, s.configs_dir / "controller_train.jsonl",
                mode, s.retrieve_threshold, s.suppress_threshold, s.rule_min_content_tokens)
        return self._controllers[mode]

    def synthesizer(self, reranker_enabled: bool, quantity_constraints: bool = False):
        s = self.settings
        if s.llm_provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            from app.synthesis.llm import AnthropicProvider, LLMSynthesizer
            return LLMSynthesizer(self.index, AnthropicProvider(s.llm_model))
        return ExtractiveSynthesizer(self.index, reranker_enabled, s.sentences_per_subquery, s.min_sentence_sim,
                                     s.min_rerank_logit, s.min_dense_sim,
                                     self.reranker if reranker_enabled and self.reranker.name != "none" else None,
                                     self.coverage, self.gate, quantity_constraints)

    def engine(self, options: EngineOptions | None = None, controller_mode: str | None = None) -> StreamingEngine:
        opt = options or EngineOptions(final_evidence_k=self.settings.final_evidence_k)
        rr = self.reranker if opt.rerank else NoopReranker()
        opt.rerank = opt.rerank and rr.name != "none"
        svc = RetrievalService(self.index, rr, self.settings.top_k, self.facets if opt.facet_filter else None,
                               opt.quantity_constraints)
        return StreamingEngine(self.index, self.controller(controller_mode), self.decomposer, svc,
                               self.synthesizer(opt.rerank, opt.quantity_constraints), self.validator, opt)

    def baseline(self, mode: str = "dense") -> BaselineEngine:
        svc = RetrievalService(self.index, NoopReranker(), self.settings.top_k)
        return BaselineEngine(self.index, svc, self.synthesizer(False), self.validator, mode,
                              self.settings.final_evidence_k)
