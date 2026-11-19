"""Search the FAISS index for passages relevant to a question."""
import json
from pathlib import Path
from typing import Dict, List

import faiss
import numpy as np

from backend.config import settings
from backend.services import embeddings
from backend.services.ingest import INDEX_FILE, META_FILE, build_index

_index = None
_chunks: List[Dict] = []


def reset() -> None:
    global _index, _chunks
    _index, _chunks = None, []


def _ensure_loaded() -> None:
    global _index, _chunks
    if _index is not None:
        return
    folder = Path(settings.index_dir)
    if not (folder / INDEX_FILE).exists():
        build_index()
    _index = faiss.read_index(str(folder / INDEX_FILE))
    _chunks = json.loads((folder / META_FILE).read_text(encoding="utf-8"))


def search(query: str, k: int = None) -> List[Dict]:
    _ensure_loaded()
    k = min(k or settings.top_k, len(_chunks))
    qv = np.ascontiguousarray(embeddings.embed_texts([query]))
    scores, ids = _index.search(qv, k)
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        c = _chunks[int(idx)]
        results.append({"text": c["text"], "source": c["source"], "section": c["section"], "score": float(score)})
    return results
