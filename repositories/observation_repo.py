"""Data access for Observation entities (field notes/photos + AI analysis)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.models import Observation, ObservationSource


def list_observations(session: Session, season_id: uuid.UUID, limit: int | None = None) -> list[Observation]:
    query = (
        session.query(Observation)
        .filter(Observation.season_id == season_id)
        .order_by(Observation.observed_at.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def get_observation(session: Session, observation_id: uuid.UUID) -> Observation | None:
    return session.query(Observation).filter(Observation.id == observation_id).first()


def create_observation(
    session: Session,
    season_id: uuid.UUID,
    user_id: uuid.UUID,
    note: str | None = None,
    image_url: str | None = None,
    source: ObservationSource = ObservationSource.FARMER,
) -> Observation:
    observation = Observation(
        season_id=season_id,
        user_id=user_id,
        note=note,
        image_url=image_url,
        source=source,
    )
    session.add(observation)
    session.flush()
    return observation


def save_ai_analysis(
    session: Session,
    observation: Observation,
    ai_analysis: str | None = None,
    ai_category: str | None = None,
    ai_confidence: float | None = None,
    ai_recommendation: str | None = None,
    ai_raw_response: dict | None = None,
) -> Observation:
    """
    Attach AI-derived fields to an existing Observation without touching the
    farmer-entered `note`/`image_url`. Safe to call repeatedly (e.g. to
    re-run analysis with an improved model) -- always overwrites only the
    ai_* columns, stamping ai_analyzed_at to the current time.
    """
    observation.ai_analysis = ai_analysis
    observation.ai_category = ai_category
    observation.ai_confidence = ai_confidence
    observation.ai_recommendation = ai_recommendation
    observation.ai_raw_response = ai_raw_response
    observation.ai_analyzed_at = datetime.now(timezone.utc)
    session.flush()
    return observation


def delete_observation(session: Session, observation: Observation) -> None:
    session.delete(observation)
