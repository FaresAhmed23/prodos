"""Deterministic, offline explanations. This is the floor, not the ceiling.

The audience is a cafe/clinic owner with no security background. Rules that
matter more than the wording:
- never say "deauthentication frame", "BSSID", "802.11", "packet", "probe"
- say what is happening, why it matters to them, then one concrete next step
- calm at 1-3, matter-of-fact at 4-7, urgent but not panicked at 8-10
- never give advice that does not actually work (see notes per builder)

Languages: "en" (default) and "ar" (simple Egyptian Arabic). Unknown codes fall
back to English. Every explanation is at most 3 sentences, to match the LLM
prompt ceiling, in both languages.
"""

from ..schemas import DetectionEvent
from .explanation import Explanation

# Strings

_TEXT = {
    "en": {
        "calm": "We noticed this and are keeping an eye on it.",
        "serious": "We are watching this closely.",
        "urgent": "We think this needs your attention today.",

        # deauth flood
        "deauth_title": "Someone is trying to knock customers off your WiFi",
        # {lead} is either "" or ", about N in a short burst"
        "deauth_expl": (
            "A device nearby keeps sending fake \"disconnect\" messages that kick "
            "customers off your WiFi{lead}. Sometimes this is done to push people "
            "onto a fake copy of your network. {band}"
        ),
        "deauth_lead": ", about {count} in a short burst",
        # Changing the password does NOT stop this attack, so we do not suggest it.
        "deauth_action": (
            "Ask whoever set up your router to turn on the \"PMF\" option in its "
            "WiFi security settings, if it has one."
        ),

        # evil twin
        "twin_title": "An unknown copy of your WiFi network has appeared",
        "twin_expl": (
            "Someone nearby is broadcasting a network with the same name as "
            "yours{which}. If it is not a second router or extender of your own, "
            "customers who connect to it could have their activity watched or be "
            "tricked into typing in passwords. {band}"
        ),
        "twin_which": " (\"{ssid}\")",
        "twin_action": (
            "First check whether you added a second router or WiFi extender with "
            "the same name. If not, ask staff to tell customers not to enter "
            "passwords or card details over the WiFi until it is gone."
        ),

        # rogue AP
        "rogue_title": "An unknown wireless network appeared nearby",
        "rogue_expl_low": (
            "One of our sensors picked up a WiFi network we do not recognise near "
            "your business. Most of the time it is a neighbour's router or "
            "someone's phone hotspot, but it's being logged just in case. {band}"
        ),
        "rogue_expl_high": (
            "One of our sensors picked up a WiFi network we do not recognise near "
            "your business. It may be a neighbour's router or a phone hotspot, "
            "but it looks unusual enough that we want you to know. {band}"
        ),
        "rogue_action_low": (
            "Nothing to do right now. If customers start having WiFi trouble, "
            "check the alerts list, or ask Prodos."
        ),
        "rogue_action_high": (
            "Check the list of detected networks for one that uses your WiFi "
            "name or ask Prodos to find it for you. If you find one, ask "
            "staff to warn customers away from it."
        ),

        # unknown
        "unknown": (
            "Something unusual happened on your network.",
            "Our sensors noticed activity that does not look like normal "
            "behaviour, but we could not pin down the cause, so we are flagging "
            "it for a closer look.",
            "Nothing to do right now. If customers start having trouble "
            "connecting, check the alerts list.",
        ),
    },

    # Simple Egyptian Arabic.
    "ar": {
        "calm": "لاحظنا ده وبنراقبه.",
        "serious": "بنتابع الموضوع ده عن قرب.",
        "urgent": "الموضوع ده محتاج اهتمامك النهارده.",
        "deauth_title": "حد بيحاول يفصل زباينك عن الواي فاي بتاعك",
        "deauth_expl": (
            "جهاز قريب منك بيبعت رسايل «افصل» مزيفة بتخلّي موبايلات الزباين "
            "تفصل من الواي فاي{lead}. ساعات بيتعمل كده عشان الناس تدخل على "
            "نسخة مزيفة من شبكتك. {band}"
        ),
        "deauth_lead": "، حوالي {count} رسالة في وقت قصير",
        "deauth_action": (
            "اطلب من اللي ظبّط لك الراوتر إنه يفعّل خيار «PMF» في إعدادات "
            "أمان الواي فاي، لو موجود."
        ),
        "twin_title": "ظهرت نسخة مقلّدة من شبكة الواي فاي بتاعتك",
        "twin_expl": (
            "في جهاز قريب منك بيبثّ شبكة بنفس اسم شبكتك{which}. لو مش راوتر "
            "تاني أو مقوّي شبكة بتاعك، يبقى أي زبون يدخل عليها ممكن حد يتفرج "
            "على اللي بيعمله أو يضحك عليه عشان يكتب الباسورد. {band}"
        ),
        "twin_which": " («{ssid}»)",
        "twin_action": (
            "اتأكد الأول إنك ما ضفتش راوتر تاني أو مقوّي شبكة بنفس الاسم. لو "
            "لأ، قول للموظفين ينبّهوا الزباين ما يكتبوش باسوردات أو بيانات "
            "كارت على الواي فاي لحد ما الموضوع يخلص."
        ),
        "rogue_title": "ظهرت شبكة واي فاي مش معروفة قريب منك",
        "rogue_expl_low": (
            "واحد من السنسورات بتاعتنا لقط شبكة واي فاي مش عارفينها قريبة من "
            "مكانك. في الغالب بتبقى راوتر جار أو هوت سبوت موبايل حد، بس بنسجّلها "
            "للاحتياط. {band}"
        ),
        "rogue_expl_high": (
            "واحد من السنسورات بتاعتنا لقط شبكة واي فاي مش عارفينها قريبة من "
            "مكانك. ممكن تكون راوتر جار أو هوت سبوت، بس شكلها غريب كفاية "
            "إننا نعرّفك. {band}"
        ),
        "rogue_action_low": (
            "مفيش حاجة لازم تعملها دلوقتي. لو الزباين بدأوا يشتكوا من الواي "
            "فاي، بص على قائمة التنبيهات او اسأل برودوس عن الموضوع."
        ),
        "rogue_action_high": (
            "بص على قائمة الشبكات اللي اتلقطت وشوف فيها شبكة بنفس اسم الواي "
            "فاي بتاعك او اسأل برودوس يلاقيها. "
            "لو لقيت واحدة، قول للموظفين يحذّروا الزباين منه."
        ),
        "unknown": (
            "حصل حاجة غريبة على شبكتك.",
            "السنسورات لقطت نشاط مش طبيعي, بس معرفناش السبب "
            "بالظبط، فعلّمنا عليه عشان يتراجع.",
            "مفيش حاجة لازم تعملها دلوقتي. لو الزباين بدأوا يلاقوا مشاكل في "
            "الاتصال، بص على قائمة التنبيهات او اسأل برودوس.",
        ),
    },
}

_UNKNOWN_FALLBACK = _TEXT["en"]["unknown"]

# Helpers

def _t(lang: str) -> dict:
    return _TEXT.get(lang, _TEXT["en"])


def _band(severity: int, lang: str = "en") -> str:
    t = _t(lang)
    if severity <= 3:
        return t["calm"]
    if severity <= 7:
        return t["serious"]
    return t["urgent"]


def _clean_ssid(value) -> str:
    """SSIDs are attacker-controlled. Drop control/bidi/zero-width characters
    (not printable) and cap at the 32-character SSID maximum."""
    if not isinstance(value, str):
        return ""
    return "".join(ch for ch in value if ch.isprintable()).strip()[:32]

# Builders

def _deauth(event: DetectionEvent, lang: str = "en") -> Explanation:
    t = _t(lang)
    count = event.details.get("count")
    lead = t["deauth_lead"].format(count=count) if isinstance(count, int) else ""
    return Explanation(
        title=t["deauth_title"],
        explanation=t["deauth_expl"].format(lead=lead, band=_band(event.severity, lang)),
        recommended_action=t["deauth_action"],
    )


def _evil_twin(event: DetectionEvent, lang: str = "en") -> Explanation:
    t = _t(lang)
    ssid = _clean_ssid(event.details.get("ssid"))
    which = t["twin_which"].format(ssid=ssid) if ssid else ""
    return Explanation(
        title=t["twin_title"],
        explanation=t["twin_expl"].format(which=which, band=_band(event.severity, lang)),
        recommended_action=t["twin_action"],
    )


def _rogue_ap(event: DetectionEvent, lang: str = "en") -> Explanation:
    t = _t(lang)
    high = event.severity >= 8
    return Explanation(
        title=t["rogue_title"],
        explanation=t["rogue_expl_high" if high else "rogue_expl_low"].format(
            band=_band(event.severity, lang)
        ),
        recommended_action=t["rogue_action_high" if high else "rogue_action_low"],
    )


def _unknown(lang: str = "en") -> Explanation:
    title, explanation, action = _t(lang)["unknown"]
    return Explanation(title=title, explanation=explanation, recommended_action=action)

_BUILDERS = {
    "deauth_flood": _deauth,
    "evil_twin": _evil_twin,
    "rogue_ap": _rogue_ap,
}


class TemplateProvider:
    """Offline provider. Always succeeds -- it is the safety net."""

    async def explain(self, event: DetectionEvent, language="end") -> Explanation:
        builder = _BUILDERS.get(event.event_type)
        return builder(event, language) if builder else _unknown(lang=language)