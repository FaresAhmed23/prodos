from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert as AlertModel
from ..models import utcnow
from ..pagination import InvalidCursor, paginate
from ..schemas import Alert, AlertStatus, AlertUpdate

router = APIRouter(tags=["alerts"])

# Severity bands match the phrasing bands in ai/template_provider.py, so a card
# saying "high" and an alert that reads urgent are the same judgement.
_BANDS = (("low", 1, 3), ("medium", 4, 7), ("high", 8, 10))


class AlertStats(BaseModel):
    """Dashboard summary. Deliberately not in schemas.py: it is a REST-only
    convenience, not the team-wide MQTT/Alert contract in §5."""

    window_hours: int
    total: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    newest_alert_at: datetime | None


@router.get("/alerts/stats", response_model=AlertStats)
def alert_stats(
    window_hours: int = Query(24, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
) -> AlertStats:
    cutoff = utcnow() - timedelta(hours=window_hours)

    by_status = {
        row[0]: row[1]
        for row in db.execute(
            select(AlertModel.status, func.count())
            .where(AlertModel.created_at >= cutoff)
            .group_by(AlertModel.status)
        )
    }
    # Always report all three bands so a card can render an empty state without
    # special-casing a missing key.
    by_severity = {name: 0 for name, _, _ in _BANDS}
    for name, low, high in _BANDS:
        by_severity[name] = db.scalar(
            select(func.count())
            .select_from(AlertModel)
            .where(AlertModel.created_at >= cutoff, AlertModel.severity.between(low, high))
        ) or 0

    newest = db.scalar(
        select(func.max(AlertModel.created_at)).where(AlertModel.created_at >= cutoff)
    )

    return AlertStats(
        window_hours=window_hours,
        total=sum(by_status.values()),
        by_status=by_status,
        by_severity=by_severity,
        newest_alert_at=newest,
    )


@router.get("/alerts", response_model=list[Alert])
def list_alerts(
    response: Response,
    limit: int = Query(50, ge=1, le=500),
    status: AlertStatus | None = None,
    cursor: str | None = Query(
        None, description="alert_id of the last alert you saw; omit for the newest page"
    ),
    db: Session = Depends(get_db),
) -> list[AlertModel]:
    stmt = select(AlertModel)
    if status is not None:
        stmt = stmt.where(AlertModel.status == status)
    try:
        rows, has_more, next_cursor = paginate(
            db, stmt, AlertModel, AlertModel.created_at, AlertModel.alert_id,
            cursor_id=cursor, limit=limit,
        )
    except InvalidCursor:
        raise HTTPException(status_code=400, detail="unknown cursor")
    response.headers["X-Has-More"] = str(has_more).lower()
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return rows


@router.patch("/alerts/{alert_id}", response_model=Alert)
def update_alert(
    alert_id: str,
    body: AlertUpdate,
    db: Session = Depends(get_db),
) -> AlertModel:
    alert = db.get(AlertModel, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = body.status
    db.commit()
    db.refresh(alert)
    return alert