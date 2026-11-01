"""
ALl editable constants for the context builder, in frozen dataclasses.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IncidentConfig:
    gap_minutes: int = 30              # silence that closes an incident
    related_window_days: int = 7
    max_related: int = 5
    high_severity_threshold: int = 8
    max_candidates_scanned: int = 200


@dataclass(frozen=True)
class ReuseConfig:
    reuse_minutes: int = 15
    regenerate_every_n_events: int = 5  # new text once incident grew by n events
    require_same_lang: bool = True
    block_on_severity_escalation: bool = True


@dataclass(frozen=True)
class SiteConfig:
    default_site_id: str = "default"
    unknown_site_name: str = "The business"
    unknown_filler: str = "No business details are available at the moment."
    max_sensors_listed: int = 10


@dataclass(frozen=True)
class ContextConfig:
    max_prompt_chars: int = 6000       # about 1,500 tokens
    default_lang: str = "en"


@dataclass(frozen=True)
class ContextBuilderConfig:
    incident: IncidentConfig = field(default_factory=IncidentConfig)
    reuse: ReuseConfig = field(default_factory=ReuseConfig)
    site: SiteConfig = field(default_factory=SiteConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


DEFAULT_CONFIG = ContextBuilderConfig()