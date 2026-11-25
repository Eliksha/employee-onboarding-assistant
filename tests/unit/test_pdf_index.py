"""M4: canonical PDF ingestion, page-aware chunks, versioned index with atomic activation and recovery."""
import json
import shutil

import faiss
import numpy as np
import pytest

from backend.config import settings
from backend.services import embeddings, guardrails, ingest, retriever

RAW = settings.raw_dir
SENTINEL = "ZEBRA-MARKDOWN-ONLY-SENTINEL-4711"


def _norm(text):
    return " ".join(text.split())


@pytest.fixture
def raw_dir(tmp_path):
    """A knowledge base whose Markdown handbook copy differs from the PDF (contains a sentinel)."""
    d = tmp_path / "raw"
    d.mkdir()
    shutil.copy(RAW / "handbook.pdf", d / "handbook.pdf")
    shutil.copy(RAW / "faqs.md", d / "faqs.md")
    (d / "handbook.md").write_text(f"# Handbook\n\n## 1. Working Hours\n{SENTINEL} only in Markdown.\n", encoding="utf-8")
    return d


# ---------------------------------------------------------------- PDF is the canonical handbook source
def test_repository_knowledge_base_uses_the_pdf_not_the_markdown_copy():
    chunks = ingest.load_chunks()
    sources = {c["source"] for c in chunks}
    assert sources == {"handbook.pdf", "faqs.md"}
    pdf = [c for c in chunks if c["source"] == "handbook.pdf"]
    assert pdf and all(isinstance(c["page"], int) and c["page"] >= 1 for c in pdf)
    assert {c["page"] for c in pdf} == {1, 2, 3}
    selected, skipped = ingest.select_documents()
    assert [p.name for p in selected] == ["handbook.pdf", "faqs.md"]
    assert skipped == [{"file": "handbook.md", "reason": "derived copy of handbook.pdf (PDF is canonical)"}]


def test_pdf_chunk_text_comes_from_the_extracted_page_it_cites():
    pages = [_norm(t) for t in ingest.read_pdf_pages(RAW / "handbook.pdf")]
    for chunk in ingest.chunk_pdf(RAW / "handbook.pdf"):
        body = _norm(chunk["text"][len(chunk["section"]) + 2:])
        assert body in pages[chunk["page"] - 1], (chunk["section"], chunk["page"])
    cab = [c for c in ingest.chunk_pdf(RAW / "handbook.pdf") if c["section"] == "7. Expenses and Travel"]
    assert [c["page"] for c in cab] == [3] and "company cab is provided" in cab[0]["text"]
    posh = [c for c in ingest.chunk_pdf(RAW / "handbook.pdf") if c["section"].startswith("6. Code of Conduct")]
    assert [c["page"] for c in posh] == [3]  # heading on page 2, text on page 3


def test_pdf_sections_reproduce_the_handbook_structure():
    pdf = [c["section"] for c in ingest.chunk_pdf(RAW / "handbook.pdf")]
    md = [c["section"] for c in ingest.chunk_markdown_handbook((RAW / "handbook.md").read_text(encoding="utf-8"),
                                                               "handbook.md")]
    assert pdf[1:] == md[1:]          # every numbered section, same labels, same order
    assert pdf[0] == "Introduction"


def test_numbered_body_lines_are_not_mistaken_for_headings(tmp_path, monkeypatch):
    pages = ["1. Intro\nSome text.\n3 times a month is fine.\n2.1 Out Of Sequence\n2. Leave Policy\n2.1 Casual Leave\nBody."]
    monkeypatch.setattr(ingest, "read_pdf_pages", lambda path: pages)
    sections = [c["section"] for c in ingest.chunk_pdf(tmp_path / "x.pdf")]
    assert sections == ["1. Intro", "2. Leave Policy > 2.1 Casual Leave"]
    first = ingest.chunk_pdf(tmp_path / "x.pdf")[0]["text"]
    assert "2.1 Out Of Sequence" in first and "3 times a month" in first


def test_built_index_contains_pdf_text_and_never_the_markdown_substitute(env, raw_dir):
    n = ingest.build_index(raw_dir=raw_dir)
    _, _, stored, manifest = ingest.load_active()
    assert n == len(stored) and not any(SENTINEL in c["text"] or SENTINEL in c.get("context", "") for c in stored)
    assert {d["file"] for d in manifest["documents"]} == {"handbook.pdf", "faqs.md"}
    assert manifest["skipped"][0]["file"] == "handbook.md"
    hits = retriever.search("company cab provided for employees working beyond 9:00 PM", 4)
    assert hits[0]["source"] == "handbook.pdf" and hits[0]["page"] == 3 and "cab" in hits[0]["text"]
    # Without the PDF the Markdown copy is used - proving the switch is the PDF, not a coincidence.
    (raw_dir / "handbook.pdf").unlink()
    assert any(SENTINEL in c["text"] for c in ingest.load_chunks(raw_dir))


def test_identical_documents_are_indexed_once(tmp_path):
    d = tmp_path / "dup"
    d.mkdir()
    shutil.copy(RAW / "faqs.md", d / "faqs.md")
    shutil.copy(RAW / "faqs.md", d / "faqs_copy.md")
    selected, skipped = ingest.select_documents(d)
    assert [p.name for p in selected] == ["faqs.md"] and skipped[0]["reason"] == "identical to faqs.md"


def test_windows_keep_the_whole_section_as_context():
    parent = {"source": "handbook.pdf", "section": "7. Expenses and Travel", "page": 3,
              "text": "7. Expenses and Travel: One. Two. Three. Four."}
    units = ingest.with_windows([parent])
    assert [u["text"] for u in units] == ["7. Expenses and Travel: One. Two.", "7. Expenses and Travel: Two. Three.",
                                          "7. Expenses and Travel: Three. Four."]
    assert all(u["context"] == parent["text"] and u["page"] == 3 for u in units)
    faq = {"source": "faqs.md", "section": "FAQ: Q?", "text": "Q: Q? A: One. Two. Three."}
    assert ingest.with_windows([faq]) == [{**faq, "context": faq["text"]}]


def test_retriever_returns_each_section_once_with_full_context(env, raw_dir):
    ingest.build_index(raw_dir=raw_dir)
    hits = retriever.search("expense claims receipts payroll cab", 4)
    keys = [(h["source"], h["section"], h.get("page")) for h in hits]
    assert len(keys) == len(set(keys))
    expenses = [h for h in hits if h["section"] == "7. Expenses and Travel"]
    assert expenses and "Business expense claims" in expenses[0]["text"] and "company cab" in expenses[0]["text"]


# ---------------------------------------------------------------- versions, atomic activation, recovery
def test_build_writes_a_validated_version_and_activates_it_atomically(env, raw_dir):
    ingest.build_index(raw_dir=raw_dir)
    folder = settings.index_dir
    first = ingest.active_version()
    assert json.loads((folder / "ACTIVE").read_text())["version"] == first
    v = folder / "versions" / first
    assert {p.name for p in v.iterdir()} == {"faiss.index", "chunks.json", "manifest.json"}
    manifest = json.loads((v / "manifest.json").read_text())
    assert manifest["format"] == ingest.FORMAT and manifest["n_chunks"] == faiss.read_index(str(v / "faiss.index")).ntotal
    for _ in range(4):
        ingest.build_index(raw_dir=raw_dir)
    versions = [p for p in (folder / "versions").iterdir()]
    assert len(versions) == ingest.KEEP_VERSIONS and not any(p.name.startswith(".") for p in versions)
    assert ingest.active_version() in {p.name for p in versions}


@pytest.mark.parametrize("failure", ["embedding", "write", "validation"])
def test_failed_rebuild_keeps_the_previous_index_active_and_serving(env, raw_dir, monkeypatch, failure):
    ingest.build_index(raw_dir=raw_dir)
    before = ingest.active_version()
    assert retriever.search("casual leave", 2)
    with monkeypatch.context() as m:
        if failure == "embedding":
            m.setattr(embeddings, "embed_texts", lambda texts: (_ for _ in ()).throw(RuntimeError("model gone")))
        elif failure == "write":
            m.setattr(ingest, "_write_json", lambda path, data: (_ for _ in ()).throw(OSError(28, "disk full")))
        else:
            m.setattr(ingest, "_validate", lambda *a, **k: (_ for _ in ()).throw(ingest.IndexUnavailable("bad")))
        with pytest.raises((RuntimeError, OSError, ingest.IndexUnavailable)):
            ingest.build_index(raw_dir=raw_dir)
    assert ingest.active_version() == before
    assert not [p for p in (settings.index_dir / "versions").iterdir() if p.name.startswith(".")]
    assert retriever.search("casual leave", 2)


def test_broken_new_version_is_not_served_and_last_good_version_stays(env, raw_dir, caplog):
    ingest.build_index(raw_dir=raw_dir)
    good = ingest.active_version()
    assert retriever.search("casual leave", 1) and retriever.loaded_version() == good
    broken = settings.index_dir / "versions" / "broken"
    broken.mkdir()
    (broken / "chunks.json").write_text("[]", encoding="utf-8")
    (settings.index_dir / "ACTIVE").write_text(json.dumps({"version": "broken"}), encoding="utf-8")
    with caplog.at_level("WARNING", logger="app"):
        assert retriever.search("casual leave", 1)
    assert retriever.loaded_version() == good
    assert any("keeping version" in r.getMessage() for r in caplog.records)


def test_new_version_is_picked_up_without_a_restart(env, raw_dir):
    ingest.build_index(raw_dir=raw_dir)
    retriever.search("casual leave", 1)
    first = retriever.loaded_version()
    (raw_dir / "faqs.md").write_text((raw_dir / "faqs.md").read_text(encoding="utf-8") +
                                     "\n**Q:** Is there a canteen?\n**A:** Yes, on floor 2.\n", encoding="utf-8")
    ingest.build_index(raw_dir=raw_dir)
    retriever.search("canteen", 1)
    assert retriever.loaded_version() != first


def test_request_path_never_builds_or_writes_an_index(env):
    folder = settings.index_dir
    assert not folder.exists()
    with pytest.raises(ingest.IndexUnavailable):
        retriever.search("casual leave", 1)
    assert not folder.exists()


def test_legacy_flat_index_still_loads(env):
    folder = settings.index_dir
    folder.mkdir(parents=True)
    chunks = [{"source": "handbook.md", "section": "1. Working Hours", "text": "1. Working Hours: 9:30 AM"}]
    index = faiss.IndexFlatIP(512)
    index.add(np.ascontiguousarray(embeddings.embed_texts([chunks[0]["text"]])))
    faiss.write_index(index, str(folder / "faiss.index"))
    (folder / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    assert ingest.active_version() == "legacy"
    assert retriever.search("working hours", 1)[0]["section"] == "1. Working Hours"


def test_inconsistent_index_is_rejected(env):
    folder = settings.index_dir
    folder.mkdir(parents=True)
    faiss.write_index(faiss.IndexFlatIP(8), str(folder / "faiss.index"))
    (folder / "chunks.json").write_text(json.dumps([{"text": "x"}]), encoding="utf-8")
    with pytest.raises(ingest.IndexUnavailable):
        ingest.load_active()


# ---------------------------------------------------------------- page-aware citations
def test_handbook_citation_maps_to_pdf_passages():
    passages = [{"source": "handbook.pdf", "section": "2. Leave Policy > 2.1 Casual Leave", "page": 1,
                 "text": "2. Leave Policy > 2.1 Casual Leave: Employees get 8 casual leaves per calendar year."}]
    verdict = guardrails.validate_answer("You get 8 casual leaves per year [Handbook 2.1].", passages)
    assert verdict.ok and verdict.sources[0]["page"] == 1


def test_admin_ingest_on_a_read_only_index_returns_409_and_keeps_the_index(admin_client, monkeypatch):
    def read_only(*a, **k):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(ingest, "build_index", read_only)
    r = admin_client.post("/ingest")
    assert r.status_code == 409 and "read-only" in r.json()["detail"]
