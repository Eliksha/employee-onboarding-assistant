"""Read the knowledge base, split it into chunks, embed them and build a versioned FAISS index.

Sources (data/raw)
  * PDF documents are canonical: each page's text is extracted (pypdf), split at numbered headings
    ("2. Leave Policy", "2.1 Casual Leave") and chunked per section AND page, so every chunk carries
    `page` metadata and the same section labels as the Markdown chunker ("2. Leave Policy > 2.1 Casual Leave").
  * A Markdown file whose stem matches a PDF (handbook.md vs handbook.pdf) is a derived copy and is NOT
    indexed, so the same content is never indexed twice. Other Markdown files (faqs.md) are indexed.
  * Byte-identical documents are indexed once (SHA-256).

Index versions (index_dir)
  versions/<id>/faiss.index, chunks.json, manifest.json   complete, validated builds
  ACTIVE                                                    {"version": "<id>"}; replaced atomically
A build is written to a temporary directory, validated (vector count, metadata count, dimension, a
self-search), renamed into versions/ and only then activated by atomically replacing ACTIVE. Any failure
leaves the previously active version untouched. Without ACTIVE, the legacy flat files (faiss.index +
chunks.json in index_dir) are used, so older deployments keep working.

Rebuild on the host (Docker mounts data/index read-only):  python -m backend.services.ingest
"""
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np

from backend.config import settings
from backend.services import embeddings

INDEX_FILE = "faiss.index"
META_FILE = "chunks.json"
MANIFEST_FILE = "manifest.json"
ACTIVE_FILE = "ACTIVE"
VERSIONS_DIR = "versions"
KEEP_VERSIONS = 3
FORMAT = "onboardai-index-v2"

_MAJOR_RE = re.compile(r"^(\d{1,2})\.\s+([A-Z][^\n]{1,80})$")
_MINOR_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\s+([A-Z][^\n]{1,80})$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class IndexUnavailable(RuntimeError):
    """No valid FAISS index is available (missing, incomplete or inconsistent)."""


# ---------------------------------------------------------------- chunking
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


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
WINDOW_SENTENCES = 2


def with_windows(chunks: List[Dict]) -> List[Dict]:
    """Small-to-big retrieval units: each section chunk becomes overlapping 2-sentence windows.

    `text` (what is embedded and matched) is the section label + the window; `context` is the whole
    section chunk, which the retriever returns to the LLM. A focused fact inside a longer section (for
    example the last sentence of "7. Expenses and Travel") is then retrievable on its own, while answers
    still see the complete section. Sections of up to two sentences stay a single unit.
    """
    out: List[Dict] = []
    for chunk in chunks:
        prefix = f"{chunk['section']}: "
        body = chunk["text"][len(prefix):] if chunk["text"].startswith(prefix) else chunk["text"]
        sentences = [s for s in _SENTENCE_RE.split(body) if s.strip()]
        if len(sentences) <= WINDOW_SENTENCES or chunk["section"].startswith("FAQ:"):
            out.append({**chunk, "context": chunk["text"]})
            continue
        for i in range(len(sentences) - WINDOW_SENTENCES + 1):
            window = " ".join(sentences[i:i + WINDOW_SENTENCES])
            out.append({**chunk, "text": prefix + window, "context": chunk["text"]})
    return out


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


def read_pdf_pages(path: Path) -> List[str]:
    """Text of every page (1-based order), control characters removed."""
    from pypdf import PdfReader

    return [_CONTROL_RE.sub(" ", page.extract_text() or "") for page in PdfReader(str(path)).pages]


def chunk_pdf(path: Path) -> List[Dict]:
    """Page-aware, heading-aware chunks from a PDF's extracted text.

    Headings are accepted only in numeric sequence (1., 2., 2.1, 2.2, 3. ...), so body lines that begin
    with a number are never mistaken for headings. A section that continues on the next page yields one
    chunk per page, each labelled with the same section.
    """
    source = path.name
    chunks: List[Dict] = []
    major_no, minor_no = 0, 0
    major_title, minor_title = "", ""
    buf: List[str] = []
    page_no = 1

    def section_label() -> str:
        if not major_title:
            return "Introduction"
        major = f"{major_no}. {major_title}"
        return f"{major} > {major_no}.{minor_no} {minor_title}" if minor_title else major

    def flush():
        body = " ".join(" ".join(buf).split())
        buf.clear()
        if not body:
            return
        label = section_label()
        for part in _split_long(body, settings.chunk_words, settings.chunk_overlap_words):
            chunks.append({"source": source, "section": label, "page": page_no, "text": f"{label}: {part}"})

    for page_no, text in enumerate(read_pdf_pages(path), start=1):
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if not line:
                continue
            minor, major = _MINOR_RE.match(line), _MAJOR_RE.match(line)
            if minor and int(minor.group(1)) == major_no and int(minor.group(2)) == minor_no + 1 \
                    and not line.endswith("."):
                flush()
                minor_no, minor_title = int(minor.group(2)), minor.group(3).strip()
            elif major and int(major.group(1)) == major_no + 1 and not line.endswith("."):
                flush()
                major_no, major_title, minor_no, minor_title = int(major.group(1)), major.group(2).strip(), 0, ""
            else:
                buf.append(line)
        flush()  # chunks never span pages
    return chunks


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_documents(raw_dir: Optional[Path] = None) -> Tuple[List[Path], List[Dict]]:
    """Documents to index (PDF canonical over a same-stem Markdown copy; identical files once) + skip notes."""
    raw = Path(raw_dir or settings.raw_dir)
    pdf_stems = {p.stem.lower() for p in raw.glob("*.pdf")}
    selected, skipped, seen = [], [], {}
    for path in sorted(list(raw.glob("*.pdf")) + list(raw.glob("*.md")), key=lambda p: (p.suffix != ".pdf", p.name)):
        if path.suffix == ".md" and path.stem.lower() in pdf_stems:
            skipped.append({"file": path.name, "reason": f"derived copy of {path.stem}.pdf (PDF is canonical)"})
            continue
        digest = _sha256(path)
        if digest in seen:
            skipped.append({"file": path.name, "reason": f"identical to {seen[digest]}"})
            continue
        seen[digest] = path.name
        selected.append(path)
    return selected, skipped


def load_chunks(raw_dir: Optional[Path] = None) -> List[Dict]:
    chunks: List[Dict] = []
    for path in select_documents(raw_dir)[0]:
        if path.suffix == ".pdf":
            chunks += chunk_pdf(path)
        elif path.stem.lower().startswith("faq"):
            chunks += chunk_faqs(path.read_text(encoding="utf-8"), path.name)
        else:
            chunks += chunk_markdown_handbook(path.read_text(encoding="utf-8"), path.name)
    return with_windows(chunks)


# ---------------------------------------------------------------- versioned index
def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _validate(folder: Path, expected_dim: Optional[int] = None):
    """Load and check one index folder; returns (index, chunks, manifest)."""
    index = faiss.read_index(str(folder / INDEX_FILE))
    chunks = json.loads((folder / META_FILE).read_text(encoding="utf-8"))
    manifest_path = folder / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if index.ntotal != len(chunks) or not chunks:
        raise IndexUnavailable(f"index has {index.ntotal} vectors but {len(chunks)} chunks")
    if manifest is not None and (manifest.get("format") != FORMAT or manifest.get("n_chunks") != len(chunks)
                                 or manifest.get("dim") != index.d):
        raise IndexUnavailable("manifest does not match the index")
    if expected_dim is not None and index.d != expected_dim:
        raise IndexUnavailable(f"index dimension {index.d} != embedding dimension {expected_dim}")
    return index, chunks, manifest


def active_version(index_dir: Optional[Path] = None) -> str:
    """Identifier of the active version ('legacy' for flat files, '' when nothing exists)."""
    folder = Path(index_dir or settings.index_dir)
    active = folder / ACTIVE_FILE
    if active.exists():
        return json.loads(active.read_text(encoding="utf-8"))["version"]
    return "legacy" if (folder / INDEX_FILE).exists() else ""


def load_active(index_dir: Optional[Path] = None):
    """(version, faiss index, chunks, manifest) of the active index; raises IndexUnavailable."""
    folder = Path(index_dir or settings.index_dir)
    try:
        version = active_version(folder)
        if not version:
            raise IndexUnavailable(f"no index in {folder}; build it with: python -m backend.services.ingest")
        target = folder if version == "legacy" else folder / VERSIONS_DIR / version
        index, chunks, manifest = _validate(target)
        return version, index, chunks, manifest
    except IndexUnavailable:
        raise
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise IndexUnavailable(f"active index cannot be loaded: {type(exc).__name__}") from exc


def build_index(raw_dir: Optional[Path] = None, index_dir: Optional[Path] = None) -> int:
    """Build, validate and atomically activate a new index version; the previous version stays on failure."""
    out = Path(index_dir or settings.index_dir)
    documents, skipped = select_documents(raw_dir)
    chunks = load_chunks(raw_dir)
    if not chunks:
        raise RuntimeError(f"No documents found in {raw_dir or settings.raw_dir}")
    vectors = np.ascontiguousarray(embeddings.embed_texts([c["text"] for c in chunks]), dtype="float32")
    digest = hashlib.sha256(json.dumps(chunks, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    version = f"{time.strftime('%Y%m%dT%H%M%S')}-{time.time_ns() % 10**9:09d}-{digest}"
    versions = out / VERSIONS_DIR
    versions.mkdir(parents=True, exist_ok=True)
    tmp = versions / f".tmp-{version}-{os.getpid()}"
    final = versions / version
    try:
        tmp.mkdir()
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(tmp / INDEX_FILE))
        _write_json(tmp / META_FILE, chunks)
        _write_json(tmp / MANIFEST_FILE, {
            "format": FORMAT, "version": version, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "embed_model": settings.embed_model, "dim": int(vectors.shape[1]), "n_chunks": len(chunks),
            "chunking": {"words": settings.chunk_words, "overlap_words": settings.chunk_overlap_words},
            "documents": [{"file": p.name, "sha256": _sha256(p),
                           "chunks": sum(c["source"] == p.name for c in chunks),
                           "pages": len({c.get("page") for c in chunks if c["source"] == p.name and c.get("page")})}
                          for p in documents],
            "skipped": skipped,
        })
        loaded, stored, _ = _validate(tmp, expected_dim=int(vectors.shape[1]))
        scores, ids = loaded.search(vectors[:1], 1)
        if int(ids[0][0]) != 0 or [c["text"] for c in stored] != [c["text"] for c in chunks]:
            raise IndexUnavailable("self-search check failed")
        if final.exists():
            shutil.rmtree(final)
        os.replace(tmp, final)
        pointer = out / f".{ACTIVE_FILE}.tmp-{os.getpid()}"
        _write_json(pointer, {"version": version})
        os.replace(pointer, out / ACTIVE_FILE)  # atomic activation
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    _prune(versions, keep={version})
    return len(chunks)


def _prune(versions: Path, keep: set) -> None:
    """Keep the newest KEEP_VERSIONS complete versions (never the active one); remove stale temp dirs."""
    complete = sorted((p for p in versions.iterdir() if p.is_dir() and not p.name.startswith(".")), reverse=True)
    for old in complete[KEEP_VERSIONS:]:
        if old.name not in keep:
            shutil.rmtree(old, ignore_errors=True)


if __name__ == "__main__":
    n = build_index()
    print(f"Indexed {n} chunks into {settings.index_dir} (active version: {active_version()})")
