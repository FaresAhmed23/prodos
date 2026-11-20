"""ShieldScore constants and checklist wording.

Spec: docs/plans/shieldscore.md §3, §4, §8. Every number and every
owner-readable question lives here so F-20 computes with nothing inline.
"""

WINDOW_DAYS = 7
BUCKET_SECONDS = 600
BUCKETS_PER_WINDOW = WINDOW_DAYS * 24 * 60 * 60 // BUCKET_SECONDS  # 1008

WEIGHTS = {
    "monitoring_coverage": 30,
    "alert_response": 30,
    "network_hygiene": 15,
    "practices_checklist": 15,
    "threat_exposure": 10,
}

BANDS = (
    (0, 59, "needs attention"),
    (60, 79, "fair"),
    (80, 100, "good"),
)

RESPONSE_WINDOW_HOURS = 24
UNACKED_CAP_AFTER_HOURS = 72
UNACKED_CAP_RATIO = 0.5
EXPOSURE_CAP_WEIGHT = 40

# §8 fixed keys. The Arabic wording belongs to Mohamed Ahmed: add an "ar"
# value beside each "en" one when supplied. Nothing here is stored in the DB.
CHECKLIST_QUESTIONS = {
    "router_admin_password_changed": {
        "en": "Router admin password changed from the factory default"
    },
    "wpa2_or_wpa3": {
        "en": "Network encryption is WPA2 or WPA3 (not WEP, not open)"
    },
    "guest_network_separate": {
        "en": "Customers use a separate guest network, apart from business devices"
    },
    "firmware_updated_12m": {
        "en": "Router firmware updated in the last 12 months"
    },
    "password_rotated_6m": {
        "en": "WiFi password changed in the last 6 months"
    },
    "router_physically_secured": {
        "en": "Router sits in a protected spot, not publicly reachable"
    },
    "no_unmanaged_extenders": {
        "en": "All extenders, repeaters, or extra routers were set up by staff "
              "or a trusted technician"
    },
    "staff_share_password_in_person_only": {
        "en": "Staff share the WiFi password in person only (never posted or "
              "sent in chat)"
    },
}
