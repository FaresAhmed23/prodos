"""
Reusable text rules: plain text in, list of Failure out (empty list = passed).
None of them depends on Explanation, so the chat agent can call them directly,
e.g. check_language(answer, "ar").
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .config import (
    BANNED_WORDS,
    MAX_ARABIC_SHARE_EN,
    MIN_ARABIC_SHARE,
    UNSAFE_PHRASES,
)
from .helpers import (
    _ARABIC_LETTER_RE,
    _BULLET_RE,
    _MAC_RE,
    _NUMBER_RE,
    _QUOTED_RE,
    _WORD_RE,
    _strip_identifiers,
    normalize_digits,
    split_sentences,
)
from .results import Failure

# Reusable rules (plain text in, failures out. that's it)

def check_length(text: str, name: str, max_chars: int) -> list[Failure]:
    """Checks the length of an Explanation field or a whole reply, in characters."""
    if len(text) > max_chars:
        return [Failure("length", f"{name} is {len(text)} chars, max {max_chars}")]
    return []
 
 
def check_sentence_count(text: str, name: str, max_sentences: int) -> list[Failure]:
    """Checks the length of an Explanation field or a whole reply, in sentences."""
    n = len(split_sentences(text))
    if n > max_sentences:
        return [Failure("sentences length", f"{name} has {n} sentences, max number of sentences should be: {max_sentences}")]
    return []
 
 
def check_no_bullets(text: str, name: str) -> list[Failure]:
    """Checks if there's any lists or bullet points"""
    if _BULLET_RE.search(text):
        return [Failure("format", f"{name} must be plain sentences, not a list")]
    return []
 
 
def check_language(text: str, lang: str) -> list[Failure]:
    letters = _WORD_RE.findall(_strip_identifiers(text))
    total = sum(len(w) for w in letters)
    if total == 0:
        return [Failure("language", "no readable text found")]
    arabic = len(_ARABIC_LETTER_RE.findall(_strip_identifiers(text)))
    share = arabic / total
    if lang == "ar" and share < MIN_ARABIC_SHARE:
        return [Failure("language", f"expected Arabic, only {share:.0%} of the total letters were Arabic letters")]
    if lang == "en" and share > MAX_ARABIC_SHARE_EN:
        return [Failure("language", f"expected English, {share:.0%} of the letters were Arabic letters")]
    return []

def banned_word_hits(text: str, lang: str) -> list[str]:
    """Banned terms found in text. English list applies to every language,
    because Latin-script jargon can appear inside Arabic text."""
    lowered = _strip_identifiers(text).lower()
    terms = BANNED_WORDS["en"] + (BANNED_WORDS.get(lang, []) if lang != "en" else [])
    hits = []
    for term in terms:
        if re.search(rf"(?<!\w){re.escape(term)}\w*", lowered):
            hits.append(term)
    return hits
 
 
def check_banned_words(text: str, lang: str) -> list[Failure]:
    hits = banned_word_hits(text, lang)
    if len(hits)>2:
        return [Failure("jargon", f"technical words not allowed: {', '.join(hits)}")]
    return []
 
 
def check_safety(text: str, lang: str) -> list[Failure]:
    """Rejects advice that attacks, retaliates or disables the owner's security.
    Terms match as WHOLE words (optionally with s/es/d/ed/ing), so "jam" does not
    flag "jamboree" or "jammed door"-style substrings inside other words."""
    lowered = text.lower()
    terms = UNSAFE_PHRASES["en"] + (UNSAFE_PHRASES.get(lang, []) if lang != "en" else [])
    hits = [
        t for t in terms
        if re.search(rf"(?<!\w){re.escape(t.lower())}(?:s|es|d|ed|ing)?(?!\w)", lowered)
    ]
    if hits:
        return [Failure("safety", f"unsafe advice (Prodos only observes and advises): {', '.join(hits)}")]
    return []
 
 
def check_must_mention(text: str, must_mention: Iterable[str]) -> list[Failure]:
    lowered = text.lower()
    missing = [m for m in must_mention if m.lower() not in lowered]
    if missing:
        return [Failure("mention", f"must mention: {', '.join(missing)}")]
    return []


# data validity (grounding)
def check_grounding(text: str, evidence: dict[str, Any]) -> list[Failure]:
    """Every MAC, quoted name and number with 2+ digits in `text` must appear
    in `evidence`. Main defense against invented facts."""
    blob = normalize_digits(json.dumps(evidence, ensure_ascii=False, default=str))
    evidence_text = blob.lower()
    evidence_macs = {m.upper().replace("-", ":") for m in _MAC_RE.findall(blob)}
    evidence_numbers = {n.replace(",", "") for n in _NUMBER_RE.findall(blob)}
 
    text = normalize_digits(text)
    failures: list[Failure] = []
 
    for mac in _MAC_RE.findall(text):
        if mac.upper().replace("-", ":") not in evidence_macs:
            failures.append(Failure("grounding", f"MAC {mac} is not in the provided data"))
 
    for name in _QUOTED_RE.findall(text):
        if name.lower() not in evidence_text:
            failures.append(Failure("grounding", f'name "{name}" is not in the provided data'))
 
    no_macs = _MAC_RE.sub(" ", text)
    for num in _NUMBER_RE.findall(no_macs):
        clean = num.replace(",", "")
        if len(re.sub(r"\D", "", clean)) >= 2 and clean not in evidence_numbers:
            failures.append(Failure("grounding", f"number {num} is not in the provided data"))
 
    return failures
