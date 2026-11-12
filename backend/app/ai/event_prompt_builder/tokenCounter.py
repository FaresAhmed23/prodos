"""
Counts/Predicts the number of tokens for a given prompt.
Tokens counted for the selected model family: qwen3
"""

from __future__ import annotations

#requires: pip install tokenizers huggingface-hub
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

class tokenCounter:

    def __init__(self):
        # Download and cache the ~3 MB tokenizer file
        __tokenizer_path = hf_hub_download(repo_id="Qwen/Qwen3-0.6B", filename="tokenizer.json")
        self.__tokenizer = Tokenizer.from_file(__tokenizer_path)

    def count(self, jsonText: str) -> int:
        token_count = len(self.__tokenizer.encode(jsonText).ids)
        return token_count