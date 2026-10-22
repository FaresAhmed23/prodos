"""
Word-complexity scoring and the readability check built on it (English and
Arabic). Reusable on any text: chat answers, summaries, alerts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import (
    AR_COMPLEXITY_COFACTOR,
    COMPLEXITY_COFACTOR,
    LONG_WORD_LETTERS,
    MAX_AR_COMPLEXITY_RATING,
    MAX_COMPLEXITY_RATING,
    MAX_LONG_WORD_SHARE,
    MAX_WORDS_PER_SENTENCE,
)
from .dictionaries import AR_COMPLEXITY_WORDS, EN_COMPLEXITY_WORDS
from .helpers import (
    _AR_LETTERS,
    _AR_PREFIXES,
    _AR_SUFFIXES,
    _AR_TOKEN_RE,
    _WORD_RE,
    _strip_identifiers,
    normalize_arabic,
    normalize_digits,
    split_sentences,
)
from .results import Failure

# Built once at import: Preprocessing words and sentences in COMPLEXITY_WORDS to use them
# effeciently
_COMPLEX_PHRASES: list[tuple[re.Pattern[str], str, int]] = []
_COMPLEX_LOOKUP: dict[str, int] = {}
for _level, _entries in EN_COMPLEXITY_WORDS.items():
    for _entry in _entries:
        if re.search(r"[\s\-.]", _entry):
            _COMPLEX_PHRASES.append((
                re.compile(rf"(?<![\w]){re.escape(_entry)}s?(?![\w])"), _entry, _level))
        else:
            # keep the HIGHEST level of a word if listed twice
            _COMPLEX_LOOKUP[_entry] = max(_level, _COMPLEX_LOOKUP.get(_entry, 0))
_COMPLEX_PHRASES.sort(key=lambda item: len(item[1]), reverse=True)


# Arabic: same idea, with Arabic boundaries and optional attached prefix/suffix.
_AR_PHRASES: list[tuple[re.Pattern[str], str, int]] = []
_AR_LOOKUP: dict[str, int] = {}
_AR_PREFIX_ALT = "|".join(sorted(_AR_PREFIXES, key=len, reverse=True))

for _level, _entries in AR_COMPLEXITY_WORDS.items():
    for _entry in _entries:
        _norm = normalize_arabic(_entry)
        if " " in _norm:
            _AR_PHRASES.append((
                re.compile(
                    rf"(?<![{_AR_LETTERS}])(?:{_AR_PREFIX_ALT})?{re.escape(_norm)}"
                    rf"(?:ات|ين|ون|ه|ها|هم)?(?![{_AR_LETTERS}])"),
                _entry, _level))
        else:
            _AR_LOOKUP[_norm] = max(_level, _AR_LOOKUP.get(_norm, 0))
_AR_PHRASES.sort(key=lambda item: len(item[1]), reverse=True)


#complexity rating summary object
@dataclass(frozen=True)
class ComplexityRating:
    rating: float                       # score / (word_count * COMPLEXITY_COFACTOR)
    score: int                          # sum of weights of all complex words found
    word_count: int
    hits: tuple[tuple[str, int], ...]   # (word_or_phrase, level), one per occurrence
 
    def worst(self, n: int = 5) -> list[str]:
        """The n most complex distinct words found, for readable error messages."""
        seen: dict[str, int] = {}
        for word, level in self.hits:
            seen[word] = level
        ordered = sorted(seen.items(), key=lambda val_key: val_key[1], reverse=True)
        return [f"{w} (level {lvl})" for w, lvl in ordered[:n]]

#----------------------------------------------------------------
#complexity

def _lookup_level(word: str) -> tuple[str, int] | None:
    """Level of a single word, tolerates simple inflections (-s, -ed, -ing, -ly...)."""
    if word in _COMPLEX_LOOKUP:
        return word, _COMPLEX_LOOKUP[word]
    for suffix in ("ies", "es", "s", "ed", "d", "ing", "ly", "er"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stem = word[: -len(suffix)]
            candidates = [stem, stem + "e"]
            if suffix == "ies":
                candidates = [stem + "y"]
            for candidate in candidates:
                if candidate in _COMPLEX_LOOKUP:
                    return candidate, _COMPLEX_LOOKUP[candidate]
    return None

def _ar_lookup_level(token: str) -> tuple[str, int] | None:
    """Level of one normalized Arabic token. Tries the token as written, then with
    one attached prefix removed (ال، و، ب، ل...) and/or one suffix removed
    (ات، ون، ها...), always keeping a stem of at least 3 letters."""
    if token in _AR_LOOKUP:
        return token, _AR_LOOKUP[token]
    for prefix in [""] + [p for p in _AR_PREFIXES if token.startswith(p)]:
        base = token[len(prefix):]
        if len(base) < 3:
            continue
        if prefix and base in _AR_LOOKUP:
            return base, _AR_LOOKUP[base]
        for suffix in _AR_SUFFIXES:
            if base.endswith(suffix) and len(base) - len(suffix) >= 3:
                stem = base[: -len(suffix)]
                # feminine plural: مصادقة -> مصادقات (ة became ه when normalized)
                for candidate in ((stem, stem + "ه") if suffix == "ات" else (stem,)):
                    if candidate in _AR_LOOKUP:
                        return candidate, _AR_LOOKUP[candidate]
    return None

def _hits_en(text: str) -> list[tuple[str, int]]:
    lowered = normalize_digits(_strip_identifiers(text)).lower()
    hits: list[tuple[str, int]] = []
    # 1) multi-word phrases first (and blank them out so their parts aren't re-counted)
    for pattern, entry, level in _COMPLEX_PHRASES:
        found = pattern.findall(lowered)
        if found:
            hits.extend([(entry, level)] * len(found))
            lowered = pattern.sub(" ", lowered)
    # 2) single words
    for token in re.findall(r"[a-z][a-z0-9]*", lowered):
        match = _lookup_level(token)
        if match:
            hits.append(match)
    return hits
 
 
def _hits_ar(text: str) -> list[tuple[str, int]]:
    normalized = normalize_arabic(_strip_identifiers(text))
    hits: list[tuple[str, int]] = []
    for pattern, entry, level in _AR_PHRASES:
        found = pattern.findall(normalized)
        if found:
            hits.extend([(entry, level)] * len(found))
            normalized = pattern.sub(" ", normalized)
    for token in _AR_TOKEN_RE.findall(normalized):
        match = _ar_lookup_level(token)
        if match:
            hits.append(match)
    # Latin-script jargon inside Arabic text (BSSID, SSID, MAC...) is scored by
    # the English dictionary; it never matches Arabic letters.
    hits.extend(_hits_en(text))
    return hits

def rate_complexity(text: str, lang: str = "en") -> ComplexityRating:
    """Weighted complexity of text in `lang` ("en" or "ar").
 
    rating = (sum of each complex word's level) / (word_count * cofactor)
    Level 5 counts as five level-1 words; unlisted words count 0. The cofactor is
    COMPLEXITY_COFACTOR for English and AR_COMPLEXITY_COFACTOR for Arabic.
    Reusable on any text (e.g. chat answers); it only reads the text.
    """
    if lang == "ar":
        hits = _hits_ar(text)
        word_count = len(_WORD_RE.findall(normalize_arabic(text)))
        cofactor = AR_COMPLEXITY_COFACTOR
    else:
        hits = _hits_en(text)
        word_count = len(_WORD_RE.findall(text))
        cofactor = COMPLEXITY_COFACTOR
    word_count = max(word_count, 1)
    score = sum(level for _, level in hits)
    rating = score / (word_count * cofactor)
    return ComplexityRating(rating=rating, score=score, word_count=word_count, hits=tuple(hits))
 
def check_complexity(text: str, lang: str) -> list[Failure]:
    """Readability checks: sentence length, long-word share (English only),
    and the weighted complexity rating (English and Arabic)."""
    failures: list[Failure] = []
    for sentence in split_sentences(text):
        n_words = len(_WORD_RE.findall(sentence))
        if n_words > MAX_WORDS_PER_SENTENCE:
            failures.append(Failure(
                "complexity", f"a sentence has {n_words} words, max {MAX_WORDS_PER_SENTENCE}"))
            break
    if lang == "en":  # long-word heuristic is only meaningful for English
        words = _WORD_RE.findall(text)
        if words:
            share = sum(len(w) >= LONG_WORD_LETTERS for w in words) / len(words)
            if share > MAX_LONG_WORD_SHARE:
                failures.append(Failure(
                    "complexity", f"{share:.0%} of words are very long; use simpler words"))
    if lang in ("en", "ar"):
        limit = MAX_AR_COMPLEXITY_RATING if lang == "ar" else MAX_COMPLEXITY_RATING
        rated = rate_complexity(text, lang)
        if rated.rating > limit:
            failures.append(Failure(
                "complexity",
                f"text is too complex for non-technical users. "
                f"Avoid these word (sorted from the worst to the least worst): {', '.join(rated.worst())}"))
    return failures