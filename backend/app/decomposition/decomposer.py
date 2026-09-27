"""Multi-intent decomposition of one natural utterance into search-ready sub-queries.

Approach (cheap, deterministic, explainable - no LLM call on the hot path):

1. **Clause segmentation** on coordination boundaries (", and", "as well as",
   ";", "?", ...). This over-splits on purpose.
2. **Constraint re-attachment**: fragments that start with a preposition
   ("for 30 people", "in Pune") or have < 2 content words are constraints of
   the previous clause, not intents, and are merged back.
3. **Retrieval-overlap merge**: each remaining clause is probed against the
   corpus; adjacent clauses with the same best section whose top-3 *sections*
   also overlap (Jaccard >= 0.5) ask about the same thing and are merged. This is the guard against the
   "over-fragmenting sub-queries" pitfall - the corpus itself decides whether two
   phrasings are distinct needs.
4. **Context carry-over**: named entities that the corpus knows as proper nouns
   (e.g. "Pune") are propagated to sibling sub-queries that lack them, so
   "the cancellation policy" becomes "cancellation policy Pune".
5. **Grounded intent label**: the heading of the top section retrieved for a
   sub-query (never an invented category).

The probe results of step 3 are returned so the caller can reuse them instead of
searching twice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.schemas import ScoredChunk, SubQuery
from app.retrieval.text import STOPWORDS, content_tokens, split_sentences, tokenize

_SPLIT_RE = re.compile(
    r"\s*(?:[?;!]+\s*|\.\s+|,\s*(?:and\s+(?:also\s+)?|but\s+|also\s+|plus\s+)?|"
    r"\s+(?:and also|as well as|and then|plus|and)\s+)",
    re.IGNORECASE,
)
_FILLERS = {"so", "and", "but", "also", "then", "ok", "okay", "well", "um", "uh", "oh", "plus", "actually", "anyway"}
_WH_WORDS = {"what", "which", "who", "whom", "whose", "when", "where", "why", "how"}
_REQUEST_VERBS = {"know", "tell", "explain", "check", "find"}
_REQUEST_MARKERS = {"need", "needs", "want", "wants", "require", "requires", "looking", "tell", "give", "show", "find",
                    "book", "know", "explain", "check", "please", "help"}
_QUESTION_START = {"how", "what", "which", "who", "whom", "when", "where", "why", "do", "does", "did", "can", "could",
                   "is", "are", "should", "will", "would", "may", "must"}
_LEADING_PREPOSITIONS = {"for", "in", "at", "on", "with", "from", "by", "near", "within", "during", "before", "after"}


@dataclass
class Decomposition:
    is_multi_intent: bool
    sub_queries: list[SubQuery]
    probe_results: dict[str, list[ScoredChunk]] = field(default_factory=dict)
    trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_multi_intent": self.is_multi_intent,
            "sub_queries": [{"id": q.id, "text": q.text, "intent": q.intent, "source_span": q.source_span,
                             "carried_context": q.carried_context} for q in self.sub_queries],
            "trace": self.trace,
        }


def corpus_proper_nouns(index) -> set[str]:
    """Words the corpus writes capitalised mid-sentence (Pune, Baner, Koregaon, ...)."""
    out: set[str] = set()
    for c in index.chunks:
        for sent in split_sentences(c.text):
            words = re.findall(r"[A-Za-z]+", sent)
            out.update(w.lower() for w in words[1:] if w[0].isupper() and w.lower() not in STOPWORDS)
    return out


class Decomposer:
    def __init__(self, index, merge_overlap: float = 0.5, probe_k: int = 3):
        self.index = index
        self.merge_overlap = merge_overlap
        self.probe_k = probe_k
        self.proper_nouns = corpus_proper_nouns(index)

    # -- helpers ---------------------------------------------------------------
    def _n_content(self, text: str) -> int:
        return sum(1 for t in content_tokens(text) if self.index.bm25.vocab_idf(t) is not None or len(t) > 3)

    def _focus(self, clause: str) -> str:
        """The information-need span of a clause, used to select and verify answer
        sentences. In "so I'm heading abroad next month and I'd like to know the daily
        meal allowance", the words before the last wh-word / request marker are context,
        not the question. Falls back to the whole cleaned clause."""
        words = clause.strip(" ,.;?!").split()
        low = [re.sub(r"[^a-z']", "", w.lower()) for w in words]
        marks = [i for i, w in enumerate(low) if w in _WH_WORDS or
                 (w in _REQUEST_VERBS and i + 1 < len(low))]
        if marks:
            span = " ".join(words[marks[-1] + (1 if low[marks[-1]] in _REQUEST_VERBS else 0):])
            if self._n_content(span) >= 2:
                return self._clean(span) or span
        return self._clean(clause) or clause.strip()

    @staticmethod
    def _has_request(text: str) -> bool:
        toks = set(tokenize(text))
        return bool(toks & _REQUEST_MARKERS)

    @staticmethod
    def _is_question(text: str) -> bool:
        toks = [t for t in tokenize(text)]
        while toks and toks[0] in _FILLERS:          # "so how often ...", "and what is ..."
            toks.pop(0)
        return text.strip().endswith("?") or (bool(toks) and toks[0] in _QUESTION_START)

    @staticmethod
    def _clean(text: str) -> str:
        words = text.strip(" ,.;?!").split()
        while words and words[0].lower().strip(",") in STOPWORDS:
            words.pop(0)
        return " ".join(words)

    def entities(self, text: str) -> list[str]:
        seen: list[str] = []
        for w in re.findall(r"[A-Za-z]+", text):
            if w.lower() in self.proper_nouns and w.lower() not in (s.lower() for s in seen):
                seen.append(w[0].upper() + w[1:])
        return seen

    def _sections(self, hits: list[ScoredChunk]) -> set[str]:
        return {h.chunk_id.rsplit(":", 1)[0] for h in hits[: self.probe_k]}

    # -- main ----------------------------------------------------------------
    def decompose(self, utterance: str, id_prefix: str = "q", context_hint: str = "") -> Decomposition:
        trace: list[str] = []
        raw = [s for s in _SPLIT_RE.split(utterance) if s and s.strip(" ,.;?!")]
        trace.append(f"segments={raw}")

        clauses: list[str] = []
        for seg in raw:
            first = tokenize(seg)[:1]
            is_constraint = bool(first) and first[0] in _LEADING_PREPOSITIONS
            # A short *question* ("how do I register them") is its own intent, never a constraint.
            if clauses and (is_constraint or (self._n_content(seg) < 2 and not self._is_question(seg))):
                trace.append(f"attach '{seg.strip()}' -> previous clause (constraint/too short)")
                clauses[-1] = f"{clauses[-1]} {seg.strip()}"
            else:
                clauses.append(seg.strip())
        # Statements that carry no request ("We have customers visiting next week", "yesterday
        # I was chatting with my manager") and precede a question are context for that
        # question, not intents of their own: merge them forward.
        if len(clauses) > 1 and self._n_content(clauses[0]) < 2:
            clauses[1] = f"{clauses[0]} {clauses[1]}"
            clauses.pop(0)
        merged_ctx: list[str] = []
        buffer: list[str] = []
        for i, cl in enumerate(clauses):
            later_question = any(self._is_question(c) for c in clauses[i + 1:])
            if not self._is_question(cl) and not self._has_request(cl) and later_question:
                buffer.append(cl)
                continue
            if buffer:
                trace.append(f"context {buffer} merged into '{cl}'")
                cl = " ".join(buffer + [cl])
                buffer = []
            merged_ctx.append(cl)
        clauses = merged_ctx + ([" ".join(buffer)] if buffer else [])

        all_entities = self.entities(utterance + " " + context_hint)

        def with_context(clause: str) -> tuple[str, list[str]]:
            have = {e.lower() for e in self.entities(clause)}
            carry = [e for e in all_entities if e.lower() not in have]
            text = self._clean(clause) or clause.strip()
            return (f"{text} {' '.join(carry)}".strip(), carry)

        probes = [(c, *with_context(c)) for c in clauses]
        hits = [self.index.search(q, "hybrid", 8) for _, q, _ in probes]

        merged: list[tuple[str, str, list[str], list[ScoredChunk]]] = []
        prev_hits: list[ScoredChunk] = []
        for (clause, q, carry), h in zip(probes, hits):
            if merged:
                # Same best section AND overlapping top-3 => the two clauses ask for the same
                # thing (near-duplicate phrasing). Different best sections of the same
                # document (e.g. annual vs sick leave) stay separate intents. The comparison
                # is with the previous *clause's own* probe, not the merged query, whose
                # results drift toward whatever was merged first.
                overlap = self._jaccard(self._sections(prev_hits), self._sections(h))
                same_top = bool(h) and bool(prev_hits) and                     h[0].chunk_id.rsplit(":", 1)[0] == prev_hits[0].chunk_id.rsplit(":", 1)[0]
                prev_hits = h
                if same_top and overlap >= self.merge_overlap:
                    pc = merged[-1][0] + " and " + clause
                    nq, ncarry = with_context(pc)
                    trace.append(f"merge '{clause}' into previous (section overlap {overlap:.2f})")
                    merged[-1] = (pc, nq, ncarry, self.index.search(nq, "hybrid", 8))
                    continue
            merged.append((clause, q, carry, h))
            prev_hits = h

        sub_queries: list[SubQuery] = []
        probe_results: dict[str, list[ScoredChunk]] = {}
        for i, (clause, q, carry, h) in enumerate(merged, start=1):
            sq_id = f"{id_prefix}{i}"
            top = self.index.by_id[h[0].chunk_id] if h else None
            intent = f"{top.source_title} › {top.section_title}" if top else "unknown"
            sub_queries.append(SubQuery(sq_id, q, intent, clause, carry, self._focus(clause)))
            probe_results[sq_id] = h
        return Decomposition(len(sub_queries) > 1, sub_queries, probe_results, trace)

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        return len(a & b) / max(1, len(a | b))
