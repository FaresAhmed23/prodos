"""
Main prompt builder for the event-explanation path for ai.
It handles system prompts, event injection, and context injection.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ai.Context_builder import Context
from app.schemas import DetectionEvent

from app.ai.event_prompt_builder.context import extractContext
from app.ai.event_prompt_builder.event import extractEventInfo
from app.ai.event_prompt_builder.systemPrompt import pickPrompt
from app.ai.event_prompt_builder.tokenCounter import tokenCounter

_DEFAULT_USER_PROMPT_TEMP = """Detected event:\n{event}\n\n{context}\nExplain the detection event using the given 'alert' strucutre.""" #TODO Explain the context structure in the user template

_USER_PROMPT_TEMP_NO_CONTEXT = """Detected event:\n{event}\nExplain the detection event using the given 'alert' strucutre."""

class promptBuilder:

    def __init__(self):
        self._USER_TEMP: str
        self._token_counter: tokenCounter = tokenCounter()

    # ==== Helpers
    def _getContext(self, context: Context, freedom_level: int | None) -> str:
            cont = extractContext(context=context, freedom_level=freedom_level)
            return cont
    
    def _getEvent(self, event: DetectionEvent, compact: bool | None) -> str:
        ev = extractEventInfo(event=event, compact=compact)
        return ev

    def countTokens(self, text: str) -> int:
        return self._token_counter.count(text)

    # ==== main
    def getSystemPrompt(self, lang: str | None, version: str | None, path: Path | None) -> tuple[str, int]:
        """Returns a selected system prompt and its token count"""
        sysPrompt = pickPrompt(lang=lang, version=version)
        tokenCount = self.countTokens(sysPrompt)
        return (sysPrompt, tokenCount)

    def getUserPrompt(
        self, event: DetectionEvent, context: Context | None,
        event_compact: bool | None, context_freedom_level: int | None
    ) -> tuple[str, int]:
        """Returns a full user prompt containing a given detection event and its context if provided."""
        
        evStr = self._getEvent(event=event, compact=event_compact)

        if context:
            self._USER_TEMP = _DEFAULT_USER_PROMPT_TEMP
            conStr = self._getContext(context=context, freedom_level=context_freedom_level)
        else:
            self._USER_TEMP = _USER_PROMPT_TEMP_NO_CONTEXT
            conStr = None

        kwargs = {
            "event": evStr,
            "context": conStr
            }
        
        userPrompt = self._USER_TEMP.format(**kwargs)