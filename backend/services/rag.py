"""RAG pipeline: retrieve -> threshold check -> grounded LLM answer -> save."""
from typing import Dict

from backend.config import settings
from backend.services import db, llm, retriever

FALLBACK = (
    "I could not find this in the NovaTech employee handbook, so I don't want to guess. "
    "You can use the escalate option or contact HR at hr@novatech.example (IT questions: it-help@novatech.example)."
)


def answer_question(question: str) -> Dict:
    hits = retriever.search(question, settings.top_k)
    sources = [{"file": h["source"], "section": h["section"], "score": round(h["score"], 3)} for h in hits]

    # Guard 1: nothing relevant retrieved -> do not call the LLM at all
    if not hits or hits[0]["score"] < settings.similarity_threshold:
        answer, found = FALLBACK, False
    else:
        raw = llm.generate_answer(question, hits)
        # Guard 2: the model itself says the context does not contain the answer
        if not raw or llm.NOT_FOUND in raw.upper().replace(" ", "_"):
            answer, found = FALLBACK, False
        else:
            answer, found = raw, True

    message_id = db.save_message(question, answer, found, sources)
    return {"message_id": message_id, "answer": answer, "sources": sources if found else [], "found": found,
            "top_score": sources[0]["score"] if sources else 0.0}
