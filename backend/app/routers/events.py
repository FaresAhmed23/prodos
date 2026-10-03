from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Event
from ..pagination import InvalidCursor, paginate
from ..schemas import EventOut, EventType

router = APIRouter(tags=["events"])


@router.get("/events", response_model=list[EventOut])
def list_events(
    response: Response,
    limit: int = Query(50, ge=1, le=500),
    event_type: EventType | None = None,
    cursor: str | None = Query(
        None, description="event_id of the last event you saw; omit for the newest page"
    ),
    db: Session = Depends(get_db),
) -> list[Event]:
    stmt = select(Event)
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)
    try:
        rows, has_more, next_cursor = paginate(
            db, stmt, Event, Event.detected_at, Event.event_id,
            cursor_id=cursor, limit=limit,
        )
    except InvalidCursor:
        raise HTTPException(status_code=400, detail="unknown cursor")
    response.headers["X-Has-More"] = str(has_more).lower()
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return rows