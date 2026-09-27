"""Answer-coverage: does the retrieved evidence even mention what was asked?

A cross-encoder scores *topical* relevance, so "What is the parking fee at the
Pune venues?" scores well against a Pune-venue passage that never mentions
parking. Coverage is the complementary lexical check: the idf-weighted fraction
of the question's key terms that appear somewhere in the evidence (text + section
heading + document title).

* Key terms: non-stopword words (>= 3 chars) of the user's clause.
* Weight: surface-form idf over the corpus; words the corpus never uses get the
  maximum idf, because an absent concept is the strongest sign of "not answerable".
* Matching is on surface forms, not stems (the stemmer maps "parking" to "park",
  which would match "Koregaon Park Hall"): equal after plural stripping, or a
  shared prefix of >= 5 characters ("cancel" ~ "cancellation").

The gate that combines coverage with the cross-encoder score is calibrated per
corpus (scripts/calibrate_sufficiency.py); nothing here is corpus-specific.
"""
from __future__ import annotations

import math
import re

from app.retrieval.text import STOPWORDS

_WORD = re.compile(r"[a-z0-9]+")
# Question / degree words that say *how* something is asked, not *what* is asked.
# Generic English, not corpus-specific; used only for coverage.
_QUESTION_WORDS = frozenset("""many much long often soon quickly early late happen happens happened big bigger
biggest large larger largest small smaller smallest fit fits able allowed okay way ways kind type sort exactly
still else ever whether usually typically actually basically someone something anyone anything new""".split())
MIN_PREFIX = 5


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _match(a: str, b: str) -> bool:
    if a == b or a.rstrip("s") == b.rstrip("s"):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= MIN_PREFIX


class TermCoverage:
    def __init__(self, index):
        self.index = index
        docs = [set(words(f"{c.source_title} {c.section_title} {c.text}")) for c in index.chunks]
        n = len(docs)
        df: dict[str, int] = {}
        for d in docs:
            for w in d:
                df[w] = df.get(w, 0) + 1
        self.idf = {w: math.log(1 + n / f) for w, f in df.items()}
        self.max_idf = math.log(1 + n)
        self._by_prefix: dict[str, list[str]] = {}
        for w in self.idf:
            self._by_prefix.setdefault(w[:MIN_PREFIX], []).append(w)

    def key_terms(self, text: str) -> list[str]:
        out = []
        for w in words(text):
            if len(w) >= 3 and w not in STOPWORDS and w not in _QUESTION_WORDS and w not in out:
                out.append(w)
        return out

    def weight(self, term: str) -> float:
        if term in self.idf:
            return self.idf[term]
        near = [self.idf[w] for w in self._by_prefix.get(term[:MIN_PREFIX], []) if _match(term, w)]
        return max(near) if near else self.max_idf

    def coverage(self, text: str, chunk_ids: list[str]) -> tuple[float, list[str]]:
        """Returns (coverage in [0,1], uncovered key terms)."""
        terms = self.key_terms(text)
        if not terms:
            return 1.0, []
        ev: set[str] = set()
        for cid in chunk_ids:
            c = self.index.by_id[cid]
            ev |= set(words(f"{c.source_title} {c.section_title} {c.text}"))
        total = covered = 0.0
        missing = []
        for t in terms:
            w = self.weight(t)
            total += w
            if any(_match(t, e) for e in ev):
                covered += w
            else:
                missing.append(t)
        return covered / total, missing
