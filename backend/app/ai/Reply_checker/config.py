"""
Tunable limits, required fields and word lists for the checker package.

Everything you may want to adjust without touching logic lives here (the big
complexity dictionaries are in dictionaries.py).
"""

from __future__ import annotations

MAX_TITLE_CHARS = 90
MAX_EXPLANATION_SENTENCES = 3
MAX_ACTION_SENTENCES = 2
MAX_WORDS_PER_SENTENCE = 25
MAX_LONG_WORD_SHARE = 0.10      # share of words with >= LONG_WORD_LETTERS letters
LONG_WORD_LETTERS = 12
MIN_ARABIC_SHARE = 0.60         # for lang="ar": Arabic letters / all letters
MAX_ARABIC_SHARE_EN = 0.10      # for lang="en"

COMPLEXITY_COFACTOR = 1.0
AR_COMPLEXITY_COFACTOR = 1.0
MAX_COMPLEXITY_RATING = 0.25
MAX_AR_COMPLEXITY_RATING = 0.25
 
REQUIRED_FIELDS = ("title", "explanation", "recommended_action")

BANNED_WORDS: dict[str, list[str]] = {
    "en": [
        "deauth", "deauthentication", "bssid", "ssid", "802.11", "packet",
        "probe request", "beacon", "channel", "signal strength", "rssi",
        "mac address", "frame",
    ],
    "ar": [],  # TODO: add Arabic words
}
 
UNSAFE_PHRASES: dict[str, list[str]] = {
    "en": [
        "hack back", "attack", "jam", "jamming", "jammed", "retaliate",
        "retaliating", "retaliation", "take revenge",
        "send disconnect", "track down", "confront the person",
        "disable your security", "turn off your firewall",
    ],
    "ar": [],  # TODO: Add arabic words
}