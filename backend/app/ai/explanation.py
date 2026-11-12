"""The seam between "we detected something" and "we told the owner about it".

Every provider returns the same three strings. Alert delivery must never depend
on any provider being reachable, so callers are expected to treat an exception
from `explain` as "fall back", not as "drop the alert".
"""

from dataclasses import dataclass
from typing import Protocol
from ..schemas import DetectionEvent


@dataclass(frozen=True)
class Explanation:
    title: str
    explanation: str
    recommended_action: str


class ExplanationProvider(Protocol):
    async def explain(self, event: DetectionEvent) -> Explanation: ...