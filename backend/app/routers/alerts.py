from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert as AlertModel
from ..schemas import Alert, AlertStatus, AlertUpdate

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[Alert])
def list_alerts(
    limit: int = Query(50, ge=1, le=500),
    status: AlertStatus | None = None,
    db: Session = Depends(get_db),
) -> list[AlertModel]:
    stmt = select(AlertModel)
    if status is not None:
        stmt = stmt.where(AlertModel.status == status)
    stmt = stmt.order_by(AlertModel.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


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