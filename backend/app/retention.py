import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from .config import settings
from .database import SessionLocal
from .models import Frame, utcnow

log = logging.getLogger(__name__)

DELETE_BATCH = 10_000
RETENTION_INTERVAL_S = 3600


def purge_expired(cutoff: datetime) -> int:
    """Delete frames older than cutoff, one bounded batch per transaction.

    Committing per batch means we never hold a long-running lock on frames,
    so ingestion keeps running while a big purge drains.
    """
    removed = 0
    with SessionLocal() as session:
        while True:
            result = session.execute(
                delete(Frame).where(
                    Frame.id.in_(
                        select(Frame.id).where(Frame.received_at < cutoff).limit(DELETE_BATCH)
                    )
                )
            )
            session.commit()
            if not result.rowcount:
                return removed
            removed += result.rowcount


async def retention_loop() -> None:
    while True:
        try:
            cutoff = utcnow() - timedelta(days=settings.retention_days)
            removed = await asyncio.to_thread(purge_expired, cutoff)
            if removed:
                log.info(
                    "retention: purged %s frames older than %s", removed, cutoff.isoformat()
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("frame retention sweep failed")
        await asyncio.sleep(RETENTION_INTERVAL_S)