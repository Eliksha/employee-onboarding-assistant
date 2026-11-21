
"""Orchestrate handbook RAG and employee-specific database queries."""

from backend.services import db, rag
from backend.services.employee_query_router import (
    classify_employee_query,
    execute_employee_query,
)
from backend.services.employee_db import UnknownEmployeeError, get_employee


def _format_employee_answer(intent: str, data) -> str:
    """Format approved database results without using an LLM."""

    if intent == "leave_balances":
        if not data:
            return "No leave balance records were found."

        return "Your leave balances:\n" + "\n".join(
            f"- {item['leave_type']}: {item['available_days']} days"
            for item in data
        )

    if intent == "assets":
        if not data:
            return "No assigned assets were found."

        return "Your assigned assets:\n" + "\n".join(
            f"- {item.get('asset_type', 'Asset')}: "
            f"{item.get('asset_name', item.get('model', 'Details unavailable'))}"
            for item in data
        )

    if intent == "checklist":
        if not data:
            return "No onboarding checklist items were found."

        return "Your onboarding checklist:\n" + "\n".join(
            f"- {'Completed' if item.get('done') else 'Pending'}: "
            f"{item.get('task', 'Unnamed task')}"
            for item in data
        )

    if intent == "tickets":
        if not data:
            return "You have no support tickets."

        return "Your support tickets:\n" + "\n".join(
            f"- Ticket #{item.get('ticket_id')}: "
            f"{item.get('subject', 'No subject')} "
            f"({item.get('status', 'Unknown')})"
            for item in data
        )

    if intent == "profile":
        return "Your employee profile:\n" + "\n".join(
            f"- {key.replace('_', ' ').title()}: {value}"
            for key, value in data.items()
            if key != "employee_id"
        )

    return "I cannot answer this employee-specific question."


def answer_question(
    question: str,
    employee_id: str | None = None,
) -> dict:
    """Route questions to approved employee tools or handbook RAG."""

    # Validate the selected demo employee before processing.
    if employee_id is not None and get_employee(employee_id) is None:
        raise UnknownEmployeeError("Unknown employee ID")

    intent = classify_employee_query(question)

    # Handbook questions use the RAG pipeline.
    if intent is None:
        return rag.answer_question(
            question=question,
            employee_id=employee_id,
        )

    # Employee-specific questions require a selected demo employee.
    if employee_id is None:
        return {
            "message_id": 0,
            "answer": (
                "Please select a demo employee to view "
                "employee-specific information."
            ),
            "sources": [],
            "found": False,
            "top_score": 0.0,
        }

    # Retrieve employee-specific information.
    data = execute_employee_query(employee_id, intent)

    # Format the answer without using an LLM.
    answer = _format_employee_answer(intent, data)

    # Save the response to employee-specific chat history.
    message_id = db.save_employee_message(
        employee_id=employee_id,
        question=question,
        answer=answer,
        found=True,
        sources=[],
    )

    return {
        "message_id": message_id,
        "answer": answer,
        "sources": [],
        "found": True,
        "top_score": 0.0,
    }
