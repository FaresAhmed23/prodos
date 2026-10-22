"""
Sample AI replies for testing the checker package:
    check_alert, check_explanation, retry_feedback

10 events, 10 raw model replies: 3 should pass, 7 should fail for different reasons.
This file is pure data (no imports from the checker), so you decide how to use it.

Each case is a dict:
    id             short name
    event          fields of the detection event (adapt to your DetectionEvent)
    evidence       the facts the reply is allowed to quote (what the context
                   builder would pass as `evidence=`); same shape as
                   evidence_from_event(): event_type, severity, sensor_ids, details
    lang           "en" or "ar"  (what the user should receive)
    must_mention   strings the reply must contain (passed as `must_mention=`)
    reply          the RAW string the model returned (what check_alert receives)
    expected_ok    True / False
    expected_rules set of Failure.rule values you should see (empty if it passes)
    note           why it passes / fails

Failure rule names produced by the checker:
    json, fields, length, "sentences length", format, language, complexity,
    jargon, grounding, mention, safety
"""

import json


def _reply(title: str, explanation: str, action: str) -> str:
    """Build a well-formed JSON reply string (escaping handled for you)."""
    return json.dumps(
        {"title": title, "explanation": explanation, "recommended_action": action},
        ensure_ascii=False,
    )


def _event(event_type: str, severity, sensor_ids: list, details: dict) -> dict:
    return {
        "event_type": event_type,
        "severity": severity,
        "sensor_ids": sensor_ids,
        "details": details,
    }


CASES: list[dict] = []


def _add(id, event, lang, reply, expected_ok, expected_rules, note, must_mention=()):
    CASES.append({
        "id": id,
        "event": event,
        "evidence": dict(event),          # same facts, as the context builder would pass
        "lang": lang,
        "must_mention": list(must_mention),
        "reply": reply,
        "expected_ok": expected_ok,
        "expected_rules": set(expected_rules),
        "note": note,
    })


# ---------------------------------------------------------------------------
# 1. PASS: clean English evil-twin alert
# ---------------------------------------------------------------------------
_add(
    id="01_evil_twin_pass",
    event=_event("evil_twin", "high", ["sensor-1"], {
        "ssid": "CafeWiFi",
        "rogue_mac": "AA:BB:CC:00:11:22",
        "legit_mac": "DD:EE:FF:33:44:55",
    }),
    lang="en",
    must_mention=["CafeWiFi"],
    reply=_reply(
        "A fake copy of your WiFi is nearby",
        "Another device is sending out a WiFi network called \"CafeWiFi\", the same name as yours. "
        "Customers could connect to it by mistake, and a stranger could then see what they do online.",
        "Check that your router is working normally. "
        "Ask staff to tell customers the exact name of your WiFi.",
    ),
    expected_ok=True,
    expected_rules=[],
    note="Plain words, 2 + 2 sentences, quoted name and required mention are in the data.",
)

# ---------------------------------------------------------------------------
# 2. PASS: deauth flood, reply wrapped in a ```json fence, number is grounded
# ---------------------------------------------------------------------------
_add(
    id="02_deauth_flood_pass_fenced",
    event=_event("deauth_flood", "medium", ["sensor-2"], {
        "deauth_count": 214,
        "window_seconds": 60,
    }),
    lang="en",
    reply="```json\n" + _reply(
        "Someone is kicking customers off your WiFi",
        "Something nearby sent 214 disconnect commands to your customers in one minute. "
        "Their phones may keep dropping off your WiFi. "
        "This is often done to push people onto a fake network.",
        "Ask staff whether customers are losing their connection. "
        "Write down the time so you can tell us if it happens again.",
    ) + "\n```",
    expected_ok=True,
    expected_rules=[],
    note="Tests fence stripping; 214 appears in the evidence; 3 + 2 sentences.",
)

# ---------------------------------------------------------------------------
# 3. PASS: Arabic deauth alert
# ---------------------------------------------------------------------------
_add(
    id="03_deauth_arabic_pass",
    event=_event("deauth_flood", "medium", ["sensor-1"], {"deauth_count": 180, "window_seconds": 60}),
    lang="ar",
    reply=_reply(
        "شخص ما يحاول فصل عملائك عن شبكتك",
        "جهاز قريب من المدخل يرسل أوامر متكررة لفصل العملاء عن شبكتك. "
        "قد يحدث هذا لإجبار الناس على الاتصال بنسخة مزيفة من شبكتك.",
        "اسأل موظفيك إن كان العملاء يشتكون من انقطاع الاتصال.",
    ),
    expected_ok=True,
    expected_rules=[],
    note="Arabic text, Arabic complexity dictionary stays under the limit.",
)

# ---------------------------------------------------------------------------
# 4. FAIL json: the model answered in prose, not JSON
# ---------------------------------------------------------------------------
_add(
    id="04_not_json",
    event=_event("evil_twin", "high", ["sensor-1"], {"ssid": "CafeWiFi", "rogue_mac": "AA:BB:CC:00:11:22"}),
    lang="en",
    reply="Sure! Here is your alert: someone is copying your WiFi, so please be careful and ask your staff to check.",
    expected_ok=False,
    expected_rules=["json"],
    note="No JSON object anywhere in the reply; nothing else can be checked, explanation is None.",
)

# ---------------------------------------------------------------------------
# 5. FAIL fields: fenced JSON, missing recommended_action + an unexpected key
# ---------------------------------------------------------------------------
_add(
    id="05_missing_and_extra_fields",
    event=_event("deauth_flood", "low", ["sensor-3"], {"deauth_count": 95, "window_seconds": 60}),
    lang="en",
    reply="```json\n" + json.dumps({
        "title": "Customers are being disconnected",
        "explanation": "Something nearby is cutting customers off your WiFi again and again.",
        "severity": "low",
    }) + "\n```",
    expected_ok=False,
    expected_rules=["fields"],
    note="'recommended_action' missing and key 'severity' not allowed: two 'fields' failures.",
)

# ---------------------------------------------------------------------------
# 6. FAIL jargon + complexity: technical terms a shop owner can't understand
# ---------------------------------------------------------------------------
_add(
    id="06_technical_jargon",
    event=_event("deauth_flood", "high", ["sensor-1"], {"deauth_count": 540, "window_seconds": 60, "bssid": "DD:EE:FF:33:44:55"}),
    lang="en",
    reply=_reply(
        "Deauthentication frames detected",
        "Forged deauthentication frames from an unknown BSSID are knocking clients off your SSID.",
        "Ask staff to tell customers to reconnect.",
    ),
    expected_ok=False,
    expected_rules=["jargon", "complexity"],
    note="deauth, deauthentication, bssid, ssid, frame all banned; complexity rating far above 0.25.",
)

# ---------------------------------------------------------------------------
# 7. FAIL grounding: invented MAC, invented number, invented network name
# ---------------------------------------------------------------------------
_add(
    id="07_invented_facts",
    event=_event("evil_twin", "high", ["sensor-1"], {
        "ssid": "CafeWiFi",
        "rogue_mac": "AA:BB:CC:00:11:22",
    }),
    lang="en",
    reply=_reply(
        "A fake copy of your WiFi is nearby",
        "A device with the address AA:BB:CC:11:22:33 is copying your WiFi name \"GuestNet\" "
        "and 37 customers may be affected.",
        "Ask staff to tell customers the exact name of your WiFi.",
    ),
    expected_ok=False,
    expected_rules=["grounding"],
    note="MAC, quoted name and number are not in the evidence: three 'grounding' failures.",
)

# ---------------------------------------------------------------------------
# 8. FAIL language: user needs Arabic, the model answered in English
# ---------------------------------------------------------------------------
_add(
    id="08_wrong_language",
    event=_event("evil_twin", "high", ["sensor-2"], {"ssid": "ClinicGuest", "rogue_mac": "AA:BB:CC:44:55:66"}),
    lang="ar",
    reply=_reply(
        "A fake copy of your WiFi is nearby",
        "Another device is sending out a WiFi network with the same name as yours. "
        "Patients could connect to it by mistake.",
        "Ask staff to tell patients the exact name of your WiFi.",
    ),
    expected_ok=False,
    expected_rules=["language"],
    note="Checked with lang='ar': 0% Arabic letters. Everything else is clean.",
)

# ---------------------------------------------------------------------------
# 9. FAIL shape: title too long, 5-sentence explanation, bulleted action
# ---------------------------------------------------------------------------
_add(
    id="09_bad_shape",
    event=_event("deauth_flood", "high", ["sensor-1"], {"deauth_count": 300, "window_seconds": 60}),
    lang="en",
    reply=_reply(
        "Important security warning: someone near your shop seems to be disconnecting your customers from your WiFi on purpose",
        "Something nearby is cutting customers off. It started a short while ago. "
        "It keeps repeating. Customers will notice slow WiFi. They may complain to your staff.",
        "- Call your IT person\n- Change the WiFi password",
    ),
    expected_ok=False,
    expected_rules=["length", "sentences length", "format"],
    note="title > 90 chars, explanation has 5 sentences (max 3), action is a bullet list.",
)

# ---------------------------------------------------------------------------
# 10. FAIL safety + mention: harmful advice and the required name is missing
# ---------------------------------------------------------------------------
_add(
    id="10_unsafe_advice_missing_mention",
    event=_event("evil_twin", "high", ["sensor-1"], {
        "ssid": "CafeWiFi",
        "rogue_mac": "AA:BB:CC:00:11:22",
    }),
    lang="en",
    must_mention=["CafeWiFi"],
    reply=_reply(
        "A fake copy of your WiFi is nearby",
        "Another device is sending out a WiFi network with the same name as yours. "
        "Customers could connect to it by mistake.",
        "Find the device and jam its signal, or attack it back to teach them a lesson.",
    ),
    expected_ok=False,
    expected_rules=["safety", "mention"],
    note="Advice to jam/attack is rejected, and the required name 'CafeWiFi' is never mentioned.",
)


if __name__ == "__main__":
    for c in CASES:
        print(f"{c['id']:<38} lang={c['lang']}  expected_ok={c['expected_ok']}  rules={sorted(c['expected_rules'])}")