"""Load Hugging Face weights without surprise network calls.

Order: ``data/models/<name>`` (vendored, e.g. by scripts/download_models.py) ->
local HF cache -> download.
"""
from __future__ import annotations

from app.config import REPO_ROOT


def load_pretrained(cls, name: str):
    vendored = REPO_ROOT / "data" / "models" / name
    if (vendored / "config.json").exists() and (vendored / "model.safetensors").exists():
        return cls.from_pretrained(str(vendored))
    try:
        return cls.from_pretrained(name, local_files_only=True)
    except OSError:
        return cls.from_pretrained(name)
