"""Download the two CPU models into data/models/ (vendored, so runs are offline and
reproducible afterwards). ~180 MB total. Safe to re-run."""
import _bootstrap  # noqa: F401
from huggingface_hub import snapshot_download

from app.config import REPO_ROOT, get_settings

PATTERNS = ["*.json", "*.txt", "model.safetensors"]


def main() -> None:
    s = get_settings()
    for name in (s.embedding_model, s.reranker_model):
        dest = REPO_ROOT / "data" / "models" / name
        if (dest / "model.safetensors").exists():
            print(f"ok  {name} (already present)")
            continue
        snapshot_download(name, local_dir=dest, allow_patterns=PATTERNS)
        print(f"got {name} -> {dest}")


if __name__ == "__main__":
    main()
