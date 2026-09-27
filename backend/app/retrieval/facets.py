"""Facet-consistency filter, derived automatically from document titles.

Documents whose titles are identical once proper nouns are removed form a *family*
("Approved Event Venues - Pune" / "... - Bengaluru"); the removed words are the
facet values. If a query names a facet value of a family, chunks from sibling
documents with a *different* value are dropped: a Pune request must not be
answered with a Bengaluru venue just because the capacity matches.

Nothing is hard-coded: families and values come from the corpus, and documents
outside any family are never filtered.
"""
from __future__ import annotations

import re

from app.models.schemas import ScoredChunk


class FacetFilter:
    def __init__(self, index, proper_nouns: set[str]):
        titles: dict[str, str] = {}
        for c in index.chunks:
            titles.setdefault(c.document_id, c.source_title)
        families: dict[str, dict[str, set[str]]] = {}
        for doc, title in titles.items():
            words = re.findall(r"[A-Za-z]+", title)
            values = {w.lower() for w in words if w.lower() in proper_nouns}
            skeleton = " ".join(w.lower() for w in words if w.lower() not in proper_nouns)
            if values:
                families.setdefault(skeleton, {})[doc] = values
        # keep only real families (>= 2 documents that differ in their facet values)
        self.doc_values: dict[str, set[str]] = {}
        self.family_of: dict[str, str] = {}
        for skel, docs in families.items():
            if len(docs) >= 2 and len({frozenset(v) for v in docs.values()}) >= 2:
                for d, v in docs.items():
                    self.doc_values[d] = v
                    self.family_of[d] = skel
        self.index = index

    @property
    def families(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for d, f in self.family_of.items():
            out.setdefault(f, []).append(d)
        return out

    def apply(self, query: str, cands: list[ScoredChunk]) -> tuple[list[ScoredChunk], list[str]]:
        q = {w.lower() for w in re.findall(r"[A-Za-z]+", query)}
        wanted: dict[str, set[str]] = {}
        for d, vals in self.doc_values.items():
            if vals & q:
                wanted.setdefault(self.family_of[d], set()).update(vals & q)
        if not wanted:
            return cands, []
        kept, dropped = [], []
        for c in cands:
            doc = self.index.by_id[c.chunk_id].document_id
            fam = self.family_of.get(doc)
            if fam in wanted and not (self.doc_values[doc] & wanted[fam]):
                dropped.append(c.chunk_id)
            else:
                kept.append(c)
        return kept, dropped
