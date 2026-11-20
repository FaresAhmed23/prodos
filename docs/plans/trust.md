Prodos Trust — spec (F-21)

Status: spec ready — NOT STARTED. Owners: backend Fares (agent); public page is server-rendered HTML (no frontend dependency); owner-side QR card in the dashboard = Arsany later.

## 1. What it is

A public per-site trust page + QR code showing observed security posture. The customer scans, sees the café's Prodos band and freshness. The business earns visible trust; Prodos gains a public proof point.

## 2. Two hard rules

1. Observed posture, NEVER a safety promise. The page always shows the disclaimer: "This shows observed monitoring posture over the last 7 days, not a promise of safety."
2. Zero owner data beyond the whitelist. Allowed on the public page: business_name, band, score, last_checked, monitored-since (first snapshot date), and the disclaimer. Forbidden anywhere in the HTML: notes, router_model, primary_language, any owner contact, any sensor identifier.

## 3. Token model

Columns on site_profile (one alembic revision, nullable):

- trust_token str unique nullable — null = not enrolled.
- trust_token_created_at, trust_token_rotated_at (tz UTC, nullable).

Enroll: generate a 32-char urlsafe random token. Rotate: new token, old token immediately dead. Revoke: token set to null. Lookup miss or revoked token -> JSON 404 {"error": "verification unavailable"} — nothing about why.

## 4. Endpoints

Public (no auth — that is the point; LAN pilot):

- GET /trust/{token} — minimal server-rendered HTML page. Cache-Control: public, max-age=300.
- GET /trust/{token}/qr.png — QR of the public trust URL. segno (pure Python, approved). Content-Type image/png, same cache headers.

Owner-side (X-Admin-Key when ADMIN_API_KEY set):

- POST /sites/{site_id}/trust — enroll (or rotate if enrolled). Returns token.
- DELETE /sites/{site_id}/trust — revoke.

## 5. Forbidden-content tests (part of acceptance)

    Rendered HTML must NOT contain any of: "guaranteed", "risk-free","100% safe", "completely safe", "protected by Prodos". (The disclaimeritself is allowed — it negates.)
    Both forbidden checks run against the whitespace-collapsed, lower-casedtext of the rendered HTML (collapse every run of whitespace to one space),so template line-wrapping can never hide a phrase.
    Rendered HTML must NOT contain: the site's notes value, router_model value,or any sensor_id — seed distinctive values and assert absence.

(Your transmission ate the space in "100% safe"; normal spacing is the intent. The normalization rule makes the test robust regardless.)

## 6. Acceptance criteria

Token roundtrip (enroll -> public page 200 -> rotate -> old token 404, new 200 -> revoke -> 404). Forbidden-phrase and forbidden-field tests green. QR endpoint returns a PNG whose decoded content equals the trust URL. Cache headers present on both public routes. One migration; test_migrations updated; schemas.py untouched.

## 7. Out of scope (v3)

Verification tiers, certification programs, Ofcom-style schemes, subscriptions, rate limiting (cache headers only).
