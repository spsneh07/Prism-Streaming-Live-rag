"""Retrieval controller: WAIT / RETRIEVE / SUPPRESS on every transcript chunk.

Two small learned models plus deterministic guardrails:

* **Intent classifier** (logistic regression on the MiniLM embedding + 4 scalar
  features) -> new_request | refinement | presentation | chitchat. Decides
  whether the corpus is needed at all (SUPPRESS for presentation/chitchat).
* **Readiness model** (logistic regression on 6 corpus-aware features of the
  partial transcript) -> P(the prefix is specific enough that retrieving now is
  useful). This is the "intent stability" check: it does NOT search the corpus
  per chunk; it only embeds the prefix and looks tokens up in the BM25 vocabulary.

Guardrails (deterministic, explainable):
* never RETRIEVE twice for the same content (``new_content`` must be >= 1);
* presentation/refinement require a prior answer in the session;
* at utterance end the controller always resolves to RETRIEVE or SUPPRESS.

``mode="rule"`` swaps both models for keyword/threshold rules; it exists only as
the ablation baseline required by the Theme 4 guide.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from app.models.schemas import Decision
from app.retrieval.text import DANGLING, content_tokens, tokenize

INTENTS = ["new_request", "refinement", "presentation", "chitchat"]
_WH = {"what", "which", "who", "whom", "how", "when", "where", "why", "can", "could", "is", "are", "do", "does",
       "should", "tell", "explain"}
# Syntactic cue for presentation requests: an imperative verb acting on the previous
# answer ("put THAT ...", "make IT ...", "give ME ..."). Refinements are declarative
# ("the trip WAS ...", "we'll HAVE ..."). Used as one learned feature, not a rule.
_OBJ_REF = {"that", "it", "this", "those", "these", "your", "me", "them"}
_NOT_VERB_START = {"it", "that", "this", "those", "these", "we", "i", "they", "you", "he", "she", "there", "the", "a",
                   "an", "some", "oh", "also", "and", "but", "actually", "so", "my", "our", "its", "what", "which",
                   "who", "how", "when", "where", "why", "can", "could", "is", "are", "do", "does", "will", "would",
                   "separately", "unrelated", "different", "another", "switching"}


def imperative_on_previous(tokens: list[str]) -> float:
    return float(len(tokens) >= 2 and tokens[0] not in _NOT_VERB_START and any(t in _OBJ_REF for t in tokens[1:3]))


_RULE_SUPPRESS = ("shorter", "bullet", "repeat", "rephrase", "summarize your", "summarise your", "again",
                  "thanks", "thank you", "hello")


@dataclass
class StreamState:
    """Per-utterance controller memory (lives inside one session turn)."""
    prev_prefix: str = ""
    retrieved_tokens: set[str] = field(default_factory=set)


class RetrievalController:
    def __init__(self, index, embedder, proper_nouns: set[str], train_file: Path, mode: str = "learned",
                 retrieve_threshold: float = 0.5, suppress_threshold: float = 0.5, rule_min_content: int = 3):
        self.index, self.embedder, self.proper_nouns = index, embedder, proper_nouns
        self.mode = mode
        self.retrieve_threshold = retrieve_threshold
        self.suppress_threshold = suppress_threshold
        self.rule_min_content = rule_min_content
        self.train_report: dict = {}
        self._train(train_file)

    # ------------------------------------------------------------------ features
    def _content(self, text: str) -> list[str]:
        return [t for t in content_tokens(text) if self.index.bm25.vocab_idf(t) is not None]

    def readiness_features(self, prefix: str, state: StreamState) -> dict[str, float]:
        toks = tokenize(prefix)
        cont = self._content(prefix)
        new = [t for t in set(cont) if t not in state.retrieved_tokens]
        drift = 0.0
        if state.prev_prefix:
            drift = 1.0 - float(self.embedder.encode_one(prefix) @ self.embedder.encode_one(state.prev_prefix))
        return {
            "n_content": len(set(cont)) / 5.0,
            "idf_mass": sum(self.index.bm25.vocab_idf(t) or 0.0 for t in set(cont)) / 10.0,
            "dangling": float(bool(toks) and toks[-1] in DANGLING),
            "new_content": len(new) / 3.0,
            "drift": drift,
            "has_entity": float(any(t in self.proper_nouns for t in toks)),
        }

    def _intent_vector(self, text: str, prev: str | None) -> np.ndarray:
        emb = self.embedder.encode_one(text)
        toks = tokenize(text)
        sim_prev = float(emb @ self.embedder.encode_one(prev)) if prev else 0.0
        # New corpus content relative to the current topic: refinements add searchable
        # constraints ("international", "gluten"); presentation requests add none.
        new_mass = 0.0
        if prev:
            old = set(self._content(prev))
            new_mass = sum(self.index.bm25.vocab_idf(t) or 0.0 for t in set(self._content(text)) - old) / 10.0
        extra = np.array([
            float(bool(toks) and (toks[0] in _WH or text.strip().endswith("?"))),
            float(prev is not None),
            sim_prev,
            float(len(toks) <= 8),
            min(new_mass, 1.0),
            imperative_on_previous(toks),
        ], dtype=np.float32) * 2.0  # scaled so they are not drowned by 384 embedding dims
        return np.concatenate([emb, extra])

    # ------------------------------------------------------------------ training
    def _train(self, path: Path) -> None:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        ix = [r for r in rows if r["kind"] == "intent"]
        X = np.stack([self._intent_vector(r["text"], r["prev"]) for r in ix])
        y = np.array([INTENTS.index(r["label"]) for r in ix])
        self.intent_clf = LogisticRegression(max_iter=2000, C=4.0).fit(X, y)

        feats, labels = [], []
        for r in (r for r in rows if r["kind"] == "readiness"):
            st = StreamState()
            prefix = ""
            for chunk, lab in zip(r["chunks"], r["labels"]):
                prefix = f"{prefix} {chunk}".strip()
                f = self.readiness_features(prefix, st)
                feats.append(list(f.values()))
                labels.append(lab)
                st.prev_prefix = prefix
                if lab:
                    st.retrieved_tokens |= set(self._content(prefix))
        self.readiness_keys = list(self.readiness_features("x", StreamState()).keys())
        self.ready_clf = LogisticRegression(max_iter=2000).fit(np.array(feats), np.array(labels))
        self.train_report = {
            "intent_examples": len(ix),
            "intent_train_acc": float(self.intent_clf.score(X, y)),
            "readiness_examples": len(labels),
            "readiness_train_acc": float(self.ready_clf.score(np.array(feats), np.array(labels))),
            "readiness_weights": dict(zip(self.readiness_keys, np.round(self.ready_clf.coef_[0], 3).tolist())),
        }

    # ------------------------------------------------------------------ inference
    def classify_intent(self, text: str, prev: str | None) -> tuple[str, dict[str, float]]:
        if self.mode == "rule":
            low = text.lower()
            if any(k in low for k in _RULE_SUPPRESS):
                label = "chitchat" if any(k in low for k in ("thank", "hello")) else "presentation"
            else:
                label = "new_request"
            return label, {label: 1.0}
        p = self.intent_clf.predict_proba(self._intent_vector(text, prev)[None, :])[0]
        probs = {INTENTS[i]: float(p[i]) for i in range(len(INTENTS))}
        return max(probs, key=probs.get), probs

    def decide(self, prefix: str, state: StreamState, *, is_final: bool, prev_answer_topic: str | None
               ) -> Decision:
        has_prior = prev_answer_topic is not None
        intent, probs = self.classify_intent(prefix, prev_answer_topic)
        feats = self.readiness_features(prefix, state)
        feats_out = {k: round(v, 3) for k, v in feats.items()}
        feats_out.update({f"p_{k}": round(v, 3) for k, v in probs.items()})

        # --- guardrails on intent -------------------------------------------------
        if intent == "refinement" and not has_prior:
            intent = "new_request"
        if intent in ("presentation", "chitchat") and probs.get(intent, 1.0) >= self.suppress_threshold:
            if intent == "presentation" and not has_prior:
                return Decision("SUPPRESS", "presentation request but no prior answer in session",
                                probs[intent], intent, feats_out)
            if is_final or probs[intent] >= 0.8:
                reason = ("presentation_restructure: reuse session answer, no corpus search"
                          if intent == "presentation" else "conversational turn: no factual content requested")
                return Decision("SUPPRESS", reason, probs[intent], intent, feats_out)
            return Decision("WAIT", f"leaning {intent} ({probs[intent]:.2f}); waiting for more words",
                            probs[intent], intent, feats_out)

        # --- readiness ----------------------------------------------------------------
        if self.mode == "rule":
            p_ready = 1.0 if feats["n_content"] * 5 >= self.rule_min_content else 0.0
        else:
            p_ready = float(self.ready_clf.predict_proba(np.array([list(feats.values())]))[0, 1])
        feats_out["p_ready"] = round(p_ready, 3)
        has_new = feats["new_content"] > 0

        if is_final:
            if not self._content(prefix) and intent != "refinement":
                return Decision("SUPPRESS", "utterance has no searchable content", 1.0, "chitchat", feats_out)
            if not has_new:
                return Decision("RETRIEVE", "utterance complete; all content already retrieved provisionally",
                                1.0, intent, feats_out)
            return Decision("RETRIEVE", "utterance complete; retrieving remaining content", 1.0, intent, feats_out)
        if p_ready >= self.retrieve_threshold and has_new:
            why = "stable, specific intent" if not feats["dangling"] else "specific content despite open phrase"
            return Decision("RETRIEVE", f"{why} (p_ready={p_ready:.2f}, +{round(feats['new_content'] * 3)} new terms)",
                            p_ready, intent, feats_out)
        if not has_new and p_ready >= self.retrieve_threshold:
            return Decision("WAIT", "no new content since last retrieval", 1 - p_ready, intent, feats_out)
        why = "phrase is unfinished" if feats["dangling"] else "intent not yet specific"
        return Decision("WAIT", f"{why} (p_ready={p_ready:.2f})", 1 - p_ready, intent, feats_out)

    @staticmethod
    def mark_retrieved(state: StreamState, tokens: set[str]) -> None:
        state.retrieved_tokens |= tokens
