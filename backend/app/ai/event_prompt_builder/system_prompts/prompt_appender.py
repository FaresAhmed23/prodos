"""this file just appends a new prompt to the json file"""

from __future__ import annotations

import json
from pathlib import Path

PROMPTS_FILE = Path(__file__).resolve().parent / "prompts.json"
TXT_FILE = Path(__file__).resolve().parent / "prompt_writing_space.txt"

def get_txt_data() -> dict:
    with open(TXT_FILE, "r", encoding="utf-8") as file:
        content = file.read()

    keywords = {
        "language": "language: ",
        "prompt_id": "prompt_id: ",
        "prompt": "prompt:\n\n"
        }

    values = {}

    for type, word in keywords.items():
        if word in content and type == "prompt":
            _, _, value = content.partition(word)
            values[type] = value
        elif word in content:
            _, _, value = content.partition(word)
            words = value.split()

            if words:
                word = words[0]
                values[type] = word
            else:
                print(f"no words after {keywords[type]}")
        else:
            print(f"{type} not found. Ensure txt file structure is\nlanguage: 'lang'\nprompt_id: 'prompt_id;\nprompt:\n\n'prompt'")
            return
    return values

def add_prompt(prompt: str, lang: str, prompt_id: int) -> str:
    """
    Add a prompt to prompts.json

    Args:
        prompt: The prompt text, possibly spanning multiple lines.
        lang: Language key, e.g. "en" or "ar".
        prompt_id: Major version number, e.g. 0 for versions 0.1, 0.2, etc.

    Returns:
        The version key assigned to the prompt, e.g. "0.3".
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a nonempty string.")

    if not isinstance(lang, str) or not lang.strip():
        raise ValueError("Language must be a nonempty string.")

    if isinstance(prompt_id, bool) or not isinstance(prompt_id, int) or prompt_id < 0:
        raise ValueError("prompt_id must be a non-negative integer.")

    # Load existing prompts, or initialize the JSON structure.
    if PROMPTS_FILE.exists():
        with PROMPTS_FILE.open("r", encoding="utf-8") as file:
            prompts = json.load(file)
    else:
        prompts = {}

    # Create the language section if it doesn't exist.
    prompts.setdefault(lang, {})

    # Find existing versions belonging to this prompt ID.
    existing_versions = []

    for version in prompts[lang]:
        major, separator, minor = version.partition(".")

        if separator and major.isdigit() and minor.isdigit():
            if int(major) == prompt_id:
                existing_versions.append(int(minor))

    # Automatically assign the next minor version.
    next_minor = max(existing_versions, default=0) + 1
    version_key = f"{prompt_id}.{next_minor}"

    # Store the prompt as one string.
    prompts[lang][version_key] = prompt

    # Write the complete structure back without losing existing prompts.
    with PROMPTS_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            prompts,
            file,
            ensure_ascii=False,
            indent=4
        )
        file.write("\n")

    return version_key

if __name__ == "__main__":

    values = get_txt_data()
    
    print(f"your new prompt version key: {add_prompt(prompt=values["prompt"], lang=values["language"], prompt_id=int(values["prompt_id"]))}")