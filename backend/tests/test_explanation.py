"""The explanation layer: provider selection, the LLM path, and the fallback.

The fallback tests are the important ones. "An unreachable model must not cost
the owner an alert" is a project rule, and it is the kind of rule that rots
silently the first time someone refactors the try/except.
"""

import asyncio
import uuid

import pytest

from app.ai.llm_provider import LLMProvider, _extract
from app.ai.template_provider import TemplateProvider
from app.config import settings
from app.models import Alert, ExplanationLog
from app.schemas import DetectionEvent


def make_event(**over):
    from datetime import datetime, timedelta, timezone

    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "deauth_flood",
        "detected_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        "severity": 8,
        "confidence": 0.95,
        "sensor_ids": ["sensor-1"],
        "details": {"src_mac": "AA:BB:CC:DD:EE:FF", "count": 63},
    }
    payload.update(over)
    return DetectionEvent(**payload)


# --- provider selection: the key is the only switch ------------------------


def test_no_key_selects_the_offline_template(monkeypatch):
    from app.alerts import build_provider

    monkeypatch.setattr(settings, "llm_api_key", None)
    assert isinstance(build_provider(), TemplateProvider)


def test_key_with_base_and_model_selects_the_llm(monkeypatch):
    from app.alerts import build_provider

    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_api_base", "http://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "some-model")
    assert isinstance(build_provider(), LLMProvider)


def test_key_without_a_model_stays_on_the_template(monkeypatch):
    """Half-configured must not become a call to something undefined."""
    from app.alerts import build_provider

    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_api_base", None)
    monkeypatch.setattr(settings, "llm_model", None)
    assert isinstance(build_provider(), TemplateProvider)


def test_timeout_is_configurable(monkeypatch):
    from app.alerts import build_provider

    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_api_base", "http://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr(settings, "llm_timeout", 1.25)
    assert build_provider()._timeout == 1.25


# --- the LLM path, against a real loopback chat-completions server ----------


def test_llm_output_is_returned(stub_llm):
    provider = LLMProvider(base=stub_llm["base"], model="stub-model", api_key="sk-test")
    result = asyncio.run(provider.explain(make_event()))
    assert (result.title, result.explanation, result.recommended_action) == (
        "STUB TITLE", "STUB BODY.", "STUB ACTION.",
    )


def test_llm_request_carries_key_and_system_prompt(stub_llm):
    provider = LLMProvider(base=stub_llm["base"], model="stub-model", api_key="sk-test")
    asyncio.run(provider.explain(make_event()))
    sent = stub_llm["received"][0]
    assert sent["auth"] == "Bearer sk-test"
    assert sent["body"]["model"] == "stub-model"
    assert sent["body"]["messages"][0]["role"] == "system"
    assert "recommended_action" in sent["body"]["messages"][0]["content"]


def test_prompt_is_captured_for_the_log(stub_llm):
    provider = LLMProvider(base=stub_llm["base"], model="stub-model", api_key="sk-test")
    event = make_event()
    assert provider.build_prompt(event) == provider.build_prompt(event)
    assert "deauth_flood" in provider.build_prompt(event)


# --- reply parsing: a model that misbehaves must not corrupt an alert -------


def test_extract_handles_fenced_json():
    import json

    body = json.dumps({"title": "t", "explanation": "e", "recommended_action": "r"})
    assert _extract(f"```json\n{body}\n```").title == "t"


def test_extract_handles_chatty_prose_around_json():
    assert _extract('Sure! Here you go:\n{"title":"t","explanation":"e","recommended_action":"r"}').title == "t"


def test_extract_rejects_a_reply_with_no_json():
    with pytest.raises(ValueError):
        _extract("I'm sorry, I can't help with that.")


def test_extract_rejects_json_missing_a_field():
    with pytest.raises(ValueError):
        _extract('{"title":"t","explanation":"e"}')


# --- the fallback: the rule that matters -----------------------------------


def test_unreachable_llm_still_delivers_an_alert(alerts_on_test_db, session, monkeypatch, stub_llm):
    """A dead endpoint must cost tone, not the alert."""
    alerts = alerts_on_test_db
    monkeypatch.setattr(
        alerts, "provider",
        LLMProvider(base="http://127.0.0.1:1/v1", model="m", api_key="k", timeout=0.5),
    )
    alert = asyncio.run(alerts.handle_detection_event(make_event()))
    assert alert is not None
    assert alert.title == "Someone is trying to knock customers off your WiFi"
    assert alert.explanation


def test_fallback_is_logged_as_the_template(alerts_on_test_db, session, monkeypatch):
    alerts = alerts_on_test_db
    monkeypatch.setattr(
        alerts, "provider",
        LLMProvider(base="http://127.0.0.1:1/v1", model="m", api_key="k", timeout=0.5),
    )
    asyncio.run(alerts.handle_detection_event(make_event()))
    rows = session.query(ExplanationLog).all()
    assert [r.provider_used for r in rows] == ["template"]
    assert rows[0].prompt is None, "a fallback explanation has no LLM prompt to record"


def test_successful_llm_call_is_logged_as_llm_with_its_prompt(alerts_on_test_db, session, monkeypatch, stub_llm):
    alerts = alerts_on_test_db
    monkeypatch.setattr(
        alerts, "provider",
        LLMProvider(base=stub_llm["base"], model="stub-model", api_key="k"),
    )
    asyncio.run(alerts.handle_detection_event(make_event()))
    row = session.query(ExplanationLog).one()
    assert row.provider_used == "llm"
    assert row.prompt, "an LLM explanation must record the prompt it was given"
    assert row.output["title"] == "STUB TITLE"


def test_malformed_llm_reply_falls_back(alerts_on_test_db, monkeypatch):
    """A model that returns prose instead of JSON must not reach the dashboard."""
    alerts = alerts_on_test_db

    class Babbling(LLMProvider):
        async def explain(self, event):
            from app.ai.explanation import Explanation

            raise ValueError("no JSON object in reply")

    monkeypatch.setattr(alerts, "provider", Babbling(base="http://x/v1", model="m", api_key="k"))
    alert = asyncio.run(alerts.handle_detection_event(make_event()))
    assert alert.title.startswith("Someone is trying")


# --- the fine-tuning dataset ----------------------------------------------


def test_one_log_row_per_alert(alerts_on_test_db, session):
    asyncio.run(alerts_on_test_db.handle_detection_event(make_event()))
    asyncio.run(alerts_on_test_db.handle_detection_event(make_event(event_type="evil_twin")))
    assert session.query(ExplanationLog).count() == 2
    assert session.query(Alert).count() == 2


def test_replayed_event_makes_no_second_log_row(alerts_on_test_db, session):
    """MQTT is at-least-once; the dataset must not inherit the duplicate."""
    event = make_event()
    first = asyncio.run(alerts_on_test_db.handle_detection_event(event))
    second = asyncio.run(alerts_on_test_db.handle_detection_event(event))
    assert first is not None and second is None
    assert session.query(Alert).count() == 1
    assert session.query(ExplanationLog).count() == 1


def test_log_row_keeps_the_event_and_output(alerts_on_test_db, session):
    asyncio.run(alerts_on_test_db.handle_detection_event(make_event(severity=9)))
    row = session.query(ExplanationLog).one()
    assert row.event["event_type"] == "deauth_flood"
    assert isinstance(row.event["detected_at"], str), "datetimes must be JSON-safe"
    assert set(row.output) == {"title", "explanation", "recommended_action"}


# --- the offline floor is the floor ----------------------------------------


JARGON = ("deauth", "bssid", "802.11", "packet", "ssid", "beacon", "probe")


@pytest.mark.parametrize(
    "event_type,severity", [("deauth_flood", 8), ("evil_twin", 9), ("rogue_ap", 5)]
)
def test_template_explanations_are_jargon_free(event_type, severity):
    result = asyncio.run(TemplateProvider().explain(make_event(event_type=event_type, severity=severity)))
    blob = f"{result.title} {result.explanation} {result.recommended_action}".lower()
    assert not [w for w in JARGON if w in blob]


@pytest.mark.parametrize("event_type", ["deauth_flood", "evil_twin", "rogue_ap"])
def test_template_explanations_respect_the_sentence_ceiling(event_type):
    """The LLM prompt caps at 3 sentences; the floor must not exceed it, or the
    owner can tell which provider wrote an alert from its length alone."""
    result = asyncio.run(TemplateProvider().explain(make_event(event_type=event_type)))
    sentences = [s for s in result.explanation.replace("!", ".").split(".") if s.strip()]
    assert len(sentences) <= 3


def test_template_severity_tone_escalates():
    calm = asyncio.run(TemplateProvider().explain(make_event(severity=2)))
    urgent = asyncio.run(TemplateProvider().explain(make_event(severity=9)))
    assert calm.explanation != urgent.explanation


def test_template_always_has_an_action():
    # "anomaly" is a real EventType with no dedicated builder, so it is the path
    # that reaches the template's unknown-type fallback.
    for event_type in ("deauth_flood", "evil_twin", "rogue_ap", "anomaly"):
        result = asyncio.run(TemplateProvider().explain(make_event(event_type=event_type)))
        assert result.recommended_action.strip()


def test_template_handles_an_unknown_event_type():
    result = asyncio.run(TemplateProvider().explain(make_event(event_type="anomaly")))
    assert result.title and result.explanation and result.recommended_action
