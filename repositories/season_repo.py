"""Data access for Season entities, scoped by user_id."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session, joinedload

from db.models import Season, SeasonStatus


def list_seasons(session: Session, user_id: uuid.UUID, status: SeasonStatus | None = None) -> list[Season]:
    query = (
        session.query(Season)
        .options(joinedload(Season.crop), joinedload(Season.farm))
        .filter(Season.user_id == user_id)
    )
    if status is not None:
        query = query.filter(Season.status == status)
    return query.order_by(Season.sowing_date.desc()).all()


def get_season(session: Session, user_id: uuid.UUID, season_id: uuid.UUID) -> Season | None:
    return (
        session.query(Season)
        .options(joinedload(Season.crop), joinedload(Season.farm))
        .filter(Season.user_id == user_id, Season.id == season_id)
        .first()
    )


def get_active_season(session: Session, user_id: uuid.UUID, farm_id: uuid.UUID | None = None) -> Season | None:
    """The most-recently-sown active season (optionally restricted to a farm) -- used as the dashboard default."""
    query = session.query(Season).options(joinedload(Season.crop), joinedload(Season.farm)).filter(
        Season.user_id == user_id, Season.status == SeasonStatus.ACTIVE
    )
    if farm_id is not None:
        query = query.filter(Season.farm_id == farm_id)
    return query.order_by(Season.sowing_date.desc()).first()


def create_season(
    session: Session,
    user_id: uuid.UUID,
    farm_id: uuid.UUID,
    crop_id: uuid.UUID,
    crop_template_version_id: uuid.UUID,
    sowing_date: date,
    area: float,
    variety: str | None = None,
    area_unit: str = "Acres",
    notes: str | None = None,
) -> Season:
    season = Season(
        user_id=user_id,
        farm_id=farm_id,
        crop_id=crop_id,
        crop_template_version_id=crop_template_version_id,
        variety=variety,
        sowing_date=sowing_date,
        area=area,
        area_unit=area_unit,
        notes=notes,
        status=SeasonStatus.ACTIVE,
    )
    session.add(season)
    session.flush()
    return season


def update_season_status(session: Session, season: Season, status: SeasonStatus) -> Season:
    season.status = status
    session.flush()
    return season
