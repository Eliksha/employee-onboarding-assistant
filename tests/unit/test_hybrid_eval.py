"""M3: held-out evaluation dataset integrity, grading logic and the routing regression floor (no LLM, no DB)."""
import re
from datetime import date

import pytest

from backend.services import orchestrator, rag
from backend.services.employee_query_router import ALLOWED_OPERATIONS, COMPANY_OPERATIONS
from scripts import hybrid_eval as he
from scripts import rag_eval
from tests.unit.test_intent_router import ROUTING_TABLE

DATA = he.load_dataset()
ITEMS = DATA["questions"]
INTENTS = set(ALLOWED_OPERATIONS) | set(COMPANY_OPERATIONS)


# ---------------------------------------------------------------- dataset integrity
def test_dataset_shape_and_coverage():
    ids = [i["id"] for i in ITEMS]
    assert len(ids) == len(set(ids)) and len(ITEMS) >= 60
    counts = {c: sum(i["category"] == c for i in ITEMS) for c in he.CATEGORIES}
    assert all(n >= 6 for n in counts.values()), counts
    for item in ITEMS:
        assert item["category"] in he.CATEGORIES
        assert item["expected_kind"] in ("records", "handbook", "mixed")
        assert set(item.get("expected_intents", [])) <= INTENTS
        if item["category"] in ("records", "mixed", "unauthorized"):
            assert item.get("expected_intents"), item["id"]
        if item["category"] in ("handbook", "mixed"):
            assert item.get("sections") and item.get("answer_keys"), item["id"]


def test_handbook_expectations_are_verbatim_knowledge_base_text():
    kb = rag_eval.kb_text().lower()
    for item in ITEMS:
        if item.get("answer_keys"):
            assert any(k.lower() in kb for k in item["answer_keys"]), f"{item['id']}: no answer key in the KB"


def test_expected_sections_exist_in_the_knowledge_base():
    from backend.services import ingest

    sections = [c["section"] for c in ingest.load_chunks()]
    for item in ITEMS:
        for wanted in item.get("sections", []):
            assert any(wanted.lower() in s.lower() for s in sections), f"{item['id']}: '{wanted}' not a section"


def test_out_of_scope_terms_are_really_absent_from_the_knowledge_base():
    kb = rag_eval.kb_text().lower()
    for item in ITEMS:
        for term in item.get("absent_terms", []):
            assert not re.search(rf"\b{re.escape(term.lower())}\b", kb), f"{item['id']}: '{term}' is in the KB"


def test_held_out_questions_do_not_reuse_router_test_or_rag_eval_questions():
    seen = {q.lower().strip(" ?") for q, _, _ in ROUTING_TABLE}
    seen |= {c[2].lower().strip(" ?") for c in rag_eval.RETRIEVAL_CASES}
    reused = [i["id"] for i in ITEMS if i["question"].lower().strip(" ?") in seen]
    assert not reused, reused


def test_other_employee_markers_do_not_belong_to_the_session_employee():
    markers = [m.lower() for m in DATA["other_employee_markers"]]
    assert DATA["session_employee"] == "EMP001"
    assert not any(m in ("aarav", "aarav sharma", "dell latitude", "aarav.sharma@example.com") for m in markers)


# ---------------------------------------------------------------- routing regression floor
def test_held_out_routing_accuracy_does_not_drop_below_the_measured_baseline():
    rows = [{**i, **he.routing_result(i)} for i in ITEMS]
    metrics = he.routing_metrics(rows)
    assert metrics["third_party_false_positives"] == 0
    assert metrics["accuracy"] >= DATA["routing_baseline_accuracy"], [r["id"] for r in rows if not r["routing_ok"]]


# ---------------------------------------------------------------- grading logic
TRUTH = {
    "checklist": [{"done": True}] * 4 + [{"done": False}] * 11,
    "leave_balances": [{"leave_type": "Casual Leave", "available_days": 8.0},
                       {"leave_type": "Sick Leave", "available_days": 6}],
    "assets": [{"asset_name": "Dell Latitude"}],
    "tickets": [],
    "profile": {"department": "Technology", "joining_date": "2026-11-02"},
    "payroll": [{"payment_date": "2026-11-30"}, {"payment_date": "2026-12-31"}],
}
MARKERS = ["Meera", "HP EliteBook"]


def _grade(item, kind, answer, sources=()):
    return he.grade(item, {"kind": kind}, {"answer": answer, "sources": list(sources)}, TRUTH,
                    rag.FALLBACK, orchestrator.THIRD_PARTY_REFUSAL, MARKERS)


def test_expected_record_values_come_from_ground_truth():
    assert he.expected_record_values("checklist", TRUTH) == ["4 of 15"]
    assert he.expected_record_values("leave_balances", TRUTH) == ["Casual Leave: 8 days", "Sick Leave: 6 days"]
    assert he.expected_record_values("tickets", TRUTH) == ["You have no support tickets"]
    assert he.expected_record_values("payroll", TRUTH, today=date(2026, 12, 1)) == ["2026-12-31"]
    assert he.expected_record_values("payroll", TRUTH, today=date(2027, 1, 1)) == ["No upcoming payroll date"]


def test_records_grading_requires_every_expected_value():
    item = {"id": "x", "category": "records", "expected_intents": ["leave_balances"]}
    assert _grade(item, "records", "- Casual Leave: 8 days\n- Sick Leave: 6 days")["records_ok"] is True
    assert _grade(item, "records", "- Casual Leave: 8 days")["records_ok"] is False


def test_mixed_grading_checks_both_parts_and_citations():
    item = {"id": "m", "category": "mixed", "expected_intents": ["assets"], "sections": ["5.5 Lost"],
            "answer_keys": ["2 hours"]}
    good = "From your records:\n- Laptop: Dell Latitude\n\nFrom the handbook:\nReport within 2 hours [Handbook 5.5]."
    src = [{"file": "Your records", "section": "Assigned assets"},
           {"file": "handbook.md", "section": "5. IT > 5.5 Lost or Stolen Devices"}]
    g = _grade(item, "mixed", good, src)
    assert g["mixed_ok"] and g["citation_precision"] == 1.0 and not g["false_fallback"]
    fallback = "From your records:\n- Laptop: Dell Latitude\n\nFrom the handbook:\n" + rag.FALLBACK
    g = _grade(item, "mixed", fallback, src[:1])
    assert g["records_ok"] and g["false_fallback"] and not g["mixed_ok"] and g["citation_precision"] is None


def test_refusal_leak_and_fallback_grading():
    unauthorized = {"id": "u", "category": "unauthorized", "expected_intents": ["assets"], "expect_refusal": True}
    assert _grade(unauthorized, "records", orchestrator.THIRD_PARTY_REFUSAL)["refusal_ok"] is True
    shown = _grade(unauthorized, "records", "Your assigned assets:\n- Laptop: HP EliteBook")
    assert shown["refusal_ok"] is False and shown["leak"] is True
    oos = {"id": "o", "category": "out_of_scope", "expect_fallback": True}
    assert _grade(oos, "handbook", rag.FALLBACK)["fallback_ok"] is True
    assert _grade(oos, "handbook", "Pets are welcome [Handbook 1].",
                  [{"file": "handbook.md", "section": "1. Working Hours"}])["fallback_ok"] is False


def test_errors_are_reported_not_graded():
    g = he.grade({"id": "e", "category": "handbook", "answer_keys": ["x"], "sections": ["1."]}, {"kind": "handbook"},
                 {"error": "llm_unavailable"}, TRUTH, rag.FALLBACK, orchestrator.THIRD_PARTY_REFUSAL, MARKERS)
    assert g == {"error": "llm_unavailable", "leak": False}


@pytest.mark.parametrize("values, pct, expected", [([], 50, None), ([5], 95, 5), ([1, 2, 3, 4], 50, 2),
                                                   (list(range(1, 21)), 95, 19), (list(range(1, 21)), 50, 10)])
def test_nearest_rank_percentile(values, pct, expected):
    assert he.percentile(values, pct) == expected


def test_split_answer_by_route_kind():
    assert he.split_answer("abc", "records") == ("abc", "")
    assert he.split_answer("abc", "handbook") == ("", "abc")
    assert he.split_answer("From your records:\nA\n\nFrom the handbook:\nB", "mixed") == ("From your records:\nA", "B")
