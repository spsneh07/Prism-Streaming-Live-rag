"""Corpus loading and section-aware chunking - format-agnostic.

Supported inputs (recursively under ``data/raw``):

* ``.md``    - optional ``key: value`` front matter; any ``#``..``######`` heading
               starts a section. Section ids are preserved from the source when the
               heading carries one (``## Refunds {#S4}`` or a leading number such as
               ``## 4.2 Refunds``); otherwise they are assigned S1, S2, ... in order.
* ``.txt``   - headings detected heuristically (short numbered / Title Case / UPPER
               lines followed by text); otherwise the file is one section.
* ``.json`` / ``.jsonl`` - records ``{doc_id|id, title, text}`` or
               ``{doc_id, title, sections: [{section_id|id, title|heading, text}]}``;
               ids given by the source are kept verbatim.
* ``.pdf``   - one section per page (``p3``), requires PyMuPDF (optional).
* ``.docx``  - sections from Heading/Title paragraph styles, requires python-docx (optional).

Nothing is invented: metadata comes only from the source (front matter / JSON
fields). The only derived field is ``superseded_by``, the inverse of a source
``supersedes`` declaration, so either direction can be declared.
Every chunk records its source file and line (or page) range.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.models.schemas import Chunk

SUPPORTED = {".md", ".markdown", ".txt", ".json", ".jsonl", ".pdf", ".docx"}
_HEADING_MD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_EXPLICIT_ID = re.compile(r"\s*\{#([A-Za-z0-9_.\-]+)\}\s*$")
_NUMBERED = re.compile(r"^(?:(?:section|sec\.?|§)\s*)?(\d+(?:\.\d+)*)[.)]?\s+(\S.*)$", re.IGNORECASE)

Para = tuple[int, int, str]                 # (line_start, line_end, text)
Section = tuple[str | None, str, list[Para]]  # (source section id or None, title, paragraphs)


# ----------------------------------------------------------------------------- helpers
def _safe_id(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", s.strip()).strip("_") or "X"


def _parse_front_matter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta: dict[str, str] = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return meta, i + 1
        if ":" in lines[i]:
            k, v = lines[i].split(":", 1)
            meta[k.strip()] = v.strip()
    raise ValueError("unterminated front matter")


def _split_heading(text: str) -> tuple[str | None, str]:
    """Return (source section id or None, clean title)."""
    m = _EXPLICIT_ID.search(text)
    if m:
        return m.group(1), text[: m.start()].strip()
    m = _NUMBERED.match(text)
    if m:
        return m.group(1), m.group(2).strip()
    return None, text.strip()


def _split_long(paragraphs: list[Para], max_words: int) -> list[Para]:
    """Greedy paragraph packing; a section is only split when it exceeds max_words.
    A single paragraph longer than max_words is split on sentence boundaries."""
    units: list[Para] = []
    for ls, le, text in paragraphs:
        if len(text.split()) <= max_words:
            units.append((ls, le, text))
            continue
        buf: list[str] = []
        for sent in re.split(r"(?<=[.!?])\s+", text):
            if buf and len(" ".join(buf + [sent]).split()) > max_words:
                units.append((ls, le, " ".join(buf)))
                buf = []
            buf.append(sent)
        if buf:
            units.append((ls, le, " ".join(buf)))
    out: list[Para] = []
    cur: list[Para] = []
    words = 0
    for p in units:
        n = len(p[2].split())
        if cur and words + n > max_words:
            out.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
            cur, words = [], 0
        cur.append(p)
        words += n
    if cur:
        out.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
    return out


def _paragraphs_by_lines(lines: list[str], start: int, is_heading) -> list[Section]:
    """Generic line walker: ``is_heading(line) -> title | None``."""
    sections: list[Section] = []
    para: list[tuple[int, str]] = []

    def flush() -> None:
        if para:
            if not sections:
                sections.append((None, "Introduction", []))
            sections[-1][2].append((para[0][0], para[-1][0], " ".join(t for _, t in para)))
        para.clear()

    for idx in range(start, len(lines)):
        line = lines[idx].rstrip()
        head = is_heading(idx, line)
        if head is not None:
            flush()
            sid, title = _split_heading(head)
            sections.append((sid, title, []))
        elif not line.strip():
            flush()
        else:
            para.append((idx + 1, line.strip()))
    flush()
    return [s for s in sections if s[2]]


# ----------------------------------------------------------------------------- per format
def _read_markdown(path: Path) -> tuple[dict, list[Section]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta, start = _parse_front_matter(lines)
    # A lone top-level "# Title" before any other heading is the document title.
    first = next((i for i in range(start, len(lines)) if _HEADING_MD.match(lines[i])), None)
    if first is not None and "title" not in meta:
        m = _HEADING_MD.match(lines[first])
        if len(m.group(1)) == 1:
            meta["title"] = m.group(2)
            start = first + 1

    def is_heading(_i, line):
        m = _HEADING_MD.match(line)
        return m.group(2) if m else None

    return meta, _paragraphs_by_lines(lines, start, is_heading)


def _read_text(path: Path) -> tuple[dict, list[Section]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    meta, start = _parse_front_matter(lines)

    def is_heading(i, line):
        s = line.strip()
        if not s or len(s.split()) > 10 or s[-1] in ".,;:?!":
            return None
        nxt = next((lines[j] for j in range(i + 1, len(lines)) if lines[j].strip()), "")
        if not nxt or len(nxt.split()) < 6:           # a heading introduces a paragraph
            return None
        prev_blank = i == start or not lines[i - 1].strip()
        looks = _NUMBERED.match(s) or s.isupper() or all(w[0].isupper() for w in s.split() if w[0].isalpha())
        return s if (prev_blank and looks) else None

    secs = _paragraphs_by_lines(lines, start, is_heading)
    return meta, secs


def _read_json_records(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(l) for l in raw.splitlines() if l.strip()]
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("documents"), list):
        return data["documents"]
    return data if isinstance(data, list) else [data]


def _record_sections(rec: dict) -> list[Section]:
    if isinstance(rec.get("sections"), list):
        out = []
        for i, s in enumerate(rec["sections"], start=1):
            text = str(s.get("text", "")).strip()
            if text:
                sid = s.get("section_id") or s.get("id")
                out.append((str(sid) if sid is not None else None, str(s.get("title") or s.get("heading") or f"Section {i}"),
                            [(i, i, p.strip()) for p in re.split(r"\n\s*\n", text) if p.strip()]))
        return out
    text = str(rec.get("text") or rec.get("content") or "").strip()
    return [(None, str(rec.get("section_title") or "Content"),
             [(i + 1, i + 1, p.strip()) for i, p in enumerate(re.split(r"\n\s*\n", text)) if p.strip()])] if text else []


def _read_pdf(path: Path) -> tuple[dict, list[Section]]:
    try:
        import pymupdf
    except ImportError as exc:  # optional dependency
        raise RuntimeError(f"{path.name}: install pymupdf to ingest PDF files") from exc
    doc = pymupdf.open(path)
    meta = {"title": (doc.metadata or {}).get("title") or path.stem}
    secs: list[Section] = []
    for pno, page in enumerate(doc, start=1):
        paras = [(pno, pno, " ".join(b[4].split())) for b in page.get_text("blocks") if b[4].strip()]
        if paras:
            secs.append((f"p{pno}", f"Page {pno}", paras))
    return meta, secs


def _read_docx(path: Path) -> tuple[dict, list[Section]]:
    try:
        import docx
    except ImportError as exc:
        raise RuntimeError(f"{path.name}: install python-docx to ingest .docx files") from exc
    d = docx.Document(str(path))
    meta: dict[str, str] = {"title": d.core_properties.title or path.stem}
    secs: list[Section] = []
    for i, p in enumerate(d.paragraphs, start=1):
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        if style.startswith("heading") or style == "title":
            sid, title = _split_heading(text)
            secs.append((sid, title, []))
        else:
            if not secs:
                secs.append((None, "Introduction", []))
            secs[-1][2].append((i, i, text))
    return meta, [s for s in secs if s[2]]


# ----------------------------------------------------------------------------- chunking
def _to_chunks(doc_id: str, title: str, meta: dict, sections: list[Section], source: str,
               max_chunk_words: int) -> list[Chunk]:
    extra = {k: v for k, v in meta.items() if k not in {"doc_id", "id", "title", "text", "sections", "content"}}
    chunks: list[Chunk] = []
    used: set[str] = set()
    for s_idx, (sid, sec_title, paras) in enumerate(sections, start=1):
        section_id = _safe_id(sid) if sid else f"S{s_idx}"
        if section_id in used:                      # repeated source id -> keep unique, stay traceable
            section_id = f"{section_id}_{s_idx}"
        used.add(section_id)
        for c_idx, (ls, le, text) in enumerate(_split_long(paras, max_chunk_words), start=1):
            chunks.append(Chunk(
                chunk_id=f"{doc_id}:{section_id}:c{c_idx}", document_id=doc_id, section_id=section_id,
                section_title=sec_title, source_title=title, text=text, line_start=ls, line_end=le,
                source_file=source, metadata={k: str(v) for k, v in extra.items()}))
    return chunks


def parse_document(path: Path, max_chunk_words: int = 160, root: Path | None = None) -> list[Chunk]:
    source = str(path.relative_to(root)).replace("\\", "/") if root else path.name
    suf = path.suffix.lower()
    if suf in {".json", ".jsonl"}:
        out: list[Chunk] = []
        for n, rec in enumerate(_read_json_records(path), start=1):
            doc_id = _safe_id(str(rec.get("doc_id") or rec.get("id") or f"{path.stem}_{n}"))
            out += _to_chunks(doc_id, str(rec.get("title") or doc_id), rec, _record_sections(rec), source,
                              max_chunk_words)
        return out
    reader = {".md": _read_markdown, ".markdown": _read_markdown, ".txt": _read_text,
              ".pdf": _read_pdf, ".docx": _read_docx}[suf]
    meta, sections = reader(path)
    doc_id = _safe_id(meta.get("doc_id") or path.stem)
    return _to_chunks(doc_id, meta.get("title") or path.stem, meta, sections, source, max_chunk_words)


def load_corpus(raw_dir: Path, max_chunk_words: int = 160) -> tuple[list[Chunk], dict]:
    files = sorted(p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED
                   and not p.name.startswith("."))
    if not files:
        raise FileNotFoundError(f"no supported documents ({', '.join(sorted(SUPPORTED))}) found in {raw_dir}")
    chunks: list[Chunk] = []
    digest = hashlib.sha256()
    for f in files:
        digest.update(str(f.relative_to(raw_dir)).encode())
        digest.update(f.read_bytes())
        chunks.extend(parse_document(f, max_chunk_words, raw_dir))
    seen: set[str] = set()
    dupes = sorted({c.chunk_id for c in chunks if c.chunk_id in seen or seen.add(c.chunk_id)})
    if dupes:
        raise ValueError(f"duplicate chunk ids (two documents share a doc_id?): {dupes[:5]}")
    # derive superseded_by from supersedes (either direction may be declared in the source)
    docs = {c.document_id for c in chunks}
    newer_of = {c.metadata["supersedes"]: c.document_id for c in chunks if c.metadata.get("supersedes") in docs}
    for c in chunks:
        if c.document_id in newer_of and "superseded_by" not in c.metadata:
            c.metadata["superseded_by"] = newer_of[c.document_id]
    manifest = {
        "num_documents": len(docs),
        "num_files": len(files),
        "num_chunks": len(chunks),
        "corpus_sha256": digest.hexdigest(),
        "formats": sorted({f.suffix.lower() for f in files}),
        "synthetic": any(c.metadata.get("synthetic") == "true" for c in chunks),
        "files": [str(f.relative_to(raw_dir)).replace("\\", "/") for f in files],
    }
    return chunks, manifest


def write_chunks(chunks: list[Chunk], manifest: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    (out_dir / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def read_chunks(out_dir: Path) -> list[Chunk]:
    with (out_dir / "chunks.jsonl").open(encoding="utf-8") as fh:
        return [Chunk(**json.loads(line)) for line in fh if line.strip()]
