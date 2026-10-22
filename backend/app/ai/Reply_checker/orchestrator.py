"""
Orchestrator: the surface of the package for Explanation-shaped alerts.

`check_alert(reply, ...)` takes a raw model reply and runs, in order:
parse JSON -> required fields -> Explanation, then every rule in rules.py and
complexity.py. This is the only module that knows about Explanation and
DetectionEvent; everything else in the package is reusable on plain text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..explanation import Explanation
from ...schemas import DetectionEvent
from .complexity import check_complexity
from .config import (
    MAX_ACTION_SENTENCES,
    MAX_EXPLANATION_SENTENCES,
    MAX_TITLE_CHARS,
    REQUIRED_FIELDS,
)
from .parsing import extract_json
from .results import Failure, retry_feedback
from .rules import (
    check_banned_words,
    check_grounding,
    check_language,
    check_length,
    check_must_mention,
    check_no_bullets,
    check_safety,
    check_sentence_count,
)

@dataclass
class CheckResult:
    ok: bool
    failures: list[Failure] = field(default_factory=list)
    explanation: Explanation | None = None
 
    def retry_feedback(self) -> str:
        return retry_feedback(self.failures)


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


# data validity (grounding)
def evidence_from_event(event: DetectionEvent) -> dict[str, Any]:
    """Extracts evidence from an event. The context builder can
    pass a richer dict (durations, counts, sensor names) using `evidence=` in the main function."""
    return {
        "event_type": event.event_type,
        "severity": event.severity,
        "sensor_ids": event.sensor_ids,
        "details": event.details,
    }


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