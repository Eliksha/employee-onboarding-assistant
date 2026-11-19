from fastapi import APIRouter

from backend.services import ingest, retriever

router = APIRouter()


@router.post("/ingest")
def reindex():
    """Rebuild the FAISS index from the documents in data/raw."""
    count = ingest.build_index()
    retriever.reset()
    return {"status": "indexed", "chunks": count}
