"""Ingest (if needed) and build the dense + sentence index under data/processed/index."""
import json

import _bootstrap  # noqa: F401
import ingest
from app.config import get_settings
from app.ingestion.loader import read_chunks
from app.retrieval.embedder import Embedder
from app.retrieval.index import build_index


def main() -> dict:
    s = get_settings()
    manifest = ingest.main()
    meta = build_index(read_chunks(s.processed_dir), Embedder(s.embedding_model),
                       s.processed_dir / "index", manifest["corpus_sha256"])
    print(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    main()
