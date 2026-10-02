"""Deterministic, offline explanations. This is the floor, not the ceiling.

The audience is a café/clinic owner with no security background. Rules that
matter more than the wording:
- never say "deauthentication frame", "BSSID", "802.11", "packet", "probe"
- say what is happening, why it matters to them, then one concrete next step
- calm at 1-3, matter-of-fact at 4-7, urgent but not panicked at 8-10
"""

from ..schemas import DetectionEvent
from .explanation import Explanation

_CALM = "We noticed this and are keeping an eye on it."
_SERIOUS = "We are watching this closely."
_URGENT = "We think this needs your attention today."

_BAND = ((3, _CALM), (7, _SERIOUS), (10, _URGENT))

_UNKNOWN_FALLBACK = (
    "Something unusual happened on your network.",
    "Our sensors noticed activity that does not match normal behaviour. "
    "We could not identify the specific cause, so we are flagging it for a closer look.",
    "No action needed yet. If you notice customers having trouble connecting, tell us.",
)


def _band(severity: int) -> str:
    for ceiling, text in _BAND:
        if severity <= ceiling:
            return text
    return _URGENT


def _deauth(event: DetectionEvent) -> Explanation:
    count = event.details.get("count")
    lead = (
        f"A nearby device sent {count} of these messages in a short burst."
        if isinstance(count, int) else "A nearby device sent these messages repeatedly."
    )
    return Explanation(
        title="Someone is trying to knock customers off your WiFi",
        explanation=(
            "A device near your premises is repeatedly telling your WiFi to disconnect "
            "customers. This is often done to force people to reconnect to a fake copy of "
            f"your network. {lead} {_band(event.severity)}"
        ),
        recommended_action=(
            "Check the alerts list. If customers keep saying they get disconnected, "
            "consider changing your WiFi password until we confirm the problem has stopped."
        ),
    )


def _evil_twin(event: DetectionEvent) -> Explanation:
    ssid = event.details.get("ssid")
    which = f" the name \"{ssid}\"" if isinstance(ssid, str) and ssid else ""
    return Explanation(
        title="A copy of your WiFi network has appeared",
        explanation=(
            f"Someone nearby is broadcasting a network with{which}, the same name you use. "
            "Customers who connect to it by mistake could have their browsing exposed to "
            f"someone else. {_band(event.severity)}"
        ),
        recommended_action=(
            "Ask staff to remind customers to check the network name before connecting, "
            "and to avoid any network that asks them to sign in again. We will keep "
            "tracking the copy."
        ),
    )


def _rogue_ap(event: DetectionEvent) -> Explanation:
    return Explanation(
        title="An unknown wireless network appeared nearby",
        explanation=(
            "One of your sensors picked up a wireless network it does not recognise near "
            "your premises. On its own this is common and often harmless, but we are "
            f"recording it in case it is relevant. {_band(event.severity)}"
        ),
        recommended_action=(
            "No action needed unless you suspect someone is impersonating your business. "
            "You can check the full list of detected networks at any time."
        ),
    )


_BUILDERS = {
    "deauth_flood": _deauth,
    "evil_twin": _evil_twin,
    "rogue_ap": _rogue_ap,
}


class TemplateProvider:
    """Offline provider. Always succeeds -- it is the safety net."""

    async def explain(self, event: DetectionEvent) -> Explanation:
        builder = _BUILDERS.get(event.event_type)
        return builder(event) if builder else Explanation(*_UNKNOWN_FALLBACK)