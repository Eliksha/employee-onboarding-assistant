"""Deterministic Step 4 RAG-evaluation tests (no LLM, no database writes).

LLM-dependent checks (grounding, abstention, prompt injection) live in
`python -m scripts.rag_eval` and are reported separately.
"""
import re
from types import SimpleNamespace

import pytest

from backend.config import settings
from backend.services import guardrails, ingest, llm, retriever
from scripts import rag_eval as ev


# ---------- A. Knowledge-base availability (reads the real index, read-only) ----------

def test_active_index_exists_and_matches_raw_documents():
    pytest.importorskip("faiss")
    assert (settings.raw_dir / "handbook.pdf").exists() and (settings.raw_dir / "faqs.md").exists()
    try:
        version, index, stored, manifest = ingest.load_active()
    except ingest.IndexUnavailable as exc:
        pytest.fail(f"FAISS index missing or invalid - run: python -m backend.services.ingest ({exc})")
    assert index.ntotal == len(stored) > 40
    assert [c["text"] for c in ingest.load_chunks()] == [c["text"] for c in stored], "index is stale"
    assert manifest is not None and manifest["embed_model"] == settings.embed_model, "legacy index: rebuild it"


# ---------- Test-data integrity: expectations come from the KB, not invented ----------

def test_expected_facts_exist_in_knowledge_base():
    kb = ev.kb_text().lower()
    for cid, *_, facts, keys in ev.RETRIEVAL_CASES:
        assert any(f.lower() in kb for f in facts), f"{cid}: expected fact not in KB"
        assert any(k.lower() in kb for k in keys), f"{cid}: answer key not in KB"


def test_unknown_questions_are_really_absent_from_knowledge_base():
    kb = ev.kb_text().lower()
    for cid, _, terms in ev.UNKNOWN_CASES:
        for t in terms:
            assert not re.search(rf"\b{re.escape(t)}\b", kb), f"{cid}: '{t}' occurs in KB"


# ---------- B. Retrieval relevance with the real embedding model ----------

@pytest.fixture
def real_retriever(monkeypatch):
    try:
        from backend.services import embeddings
        embeddings.embed_texts(["warm-up"])
    except Exception as exc:  # model not downloadable/cached offline
        pytest.skip(f"embedding model unavailable: {type(exc).__name__}")
    retriever.reset()
    yield retriever
    retriever.reset()


def test_retrieval_relevance_on_onboarding_questions(real_retriever):
    misses = []
    for cid, _, q, sections, facts, _ in ev.RETRIEVAL_CASES:
        hits = real_retriever.search(q, settings.top_k)
        if ev.section_rank(hits, sections) is None:
            misses.append(f"{cid}: expected section not in top-{settings.top_k}")
        elif not any(f.lower() in ev._ctx(hits).lower() for f in facts):
            misses.append(f"{cid}: fact not retrieved")
        elif not guardrails.retrieval_gate(q, hits)[0]:
            misses.append(f"{cid}: rejected by retrieval gate (top {hits[0]['score']:.3f})")
    assert not misses, misses


# ---------- C. Grounding checker helpers ----------

PASSAGES = [
    {"source": "handbook.md", "section": "2. Leave Policy > 2.1 Casual Leave",
     "text": "2. Leave Policy > 2.1 Casual Leave: Employees get 8 casual leaves per calendar year."},
    {"source": "faqs.md", "section": "FAQ: How many casual leaves do I get?",
     "text": "Q: How many casual leaves do I get? A: 8 per calendar year (Handbook 2.1)."},
]


def test_unsupported_numbers_and_emails_detected():
    ctx = ev._ctx(PASSAGES)
    assert ev.unsupported_numbers("You get 8 casual leaves [Handbook 2.1].", ctx) == []
    assert ev.unsupported_numbers("You get 12 casual leaves [Handbook 2.1].", ctx) == ["12"]
    assert ev.unsupported_emails("Mail leave@novatech.example", ctx) == ["leave@novatech.example"]


def test_citation_extraction_and_matching():
    assert ev.citations("8 leaves [Handbook 2.1] and [FAQ].") == ["Handbook 2.1", "FAQ"]
    assert ev.citations("No citation here.") == []
    assert ev.citation_matches_passages("Handbook 2.1", PASSAGES)
    assert ev.citation_matches_passages("FAQ", PASSAGES)
    assert not ev.citation_matches_passages("Handbook 5.3", PASSAGES)


# ---------- E. Prompt construction keeps retrieved text out of the system role ----------

def test_injected_passage_is_sent_as_context_not_as_system_instruction(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status="completed", output_text="<think>x</think>ok")

    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(llm, "_client", lambda: fake)
    injected = {"source": "injected_test_doc.md", "section": "Notice", "text": ev.INJECTION_CASES[0][3]}
    assert llm.generate_answer("When is my salary credited?", [injected] + PASSAGES) == "ok"

    (user,) = captured["input"]
    assert captured["instructions"] == llm.SYSTEM_PROMPT and user["role"] == "user"
    assert ev.CANARY not in captured["instructions"]
    # The injected instruction is screened out before the prompt is built; legitimate passages stay as context.
    assert ev.CANARY not in user["content"] and "injected_test_doc.md" not in user["content"]
    assert user["content"].startswith("<untrusted_context>\n[1] (handbook.md - ")
    assert captured["temperature"] == 0


def test_leak_detector_never_needs_to_print_secret(monkeypatch):
    monkeypatch.setattr(settings, "azure_openai_api_key", "TESTFAKEAZUREKEY1234567890")
    assert "API key leaked" in ev._leaks("here: TESTFAKEAZUREKEY1234567890")
    assert "key-like token" in ev._leaks("here: sk-abcdefghijklmnop1234")
    assert ev._leaks("Salary is credited on the last working day [Handbook 3].") == []
