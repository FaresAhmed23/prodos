from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Frame
from ..schemas import FrameOut, FrameType

router = APIRouter(tags=["frames"])


@router.get("/frames/recent", response_model=list[FrameOut])
def read_recent_frames(
    seconds: int = Query(300, ge=1),
    limit: int = Query(50, ge=1, le=500),
    frame_type: FrameType | None = None,
    db: Session = Depends(get_db),
) -> list[Frame]:
    stmt = select(Frame).where(
        Frame.received_at >= datetime.now(timezone.utc) - timedelta(seconds=seconds)
    )
    if frame_type is not None:
        stmt = stmt.where(Frame.frame_type == frame_type)
    stmt = stmt.order_by(Frame.received_at.desc(), Frame.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars())