"""Read handbook/FAQs, split into chunks, embed, and build the FAISS index."""
import json
import re
from pathlib import Path
from typing import Dict, List

import faiss
import numpy as np

from backend.config import settings
from backend.services import embeddings

INDEX_FILE = "faiss.index"
META_FILE = "chunks.json"


def _split_long(text: str, max_words: int, overlap: int) -> List[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    parts, start = [], 0
    while start < len(words):
        parts.append(" ".join(words[start : start + max_words]))
        if start + max_words >= len(words):
            break
        start += max_words - overlap
    return parts


def chunk_markdown_handbook(text: str, source: str) -> List[Dict]:
    """Section-aware chunking: every heading block becomes a chunk labelled with its section."""
    chunks: List[Dict] = []
    h1 = h2 = h3 = ""
    buf: List[str] = []

    def flush():
        body = " ".join(l.strip() for l in buf if l.strip())
        buf.clear()
        if not body:
            return
        section = " > ".join(p for p in (h2, h3) if p) or h1 or "Introduction"
        for part in _split_long(body, settings.chunk_words, settings.chunk_overlap_words):
            chunks.append({"source": source, "section": section, "text": f"{section}: {part}"})

    for line in text.splitlines():
        if line.startswith("### "):
            flush(); h3 = line[4:].strip()
        elif line.startswith("## "):
            flush(); h2 = line[3:].strip(); h3 = ""
        elif line.startswith("# "):
            flush(); h1 = line[2:].strip(); h2 = h3 = ""
        else:
            buf.append(line)
    flush()
    return chunks


def chunk_faqs(text: str, source: str) -> List[Dict]:
    chunks = []
    for m in re.finditer(r"\*\*Q:\*\*\s*(.+?)\s*\*\*A:\*\*\s*(.+?)(?=\n\s*\*\*Q:\*\*|\Z)", text, flags=re.S):
        q, a = m.group(1).strip(), " ".join(m.group(2).split())
        chunks.append({"source": source, "section": f"FAQ: {q}", "text": f"Q: {q} A: {a}"})
    return chunks


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def load_chunks() -> List[Dict]:
    raw = Path(settings.raw_dir)
    chunks: List[Dict] = []
    for path in sorted(raw.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if path.stem.lower().startswith("faq"):
            chunks += chunk_faqs(text, path.name)
        else:
            chunks += chunk_markdown_handbook(text, path.name)
    # PDFs are only used when there is no Markdown version of the same document
    for path in sorted(raw.glob("*.pdf")):
        if not (raw / f"{path.stem}.md").exists():
            for part in _split_long(_read_pdf(path), settings.chunk_words, settings.chunk_overlap_words):
                chunks.append({"source": path.name, "section": "PDF text", "text": part})
    return chunks


def build_index() -> int:
    chunks = load_chunks()
    if not chunks:
        raise RuntimeError(f"No documents found in {settings.raw_dir}")
    vectors = embeddings.embed_texts([c["text"] for c in chunks])
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(np.ascontiguousarray(vectors))
    out = Path(settings.index_dir)
    out.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out / INDEX_FILE))
    (out / META_FILE).write_text(json.dumps(chunks, indent=2), encoding="utf-8")
    return len(chunks)


if __name__ == "__main__":
    n = build_index()
    print(f"Indexed {n} chunks into {settings.index_dir}")
