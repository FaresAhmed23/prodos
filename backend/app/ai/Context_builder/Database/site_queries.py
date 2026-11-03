"""Read-only access to site_profile and sensors (mixin)."""
from __future__ import annotations

from sqlalchemy import select

from app import models

class SiteQueries:
    """Mixin for Database."""

    def get_site_profile(self, site_id: str) -> dict | None:
        """site_profile row as a dict, or None if the site does not exist."""
        with self.session() as s:
            row = s.get(models.SiteProfile, site_id)
            if row is None:
                return None
            return {
                "site_id": row.site_id,
                "business_name": row.business_name,
                "business_type": row.business_type,
                "wifi_ssids": list(row.wifi_ssids or []),
                "known_access_points": list(row.known_access_points or []),
                "router_model": row.router_model,
                "primary_language": row.primary_language or "en",
                "notes": row.notes,
            }

    def list_sensors(self, site_id: str, limit: int) -> list[dict]:
        """Only this site's active sensors, ordered by sensor_id."""
        with self.session() as s:
            rows = s.scalars(
                select(models.Sensor)
                .where(models.Sensor.site_id == site_id,
                       models.Sensor.status != "offline")
                .order_by(models.Sensor.sensor_id)
                .limit(limit)
            ).all()
            return [
                {
                    "id": r.sensor_id,
                    "name": r.name,
                    "location": r.location,
                    "status": r.status,
                    "last_seen_at": self._utc(r.last_seen_at),
                }
                for r in rows
            ]

    def resolve_site_id(sensor_ids: list[str]) -> list[str]:
        pass # TODO: return all sites for all the given sensors