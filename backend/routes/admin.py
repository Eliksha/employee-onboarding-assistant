"""Administrative endpoints (administrator role + CSRF token required)."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.security import require_admin_write
from backend.services import ingest, retriever

router = APIRouter()
logger = logging.getLogger("app")

READ_ONLY_INDEX = ("The index directory is read-only in this deployment (Docker mounts data/index read-only). "
                   "Rebuild it on the host with: python -m backend.services.ingest")


@router.post("/ingest", dependencies=[Depends(require_admin_write)])
def reindex():
    """Build, validate and atomically activate a new FAISS index version (the previous one stays on failure)."""
    try:
        count = ingest.build_index()
    except PermissionError:
        raise HTTPException(status_code=409, detail=READ_ONLY_INDEX)
    except OSError as exc:
        if getattr(exc, "errno", None) == 30:  # EROFS: read-only file system
            raise HTTPException(status_code=409, detail=READ_ONLY_INDEX)
        raise
    retriever.reset()
    logger.info("index rebuilt: version %s, %d chunks", ingest.active_version(), count)
    return {"status": "indexed", "chunks": count, "version": ingest.active_version()}
