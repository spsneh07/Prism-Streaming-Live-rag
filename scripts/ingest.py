"""Parse data/raw into section-level chunks -> data/processed/chunks.jsonl."""
import time

import _bootstrap  # noqa: F401
from app.config import get_settings
from app.ingestion.loader import load_corpus, write_chunks


def main() -> dict:
    s = get_settings()
    t0 = time.perf_counter()
    chunks, manifest = load_corpus(s.raw_dir, s.max_chunk_words)
    manifest["ingest_seconds"] = round(time.perf_counter() - t0, 4)
    write_chunks(chunks, manifest, s.processed_dir)
    print(f"ingested {manifest['num_documents']} documents -> {manifest['num_chunks']} chunks "
          f"(sha256 {manifest['corpus_sha256'][:12]}) in {manifest['ingest_seconds']}s")
    return manifest


if __name__ == "__main__":
    main()
