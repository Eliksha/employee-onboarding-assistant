
"""RAG pipeline: retrieve -> threshold check -> grounded LLM answer (`answer_policy`) -> save (`answer_question`)."""

import logging
from typing import Dict, List

from backend.config import settings
from backend.services import db, guardrails, llm, retriever

logger = logging.getLogger("app")


FALLBACK = (
    "I could not find this in the NovaTech employee handbook, "
    "so I don't want to guess. "
    "You can use the Escalate to HR/IT button below this answer or contact HR at "
    "hr@novatech.example "
    "(IT questions: it-help@novatech.example)."
)


def answer_policy(question: str) -> Dict:
    """Grounded handbook answer WITHOUT persistence (used alone and as the handbook part of mixed questions).

    Returns {answer, sources, found, top_score}. Raises llm.LLMUnavailable like the full pipeline;
    the caller decides how to surface it.
    """

    # Step 1: Retrieve relevant handbook chunks.
    hits = retriever.search(question, settings.top_k)

    # Step 2: Retrieval gate (threshold + corroborated borderline band).
    gate_ok, gate_reason = guardrails.retrieval_gate(question, hits)
    cited: List[Dict] = []

    if not gate_ok:
        answer = FALLBACK
        found = False

    else:
        # Step 3: Generate an answer using retrieved context.
        raw = llm.generate_answer(question, hits)

        # Step 4: Prevent unsupported answers (NOT_FOUND, leaks, bad citations, unsupported facts).
        if not raw or llm.NOT_FOUND in raw.upper().replace(" ", "_"):
            answer = FALLBACK
            found = False
        else:
            verdict = guardrails.validate_answer(raw, hits)
            if verdict.ok:
                answer = raw
                found = True
                cited = verdict.sources
            else:
                logger.warning("answer rejected by guardrails: %s (gate=%s)", verdict.reason, gate_reason)
                answer = FALLBACK
                found = False

    # Only passages actually cited in the answer are returned as sources.
    sources = [
        {"file": h["source"], "section": h["section"], "score": round(h["score"], 3),
         **({"page": h["page"]} if h.get("page") else {})}
        for h in cited
    ]

    return {
        "answer": answer,
        "sources": sources,
        "found": found,
        "top_score": round(hits[0]["score"], 3) if hits else 0.0,
    }


def answer_question(
    question: str,
    employee_id: str | None = None,
) -> Dict:
    """Answer handbook questions using grounded RAG and save the exchange once."""

    result = answer_policy(question)
    answer, found, sources = result["answer"], result["found"], result["sources"]

    # Step 5: Save chat history.
    if employee_id is not None:
        # Save under the selected fictional employee.
        message_id = db.save_employee_message(
            employee_id=employee_id,
            question=question,
            answer=answer,
            found=found,
            sources=sources,
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
        "sources": sources,
        "found": found,
        "top_score": result["top_score"],
    }
