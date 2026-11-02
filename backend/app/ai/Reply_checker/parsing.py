"""
Reply parsing that is not specific to any output type: pull a JSON object out
of a raw model reply.
"""

from __future__ import annotations

import json
import re

from .results import Failure

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
    return None, [Failure("json", "reply does not contain valid JSON format")]