"""Tokenisation shared by BM25, the controller and the grounding checker."""
from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+(?:[.,]\d+)*")
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")

# Compact English stop list (function words + conversational filler that never
# carries retrieval signal in spoken requests).
STOPWORDS = frozenset(
    """a an the and or but if then so of to in on at by for with from into about as is are was were be been
    being am do does did doing have has had having i me my we our you your he she it its they them their this
    that these those there here what which who whom whose when where why how all any both each few more most
    other some such no nor not only own same than too very can will just should could would may might must
    shall also please need needs want wants like tell know let lets get got give show make made up out over
    under again further once ok okay um uh hmm yeah yes well actually really maybe one thing things something
    anything need also plus too im i'm dont don't whats what's could you can you""".split()
)

# Words after which an utterance is almost certainly unfinished.
DANGLING = frozenset(
    """a an the and or but of to in on at by for with from into about as is are was were my our your their
    this that these those some any need want plan planning looking find which who what when where how than
    if then so i we you""".split()
)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


_SUFFIXES = (("ations", ""), ("ation", ""), ("ies", "y"), ("sses", "ss"), ("ings", ""), ("ing", ""),
             ("ed", ""), ("es", ""), ("s", ""))


def stem(tok: str) -> str:
    """Small suffix stripper so cancel/cancelled/cancellation/cancelling share a stem.

    Not a full Porter stemmer (no NLTK dependency); it only needs to be applied
    identically to queries and documents.
    """
    if len(tok) <= 3 or tok.isdigit():
        return tok
    for suf, rep in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            tok = tok[: len(tok) - len(suf)] + rep
            break
    if len(tok) > 4 and tok[-1] == tok[-2] and tok[-1] in "lpt":   # cancell -> cancel
        tok = tok[:-1]
    if len(tok) > 4 and tok.endswith("e"):                          # reserve -> reserv
        tok = tok[:-1]
    return tok


def content_tokens(text: str) -> list[str]:
    """Stemmed non-stopword tokens."""
    return [stem(t) for t in tokenize(text) if t not in STOPWORDS]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()]


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM_RE.findall(text)}
