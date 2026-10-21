"""
Every generated prompt is checked here to ensure an excellant ai experience
for all users.

The checker is built from small, independent RULE functions (one per criterion).
Each rule takes plain text (or a parsed object) and returns a list of Failure.

objects: empty list = passed. Because rules only depend on text, the future chat
agent can reuse them directly (e.g. check_language(answer, "ar")).



Each AI response will be validated against the following criteria:
    * Text length (for explanation and action separatly)
    * Words complexty
    * Correct JSON format / required fields
    * Language matching
    * necessary-to-mention sentances
    * important data validity
    * Response shape
    * Banned words rate
    
The checker returns validity state and reason for invalidity if it's invalid.
It also returns explanation to spare llm_provider from doing it again.

Orchestration order (check_alert):
    parse JSON -> required fields -> Explanation object
    -> text length -> sentence count -> language -> word complexity
    -> banned words -> data validity (grounding) -> necessary mentions -> safety

The checker returns a CheckResult: ok flag, the list of failures (reason for
invalidity) and the parsed Explanation, so llm_provider does not have to parse
the reply a second time. `retry_feedback()` turns failures into a short message
to append on the one allowed retry.
"""

from __future__ import annotations
 
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
 
from .explanation import Explanation
from ..schemas import DetectionEvent
 
# Will be added to a config file one day.

MAX_TITLE_CHARS = 90
MAX_EXPLANATION_SENTENCES = 3
MAX_ACTION_SENTENCES = 2
MAX_WORDS_PER_SENTENCE = 25
MAX_LONG_WORD_SHARE = 0.10      # share of words with >= LONG_WORD_LETTERS letters
LONG_WORD_LETTERS = 12
MIN_ARABIC_SHARE = 0.60         # for lang="ar": Arabic letters / all letters
MAX_ARABIC_SHARE_EN = 0.10      # for lang="en"

COMPLEXITY_COFACTOR = 1.0
MAX_COMPLEXITY_RATING = 0.25    # e.g. 40 words may carry ~10 points of complexity
 
REQUIRED_FIELDS = ("title", "explanation", "recommended_action")

COMPLEXITY_WORDS: dict[int, list[str]] = {
    1: [
        "approximately", "additional", "assistance", "indicate", "currently",
        "numerous", "obtain", "require", "sufficient", "attempt", "verify",
        "ensure", "initiate", "subsequent", "regarding", "therefore",
        "utilize", "utilise", "commence", "terminate", "proceed",
        "demonstrate", "individual", "persistent", "potential", "substantial",
        "significant", "particular", "frequently", "consecutive",
        "simultaneously", "unusual", "consequently", "furthermore",
        "nevertheless", "whereas", "prior", "remain", "determine",
        "identify", "implement", "maintain", "monitor", "observe",
        "recommend", "occurrence", "continuous", "repeated", "excessive",
        "affect", "associated", "respective",
    ],
    2: [
        "suspicious", "unauthorized", "unauthorised", "malicious",
        "legitimate", "anomaly", "anomalous", "intercept", "impersonate",
        "impersonation", "imitate", "vulnerable", "compromised", "compromise",
        "credentials", "attacker", "interference", "intruder", "deceptive",
        "fraudulent", "counterfeit", "disrupt", "disruption", "interruption",
        "unprotected", "exposure", "expose", "mitigate", "mitigation",
        "safeguard", "precaution", "escalate", "incident", "verification",
        "broadcast", "fabricated", "unsecured", "adversary", "tamper",
        "tampering", "sabotage", "unverified", "obscure", "coordinated",
        "deliberate", "deliberately", "malfunction",
    ],
    3: [
        "encryption", "encrypted", "encrypt", "authentication", "authorization",
        "protocol", "bandwidth", "firmware", "spoof", "spoofing", "spoofed",
        "configuration", "configure", "configured", "interface",
        "infrastructure", "intrusion", "transmission", "transmit",
        "transmitter", "transmitted", "frequency", "threshold", "algorithm",
        "diagnostic", "parameter", "subnet", "administrator", "passphrase",
        "certificate", "latency", "throughput", "wireless-layer", "unicast",
        "multicast", "interoperability", "redundancy", "heuristic",
        "metadata", "anonymized", "proxy", "tunnel", "tunneling",
        "synchronization", "timestamp", "baseline", "signature", "payload",
        "peripheral", "diagnostics",
    ],
    4: [
        "eavesdropping", "eavesdrop", "eavesdropper", "phishing", "handshake",
        "rogue", "hijack", "hijacking", "hijacked", "malware", "ransomware",
        "firewall", "gateway", "vulnerability", "exploit", "exploitation",
        "reconnaissance", "authenticate", "authenticated", "sniffer",
        "sniffing", "sniffed", "interception", "decryption", "decrypt",
        "cryptographic", "telemetry", "replay", "brute-force", "channel",
        "credential harvesting", "attack vector", "anomaly detection",
        "rogue access point", "session hijacking", "downgrade attack",
        "exfiltration", "lateral movement", "backdoor", "botnet", "spyware",
        "keylogger", "zero-day", "penetration", "intrusion detection",
        "fingerprinting", "triangulation", "obfuscation",
    ],
    5: [
        "deauthentication", "deauthenticate", "deauthenticated", "deauth",
        "de-authentication", "disassociation", "disassociate", "bssid",
        "ssid", "essid", "rssi", "mac address", "access point",
        "man-in-the-middle", "mitm", "evil twin", "management frame",
        "protected management frames", "pmf", "packet", "beacon",
        "probe request", "probe response", "802.11", "802.11w", "wpa", "wpa2",
        "wpa3", "wep", "monitor mode", "promiscuous", "frame",
        "denial of service", "denial-of-service", "ddos", "captive portal",
        "radius", "vlan", "tcp", "udp", "ip address", "dns", "ssl", "tls",
        "wi-fi protected access", "sequence number", "signal strength",
        "received signal strength", "payload frame", "control frame",
        "association request", "authentication frame", "pairwise master key",
        "four-way handshake", "ieee",
    ],
}

BANNED_WORDS: dict[str, list[str]] = {
    "en": [
        "deauth", "deauthentication", "bssid", "ssid", "802.11", "packet",
        "probe request", "beacon", "channel", "signal strength", "rssi",
        "mac address", "frame",
    ],
    "ar": [],  # TODO: add Arabic words
}
 
UNSAFE_PHRASES: dict[str, list[str]] = {
    "en": [
        "hack back", "attack", "jam", "retaliate", "take revenge",
        "send disconnect", "track down", "confront the person",
        "disable your security", "turn off your firewall",
    ],
    "ar": [],  # TODO: Add arabic words
}

# Built once at import: Preprocessing words and sentences in COMPLEXITY_WORDS to use them
# effeciently
_COMPLEX_PHRASES: list[tuple[re.Pattern[str], str, int]] = []
_COMPLEX_LOOKUP: dict[str, int] = {}
for _level, _entries in COMPLEXITY_WORDS.items():
    for _entry in _entries:
        if re.search(r"[\s\-.]", _entry):
            _COMPLEX_PHRASES.append((
                re.compile(rf"(?<![\w]){re.escape(_entry)}s?(?![\w])"), _entry, _level))
        else:
            # keep the HIGHEST level if a word is listed twice
            _COMPLEX_LOOKUP[_entry] = max(_level, _COMPLEX_LOOKUP.get(_entry, 0))
_COMPLEX_PHRASES.sort(key=lambda item: len(item[1]), reverse=True)

# Result objects
@dataclass(frozen=True)
class Failure:
    rule: str      # "json", "length", "jargon"
    detail: str    # human-readable reason, also fed back to the model on retry
 
 
@dataclass
class CheckResult:
    ok: bool
    failures: list[Failure] = field(default_factory=list)
    explanation: Explanation | None = None
 
    def retry_feedback(self) -> str:
        return retry_feedback(self.failures)

#complexity rating summary object
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

#only returns a summary of failures for the agent to try again, USED OUTSIDE THE CHECKER 
def retry_feedback(failures: Iterable[Failure]) -> str:
    lines = "; ".join(f"[{f.rule}] {f.detail}" for f in failures)
    return (
        "Your previous reply was rejected for these reasons: "
        f"{lines}. Reply again with JSON object only, fixing every problem mentioned."
    )
 
 
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

 
# Step 1: JSON extraction and parsing

def extract_json(reply: str) -> tuple[dict | None, list[Failure]]:
    """Pull a JSON object out of a raw model reply (handles ``` fences)."""
    text = reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
 
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
 
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data, []
        return None, [Failure("json", "reply has JSON format but not an object")]
    return None, [Failure("json", "reply doesn not contain valid JSON format")]
 
 
def parse_explanation(reply: str) -> tuple[Explanation | None, list[Failure]]:
    """JSON -> Explanation, checking required fields and their types."""
    data, failures = extract_json(reply)
    if failures or data is None:
        return None, failures
 
    problems: list[Failure] = []
    for key in REQUIRED_FIELDS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(Failure("fields", f"'{key}' is missing or empty"))
    extra = set(data) - set(REQUIRED_FIELDS)
    if extra:
        problems.append(Failure("fields", f"The json object has unexpected keys: {sorted(extra)}"))
    if problems:
        return None, problems
 
    return Explanation(
        title=data["title"].strip(),
        explanation=data["explanation"].strip(),
        recommended_action=data["recommended_action"].strip(),
    ), []
 

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
        return [Failure("sentences length", f"{name} has {n} sentences, max number of sentences shoud be: {max_sentences}")]
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

def rate_complexity(text: str) -> ComplexityRating:
    """Weighted complexity of ENGLISH text.
 
    rating = (sum of each complex word's level) / (word_count * COMPLEXITY_COFACTOR)
    Level 5 counts as five level-1 words; unlisted words count 0.
    Reusable on any text (e.g. chat answers); it only reads the text.
    """
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
 
    word_count = max(len(_WORD_RE.findall(text)), 1)
    score = sum(level for _, level in hits)
    rating = score / (word_count * COMPLEXITY_COFACTOR)
    return ComplexityRating(rating=rating, score=score, word_count=word_count, hits=tuple(hits))
 
def check_complexity(text: str, lang: str) -> list[Failure]:
    """Readability checks: sentence length, long-word share, weighted complexity."""
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
        rated = rate_complexity(text)
        if rated.rating > MAX_COMPLEXITY_RATING:
            failures.append(Failure(
                "complexity",
                f"text is too complex (rating {rated.rating:.2f}, max {MAX_COMPLEXITY_RATING}); "
                f"replace: {', '.join(rated.worst())}"))
    return failures

# /complexity
#---------------------------------------------------------------------------------
 
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
    if hits>2:
        return [Failure("jargon", f"technical words not allowed: {', '.join(hits)}")]
    return []
 
 
def check_safety(text: str, lang: str) -> list[Failure]:
    lowered = text.lower()
    terms = UNSAFE_PHRASES["en"] + (UNSAFE_PHRASES.get(lang, []) if lang != "en" else [])
    hits = [t for t in terms if t in lowered]
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
def evidence_from_event(event: DetectionEvent) -> dict[str, Any]:
    """Minimal evidence when only the event is known. The context builder can
    pass a richer dict (durations, counts, sensor names) using `evidence=` in the main function."""
    return {
        "event_type": event.event_type,
        "severity": event.severity,
        "sensor_ids": event.sensor_ids,
        "details": event.details,
    }
 
 
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
 
 
# Orchestrator
def check_explanation(
    exp: Explanation,
    lang: str = "en",
    *,
    evidence: dict[str, Any] | None = None,
    must_mention: Iterable[str] = (),
    allow_technical: bool = False,
) -> list[Failure]:
    """Run all rules on an already-parsed Explanation."""
    failures: list[Failure] = []
    failures += check_length(exp.title, "title", MAX_TITLE_CHARS)
    failures += check_sentence_count(exp.explanation, "explanation", MAX_EXPLANATION_SENTENCES)
    failures += check_sentence_count(exp.recommended_action, "recommended_action", MAX_ACTION_SENTENCES)
    failures += check_no_bullets(exp.recommended_action, "recommended_action")
 
    full_text = f"{exp.title}. {exp.explanation} {exp.recommended_action}"
    failures += check_language(full_text, lang)
    failures += check_complexity(exp.explanation, lang)
    if not allow_technical:
        failures += check_banned_words(full_text, lang)
    if evidence is not None:
        failures += check_grounding(full_text, evidence)
    failures += check_must_mention(full_text, must_mention)
    failures += check_safety(full_text, lang)
    return failures
 
 
def check_alert(
    reply: str,
    event: DetectionEvent | None = None,
    lang: str = "en",
    *,
    evidence: dict[str, Any] | None = None,
    must_mention: Iterable[str] = (),
    allow_technical: bool = False,
) -> CheckResult:
    """Validate a raw model reply.
 
    - `event`: if given (and no `evidence`), facts are checked against the event.
    - `evidence`: richer facts from the context builder; takes priority.
    """
    exp, failures = parse_explanation(reply)
    if exp is None:
        return CheckResult(ok=False, failures=failures)
 
    if evidence is None and event is not None:
        evidence = evidence_from_event(event)
 
    failures = check_explanation(
        exp, lang,
        evidence=evidence,
        must_mention=must_mention,
        allow_technical=allow_technical,
    )
    return CheckResult(ok=not failures, failures=failures, explanation=exp)