import pytest

from detectors.evil_twin import (
    AccessPoint, EvilTwinDetector, Severity, load_known_networks,
)


@pytest.fixture
def detector():
    return EvilTwinDetector.from_config()  # uses the path of known_aps.json


def ap(**kw):
    base = dict(ssid="Kota", bssid="aa:bb:cc:dd:ee:01", channel=6, security="WPA2")
    base.update(kw)
    return AccessPoint.from_dict(base)


def rules(alerts):
    return {a.rule for a in alerts}


def test_config_loads():
    nets = load_known_networks()
    assert {n.ssid for n in nets} >= {"Kota", "BigKota123"}


def test_legitimate_ap_raises_no_alerts(detector):
    assert detector.analyze([ap()]) == []


def test_unrelated_network_ignored(detector):
    assert detector.analyze([ap(ssid="NotKota", bssid="11:22:33:44:55:66")]) == []


def test_unknown_bssid_flagged(detector):
    alerts = detector.analyze([ap(bssid="de:ad:be:ef:00:01")])
    assert rules(alerts) == {"unknown_bssid"}
    assert alerts[0].severity == Severity.HIGH


def test_bssid_comparison_is_case_insensitive(detector):
    assert detector.analyze([ap(bssid="AA:BB:CC:DD:EE:01")]) == []


def test_security_downgrade_flagged(detector):
    alerts = detector.analyze([ap(security="OPEN")])
    assert "security_downgrade" in rules(alerts)


def test_twin_with_open_security_reports_both(detector):
    alerts = detector.analyze([ap(bssid="de:ad:be:ef:00:01", security="OPEN")])
    assert rules(alerts) == {"unknown_bssid", "security_downgrade"}


def test_unexpected_channel_flagged(detector):
    alerts = detector.analyze([ap(channel=13)])
    assert rules(alerts) == {"unexpected_channel"}
    assert alerts[0].severity == Severity.MEDIUM


@pytest.mark.parametrize("fake", ["Kosa", "BigKosa123", "Cota "])
def test_lookalike_ssid_flagged(detector, fake):
    alerts = detector.analyze([ap(ssid=fake, bssid="de:ad:be:ef:00:01")])
    assert rules(alerts) == {"lookalike_ssid"}


def test_hidden_ssid_skipped(detector):
    assert detector.analyze([ap(ssid="", bssid="de:ad:be:ef:00:01")]) == []


def test_alerts_sorted_by_severity(detector):
    scan = [ap(channel=13), ap(bssid="de:ad:be:ef:00:01")]
    sevs = [a.severity for a in detector.analyze(scan)]
    assert sevs == sorted(sevs, reverse=True)
