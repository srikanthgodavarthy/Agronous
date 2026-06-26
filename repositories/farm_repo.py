"""Data access for Farm entities. All queries are scoped by user_id."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from db.models import Farm


def list_farms(session: Session, user_id: uuid.UUID) -> list[Farm]:
    return session.query(Farm).filter(Farm.user_id == user_id).order_by(Farm.created_at).all()


def get_farm(session: Session, user_id: uuid.UUID, farm_id: uuid.UUID) -> Farm | None:
    return session.query(Farm).filter(Farm.user_id == user_id, Farm.id == farm_id).first()


def create_farm(
    session: Session,
    user_id: uuid.UUID,
    name: str,
    location: str | None = None,
    total_area: float | None = None,
    area_unit: str = "Acres",
) -> Farm:
    farm = Farm(user_id=user_id, name=name, location=location, total_area=total_area, area_unit=area_unit)
    session.add(farm)
    session.flush()
    return farm


def update_farm(session: Session, farm: Farm, **fields) -> Farm:
    for key, value in fields.items():
        if hasattr(farm, key) and value is not None:
            setattr(farm, key, value)
    session.flush()
    return farm


def delete_farm(session: Session, farm: Farm) -> None:
    session.delete(farm)
