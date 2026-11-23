"""Search the active FAISS index version for passages relevant to a question.

* Never builds or writes an index on the request path (Docker mounts data/index read-only); a missing
  index raises ingest.IndexUnavailable.
* Picks up a newly activated version (ACTIVE pointer) on the next search; if that version cannot be
  loaded, keeps serving the last good one and logs a warning.
"""
import logging
import threading
from typing import Dict, List

import numpy as np

from backend.config import settings
from backend.services import embeddings, ingest

logger = logging.getLogger("app")
_lock = threading.Lock()
_state = {"version": None, "index": None, "chunks": []}


def reset() -> None:
    with _lock:
        _state.update(version=None, index=None, chunks=[])


def loaded_version():
    return _state["version"]


def _ensure_loaded() -> None:
    try:
        wanted = ingest.active_version()
    except (OSError, ValueError, KeyError):
        wanted = None
    if _state["index"] is not None and wanted in (_state["version"], None):
        return
    with _lock:
        if _state["index"] is not None and wanted == _state["version"]:
            return
        try:
            version, index, chunks, _ = ingest.load_active()
        except ingest.IndexUnavailable:
            if _state["index"] is None:
                raise
            logger.warning("new index version could not be loaded; keeping version %s", _state["version"])
            return
        _state.update(version=version, index=index, chunks=chunks)
        logger.info("FAISS index version %s loaded (%d chunks)", version, len(chunks))


def search(query: str, k: int = None) -> List[Dict]:
    _ensure_loaded()
    index, chunks = _state["index"], _state["chunks"]
    k = min(k or settings.top_k, len(chunks))
    qv = np.ascontiguousarray(embeddings.embed_texts([query]))
    # Small-to-big: match windows, return each parent section once (best window score), with full context.
    scores, ids = index.search(qv, min(len(chunks), k * 6))
    results, seen = [], set()
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        c = chunks[int(idx)]
        parent = (c["source"], c["section"], c.get("page"), c.get("context", c["text"]))
        if parent in seen:
            continue
        seen.add(parent)
        hit = {"text": c.get("context", c["text"]), "source": c["source"], "section": c["section"],
               "score": float(score)}
        if c.get("page"):
            hit["page"] = int(c["page"])
        results.append(hit)
        if len(results) == k:
            break
    return results
