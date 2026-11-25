
"""Orchestrate handbook RAG and employee-specific database queries.

Flow (deterministic; the LLM is used only inside the handbook pipeline):

1. `employee_query_router.route(question)` -> records intents (closed allow-list) and/or a
   handbook part (`policy_question`).
2. Handbook only  -> `rag.answer_question` (unchanged pipeline; it persists the message itself).
3. Records only   -> allow-listed employee_db reads (Phase 1 reader role + signed employee scope)
                     -> deterministic formatting -> one saved message.
4. Mixed          -> records part + `rag.answer_policy(policy_question)` (no persistence) ->
                     "From your records" / "From the handbook" sections -> one saved message.
                     If the handbook part fails (LLM unavailable, retrieval error, no evidence)
                     the records part is still returned with a clear note.

Records text is produced only from database rows; when rows are missing the answer says so.
Records sources are labelled {"file": "Your records", ...}; handbook sources keep their file names.
"""

import logging
from datetime import date

from backend.services import db, employee_query_router, llm, rag
from backend.services.employee_db import UnknownEmployeeError, get_employee

logger = logging.getLogger("app")

RECORDS_SOURCE = "Your records"
COMPANY_SOURCE = "Company records"

RECORD_LABELS = {
    "checklist": "Onboarding checklist",
    "leave_balances": "Leave balances",
    "assets": "Assigned assets",
    "tickets": "Support tickets",
    "profile": "Employee profile",
    "payroll": "Payroll calendar",
}

NO_EMPLOYEE_WORKSPACE = (
    "Personal records (checklist, leave, assets, tickets, profile) are available only to "
    "employee accounts. This account has no employee workspace."
)
THIRD_PARTY_REFUSAL = (
    "I can only share your own records, so I have not looked up anyone else's information. "
    "Ask about your own checklist, leave, assets, tickets or profile, or contact HR at "
    "hr@novatech.example."
)
POLICY_UNAVAILABLE = (
    "I could not check the handbook right now, so I have not answered the policy part of your "
    "question. Please try again shortly."
)


# ---------------------------------------------------------------- formatting (no LLM)
def _format_checklist(data) -> str:
    if not data:
        return "No onboarding checklist items were found in your records."

    total = len(data)
    done = sum(1 for item in data if item.get("done"))
    percent = round(done * 100 / total)

    phases: dict[str, list] = {}
    for item in data:
        phases.setdefault(item.get("phase") or "Other", []).append(item)

    if done == total:
        lines = [f"You have completed all {total} onboarding tasks (100%)."]
    else:
        lines = [f"You have completed {done} of {total} onboarding tasks ({percent}%); "
                 f"{total - done} pending."]

    lines.append("")
    lines.append("By phase:")
    for phase, items in phases.items():
        phase_done = sum(1 for item in items if item.get("done"))
        lines.append(f"- {phase}: {phase_done} of {len(items)} completed")

    pending = [item for item in data if not item.get("done")]
    if pending:
        lines.append("")
        lines.append("Pending tasks:")
        lines += [f"- {item.get('phase') or 'Other'}: {item.get('task', 'Unnamed task')}" for item in pending]

    completed = [item for item in data if item.get("done")]
    if completed:
        lines.append("")
        lines.append("Completed tasks:")
        lines += [f"- {item.get('phase') or 'Other'}: {item.get('task', 'Unnamed task')}" for item in completed]

    return "\n".join(lines)


def _days(value) -> str:
    """8.0 / Decimal('8.00') -> '8'; 7.5 stays '7.5'. Display only; the value is never altered."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _format_leave(data, leave_types=()) -> str:
    if not data:
        return "No leave balance records were found."

    lines = []
    for wanted in leave_types:
        matches = [item for item in data if wanted in str(item.get("leave_type", "")).lower()]
        if matches:
            lines += [f"{item['leave_type']}: {_days(item['available_days'])} days available." for item in matches]
        else:
            lines.append(f"No {wanted} leave balance was found in your records.")
    if lines:
        lines.append("")
    lines.append("Your leave balances:")
    lines += [f"- {item['leave_type']}: {_days(item['available_days'])} days" for item in data]
    return "\n".join(lines)


def _format_payroll(data, today=None) -> str:
    if not data:
        return "No payroll calendar entries were found."

    today = (today or date.today()).isoformat()
    rows = sorted(data, key=lambda item: str(item.get("payment_date"))[:10])
    upcoming = [item for item in rows if str(item.get("payment_date"))[:10] >= today]

    lines = []
    if upcoming:
        nxt = upcoming[0]
        lines.append(f"The next payroll payment date on record is {str(nxt['payment_date'])[:10]} "
                     f"(payroll month {nxt.get('payroll_month')}, status: {nxt.get('status', 'unknown')}).")
    else:
        lines.append("No upcoming payroll date is recorded in the payroll calendar.")
    lines.append("")
    lines.append("Payroll calendar:")
    lines += [f"- {item.get('payroll_month')}: {str(item.get('payment_date'))[:10]} ({item.get('status', 'unknown')})"
              for item in rows]
    return "\n".join(lines)


def _format_employee_answer(intent: str, data, leave_types=()) -> str:
    """Format approved database results without using an LLM."""

    if intent == "leave_balances":
        return _format_leave(data, leave_types)

    if intent == "assets":
        if not data:
            return "No assigned assets were found."

        return "Your assigned assets:\n" + "\n".join(
            f"- {item.get('asset_type', 'Asset')}: "
            f"{item.get('asset_name', item.get('model', 'Details unavailable'))}"
            for item in data
        )

    if intent == "checklist":
        return _format_checklist(data)

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
        if not data:
            return "No employee profile was found."
        return "Your employee profile:\n" + "\n".join(
            f"- {key.replace('_', ' ').title()}: {value}"
            for key, value in data.items()
            if key != "employee_id"
        )

    if intent == "payroll":
        return _format_payroll(data)

    return "I cannot answer this employee-specific question."


# ---------------------------------------------------------------- parts
def _records_part(route, employee_id):
    """(text, sources, found) for the records part. Reads only through the closed allow-list."""

    if route.third_party:
        return THIRD_PARTY_REFUSAL, [], False

    texts, sources, found = [], [], False
    for intent in route.sql_intents:
        company = intent in employee_query_router.COMPANY_OPERATIONS
        if company:
            data = employee_query_router.execute_company_query(intent)
        elif employee_id is None:
            texts.append(NO_EMPLOYEE_WORKSPACE)
            continue
        else:
            data = employee_query_router.execute_employee_query(employee_id, intent)

        texts.append(_format_employee_answer(intent, data, route.leave_types))
        if data:
            found = True
            sources.append({
                "file": COMPANY_SOURCE if company else RECORDS_SOURCE,
                "section": RECORD_LABELS[intent],
                "score": 1.0,
            })

    # The same refusal is never repeated for several personal intents.
    unique = list(dict.fromkeys(texts))
    return "\n\n".join(unique), sources, found


def _policy_part(question: str):
    """(text, sources, found) for the handbook part; never raises for an LLM or retrieval failure."""

    try:
        result = rag.answer_policy(question)
    except llm.LLMUnavailable as exc:
        logger.warning("handbook part unavailable (LLM): %s", str(exc)[:200])
        return POLICY_UNAVAILABLE, [], False
    except Exception:  # noqa: BLE001 - the records part must survive a retrieval failure
        logger.exception("handbook part failed")
        return POLICY_UNAVAILABLE, [], False
    return result["answer"], result["sources"], result["found"]


def _save(employee_id, question, answer, found, sources) -> int:
    if employee_id is not None:
        return db.save_employee_message(
            employee_id=employee_id,
            question=question,
            answer=answer,
            found=found,
            sources=sources,
        )
    return db.save_message(question, answer, found, sources)


# ---------------------------------------------------------------- entry point
def answer_question(
    question: str,
    employee_id: str | None = None,
) -> dict:
    """Route questions to approved employee tools, handbook RAG, or both; persist exactly once."""

    # Validate the session employee before processing.
    if employee_id is not None and get_employee(employee_id) is None:
        raise UnknownEmployeeError("Unknown employee ID")

    route = employee_query_router.route(question)
    logger.info("chat route kind=%s intents=%s ambiguous=%s third_party=%s",
                route.kind, ",".join(route.sql_intents) or "-", route.ambiguous, route.third_party)

    # Handbook-only questions use the RAG pipeline unchanged (it saves the message itself).
    if not route.sql_intents:
        return rag.answer_question(
            question=question,
            employee_id=employee_id,
        )

    records_text, records_sources, records_found = _records_part(route, employee_id)

    if route.needs_policy:
        policy_text, policy_sources, policy_found = _policy_part(route.policy_question)
        answer = f"From your records:\n{records_text}\n\nFrom the handbook:\n{policy_text}"
        sources = records_sources + policy_sources
        found = records_found or policy_found
    else:
        answer, sources, found = records_text, records_sources, records_found

    message_id = _save(employee_id, question, answer, found, sources)

    return {
        "message_id": message_id,
        "answer": answer,
        "sources": sources,
        "found": found,
        "top_score": 0.0,
    }
