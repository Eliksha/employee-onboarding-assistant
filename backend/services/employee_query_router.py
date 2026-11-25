"""Deterministic routing of chat questions to approved employee-record tools and/or handbook RAG.

No LLM is involved and no SQL is generated here: a route only names entries of the closed
allow-list in `execute_employee_query`, which call existing employee-scoped functions.

Algorithm
---------
1. Normalise the question and split it into clauses. A split happens only at a sentence boundary
   or at a connector ("and", "also", "plus", ",", ";") that is followed by a new question
   ("what", "how", "which", "show", ...), so "casual and sick leaves" stays one clause while
   "the leave policy and how many leaves do I have left" becomes two.
2. Each clause is classified on its own with explicit precedence (first matching rule wins):

   P1 RECORD (+POLICY)  a topic's own *state cue* is present (status, progress, pending, balance,
                        left, remaining, assigned, next payroll, ...). If the clause also carries a
                        policy cue, the handbook is consulted as well.
   P2 POLICY            a policy cue is present (policy, rules, entitled, eligible, per year,
                        "can I", "how do I", "do I get", ...).
   P3 RECORD            a first-person marker (my, I, me) - or a third-party reference, see 4. -
                        together with a topic whose records are personal (leave, assets,
                        onboarding, tickets, profile). Payroll is company-wide, so "my salary"
                        alone is not a records request.
   P4 AMBIGUOUS         a topic without any cue ("casual leaves", "onboarding tasks"): answered
                        from the handbook (the safe default; `Route.ambiguous` is set).
   P5 GENERAL           no topic: a general handbook question.

   In a multi-part message, a P4/P5 clause gets the handbook part only if it is itself a question
   (starts with a question word and has at least three words, e.g. "also, what is the dress
   code"); leftovers such as "thanks" add nothing.

   A clause that names no topic inherits the topics of the previous clause, so the follow-up in
   "what is the leave policy and how many do I have left" is still about leave.
3. Clause results are merged: the union of record intents (in first-seen order) and
   `needs_policy` if any clause needs the handbook. `policy_question` holds only the
   policy clauses, so handbook retrieval and the LLM never see the records part.
4. Third-party references (another employee ID, "Meera's", "his/her/their", "my colleague's",
   "everyone's", "assigned to <name>", or a capitalised name after for/of/to/does/has/is in the
   original question) on a records clause mark the route `third_party`; the orchestrator then refuses
   the records part instead of showing the signed-in employee's own data under a misleading label.
5. A follow-up clause that only refers back with a pronoun ("can I carry them forward") is sent to
   retrieval together with the previous clause's topic words ("can i carry them forward (earned leaves)").
"""

import re
from dataclasses import dataclass, field, replace
from typing import Optional

from backend.services import employee_db


# ---------------------------------------------------------------- vocabulary
@dataclass(frozen=True)
class Topic:
    intent: str                  # allow-listed operation in execute_employee_query
    terms: tuple                 # regexes that identify the topic
    state_cues: tuple            # regexes that make the clause a records request (P1)
    personal: bool = True        # P3: a first-person marker alone is enough


TOPICS = (
    Topic(
        "checklist",
        (r"onboarding", r"check-?list", r"tasks?", r"to-?dos?", r"complete", r"finish"),
        (r"status", r"progress", r"pending", r"completed", r"finished", r"done", r"left",
         r"remaining", r"outstanding", r"still (?:need|have|to)", r"how far", r"how many",
         r"where am i", r"am i (?:done|finished|on track)", r"have i"),
    ),
    Topic(
        "leave_balances",
        (r"leaves?", r"pto", r"time off", r"days? off", r"vacation",
         r"(?:casual|sick|earned|annual|paid|personal|privilege) days?"),
        (r"balances?", r"left", r"remaining", r"do i (?:still )?have(?! to)", r"have i (?:got|used|taken)",
         r"i(?:'ve| have)? (?:used|taken)", r"available to me"),
    ),
    Topic(
        "assets",
        (r"laptops?", r"assets?", r"devices?", r"equipment", r"hardware", r"monitors?", r"phones?"),
        (r"assigned", r"issued", r"allocated", r"do i have(?! to)", r"have i (?:got|been given)",
         r"was i given"),
    ),
    Topic(
        "tickets",
        (r"tickets?", r"support requests?", r"it requests?", r"helpdesk requests?"),
        (r"status", r"open (?:tickets?|requests?)", r"(?:tickets?|requests?) (?:are |is )?(?:still )?open",
         r"pending", r"closed", r"resolved", r"(?:have|did) i (?:raise|raised|open|opened|create|created|file|filed|log|logged)",
         r"i(?:'ve)? (?:raised|opened|created|filed|logged)"),
    ),
    Topic(
        "profile",
        (r"profile", r"department", r"designation", r"joining date", r"date of joining",
         r"(?:work )?location"),
        (r"what is my", r"show my", r"which department am i"),
    ),
    Topic(
        "payroll",
        (r"payroll", r"salary", r"pay ?days?", r"pay ?dates?", r"pay ?checks?", r"pay slips?",
         r"payments? dates?", r"get paid", r"paid"),
        (r"next", r"upcoming", r"calendar", r"schedule", r"this month", r"payment dates?",
         r"pay ?dates?", r"pay ?days?"),
        personal=False,
    ),
)

POLICY_CUES = (
    r"polic(?:y|ies)", r"rules?", r"guidelines?", r"allowed", r"permitted", r"eligib(?:le|ility)",
    r"entitle(?:d|ment)s?", r"procedure", r"process", r"carry[- ]?forward", r"encash(?:ment)?",
    r"per (?:year|month|annum)", r"a year", r"annual(?:ly)?", r"in a month", r"maximum", r"minimum",
    r"how (?:do|can|should) i", r"how to", r"can i", r"may i", r"am i allowed", r"should i",
    r"do i get", r"will i get", r"(?<!still )(?<!i still )need to", r"have to", r"approv(?:e|es|ed|al|er)", r"must", r"required", r"what happens",
    r"who (?:approves|should|do i)", r"what if", r"notice period", r"lost", r"stolen", r"apply",
    r"when (?:is|are|do|does) (?:the )?(?:salary|pay)", r"credited",
)

PERSONAL = r"my|mine|me|i|i'm|i've|am i|have i|do i"

THIRD_PARTY = (
    r"emp\d{2,}(?:'s)?",
    r"his|her|hers|their|theirs|someone(?: else)?'?s?|somebody'?s?|another employee'?s?|other employees?'?",
    r"every(?:one|body)'?s?|all employees'?",
    # "how many leaves does Meera have", "has Rohan completed onboarding", "is Meera done with ..."
    r"(?:does|did) (?!(?:it|this|that|the|a|an|my|our|novatech|company|leave|policy|onboarding|checklist|everything|anything|all|sick|casual|earned|laptop)\b)[a-z]+ (?:still )?(?:have|get|use|take|complete|finish)",
    r"(?:has|is) (?!(?:it|this|that|the|a|an|my|our|there|novatech|company|leave|policy|onboarding|checklist|everything|anything|all|sick|casual|earned|laptop)\b)[a-z]+ (?:completed|finished|done|taken|used|got|been)",
    r"(?:colleague|teammate|coworker|co-worker|manager|friend|other person)(?:'s|s'?)?",
    # "which laptop is assigned to meera", "assets issued to rohan"
    r"(?:assigned|issued|allocated|given|belongs?|belonging) to (?!(?:me|myself|us|my|you|the|a|an|this|that|it|"
    r"which|whom|employees|new|all|every|each)\b)[a-z]+",
    r"(?!(?:what|that|it|there|here|who|where|how|let|today|tomorrow|company|novatech|employee|year|month|week|day)'s)[a-z]+'s",
)

_QUESTION_START = (r"what|what's|whats|how|when|which|who|where|why|can|could|do|does|did|is|are|am|"
                   r"should|will|would|show|tell|list|give|explain|also")

_SPLIT_RE = re.compile(
    rf"(?:[?;!]|\.(?=\s)|,|\b(?:and|also|plus|as well as)\b)\s*(?:(?:and|also|plus|then)\s+)?(?=(?:{_QUESTION_START})\b)"
    rf"|[?;!]\s+|\.\s+(?=[a-z])"
)

_LEAVE_TYPES = ("casual", "sick", "earned", "annual", "maternity", "paternity", "bereavement")

# A capitalised word after one of these words names a person ("checklist for Meera", "does Rohan have"),
# unless it is a known domain word. Checked on the original-case question.
_NAME_RE = re.compile(r"\b(?:for|of|to|does|did|has|is|about|with)\s+([A-Z][a-z]{2,})\b")
_DOMAIN_WORDS = frozenset("""
day week month year novatech novaconnect servicehub novavpn microsoft authenticator mfa vpn posh pto
casual sick earned annual maternity paternity bereavement leave leaves laptop laptops onboarding checklist
provident fund health insurance learning wellness payroll salary hr it monday tuesday wednesday thursday
friday saturday sunday january february march april may june july august september october november december
pune bengaluru hyderabad india handbook faq policy team company
""".split())
_ANAPHORA_RE = re.compile(r"\b(?:it|its|them|they|their|those|these|this|that|one|ones)\b")


def _any(patterns, text: str) -> bool:
    return any(re.search(rf"\b(?:{p})(?![\w'])", text) for p in patterns)


def normalise(question: str) -> str:
    text = (question or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


_CONNECTOR_ONLY = re.compile(r"^(?:and|also|plus|then|as well as)$")


def split_clauses(text: str) -> list[str]:
    parts = [p.strip(" ,.?;!") for p in _SPLIT_RE.split(text)]
    return [p for p in parts if p and not _CONNECTOR_ONLY.match(p)]


def _is_question(clause: str) -> bool:
    return bool(re.match(rf"(?:{_QUESTION_START})\b", clause)) and len(clause.split()) >= 3


# ---------------------------------------------------------------- results
@dataclass(frozen=True)
class ClauseRoute:
    text: str
    rule: str                     # P1..P5
    intents: tuple = ()
    needs_policy: bool = False
    third_party: bool = False
    query: str = ""               # text sent to retrieval when this clause needs the handbook


@dataclass(frozen=True)
class Route:
    sql_intents: tuple = ()
    needs_policy: bool = True
    policy_question: str = ""
    third_party: bool = False
    ambiguous: bool = False
    leave_types: tuple = ()
    clauses: tuple = field(default_factory=tuple)

    @property
    def kind(self) -> str:
        if self.sql_intents and self.needs_policy:
            return "mixed"
        return "records" if self.sql_intents else "handbook"


def clause_topics(clause: str) -> tuple:
    return tuple(t for t in TOPICS if _any(t.terms, clause))


def names_person(question: str) -> bool:
    """True when the original-case question names someone ("for Meera", "does Rohan have")."""
    return any(m.group(1).lower() not in _DOMAIN_WORDS for m in _NAME_RE.finditer(question or ""))


def topic_phrase(clause: str, topics) -> str:
    """Words that name the clause's topics, e.g. 'earned leaves' (leave-type modifiers kept)."""
    words = []
    for topic in topics:
        for pattern in topic.terms:
            m = re.search(rf"\b(?:(?:{'|'.join(_LEAVE_TYPES)})\s+)?(?:{pattern})(?![\w'])", clause)
            if m:
                words.append(m.group(0))
                break
    return " ".join(dict.fromkeys(words))


def classify_clause(clause: str, inherited: tuple = (), named_person: bool = False) -> ClauseRoute:
    """Classify one clause; `inherited` topics apply when the clause names none ("how many do I have left")."""
    topics = list(clause_topics(clause) or inherited)
    policy = _any(POLICY_CUES, clause)
    personal = _any((PERSONAL,), clause)
    third_party = named_person or _any(THIRD_PARTY, clause)

    stated = tuple(t.intent for t in topics if _any(t.state_cues, clause))
    if stated:                                                     # P1
        return ClauseRoute(clause, "P1", stated, policy, third_party)
    if policy:                                                     # P2
        return ClauseRoute(clause, "P2", (), True)
    personal_topics = tuple(t.intent for t in topics if t.personal)
    if (personal or third_party) and personal_topics:              # P3
        return ClauseRoute(clause, "P3", personal_topics, False, third_party)
    if topics:                                                     # P4
        return ClauseRoute(clause, "P4")
    return ClauseRoute(clause, "P5")                               # P5


def route(question: str) -> Route:
    """Deterministically route a question (see module docstring for the precedence rules)."""

    text = normalise(question)
    named = names_person(question)
    clauses_list, previous, previous_phrase = [], (), ""
    for part in split_clauses(text):
        clause = classify_clause(part, previous, named)
        own = clause_topics(part)
        if not own and previous_phrase and _ANAPHORA_RE.search(part):
            # "can I carry them forward" -> retrieval needs the topic the pronoun refers to.
            clause = replace(clause, query=f"{part} ({previous_phrase})")
        clauses_list.append(clause)
        if own:
            previous, previous_phrase = own, topic_phrase(part, own)
    clauses = tuple(clauses_list) or (ClauseRoute(text, "P5"),)

    intents: list[str] = []
    for c in clauses:
        for intent in c.intents:
            if intent not in intents:
                intents.append(intent)

    resolved = [c for c in clauses if c.rule in ("P1", "P2", "P3")]
    if resolved:
        policy_clauses = [c.query or c.text for c in clauses
                          if c.needs_policy or (c.rule in ("P4", "P5") and _is_question(c.text))]
        ambiguous = False
    else:
        # Nothing resolved: the whole question is a handbook question (P4 ambiguity -> safe default).
        policy_clauses = [text]
        ambiguous = any(c.rule == "P4" for c in clauses)

    leave_types = tuple(t for t in _LEAVE_TYPES if re.search(rf"\b{t}\b", text))
    return Route(
        sql_intents=tuple(intents),
        needs_policy=bool(policy_clauses),
        policy_question=(question.strip() if not intents else "; ".join(policy_clauses)),
        third_party=any(c.third_party for c in clauses if c.intents),
        ambiguous=ambiguous,
        leave_types=leave_types,
        clauses=clauses,
    )


def classify_employee_query(question: str) -> Optional[str]:
    """Backward-compatible wrapper: the first records intent, or None for handbook-only questions."""

    intents = route(question).sql_intents
    return intents[0] if intents else None


# ---------------------------------------------------------------- execution (closed allow-list)
# Intent -> existing employee_db function (resolved at call time). Closed: nothing else is callable.
ALLOWED_OPERATIONS = {
    "leave_balances": "get_leave_balances",
    "assets": "get_employee_assets",
    "checklist": "get_employee_checklist",
    "tickets": "get_employee_tickets",
    "profile": "get_employee",
}
COMPANY_OPERATIONS = {
    "payroll": "get_payroll_calendar",   # company-wide calendar, no employee data
}


def execute_company_query(intent: str):
    """Company-wide allow-listed reads (no employee data); usable without an employee workspace."""

    operation = COMPANY_OPERATIONS.get(intent)
    if operation is None:
        raise ValueError("Unsupported company query")
    return getattr(employee_db, operation)()


def execute_employee_query(
    employee_id: str,
    intent: str,
):
    """Execute only explicitly approved employee database functions."""

    employee = employee_db.get_employee(employee_id)

    if employee is None:
        raise employee_db.UnknownEmployeeError("Unknown employee ID")

    if intent in COMPANY_OPERATIONS:
        return getattr(employee_db, COMPANY_OPERATIONS[intent])()

    operation = ALLOWED_OPERATIONS.get(intent)

    if operation is None:
        raise ValueError("Unsupported employee query")

    return getattr(employee_db, operation)(employee_id)
