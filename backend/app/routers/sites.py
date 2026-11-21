from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..admin import require_admin
from ..database import get_db
from ..models import ChecklistAnswer, ScoreSnapshot, Sensor, SiteProfile, utcnow
from ..schemas import SensorOut, normalize_mac
from ..scoring.config import CHECKLIST_QUESTIONS

router = APIRouter(
    prefix="/sites", tags=["sites"], dependencies=[Depends(require_admin)]
)


def _normalize_macs(values: list[str]) -> list[str]:
    return [normalize_mac(value) for value in values]


# Owner-entered APs are compared against frame BSSIDs, which are normalized at
# ingest. Normalize here too, or a lowercase entry never matches.
MacList = Annotated[list[str], AfterValidator(_normalize_macs)]


class SiteCreate(BaseModel):
    site_id: str = Field(min_length=1, max_length=64)
    business_name: str | None = Field(default=None, max_length=200)
    business_type: str | None = Field(default=None, max_length=64)
    wifi_ssids: list[str] = Field(default_factory=list)
    known_access_points: MacList = Field(default_factory=list)
    router_model: str | None = Field(default=None, max_length=100)
    primary_language: str = Field(default="en", min_length=2, max_length=8)
    notes: str | None = None


class SiteUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=200)
    business_type: str | None = Field(default=None, max_length=64)
    wifi_ssids: list[str] | None = None
    known_access_points: MacList | None = None
    router_model: str | None = Field(default=None, max_length=100)
    primary_language: str | None = Field(default=None, min_length=2, max_length=8)
    notes: str | None = None


class SiteOut(BaseModel):
    site_id: str
    business_name: str | None
    business_type: str | None
    wifi_ssids: list[str]
    known_access_points: list[str]
    router_model: str | None
    primary_language: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChecklistPut(BaseModel):
    answers: dict[str, bool | None]


class ChecklistOut(BaseModel):
    site_id: str
    answers: dict[str, bool | None]
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScoreOut(BaseModel):
    """REST-only shape (spec §5/§6), same reason AlertStats is router-local."""

    site_id: str
    computed_at: datetime
    score: int
    band: str
    components: dict[str, float]
    details: dict
    window_days: int

    model_config = {"from_attributes": True}


def _site_or_404(db: Session, site_id: str) -> SiteProfile:
    site = db.get(SiteProfile, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
    return site


def _sensor_or_404(db: Session, sensor_id: str) -> Sensor:
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    return sensor


@router.get("", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db)) -> list[SiteProfile]:
    return list(db.execute(select(SiteProfile).order_by(SiteProfile.created_at)).scalars())


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteCreate, db: Session = Depends(get_db)) -> SiteProfile:
    if db.get(SiteProfile, payload.site_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "site already exists")
    site = SiteProfile(**payload.model_dump())
    db.add(site)
    db.commit()
    return site


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: str, db: Session = Depends(get_db)) -> SiteProfile:
    return _site_or_404(db, site_id)


@router.patch("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: str, payload: SiteUpdate, db: Session = Depends(get_db)
) -> SiteProfile:
    site = _site_or_404(db, site_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        # These three columns are NOT NULL; clearing a list means `[]`, not null.
        if value is None and field in ("wifi_ssids", "known_access_points", "primary_language"):
            continue
        setattr(site, field, value)
    db.commit()
    return site


@router.patch("/{site_id}/sensors/{sensor_id}", response_model=SensorOut)
def assign_sensor(
    site_id: str, sensor_id: str, db: Session = Depends(get_db)
) -> Sensor:
    _site_or_404(db, site_id)
    sensor = _sensor_or_404(db, sensor_id)
    sensor.site_id = site_id
    db.commit()
    return sensor


@router.delete("/{site_id}/sensors/{sensor_id}", response_model=SensorOut)
def unassign_sensor(
    site_id: str, sensor_id: str, db: Session = Depends(get_db)
) -> Sensor:
    _site_or_404(db, site_id)
    sensor = _sensor_or_404(db, sensor_id)
    sensor.site_id = None
    db.commit()
    return sensor


@router.put("/{site_id}/checklist", response_model=ChecklistOut)
def put_checklist(
    site_id: str, payload: ChecklistPut, db: Session = Depends(get_db)
) -> ChecklistAnswer:
    _site_or_404(db, site_id)

    unknown = sorted(set(payload.answers) - set(CHECKLIST_QUESTIONS))
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "unknown checklist keys",
                "unknown_keys": unknown,
                "valid_keys": list(CHECKLIST_QUESTIONS),
            },
        )

    row = db.get(ChecklistAnswer, site_id)
    if row is None:
        row = ChecklistAnswer(site_id=site_id, answers={})
        db.add(row)
    row.answers = dict(payload.answers)
    row.updated_at = utcnow()
    db.commit()
    return row


@router.get("/{site_id}/score", response_model=ScoreOut)
def get_score(site_id: str, db: Session = Depends(get_db)) -> ScoreSnapshot:
    _site_or_404(db, site_id)
    row = db.execute(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.site_id == site_id)
        .order_by(ScoreSnapshot.computed_at.desc(), ScoreSnapshot.id.desc())
        .limit(1)
    ).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no snapshot yet")
    return row


@router.get("/{site_id}/score/history", response_model=list[ScoreOut])
def get_score_history(
    site_id: str,
    limit: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> list[ScoreSnapshot]:
    _site_or_404(db, site_id)
    rows = list(
        db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.site_id == site_id)
            .order_by(ScoreSnapshot.computed_at.desc(), ScoreSnapshot.id.desc())
            .limit(limit)
        ).scalars()
    )
    return list(reversed(rows))
