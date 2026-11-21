Prodos ShieldScore — spec (F-19, F-20)

Status: spec ready — NOT STARTED. Owners: backend Fares (agent), checklist wording review Mohamed Ahmed, dashboard card Arsany.

## 1. What it is

A per-site security posture score, 0-100, computed once per day per site, with a band and a component breakdown the owner can act on.

## 2. Design law

The score measures the business's posture and practices, NOT how much it is attacked. A café under attack is not insecure; a café whose monitor is offline and whose alerts sit unacknowledged is. Threat exposure is capped at 10 points so a bad week dents, never dominates, the score.

## 3. Components (weights sum to 100)

| Component           | Weight | Formula                                                                                                                                                                       |
| ------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Monitoring coverage | 30     | (10-minute buckets in window with >=1 frame from an assigned sensor) / (total buckets). 7d window = 1008 buckets. No sensors assigned -> 0, flag no_sensors_assigned.         |
| Alert response      | 30     | alerts attributed to the site in window: acked_within_24h / total; total==0 -> 1.0. Any alert unacked >72h caps this component at 0.5.                                        |
| Network hygiene     | 15     | distinct BSSIDs seen by the site's assigned sensors broadcasting any of site.wifi_ssids in window; allowed = those in known_access_points; allowed/total. total==0 -> 0, flag ssids_not_configured.          |
| Practices checklist | 15     | yes_count / 8. Unanswered counts as 0 (displayed "not answered").                                                                                                             |
| Threat exposure     | 10     | 10 \* (1 - min(1, severity_weighted / EXPOSURE_CAP_WEIGHT)). severity_weighted = sum of event severities attributed to the site in window; EXPOSURE_CAP_WEIGHT = 40 (config). |

Bands: 0-59 needs attention, 60-79 fair, 80-100 good.

## 4. Decisions (already made — do not reopen)

- Window: 7 days rolling, matching RETENTION_DAYS=7. One snapshot per site per day; a second compute the same day REPLACES that day's snapshot.
- Attribution at scoring time: event.sensor_ids -> Sensor.site_id. Events with no site are excluded from every component and counted in details.siteless_events_excluded. Never silently dropped.
- Sensor-site assignment is REST-only (see endpoints). schemas.py is NOT edited. No CONTRACT CHANGE.
- All owner-side endpoints: optional X-Admin-Key header checked against env ADMIN_API_KEY; startup warning if unset. No user system.
- Every new column nullable or server_default. A score must never fail because of a metadata field.
- All weights, thresholds, bands, window, bucket size, cap: one config module (backend/app/scoring/config.py). Nothing magic inline.

## 5. Data model

- score_snapshots: id PK, site_id FK -> site_profile, computed_at (tz UTC), score int, band str, components JSON, details JSON, window_days int. Index (site_id, computed_at).
- checklist_answers: site_id PK FK, answers JSON {question_key: bool|null}, updated_at. Upsert on PUT.
- Reuse SiteProfile (models.py:113) — do not duplicate it.

## 6. API surface (owner-side, X-Admin-Key when ADMIN_API_KEY set)

- POST /sites, GET /sites, GET /sites/{site_id}, PATCH /sites/{site_id}
- PATCH /sites/{site_id}/sensors/{sensor_id} — assign (sets Sensor.site_id); DELETE /sites/{site_id}/sensors/{sensor_id} — unassign (sets null). 404 if sensor or site unknown.
- PUT /sites/{site_id}/checklist body {"answers": {key: true|false|null}}; unknown key -> 422 with the valid keys listed.
- GET /sites/{site_id}/score — latest snapshot (404 "no snapshot yet" if none). GET /sites/{site_id}/score/history?limit=30 — oldest->newest.

## 7. Background job

Daily asyncio task next to retention in main.py lifespan: for each site, compute and upsert the day's snapshot. Idempotent.

## 8. Checklist questions (fixed keys, English; ar translations = Mohamed Ahmed)

Key Question (owner-readable)
router_admin_password_changed Router admin password changed from the factory default
wpa2_or_wpa3 Network encryption is WPA2 or WPA3 (not WEP, not open)
guest_network_separate Customers use a separate guest network, apart from business devices
firmware_updated_12m Router firmware updated in the last 12 months
password_rotated_6m WiFi password changed in the last 6 months
router_physically_secured Router sits in a protected spot, not publicly reachable
no_unmanaged_extenders All extenders, repeaters, or extra routers were set up by staff or a trusted technician
staff_share_password_in_person_only Staff share the WiFi password in person only (never posted or sent in chat)

Human-readable wording lives in the config module, not in the DB.

## 9. Acceptance criteria

F-19 (foundation): sites CRUD roundtrip; assign/unassign moves Sensor.site_id; checklist PUT validates keys and persists; new tables + migration (ONE alembic revision, never edit existing ones); test_migrations TABLES updated; schemas.py byte-untouched; admin key enforced when set, warning when unset.

F-20 (engine): golden test — seed frames/alerts/checklist for a fake site, assert each component value and the total; unacked->capped response; siteless events excluded and counted; snapshot job produces exactly one row per site per day, second run replaces; /score + /score/history correct.

## 10. Out of scope (v3)

PDF reports, insurance/partner exports, per-component history charts, anything multi-tenant.
