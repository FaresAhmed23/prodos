"""
Low-level text helpers: digit/Arabic normalization, sentence splitting and
identifier stripping, plus the shared regexes and Arabic prefix/suffix tables.
No dependency on any other module of the package.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_QUOTED_RE = re.compile(r"[\"“”«»]([^\"“”«»]{1,64})[\"“”«»]")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?؟]+(?:\s+|$)")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_BULLET_RE = re.compile(r"(^|\n)\s*(?:[-*•]|\d+[.)])\s+")
 
def normalize_digits(text: str) -> str:
    """Arabic-Indic digits -> Western digits."""
    return text.translate(_ARABIC_INDIC)
 
 
def split_sentences(text: str) -> list[str]:
    """Works for English and Arabic punctuation (. ! ? ؟)."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p for p in (s.strip() for s in parts) if p]
 
 
def _strip_identifiers(text: str) -> str:
    """Remove MACs and quoted names so they don't skew language checks."""
    return _QUOTED_RE.sub(" ", _MAC_RE.sub(" ", text))


#ِArabic words preparing
_AR_DIACRITICS_RE = re.compile(r"[ً-ٰٟـ]")  # harakat, dagger alef, tatweel
_AR_TRANSLATE = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})
_AR_TOKEN_RE = re.compile(r"[ء-غف-ي]+")
_AR_LETTERS = "ء-غف-ي"
_AR_PREFIXES = ("وبال", "وال", "بال", "كال", "فال", "لل", "ال", "و", "ف", "ب", "ل", "ك", "س")
_AR_SUFFIXES = ("ات", "ون", "ين", "ان", "ها", "هم", "هن", "كم", "كن", "نا", "ي", "ه", "ك", "ا")
 
 
def normalize_arabic(text: str) -> str:
    """Remove diacritics/tatweel and unify letter variants so spelling differences
    (أ/إ/ا, ة/ه, ى/ي) don't hide a dictionary word."""
    return _AR_DIACRITICS_RE.sub("", text).translate(_AR_TRANSLATE)
