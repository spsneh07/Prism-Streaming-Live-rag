"""Presentation-only turns (retrieval SUPPRESSED): reshape the session's last answer.

Only formatting parameters are parsed here (bullet count, "shorter"); the content
always comes from the claims and citations already in session memory, so no new
facts or citations can appear.
"""
from __future__ import annotations

import re

from app.models.schemas import AnswerVersion, Claim

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "single": 1}


def parse_format(utterance: str) -> dict:
    low = utterance.lower()
    n = None
    m = re.search(r"\b(\d+|one|two|three|four|five|single)\s+(?:short\s+)?(?:bullet|bullets|point|points|sentence|sentences|lines?)\b", low)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORDS[m.group(1)]
    bullets = "bullet" in low or "point" in low or "list" in low
    shorter = any(w in low for w in ("short", "brief", "concise", "summar", "tl;dr", "one sentence"))
    return {"max_items": n, "bullets": bullets, "shorter": shorter and n is None}


def _round_robin(claims: list[Claim]) -> list[Claim]:
    """Order claims so each sub-intent contributes its best claim first."""
    groups: dict[str, list[Claim]] = {}
    for c in claims:
        groups.setdefault(c.sub_query_id, []).append(c)
    out, i = [], 0
    while any(i < len(g) for g in groups.values()):
        out += [g[i] for g in groups.values() if i < len(g)]
        i += 1
    return out


def restructure(version: AnswerVersion, utterance: str) -> tuple[list[Claim], dict]:
    fmt = parse_format(utterance)
    claims = _round_robin([c for c in version.claims if c.supported and c.status != "removed"])
    if fmt["max_items"]:
        claims = claims[: fmt["max_items"]]
    elif fmt["shorter"]:
        n_groups = len({c.sub_query_id for c in claims})
        claims = claims[: max(1, n_groups)]
    return claims, fmt


def render(claims: list[Claim], bullets: bool) -> str:
    lines = []
    for c in claims:
        cites = " ".join(f"[{cid.rsplit(':', 1)[0].replace(':', ' §')}]" for cid in dict.fromkeys(c.citations))
        lines.append(f"{'• ' if bullets else ''}{c.text} {cites}".strip())
    return ("\n" if bullets else " ").join(lines)
