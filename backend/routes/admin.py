"""Administrative endpoints (administrator role + CSRF token required)."""
from fastapi import APIRouter, Depends

from backend.security import require_admin_write
from backend.services import ingest, retriever

router = APIRouter()


@router.post("/ingest", dependencies=[Depends(require_admin_write)])
def reindex():
    """Rebuild the FAISS index from the documents in data/raw."""
    count = ingest.build_index()
    retriever.reset()
    return {"status": "indexed", "chunks": count}
