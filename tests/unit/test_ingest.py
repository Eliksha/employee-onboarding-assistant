from backend.config import settings
from backend.services import ingest


def test_handbook_chunks_have_sections():
    text = (settings.raw_dir / "handbook.md").read_text(encoding="utf-8")
    chunks = ingest.chunk_markdown_handbook(text, "handbook.md")
    sections = [c["section"] for c in chunks]
    assert any("Casual Leave" in s for s in sections)
    assert any("VPN" in s for s in sections)
    assert all(len(c["text"].split()) <= settings.chunk_words + 20 for c in chunks)


def test_faq_chunks():
    text = (settings.raw_dir / "faqs.md").read_text(encoding="utf-8")
    chunks = ingest.chunk_faqs(text, "faqs.md")
    assert len(chunks) == 25
    assert chunks[0]["text"].startswith("Q: How many casual leaves")


def test_long_text_is_split_with_overlap():
    words = " ".join(f"w{i}" for i in range(1000))
    parts = ingest._split_long(words, 350, 40)
    assert len(parts) >= 3
    assert parts[0].split()[-40:] == parts[1].split()[:40]
