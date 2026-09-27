from pathlib import Path

import pytest

from app.config import get_settings
from app.ingestion.loader import load_corpus, parse_document
from app.retrieval.bm25 import BM25
from app.retrieval.text import content_tokens, numbers, split_sentences, stem


def test_stemmer_conflates_inflections():
    assert {stem(w) for w in ["cancel", "cancelled", "cancellation", "cancelling"]} == {"cancel"}
    assert stem("bookings") == stem("booking")


def test_content_tokens_drop_filler():
    assert content_tokens("Um, I need the cancellation policy please") == ["cancel", "policy"]


def test_numbers_and_sentences():
    assert numbers("INR 1,200 per day for 30 people") == {"1200", "30"}
    assert len(split_sentences("One. Two? Three!")) == 3


def test_parse_document_sections_and_lines(tmp_path: Path):
    f = tmp_path / "x.md"
    f.write_text("---\ndoc_id: DOC_X\ntitle: T\nsupersedes: DOC_Y\n---\n## A\nalpha one.\n\nalpha two.\n## B\nbeta.\n",
                 encoding="utf-8")
    chunks = parse_document(f)
    assert [c.chunk_id for c in chunks] == ["DOC_X:S1:c1", "DOC_X:S2:c1"]
    assert chunks[0].text == "alpha one. alpha two."
    assert (chunks[0].line_start, chunks[0].line_end) == (7, 9)
    assert chunks[0].metadata == {"supersedes": "DOC_Y"}   # only front-matter fields, nothing invented
    assert chunks[1].citation == "DOC_X §S2"


def test_long_sections_are_split(tmp_path: Path):
    f = tmp_path / "y.md"
    paras = "\n\n".join(" ".join(["word"] * 60) for _ in range(4))
    f.write_text(f"---\ndoc_id: DOC_L\ntitle: L\n---\n## Long\n{paras}\n", encoding="utf-8")
    chunks = parse_document(f, max_chunk_words=100)
    assert len(chunks) == 4 and all(c.section_id == "S1" for c in chunks)


def test_duplicate_doc_ids_rejected(tmp_path: Path):
    for n in ("a", "b"):
        (tmp_path / f"{n}.md").write_text("---\ndoc_id: DOC_1\ntitle: t\n---\n## S\ntext\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_corpus(tmp_path)


def test_corpus_ingestion_is_reproducible():
    s = get_settings()
    a, ma = load_corpus(s.raw_dir)
    b, mb = load_corpus(s.raw_dir)
    assert ma["corpus_sha256"] == mb["corpus_sha256"]
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert ma["num_documents"] == 16


def test_bm25_prefers_matching_doc():
    bm = BM25(["refund for cancelled venue", "annual leave days", "laptop replacement"])
    sc = bm.scores("venue cancellation refund")
    assert sc.argmax() == 0 and sc[1] == 0 and sc[2] == 0
