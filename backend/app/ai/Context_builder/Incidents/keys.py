"""
Generating special keys for each incident based on the incident type.

site_id is NOT part of the key (it is a column). Keys don't include
severity, confidence, rates, timestamps, or sensor ids.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import DetectionEvent, normalize_mac

MAX_KEY_LEN = 200

def _mac(value) -> str | None:
    """Normalized MAC, or None if missing/unusable. Never raises."""
    if not value or not isinstance(value, str):
        return None
    try:
        return normalize_mac(value)
    except Exception:
        cleaned = value.strip().upper()
        return cleaned or None


def _text(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _join(*parts: str | None) -> str:
    return ":".join(p for p in parts if p)[:MAX_KEY_LEN]

class KeyStrategy(ABC):
    @abstractmethod
    def key(self, details: dict) -> str:
        """Build the key from event details."""


class DeauthKey(KeyStrategy):
    """deauth_flood:{src_mac} -> deauth_flood"""
    def key(self, details: dict) -> str:
        return _join("deauth_flood", _mac(details.get("src_mac")))


class EvilTwinKey(KeyStrategy):
    """evil_twin:{ssid}:{rogue_bssid} -> evil_twin:{ssid} -> evil_twin"""
    def key(self, details: dict) -> str:
        return _join("evil_twin", _text(details.get("ssid")),
                     _mac(details.get("rogue_bssid")))


class RogueApKey(KeyStrategy):
    """rogue_ap:{bssid or rogue_bssid} -> rogue_ap"""
    def key(self, details: dict) -> str:
        bssid = _mac(details.get("bssid")) or _mac(details.get("rogue_bssid"))
        return _join("rogue_ap", bssid)


class FallbackKey(KeyStrategy):
    """{event_type} only (anomaly or unknown types)."""
    def __init__(self, event_type: str) -> None:
        self._event_type = str(event_type)

    def key(self, details: dict) -> str:
        return self._event_type[:MAX_KEY_LEN]


class KeyRegistry:
    """Maps event_type -> KeyStrategy."""
    _STRATEGIES: dict[str, KeyStrategy] = {
        "deauth_flood": DeauthKey(),
        "evil_twin": EvilTwinKey(),
        "rogue_ap": RogueApKey(),
    }

    def for_type(self, event_type: str) -> KeyStrategy:
        return self._STRATEGIES.get(event_type) or FallbackKey(event_type)


_registry = KeyRegistry()


def incident_key(event: DetectionEvent) -> str:
    """Public helper: the incident key for an event. Never raises."""
    try:
        details = event.details if isinstance(event.details, dict) else {}
        return _registry.for_type(event.event_type).key(details)
    except Exception:
        return str(getattr(event, "event_type", "unknown"))[:MAX_KEY_LEN]