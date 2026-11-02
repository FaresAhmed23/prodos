"""Read-only access to alerts (mixin)."""
from __future__ import annotations

from app import models
from app.ai.Context_builder.types import ExplainedAlert


class AlertQueries:
    """Mixin for Database."""

    def get_explained_alert(self, alert_id: str, lang: str | None = None) -> ExplainedAlert | None:
        """Load a stored alert as an ExplainedAlert (None if missing).

        If `lang` is given and alert_texts has a row for (alert_id, lang),
        that text is used; otherwise the alert's primary text is returned,
        labelled with `lang` (or "en" if none was given). Callers pass the
        incident's explained_lang, so the label matches what was stored.
        """
        with self.session() as s:
            alert = s.get(models.Alert, alert_id)
            if alert is None:
                return None

            title = alert.title
            explanation = alert.explanation
            action = alert.recommended_action

            return ExplainedAlert(
                alert_id=alert.alert_id,
                title=title,
                explanation=explanation,
                recommended_action=action,
                severity=alert.severity,
                lang=lang or "en",
                created_at=self._utc(alert.created_at),
                status=alert.status,
            )