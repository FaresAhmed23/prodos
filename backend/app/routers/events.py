from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Event
from ..schemas import EventOut, EventType

router = APIRouter(tags=["events"])


@router.get("/events", response_model=list[EventOut])
def list_events(
    limit: int = Query(50, ge=1, le=500),
    event_type: EventType | None = None,
    db: Session = Depends(get_db),
) -> list[Event]:
    stmt = select(Event)
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)
    stmt = stmt.order_by(Event.detected_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())