"""
Every generated prompt is checked here to ensure an excellant ai experience
for all users.

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

Check Json & extract -> return Explanation -> check language-> check word length ->
check sentances -> overall word complexity -> data validity -> Banned words rating
"""

from __future__ import annotations

import re
import json

from explanation import Explanation
from ..schemas import DetectionEvent

def _json_valid(respnse: str) -> Explanation:
    pass