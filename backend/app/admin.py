"""Optional X-Admin-Key gate for owner-side endpoints (spec §4, §6)."""

import logging

from fastapi import Header, HTTPException, status

from .config import settings

log = logging.getLogger(__name__)


async def require_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    if settings.admin_api_key and x_admin_key != settings.admin_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid admin key")


def warn_if_admin_key_unset() -> None:
    if not settings.admin_api_key:
        log.warning(
            "ADMIN_API_KEY is unset: owner-side /sites endpoints are open. "
            "LAN pilot only."
        )
