"""Evil twin detector.

Compares access points seen from a scan to known networks and raises an alert when it detects an impostor

Rules:
  unknown_bssid      known SSID broadcast from an unrecognised BSSID   (HIGH)
  security_downgrade known SSID with weaker security than expected    (HIGH)
  unexpected_channel known SSID/BSSID on a channel we don't expect    (MEDIUM)
  lookalike_ssid     SSID nearly identical to a known one              (MEDIUM)
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Iterable

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "known_aps.json"


SECURITY_RANK = {"OPEN": 0, "WEP": 1, "WPA": 2, "WPA2": 3, "WPA3": 4}
LOOKALIKE_THRESHOLD = 0.85   # Similarity percentage


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class AccessPoint:
    """One access point from a scan."""
    ssid: str
    bssid: str
    channel: int
    security: str
    signal_dbm: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "AccessPoint":
        return cls(
            ssid=d["ssid"],
            bssid=d["bssid"].lower(),
            channel=int(d["channel"]),
            security=d["security"].upper(),
            signal_dbm=d.get("signal_dbm"),
        )


@dataclass(frozen=True)
class KnownNetwork:
    """Legitimate known network from the baseline."""
    ssid: str
    bssids: frozenset[str]
    channels: frozenset[int]
    security: frozenset[str]

    @property
    def min_security_rank(self) -> int:
        return min(SECURITY_RANK[s] for s in self.security)


@dataclass(frozen=True)
class Alert:
    rule: str
    severity: Severity
    message: str
    observed: AccessPoint


def load_known_networks(path: Path | str = DEFAULT_CONFIG) -> list[KnownNetwork]:
    data = json.loads(Path(path).read_text())
    return [
        KnownNetwork(
            ssid=n["ssid"],
            bssids=frozenset(b.lower() for b in n["bssids"]),
            channels=frozenset(n.get("channels", [])),
            security=frozenset(s.upper() for s in n["security"]),
        )
        for n in data["networks"]
    ]


class EvilTwinDetector:
    def __init__(self, known: Iterable[KnownNetwork]):
        self.known = {n.ssid: n for n in known}

    @classmethod
    def from_config(cls, path: Path | str = DEFAULT_CONFIG) -> "EvilTwinDetector":
        return cls(load_known_networks(path))

    def analyze(self, scan: Iterable[AccessPoint]) -> list[Alert]:
        alerts: list[Alert] = []
        for ap in scan:
            if not ap.ssid:  # If SSID is hidden/empty then skip
                continue
            net = self.known.get(ap.ssid)
            if net:
                alerts.extend(self._check_known_ssid(ap, net))
            else:
                alerts.extend(self._check_lookalike(ap))
        return sorted(alerts, key=lambda a: a.severity, reverse=True)

    def _check_known_ssid(self, ap: AccessPoint, net: KnownNetwork) -> list[Alert]:
        alerts = []
        if ap.bssid not in net.bssids:
            alerts.append(Alert(
                "unknown_bssid", Severity.HIGH,
                f"SSID '{ap.ssid}' seen from unknown BSSID {ap.bssid}", ap))
        elif net.channels and ap.channel not in net.channels:
            alerts.append(Alert(
                "unexpected_channel", Severity.MEDIUM,
                f"Known BSSID {ap.bssid} on unexpected channel {ap.channel}", ap))

        rank = SECURITY_RANK.get(ap.security, 0)
        if rank < net.min_security_rank:
            alerts.append(Alert(
                "security_downgrade", Severity.HIGH,
                f"'{ap.ssid}' uses {ap.security}, expected {sorted(net.security)}", ap))
        return alerts

    def _check_lookalike(self, ap: AccessPoint) -> list[Alert]:
        for name in self.known:
            ratio = difflib.SequenceMatcher(None, ap.ssid.casefold().strip(),
                                            name.casefold()).ratio()
            if ratio >= LOOKALIKE_THRESHOLD:
                return [Alert(
                    "lookalike_ssid", Severity.MEDIUM,
                    f"SSID '{ap.ssid}' resembles known '{name}' (similarity {ratio:.2f})", ap)]
        return []
