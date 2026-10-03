"""Keyset (cursor) pagination for the newest-first feeds.

Cursor is the *id of the last row the client saw*, not an offset. That matters
for `/alerts` and `/events`: a dashboard polls while new rows arrive, and
offset pagination shifts the window under the client, so it silently skips and
repeats rows. Keyset does not, because the anchor row stays pinned.

Ordering is on (timestamp, id) rather than timestamp alone so that rows sharing
a timestamp still have a deterministic total order -- without the tiebreak,
paging can repeat or skip a row.
"""

from sqlalchemy import Select, tuple_
from sqlalchemy.orm import Session


class InvalidCursor(ValueError):
    """The cursor does not name a row that exists."""


def paginate(
    session: Session,
    stmt: Select,
    model: type,
    ts_col,
    id_col,
    *,
    cursor_id: str | None,
    limit: int,
) -> tuple[list, bool, str | None]:
    """Return ``(rows, has_more, next_cursor)`` for one page, newest first.

    Fetches limit+1 to decide `has_more` without a second COUNT query, which
    on a live feed is both slower and racy.
    """
    if cursor_id is not None:
        anchor = session.get(model, cursor_id)
        if anchor is None:
            raise InvalidCursor(cursor_id)
        stmt = stmt.where(
            tuple_(ts_col, id_col) < tuple_(getattr(anchor, ts_col.key), cursor_id)
        )

    rows = list(
        session.execute(
            stmt.order_by(ts_col.desc(), id_col.desc()).limit(limit + 1)
        ).scalars()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = getattr(rows[-1], id_col.key) if has_more and rows else None
    return rows, has_more, next_cursor
