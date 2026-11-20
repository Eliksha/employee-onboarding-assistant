
"""RAG pipeline: retrieve -> threshold check -> grounded LLM answer -> save."""

from typing import Dict

from backend.config import settings
from backend.services import db, llm, retriever


FALLBACK = (
    "I could not find this in the NovaTech employee handbook, "
    "so I don't want to guess. "
    "You can use the escalate option or contact HR at "
    "hr@novatech.example "
    "(IT questions: it-help@novatech.example)."
)


def answer_question(
    question: str,
    employee_id: str | None = None,
) -> Dict:
    """Answer handbook questions using grounded RAG."""

    # Step 1: Retrieve relevant handbook chunks.
    hits = retriever.search(question, settings.top_k)

    sources = [
        {
            "file": hit["source"],
            "section": hit["section"],
            "score": round(hit["score"], 3),
        }
        for hit in hits
    ]

    # Step 2: Check retrieval relevance.
    if not hits or hits[0]["score"] < settings.similarity_threshold:
        answer = FALLBACK
        found = False

    else:
        # Step 3: Generate an answer using retrieved context.
        raw = llm.generate_answer(question, hits)

        # Step 4: Prevent unsupported answers.
        if not raw or llm.NOT_FOUND in raw.upper().replace(" ", "_"):
            answer = FALLBACK
            found = False
        else:
            answer = raw
            found = True

    # Step 5: Save chat history.
    if employee_id is not None:
        # Save under the selected fictional employee.
        message_id = db.save_employee_message(
            employee_id=employee_id,
            question=question,
            answer=answer,
            found=found,
            sources=sources if found else [],
        )
    else:
        # Preserve compatibility with existing functionality.
        message_id = db.save_message(
            question,
            answer,
            found,
            sources,
        )

    # Step 6: Return the response.
    return {
        "message_id": message_id,
        "answer": answer,
        "sources": sources if found else [],
        "found": found,
        "top_score": sources[0]["score"] if sources else 0.0,
    }
