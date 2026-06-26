"""Read-only data access for Crop Master data (CropMaster, CropTemplateVersion, CropStage, ActivityTemplate)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from db.models import ActivityTemplate, CropMaster, CropStage, CropTemplateVersion


def list_active_crops(session: Session) -> list[CropMaster]:
    return session.query(CropMaster).filter(CropMaster.is_active.is_(True)).order_by(CropMaster.name).all()


def get_crop(session: Session, crop_id: uuid.UUID) -> CropMaster | None:
    return session.query(CropMaster).filter(CropMaster.id == crop_id).first()


def get_current_version(session: Session, crop_id: uuid.UUID) -> CropTemplateVersion | None:
    """
    The version offered when a farmer starts a *new* Season for this crop.
    Exactly one version per crop should have is_current=True; if more than
    one somehow does (a data error), the highest version_number wins so the
    app still behaves sensibly rather than raising.
    """
    return (
        session.query(CropTemplateVersion)
        .filter(CropTemplateVersion.crop_id == crop_id, CropTemplateVersion.is_current.is_(True))
        .order_by(CropTemplateVersion.version_number.desc())
        .first()
    )


def get_version(session: Session, version_id: uuid.UUID) -> CropTemplateVersion | None:
    return session.query(CropTemplateVersion).filter(CropTemplateVersion.id == version_id).first()


def list_versions(session: Session, crop_id: uuid.UUID) -> list[CropTemplateVersion]:
    return (
        session.query(CropTemplateVersion)
        .filter(CropTemplateVersion.crop_id == crop_id)
        .order_by(CropTemplateVersion.version_number.desc())
        .all()
    )


def get_crop_stages(session: Session, version_id: uuid.UUID) -> list[CropStage]:
    return (
        session.query(CropStage)
        .filter(CropStage.version_id == version_id)
        .order_by(CropStage.sequence)
        .all()
    )


def get_activity_templates(session: Session, version_id: uuid.UUID) -> list[ActivityTemplate]:
    return (
        session.query(ActivityTemplate)
        .filter(ActivityTemplate.version_id == version_id, ActivityTemplate.is_active.is_(True))
        .order_by(ActivityTemplate.day_offset)
        .all()
    )
