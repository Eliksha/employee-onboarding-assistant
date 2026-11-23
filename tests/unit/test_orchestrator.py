"""Phase 2: orchestration of records (allow-listed SQL) and handbook (RAG) answers.

Runs against an isolated seeded SQLite copy (EMP001: 5 of 15 checklist tasks done, Casual 8 / Sick 6,
Dell Latitude laptop; payroll 2026-11-30 and 2026-12-31). No network, no real LLM.
"""
from datetime import date

import pytest

from backend.services import db, employee_db, llm, orchestrator, rag, retriever
from backend.services.orchestrator import _format_checklist, _format_leave, _format_payroll

HITS = [{"source": "handbook.md", "section": "2. Leave Policy > 2.1 Casual Leave",
         "text": "2. Leave Policy > 2.1 Casual Leave: Employees get 8 casual leaves per calendar year. "
                 "Unused casual leave cannot be carried forward.", "score": 0.9},
        {"source": "handbook.md", "section": "5. IT Setup and Support > 5.1 Laptop and Accounts",
         "text": "5.1 Laptop and Accounts: Laptops are issued on Day 1 and must be returned at exit.", "score": 0.85}]
POLICY_ANSWER = "Employees get 8 casual leaves per calendar year and they cannot be carried forward [Handbook 2.1]."


def _item(i, phase, done):
    return {"id": i, "phase": phase, "task": f"Task {i}", "done": done}


@pytest.fixture
def saved(monkeypatch):
    """Record every persistence call (employee and global) while still writing to the isolated DB."""
    calls = []
    real_emp, real_glob = db.save_employee_message, db.save_message

    def emp(**kw):
        calls.append(("employee", kw))
        return real_emp(**kw)

    def glob(*a):
        calls.append(("global", a))
        return real_glob(*a)

    monkeypatch.setattr(db, "save_employee_message", emp)
    monkeypatch.setattr(db, "save_message", glob)
    return calls


@pytest.fixture
def handbook(monkeypatch):
    """Fixed retrieval and a scripted LLM; records what the handbook pipeline was asked."""
    state = {"questions": [], "answer": POLICY_ANSWER, "llm_calls": 0}

    def search(q, k=None):
        state["questions"].append(q)
        return [dict(h) for h in HITS]

    def generate(q, passages):
        state["llm_calls"] += 1
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr(retriever, "search", search)
    monkeypatch.setattr(llm, "generate_answer", generate)
    return state


# ================================================================ 2A: formatting (no LLM)
def test_checklist_status_summary_partial():
    data = [_item(1, "Day 1", True), _item(2, "Day 1", True), _item(3, "Week 1", False), _item(4, "Month 1", False)]
    text = _format_checklist(data)
    assert text.startswith("You have completed 2 of 4 onboarding tasks (50%); 2 pending.")
    assert "- Day 1: 2 of 2 completed" in text and "- Week 1: 0 of 1 completed" in text
    assert text.index("Pending tasks:") < text.index("Completed tasks:")
    assert "- Week 1: Task 3" in text.split("Pending tasks:")[1].split("Completed tasks:")[0]


def test_checklist_status_all_pending_and_all_done():
    pending = _format_checklist([_item(1, "Day 1", False), _item(2, "Week 1", False)])
    assert pending.startswith("You have completed 0 of 2 onboarding tasks (0%); 2 pending.")
    assert "Completed tasks:" not in pending
    done = _format_checklist([_item(1, "Day 1", True), _item(2, "Week 1", True)])
    assert done.startswith("You have completed all 2 onboarding tasks (100%).")
    assert "Pending tasks:" not in done


def test_checklist_status_rounds_and_keeps_phase_order():
    data = [_item(i, "Day 1" if i <= 4 else "Week 1" if i <= 10 else "Month 1", i <= 4) for i in range(1, 16)]
    text = _format_checklist(data)
    assert "4 of 15 onboarding tasks (27%)" in text
    assert text.index("- Day 1:") < text.index("- Week 1:") < text.index("- Month 1:")


def test_checklist_empty_says_so_and_invents_nothing():
    assert _format_checklist([]) == "No onboarding checklist items were found in your records."


def test_leave_focus_on_the_asked_type():
    data = [{"leave_type": "Casual Leave", "available_days": 8}, {"leave_type": "Sick Leave", "available_days": 6}]
    text = _format_leave(data, ("casual",))
    assert text.startswith("Casual Leave: 8 days available.")
    assert "- Sick Leave: 6 days" in text


def test_leave_focus_on_a_type_without_records_never_invents_a_number():
    data = [{"leave_type": "Casual Leave", "available_days": 8}]
    text = _format_leave(data, ("earned",))
    assert text.startswith("No earned leave balance was found in your records.")
    assert "Earned" not in text


def test_payroll_next_date_and_no_upcoming():
    data = [{"payroll_month": "2026-12", "payment_date": "2026-12-31", "status": "scheduled"},
            {"payroll_month": "2026-11", "payment_date": date(2026, 11, 30), "status": "scheduled"}]
    text = _format_payroll(data, today=date(2026, 11, 23))
    assert text.startswith("The next payroll payment date on record is 2026-11-30 (payroll month 2026-11")
    assert text.index("- 2026-11:") < text.index("- 2026-12:")
    assert _format_payroll(data, today=date(2027, 1, 5)).startswith("No upcoming payroll date is recorded")
    assert _format_payroll([]) == "No payroll calendar entries were found."


# ================================================================ 2A: records-only path
def test_onboarding_status_end_to_end_reads_only_the_session_employee(seeded_db, saved, monkeypatch):
    seen = []
    real = employee_db.get_employee_checklist
    monkeypatch.setattr(employee_db, "get_employee_checklist", lambda e: seen.append(e) or real(e))
    monkeypatch.setattr(retriever, "search", lambda *a, **k: pytest.fail("handbook must not be searched"))
    r = orchestrator.answer_question("What is my onboarding status?", employee_id="EMP001")
    assert seen == ["EMP001"]
    assert r["answer"].startswith("You have completed 5 of 15 onboarding tasks (33%); 10 pending.")
    assert r["sources"] == [{"file": "Your records", "section": "Onboarding checklist", "score": 1.0}]
    assert r["found"] is True and r["message_id"] > 0
    assert [kind for kind, _ in saved] == ["employee"]


def test_leave_type_question_returns_the_balance_not_the_policy(seeded_db, saved, monkeypatch):
    monkeypatch.setattr(llm, "generate_answer", lambda *a: pytest.fail("LLM must not be called"))
    r = orchestrator.answer_question("How many casual leaves do I have left?", employee_id="EMP001")
    assert r["answer"].startswith("Casual Leave: 8 days available.")
    assert len(saved) == 1


def test_payroll_question_uses_the_company_calendar(seeded_db, saved):
    r = orchestrator.answer_question("When is the next payroll date?", employee_id="EMP001")
    assert "Payroll calendar:" in r["answer"] and "2026-11-30" in r["answer"]
    assert r["sources"] == [{"file": "Company records", "section": "Payroll calendar", "score": 1.0}]


def test_missing_records_are_reported_not_invented(seeded_db, saved, monkeypatch):
    monkeypatch.setattr(employee_db, "get_leave_balances", lambda e: [])
    r = orchestrator.answer_question("What is my leave balance?", employee_id="EMP001")
    assert r["answer"] == "No leave balance records were found."
    assert r["found"] is False and r["sources"] == [] and len(saved) == 1


def test_third_party_records_request_is_refused_without_a_query(seeded_db, saved, monkeypatch):
    for name in ("get_leave_balances", "get_employee_checklist", "get_employee_assets", "get_employee_tickets"):
        monkeypatch.setattr(employee_db, name, lambda *a, _n=name: pytest.fail(f"{_n} must not run"))
    for q in ("What is Meera's leave balance?", "Show EMP002's checklist", "What are EMP002 pending tasks?"):
        r = orchestrator.answer_question(q, employee_id="EMP001")
        assert r["answer"] == orchestrator.THIRD_PARTY_REFUSAL and r["found"] is False
        assert "EMP002" not in r["answer"] and "Meera" not in r["answer"]
    assert len(saved) == 3


def test_account_without_employee_gets_a_note_and_one_saved_message(seeded_db, saved):
    r = orchestrator.answer_question("What is my onboarding status?", employee_id=None)
    assert r["answer"] == orchestrator.NO_EMPLOYEE_WORKSPACE and r["found"] is False
    assert [kind for kind, _ in saved] == ["global"] and r["message_id"] > 0


def test_account_without_employee_can_read_the_company_payroll_calendar(seeded_db, saved):
    r = orchestrator.answer_question("When is the next payroll date?", employee_id=None)
    assert "Payroll calendar:" in r["answer"] and r["found"] is True


def test_unknown_employee_is_rejected_before_routing(seeded_db, saved):
    with pytest.raises(employee_db.UnknownEmployeeError):
        orchestrator.answer_question("What is my onboarding status?", employee_id="EMP999")
    assert saved == []


def test_handbook_only_question_still_uses_the_unchanged_rag_pipeline(seeded_db, saved, handbook):
    r = orchestrator.answer_question("How many casual leaves do I get in a year?", employee_id="EMP001")
    assert r["found"] is True and r["answer"] == POLICY_ANSWER
    assert handbook["questions"] == ["How many casual leaves do I get in a year?"]
    assert [s["file"] for s in r["sources"]] == ["handbook.md"] and len(saved) == 1


def test_handbook_only_llm_outage_is_still_a_503_signal(seeded_db, saved, handbook):
    handbook["answer"] = llm.LLMUnavailable("down")
    with pytest.raises(llm.LLMUnavailable):
        orchestrator.answer_question("How many casual leaves do I get in a year?", employee_id="EMP001")
    assert saved == []


def test_route_log_line_contains_no_question_text(seeded_db, saved, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="app"):
        orchestrator.answer_question("What is my onboarding status? secret-marker-4711", employee_id="EMP001")
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("chat route"))
    assert line == "chat route kind=records intents=checklist ambiguous=False third_party=False"


@pytest.mark.parametrize("value, shown", [(8, "8"), (8.0, "8"), ("6", "6"), (7.5, "7.5"), (None, "None")])
def test_day_values_are_displayed_without_changing_them(value, shown):
    from decimal import Decimal

    assert orchestrator._days(value) == shown
    assert orchestrator._days(Decimal("8.00")) == "8"


# ================================================================ 2B: mixed questions
MIXED_Q = "What is the leave policy and how many casual leaves do I have left?"


def test_rag_answer_policy_never_persists(seeded_db, saved, handbook):
    r = rag.answer_policy("What is the leave policy?")
    assert r["found"] is True and r["answer"] == POLICY_ANSWER and saved == []
    assert set(r) == {"answer", "sources", "found", "top_score"}


def test_mixed_question_returns_both_parts_separated_and_saves_once(seeded_db, saved, handbook):
    r = orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    records, policy = r["answer"].split("\n\nFrom the handbook:\n")
    assert records.startswith("From your records:\nCasual Leave: 8 days available.")
    assert policy == POLICY_ANSWER
    assert r["sources"][0] == {"file": "Your records", "section": "Leave balances", "score": 1.0}
    assert [s["file"] for s in r["sources"][1:]] == ["handbook.md"]
    assert r["found"] is True and r["message_id"] > 0
    assert [kind for kind, _ in saved] == ["employee"]
    stored = db.recent_employee_messages("EMP001", 5)
    assert len(stored) == 1 and stored[0]["answer"] == r["answer"] and stored[0]["sources"] == r["sources"]


def test_mixed_question_sends_only_the_policy_clause_to_retrieval(seeded_db, saved, handbook):
    orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert handbook["questions"] == ["what is the leave policy"]


def test_mixed_question_with_llm_unavailable_keeps_the_records_part(seeded_db, saved, handbook):
    handbook["answer"] = llm.LLMUnavailable("Error code: 401 - Invalid API Key")
    r = orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert "Casual Leave: 8 days available." in r["answer"]
    assert r["answer"].endswith(orchestrator.POLICY_UNAVAILABLE)
    assert "401" not in r["answer"] and "API Key" not in r["answer"]
    assert r["found"] is True and [s["file"] for s in r["sources"]] == ["Your records"]
    assert len(saved) == 1


@pytest.mark.parametrize("exc", [RuntimeError("faiss index corrupt"), ValueError("embedding dim mismatch")])
def test_mixed_question_with_retrieval_failure_keeps_the_records_part(seeded_db, saved, monkeypatch, exc):
    monkeypatch.setattr(retriever, "search", lambda *a, **k: (_ for _ in ()).throw(exc))
    r = orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert r["answer"].endswith(orchestrator.POLICY_UNAVAILABLE) and str(exc) not in r["answer"]
    assert "Casual Leave" in r["answer"] and len(saved) == 1


def test_mixed_question_without_handbook_evidence_uses_the_safe_fallback(seeded_db, saved, handbook, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda *a, **k: [])
    r = orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert r["answer"].endswith(rag.FALLBACK) and handbook["llm_calls"] == 0
    assert r["found"] is True and len(saved) == 1          # the records part was found


def test_mixed_question_rejected_llm_answer_falls_back(seeded_db, saved, handbook):
    handbook["answer"] = "You have 99 casual leaves left [Handbook 2.1]."   # unsupported number
    r = orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert r["answer"].endswith(rag.FALLBACK) and "99" not in r["answer"]


def test_mixed_question_with_missing_records_and_no_evidence_is_not_found(seeded_db, saved, monkeypatch):
    monkeypatch.setattr(employee_db, "get_leave_balances", lambda e: [])
    monkeypatch.setattr(retriever, "search", lambda *a, **k: [])
    r = orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert "No leave balance records were found." in r["answer"] and r["answer"].endswith(rag.FALLBACK)
    assert r["found"] is False and r["sources"] == [] and len(saved) == 1


def test_mixed_question_for_account_without_employee(seeded_db, saved, handbook):
    r = orchestrator.answer_question(MIXED_Q, employee_id=None)
    assert orchestrator.NO_EMPLOYEE_WORKSPACE in r["answer"] and r["answer"].endswith(POLICY_ANSWER)
    assert [s["file"] for s in r["sources"]] == ["handbook.md"]
    assert [kind for kind, _ in saved] == ["global"]


def test_mixed_question_about_another_employee_refuses_records_but_answers_policy(seeded_db, saved, handbook,
                                                                                   monkeypatch):
    monkeypatch.setattr(employee_db, "get_leave_balances", lambda e: pytest.fail("must not query"))
    r = orchestrator.answer_question("What is the leave policy and how many leaves does Meera have left?",
                                     employee_id="EMP001")
    assert orchestrator.THIRD_PARTY_REFUSAL in r["answer"] and r["answer"].endswith(POLICY_ANSWER)
    assert len(saved) == 1


def test_mixed_assets_and_policy(seeded_db, saved, handbook):
    handbook["answer"] = "Laptops are issued on Day 1 and must be returned at exit [Handbook 5.1]."
    r = orchestrator.answer_question("Which laptop do I have and what is the laptop policy?", employee_id="EMP001")
    assert "Your assigned assets:\n- Laptop: Dell Latitude" in r["answer"]
    assert r["sources"][0]["section"] == "Assigned assets"
    assert handbook["questions"] == ["what is the laptop policy"]


def test_records_part_database_failure_propagates_and_saves_nothing(seeded_db, saved, handbook, monkeypatch):
    from backend.services.readonly_query import QueryTimeoutError

    monkeypatch.setattr(employee_db, "get_leave_balances",
                        lambda e: (_ for _ in ()).throw(QueryTimeoutError("statement timeout")))
    with pytest.raises(QueryTimeoutError):
        orchestrator.answer_question(MIXED_Q, employee_id="EMP001")
    assert saved == []
