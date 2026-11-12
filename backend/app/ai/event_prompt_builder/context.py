"""Convert a context object to a dict"""

from __future__ import annotations

import json
from app.ai.Context_builder import Context

def _convertContext(context: Context, max_chars: int) -> dict:

    conDict = context.to_prompt_dict(max_chars=max_chars)
    return conDict

def extractContext(context: Context, freedom_level: int | None) -> str:
    """freedom_level default: 5. max chars = freedom_level * 850"""

    if freedom_level is None:
        freedom_level = 5

    if context.lang == "ar":
        freedom_level += 1

    max_chars = freedom_level * 850

    con = _convertContext(context, max_chars)
    return json.dumps(con, ensure_ascii=False, indent=2, default=str)