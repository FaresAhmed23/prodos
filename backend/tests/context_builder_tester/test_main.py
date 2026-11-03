from __future__ import annotations

from tests.context_builder_tester.seed_db import set_up_database

import uuid
from datetime import datetime, timezone

from tests.context_builder_tester.init_db import make_database, make_engine

from app.schemas import DetectionEvent
from app.ai.Context_builder import ContextBuilder

builder = ContextBuilder(db=make_database(make_engine()))

#set up the database for testing
set_up_database()

builder = ContextBuilder(db=make_database(make_engine()))


def ev(event_type, sensors, severity, details):
    return DetectionEvent(
        event_id=f"test-{uuid.uuid4().hex[:8]}", event_type=event_type,
        detected_at=datetime.now(timezone.utc), severity=severity,
        confidence=0.9, sensor_ids=sensors, details=details)


def show(name, expect, ctx):
    print(f"\n== {name}\n   expect: {expect}")
    print(f"   site={ctx.site_id} lang={ctx.lang} new_incident={ctx.is_new_incident} "
          f"count={ctx.current.event_count}")
    print(f"   reuse={ctx.explained_alert.alert_id if ctx.explained_alert else None} "
          f"related={[r.incident_id for r in ctx.related]} warnings={ctx.warnings}")


twin = {"ssid": "NileCorner_WiFi", "known_bssid": "A4:2B:B0:11:22:33",
        "rogue_bssid": "66:77:88:99:AA:BB"}

show("1. cafe evil twin continues",
     "attach, count 4, reuse=alr-cafe-05",
     builder.build(ev("evil_twin", ["cafe-s1"], 9, twin)))

show("2. hotel flood, lowercase MAC",
     "attach, count 6, reuse=None (5 events since explained), related has inc-hotel-twin-old",
     builder.build(ev("deauth_flood", ["hotel-s1"], 7,
                      {"src_mac": "c0:ff:ee:12:34:56", "rate_per_sec": 75, "window_s": 30})))

show("3. clinic rogue AP escalates to severity 8",
     "attach, lang=ar, reuse=None (severity band escalation)",
     builder.build(ev("rogue_ap", ["clinic-s2"], 8,
                      {"bssid": "3C:84:6A:5D:10:E2", "ssid": "DIRECT-Printer-1F"})))

show("4. clinic rogue AP, English requested",
     "reuse=None (language mismatch)",
     builder.build(ev("rogue_ap", ["clinic-s2"], 3,
                      {"bssid": "3C:84:6A:5D:10:E2", "ssid": "DIRECT-Printer-1F"}), lang="en"))

show("5. cafe old attacker returns",
     "NEW incident (gap exceeded), related has inc-cafe-deauth-old",
     builder.build(ev("deauth_flood", ["cafe-s1"], 6,
                      {"src_mac": "DE:AD:BE:EF:00:01", "rate_per_sec": 40, "window_s": 30})))

show("6. unknown sensor",
     "site=default, warnings sensor_without_site + business_not_found",
     builder.build(ev("anomaly", ["ghost-s9"], 2, {})))