"""Quantity constraints stated in a request ("for 30 people").

A group-size phrase "for [about] N <noun>" is read as a minimum: the evidence must
accommodate at least N of <noun>. Neither the cross-encoder nor BM25 compares numbers,
so a section that answers the constraint ("seats up to 40 people") can rank below a
section that merely shares the topic words ("customer workshops"). This module detects
the constraint and tests text against it; retrieval and synthesis use it to give
constraint-satisfying evidence a place in the answer. Nothing here is corpus-specific:
the noun is taken from the request, and matching is on the text alone.
"""
from __future__ import annotations

import re

_APPROX = r"(?:about|around|roughly|approximately|some|up to|at least)\s+"
_PATTERN = re.compile(rf"\bfor\s+(?:{_APPROX})?(\d+)\s+([a-z]+)", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z]+|\d+(?:,\d{3})*")
LOOKBACK = 8   # tokens before the noun that may hold its quantity ("capacities of 20, 35 and 80 people")


def _norm(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def quantity_constraints(text: str) -> list[tuple[int, str]]:
    """``[(N, noun)]`` for every "for N <noun>" phrase in the request."""
    return [(int(n), _norm(noun)) for n, noun in _PATTERN.findall(text or "")]


def satisfies(text: str, constraints: list[tuple[int, str]]) -> bool:
    """True when the text states a quantity >= N for the constraint's noun."""
    if not constraints:
        return False
    toks = _TOKEN.findall(text)
    for need, noun in constraints:
        for i, tok in enumerate(toks):
            if _norm(tok) != noun:
                continue
            nums = [int(t.replace(",", "")) for t in toks[max(0, i - LOOKBACK):i] if t[0].isdigit()]
            if any(n >= need for n in nums):
                return True
    return False


def promote(cands: list, constraints: list[tuple[int, str]], texts: dict[str, str], window: int = 3,
            max_promoted: int = 2) -> tuple[list, list[str]]:
    """Reorder reranked candidates so that constraint-satisfying chunks reach the answer window.

    If none of the top ``window`` chunks satisfies the constraint, up to ``max_promoted``
    satisfying chunks from further down move to the positions right after the reranker's
    top result (their own relative order is kept). The top result itself is never displaced.
    """
    if not constraints or len(cands) <= 1:
        return cands, []
    if any(satisfies(texts[c.chunk_id], constraints) for c in cands[:window]):
        return cands, []
    hits = [c for c in cands[window:] if satisfies(texts[c.chunk_id], constraints)][:max_promoted]
    if not hits:
        return cands, []
    rest = [c for c in cands[1:] if c not in hits]
    return [cands[0], *hits, *rest], [c.chunk_id for c in hits]
