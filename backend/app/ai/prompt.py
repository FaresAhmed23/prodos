"""
All prompt-related operations are here, the goal of this file is to encapsulate prompts
from the rest of the app to have better control and tracking for them.

This file contains all the system prompt versions & builds the final message the llm is gonna get.

System prompts are stored in prompts/prompts.json and are retrieved selectively.
"""

from __future__ import annotations

from ..schemas import DetectionEvent
from .explanation import Explanation

import json
from pathlib import Path

PROMPTS_FILE = Path(__file__).resolve().parent / "prompts" / "prompts.json"

_USER_TEMPLATE = """Detected event:
{event}

Write the alert.""" #next thing to edit

def _load_prompts() -> dict:
    """loads prompts from the json file in prompts subfolder"""
    with PROMPTS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_system_prompt(language: str = "en", version: str = "2.1") -> str:
    """
    Retrieves a specific system prompt from prompts/prompts.json.

    Langauge choices: ar | en
    Prompt version format: "m.n" where m is a unique prompt and n is
    the variation of that prompt.
    """
    prompts = _load_prompts()

    try:
        prompt_text = prompts[language][version]
    except KeyError as exc:
        available = {
            lang: list(versions.keys())
            for lang, versions in prompts.items()
        }
        raise ValueError(
            f"Unknown prompt: language={language!r}, "
            f"version={version!r}. Available prompts: {available}"
        ) from exc

    if not isinstance(prompt_text, str) or not prompt_text.strip():
        raise ValueError(
            f"Prompt {language}/{version} is a nonempty string"
        )

    return prompt_text

def build_prompt(event: DetectionEvent) -> str: 
    # model_dump_json, not model_dump: detected_at is a datetime and the JSON
    # column on the log row cannot store one.
    return _USER_TEMPLATE.format(event=event.model_dump_json(indent=2))