
"""Route employee questions to approved database operations."""

import re
from typing import Optional

from backend.services import employee_db


def classify_employee_query(question: str) -> Optional[str]:
    """Identify employee-specific questions requiring database access."""

    text = question.lower().strip()

    # General handbook policy questions must use RAG.
    # These are not requests for an employee's personal balance.
    policy_patterns = [
        r"\bhow many\b.*\b(leaves?|days off)\b.*\b(per year|a year|annually|annual|entitled)\b",
        r"\b(leaves?|pto)\b.*\b(policy|rules?|eligibility|entitlement)\b",
        r"\b(casual|sick|earned|annual)\s+leaves?\b",
        r"\bhow many\b.*\b(casual|sick|earned|annual)\b.*\b(leaves?|days)\b",
    ]

    if any(re.search(pattern, text) for pattern in policy_patterns):
        return None

    # Only explicitly personal questions access employee records.
    patterns = {
        "leave_balances": [
            r"\b(my|remaining|available)\b.*\b(leaves?|pto)\b",
            r"\b(leaves?|pto)\b.*\b(balance|remaining|available|left)\b",
            r"\bhow many\b.*\b(leaves?|days off)\b.*\b(do i have|have i got|left|remaining)\b",
            r"\bmy\b.*\b(days off|time off)\b",
        ],
        "assets": [
            r"\b(my|assigned)\b.*\b(laptop|assets?|devices?|equipment)\b",
            r"\b(laptop|assets?|devices?|equipment)\b.*\b(assigned|issued)\b",
        ],
        "checklist": [
            r"\b(my|onboarding)\b.*\b(checklist|tasks?|progress)\b",
            r"\b(pending|completed)\b.*\b(tasks?|checklist)\b",
        ],
        "tickets": [
            r"\b(my|open|pending)\b.*\b(tickets?|support requests?)\b",
            r"\b(tickets?|support requests?)\b.*\b(status|open|pending)\b",
        ],
        "profile": [
            r"\b(my|employee)\b.*\b(profile|department|designation|joining date)\b",
        ],
    }

    for intent, expressions in patterns.items():
        if any(re.search(pattern, text) for pattern in expressions):
            return intent

    return None


def execute_employee_query(
    employee_id: str,
    intent: str,
):
    """Execute only explicitly approved employee database functions."""

    employee = employee_db.get_employee(employee_id)

    if employee is None:
        raise ValueError("Unknown employee ID")

    allowed_operations = {
        "leave_balances": employee_db.get_leave_balances,
        "assets": employee_db.get_employee_assets,
        "checklist": employee_db.get_employee_checklist,
        "tickets": employee_db.get_employee_tickets,
        "profile": employee_db.get_employee,
    }

    operation = allowed_operations.get(intent)

    if operation is None:
        raise ValueError("Unsupported employee query")

    return operation(employee_id)
