"""
Generic result objects shared by every rule. Nothing here knows about
Explanation or Alert, so any module in the system can use them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# Result objects
@dataclass(frozen=True)
class Failure:
    rule: str      # "json", "length", "jargon"
    detail: str    # human-readable reason, also fed back to the model on retry


#only returns a summary of failures for the agent to try again, USED OUTSIDE THE CHECKER 
def retry_feedback(failures: Iterable[Failure]) -> str:
    lines = "; ".join(f"[{f.rule}] {f.detail}" for f in failures)
    return (
        "Your previous reply was rejected for these reasons: "
        f"{lines}. Reply again with JSON object only, fixing every problem mentioned."
    )