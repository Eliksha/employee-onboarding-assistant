"""Deterministic guardrails around the RAG answer (Step 5).

* Retrieval gate: similarity threshold plus a narrow borderline band that needs lexical corroboration.
* Context sanitising: retrieved text cannot close or forge the untrusted-context wrapper.
* Output validation: no secret/system-prompt leakage, valid citations only, no numbers or
  email addresses that are absent from the retrieved passages.
* Citation mapping: the API returns only the retrieved passages that the answer actually cites.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from backend.config import settings

CITE_RE = re.compile(r"\[([^\]]+)\]")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
WORD_RE = re.compile(r"[a-z][a-z0-9-]+")
CONTEXT_TAG_RE = re.compile(r"</?\s*untrusted_context[^>]*>", re.I)

# Generic words that must not count as lexical evidence in the borderline band.
STOPWORDS = set("""
a about after all also am an and any are as at be been before being but by can could did do does
doing for from get gets got had has have how i if in into is it its just me more most my no not of
on or our out over please should so some than that the their them then there these they this to too
under up us was we were what when where which while who whom why will with would you your yours
novatech company employee employees new joiner joiners tell know need want give much many there
ignore rules print show reveal
""".split())

SECRET_MIN_LEN = 6
# Every configured secret an answer must never contain (Phase 1 added the reader password and scope secret).
LEAK_CHECKED_SECRETS = ("groq_api_key", "pg_password", "pg_reader_password", "pg_scope_secret")


# ---------------------------------------------------------------- retrieval gate
def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def keyword_overlap(question: str, passages: List[Dict]) -> List[str]:
    """Distinctive question words (stopwords removed) that also occur in the passages."""
    q_words = {_stem(w) for w in WORD_RE.findall(question.lower()) if w not in STOPWORDS and len(w) >= 3}
    p_words = {_stem(w) for p in passages for w in WORD_RE.findall(p["text"].lower())}
    return sorted(q_words & p_words)


def retrieval_gate(question: str, hits: List[Dict]) -> Tuple[bool, str]:
    """Decide whether retrieval evidence is strong enough to ask the LLM.

    * top score >= threshold                    -> pass
    * threshold - margin <= top score < threshold -> pass only with keyword corroboration
    * otherwise                                 -> fail (fallback, LLM not called)
    The LLM's NOT_FOUND rule and validate_answer() still apply after this gate.
    """
    if not hits:
        return False, "no_hits"
    top = hits[0]["score"]
    if top >= settings.similarity_threshold:
        return True, "above_threshold"
    floor = round(settings.similarity_threshold - settings.borderline_margin, 6)  # avoid 0.6000000000000001
    if top >= floor:
        band = [h for h in hits if h["score"] >= floor]
        if keyword_overlap(question, band):
            return True, "borderline_keyword_match"
        return False, "borderline_no_keyword_match"
    return False, "below_threshold"


# ---------------------------------------------------------------- prompt side
def sanitize_passage(text: str) -> str:
    """Stop retrieved text from closing/forging the untrusted-context wrapper."""
    return CONTEXT_TAG_RE.sub("[removed-tag]", text or "")


# ---------------------------------------------------------------- output side
@dataclass
class Verdict:
    ok: bool
    reason: str = "ok"
    sources: List[Dict] = field(default_factory=list)


def _context_text(passages: List[Dict]) -> str:
    return "\n".join(f"{p['section']}\n{p['text']}" for p in passages)


def citations(answer: str) -> List[str]:
    return [c.strip() for c in CITE_RE.findall(answer or "") if re.search(r"handbook|faq", c, re.I)]


def _faq_answer_overlap(answer: str, passage: Dict) -> int:
    a = {_stem(w) for w in WORD_RE.findall(answer.lower()) if w not in STOPWORDS}
    p = {_stem(w) for w in WORD_RE.findall(passage["text"].lower()) if w not in STOPWORDS}
    return len(a & p)


def map_citation(cite: str, passages: List[Dict], answer: str) -> List[Dict]:
    """Retrieved passages referenced by one citation; [] if the citation is not backed by retrieval."""
    matched: List[Dict] = []
    nums = re.findall(r"\d+(?:\.\d+)?", cite) if "handbook" in cite.lower() else []
    for n in nums:
        hb = [p for p in passages if not p["source"].lower().startswith("faq")
              and ((p["section"] + " ").startswith(f"{n}.") or f"> {n} " in p["section"] + " ")]
        # FAQ answers carry "(Handbook N)" back-references; use them if the section itself was not retrieved.
        fq = [p for p in passages if p["source"].lower().startswith("faq") and f"(Handbook {n})" in p["text"]]
        found = hb or fq
        if not found:
            return []
        matched += found
    if re.search(r"\bfaq\b", cite, re.I):
        faqs = [p for p in passages if p["source"].lower().startswith("faq")]
        if not faqs:
            return []
        matched.append(max(faqs, key=lambda p: _faq_answer_overlap(answer, p)))
    if not nums and not re.search(r"\bfaq\b", cite, re.I):
        return []
    return matched


def leak_reasons(answer: str) -> List[str]:
    """Secrets or system-prompt text in the answer. Never returns the secret itself."""
    from backend.services import llm  # local import avoids a cycle

    reasons = []
    low = (answer or "").lower()
    for name in LEAK_CHECKED_SECRETS:
        secret = getattr(settings, name, "") or ""
        if len(secret) >= SECRET_MIN_LEN and secret.lower() in low:
            reasons.append(f"secret_leak:{name}")
    if re.search(r"\bgsk_[a-z0-9]{8,}", low):
        reasons.append("secret_leak:key_pattern")
    for sentence in re.split(r"(?<=[.:])\s+", llm.SYSTEM_PROMPT):
        frag = sentence.strip().lower()[:45]
        if len(frag) >= 30 and frag in low:
            reasons.append("system_prompt_leak")
            break
    return reasons


def unsupported_facts(answer: str, passages: List[Dict]) -> List[str]:
    ctx = _context_text(passages)
    body = CITE_RE.sub(" ", answer or "")
    bad = [n for n in NUM_RE.findall(body) if not re.search(rf"(?<![\d.]){re.escape(n)}(?!\d)", ctx)]
    bad += [e for e in EMAIL_RE.findall(body) if e.lower().rstrip(".") not in ctx.lower()]
    return sorted(set(bad))


def validate_answer(answer: str, passages: List[Dict]) -> Verdict:
    leaks = leak_reasons(answer)
    if leaks:
        return Verdict(False, ",".join(leaks))
    cites = citations(answer)
    if not cites:
        return Verdict(False, "missing_citation")
    sources: List[Dict] = []
    for c in cites:
        mapped = map_citation(c, passages, answer)
        if not mapped:
            return Verdict(False, "citation_not_in_retrieved_passages")
        for p in mapped:
            if p not in sources:
                sources.append(p)
    unsupported = unsupported_facts(answer, passages)
    if unsupported:
        return Verdict(False, f"unsupported_facts:{len(unsupported)}")
    order = {id(p): i for i, p in enumerate(passages)}
    return Verdict(True, "ok", sorted(sources, key=lambda p: order.get(id(p), 0)))
