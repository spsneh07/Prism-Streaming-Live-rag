"""The core system must work on a new corpus without code changes.

Builds a tiny unrelated corpus in three formats (JSON with source section ids,
plain text with headings, PDF), indexes it, and runs a streaming turn end to end.
"""
import asyncio
import json

import pytest

from app.config import Settings
from app.ingestion.loader import load_corpus, parse_document, write_chunks
from app.retrieval.index import build_index


@pytest.fixture(scope="module")
def mini_corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("mini")
    raw = root / "raw"
    (raw / "sub").mkdir(parents=True)
    (raw / "fleet.json").write_text(json.dumps({"documents": [{
        "doc_id": "FLEET-7", "title": "Company Vehicle Handbook", "supersedes": "FLEET-6",
        "sections": [
            {"section_id": "4.1", "title": "Fuel cards", "text": "Fuel cards may be used only for company vehicles. "
                                                                 "Receipts must be uploaded within 5 days."},
            {"section_id": "4.2", "title": "Servicing", "text": "Company vehicles are serviced every 12000 kilometres "
                                                                "at an authorised garage."}]}, {
        "doc_id": "FLEET-6", "title": "Company Vehicle Handbook (old)",
        "sections": [{"section_id": "4.1", "title": "Fuel cards", "text": "Receipts must be uploaded within 9 days."}]}]}),
        encoding="utf-8")
    (raw / "sub" / "parking.txt").write_text(
        "Staff Parking Rules\n\nPermits\n\nParking permits are issued by the facilities team for one year and must "
        "be displayed on the dashboard at all times.\n\nVisitors\n\nVisitor parking bays are near the main gate and "
        "must be booked one day ahead.\n", encoding="utf-8")
    try:
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Electric vehicle charging points are free for employees between 8am and 6pm.")
        doc.save(raw / "ev.pdf")
    except ImportError:
        pass
    processed = root / "processed"
    chunks, manifest = load_corpus(raw)
    write_chunks(chunks, manifest, processed)
    return raw, processed, chunks, manifest


def test_formats_and_source_ids_preserved(mini_corpus):
    _, _, chunks, manifest = mini_corpus
    ids = {c.chunk_id for c in chunks}
    assert "FLEET-7:4.1:c1" in ids and "FLEET-7:4.2:c1" in ids          # JSON section ids kept verbatim
    assert any(c.source_file == "sub/parking.txt" and c.section_title == "Visitors" for c in chunks)
    assert {c.metadata.get("superseded_by") for c in chunks if c.document_id == "FLEET-6"} == {"FLEET-7"}
    assert ".json" in manifest["formats"] and manifest["synthetic"] is False
    if ".pdf" in manifest["formats"]:
        assert any(c.section_id == "p1" for c in chunks)


def test_markdown_explicit_and_numbered_section_ids(tmp_path):
    f = tmp_path / "policy.md"
    f.write_text("# Leave Rules\n\n## 3.2 Carry over\nFive days carry over.\n\n## Appeals {#APP}\nAsk HR.\n", encoding="utf-8")
    chunks = parse_document(f)
    assert chunks[0].source_title == "Leave Rules" and chunks[0].document_id == "policy"
    assert [c.section_id for c in chunks] == ["3.2", "APP"]


def test_new_corpus_end_to_end_without_code_changes(rt, mini_corpus):
    from app.runtime import Runtime
    _, processed, chunks, manifest = mini_corpus
    build_index(chunks, rt.embedder, processed / "index", manifest["corpus_sha256"])
    s = Settings()
    s.processed_dir = processed
    rt2 = Runtime.load(s)
    assert rt2.calibration["status"].startswith("uncalibrated")          # no stale gate from the other corpus
    session = rt2.sessions.create()
    chunks_in = [{"t": 0.0, "text": "How often"}, {"t": 0.5, "text": "are company vehicles serviced?"}]
    res = asyncio.run(rt2.engine().run_turn(session, chunks_in, 1.2, speed=20))
    final = next(e for e in res.log.events if e["type"] == "FINAL_RESPONSE")
    assert any(c["chunk_id"] == "FLEET-7:4.2:c1" for c in final["citations"])
    assert all(c["chunk_id"] in rt2.index.by_id for c in final["citations"])
