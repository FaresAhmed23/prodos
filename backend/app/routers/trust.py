"""F-21 public trust page and QR (spec `docs/plans/trust.md`).

No auth: the token in the URL is the capability. The page is server-rendered
HTML so this needs no frontend, and it reads only the whitelisted values —
business name, band, score, last checked, monitored since, disclaimer. Any
other owner column or sensor id must never reach this module.
"""

import html
import io
from datetime import datetime, timezone

import segno
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ScoreSnapshot, SiteProfile

router = APIRouter(prefix="/trust", tags=["trust"])

DISCLAIMER = (
    "This shows observed monitoring posture over the last 7 days, "
    "not a promise of safety."
)
CACHE_HEADERS = {"Cache-Control": "public, max-age=300"}


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; stored values are always UTC (same as scoring)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _not_found() -> JSONResponse:
    """Lookup miss and revoked token are indistinguishable on purpose (§3)."""
    return JSONResponse(
        {"error": "verification unavailable"}, status_code=status.HTTP_404_NOT_FOUND
    )


def _site_by_token(db: Session, token: str) -> SiteProfile | None:
    return db.execute(
        select(SiteProfile).where(SiteProfile.trust_token == token)
    ).scalars().first()


def _latest_snapshot(db: Session, site_id: str) -> ScoreSnapshot | None:
    return db.execute(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.site_id == site_id)
        .order_by(ScoreSnapshot.computed_at.desc(), ScoreSnapshot.id.desc())
        .limit(1)
    ).scalars().first()


def _first_monitored_at(db: Session, site_id: str) -> datetime | None:
    return db.execute(
        select(ScoreSnapshot.computed_at)
        .where(ScoreSnapshot.site_id == site_id)
        .order_by(ScoreSnapshot.computed_at.asc(), ScoreSnapshot.id.asc())
        .limit(1)
    ).scalars().first()


def _render(site: SiteProfile, snapshot: ScoreSnapshot | None, since: datetime | None) -> str:
    business = html.escape(site.business_name or "This business")
    if snapshot is None:
        posture = "<p>Monitoring has not started yet.</p>"
    else:
        band = html.escape(str(snapshot.band))
        last_checked = _as_utc(snapshot.computed_at).strftime("%Y-%m-%d %H:%M UTC")
        posture = (
            f"<p>Observed posture: <strong>{band}</strong> "
            f"({snapshot.score} / 100)</p>"
            f"<p>Last checked: {last_checked}</p>"
        )
    monitored = (
        f"<p>Monitored since: {_as_utc(since).strftime('%Y-%m-%d')}</p>"
        if since is not None
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{business} · Prodos</title>
</head>
<body>
<main>
<h1>{business}</h1>
{posture}{monitored}<p>{DISCLAIMER}</p>
</main>
</body>
</html>"""


@router.get("/{token}", response_class=HTMLResponse, name="trust_page")
def trust_page(
    token: str, db: Session = Depends(get_db)
) -> Response:
    site = _site_by_token(db, token)
    if site is None:
        return _not_found()
    page = _render(
        site,
        _latest_snapshot(db, site.site_id),
        _first_monitored_at(db, site.site_id),
    )
    return HTMLResponse(page, headers=CACHE_HEADERS)


@router.get("/{token}/qr.png", name="trust_qr")
def trust_qr(
    token: str, request: Request, db: Session = Depends(get_db)
) -> Response:
    site = _site_by_token(db, token)
    if site is None:
        return _not_found()
    url = str(request.url_for("trust_page", token=token))
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="png", scale=6, border=2)
    return Response(buffer.getvalue(), media_type="image/png", headers=CACHE_HEADERS)
