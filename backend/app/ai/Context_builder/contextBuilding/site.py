"""Loads the site (business) state for the context."""
from __future__ import annotations

from app.ai.Context_builder.config import SiteConfig
from app.ai.Context_builder.database.core import Database
from app.ai.Context_builder.types import SiteState


class SiteStateLoader:
    def __init__(self, db: Database, cfg: SiteConfig) -> None:
        self._db = db
        self._cfg = cfg

    def load(self, site_id: str) -> tuple[SiteState, list[str]]:
        """Profile + that site's sensors. If the site is missing (ALT PATH 2):
        return SiteState.unknown(...) and a warning 'business_not_found'."""
        profile = self._db.get_site_profile(site_id)
        if profile is None:
            return SiteState.unknown(site_id, self._cfg), [f"business_not_found-id: {site_id}"]

        sensors = self._db.list_sensors(site_id, self._cfg.max_sensors_listed)
        state = SiteState(
            site_id=site_id,
            found=True,
            name=profile["business_name"] or self._cfg.unknown_site_name,
            business_type=profile["business_type"],
            wifi_ssids=profile["wifi_ssids"],
            known_access_points=profile["known_access_points"],
            router_model=profile["router_model"],
            primary_language=profile["primary_language"],
            notes=profile["notes"],
            sensors=sensors,
        )
        return state, []