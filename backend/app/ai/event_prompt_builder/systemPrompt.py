"""System Prompt fecther and finder, it picks the system prompt version and language needed."""

from __future__ import annotations

import json
from pathlib import Path

PROMPTS_FILE = Path(__file__).resolve().parent / "system_prompts" / "prompts.json"

def _fetchPrompts(jsonPath: Path) -> dict[str, dict[str, str]]:
    with open(jsonPath, "r") as file:
        prompts = json.loads(jsonPath)

    return prompts

def pickPrompt(version: str | None, lang: str ="en", jsonPath: Path = PROMPTS_FILE) -> str:
    """
    Pick a system prompt from a json file containing system prompts categorized by language and prompt-versions.
    If a value is missing like lang or version it returns the closest default version,
    with most deafult as : the last version of "en" system prompts.

    Default jsonPath: "/system_prompts/prompts.json".

    Raises.
    """

    try:
        prompts = _fetchPrompts(jsonPath)
    except Exception as e:
        raise RuntimeError(f"An error occurred trying to open the system prompts file: {e}") from e

    if not isinstance(lang, str) or not lang.strip():
        raise ValueError("Language must be a nonempty string.")

    if not version:
        version = next(reversed(prompts[lang]))

    if not isinstance(version, str) or not version.strip():
        raise ValueError("version must be in string format")

    try:
        return prompts[lang][version]
    except KeyError:
        raise ("Version wasn't found for the given language.")