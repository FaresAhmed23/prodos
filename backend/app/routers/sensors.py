from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Sensor
from ..schemas import SensorCreate, SensorOut, SensorUpdate

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("", response_model=list[SensorOut])
def list_sensors(db: Session = Depends(get_db)) -> list[Sensor]:
    return list(db.execute(select(Sensor).order_by(Sensor.registered_at)).scalars())


@router.post("", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
def create_sensor(payload: SensorCreate, db: Session = Depends(get_db)) -> Sensor:
    if db.get(Sensor, payload.sensor_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "sensor already registered")
    sensor = Sensor(**payload.model_dump(), status="offline")
    db.add(sensor)
    db.commit()
    return sensor


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(sensor_id: str, db: Session = Depends(get_db)) -> Sensor:
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    return sensor


@router.patch("/{sensor_id}", response_model=SensorOut)
def update_sensor(sensor_id: str, payload: SensorUpdate, db: Session = Depends(get_db)) -> Sensor:
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sensor, field, value)
    db.commit()
    return sensor