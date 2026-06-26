"""Data access for ScheduleActivity entities."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from db.models import ActivityCategory, ActivityStatus, ScheduleActivity


def list_activities(
    session: Session,
    season_id: uuid.UUID,
    status: ActivityStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ScheduleActivity]:
    query = session.query(ScheduleActivity).filter(ScheduleActivity.season_id == season_id)
    if status is not None:
        query = query.filter(ScheduleActivity.status == status)
    if date_from is not None:
        query = query.filter(ScheduleActivity.activity_date >= date_from)
    if date_to is not None:
        query = query.filter(ScheduleActivity.activity_date <= date_to)
    return query.order_by(ScheduleActivity.activity_date).all()


def get_todays_tasks(session: Session, season_id: uuid.UUID, today: date | None = None) -> list[ScheduleActivity]:
    today = today or date.today()
    return list_activities(session, season_id, status=ActivityStatus.PENDING, date_from=today, date_to=today)


def get_upcoming_tasks(
    session: Session, season_id: uuid.UUID, days: int = 7, today: date | None = None
) -> list[ScheduleActivity]:
    today = today or date.today()
    from datetime import timedelta

    return list_activities(
        session,
        season_id,
        status=ActivityStatus.PENDING,
        date_from=today + timedelta(days=1),
        date_to=today + timedelta(days=days),
    )


def get_activity(session: Session, activity_id: uuid.UUID) -> ScheduleActivity | None:
    return session.query(ScheduleActivity).filter(ScheduleActivity.id == activity_id).first()


def mark_complete(session: Session, activity: ScheduleActivity, remarks: str | None = None) -> ScheduleActivity:
    activity.status = ActivityStatus.COMPLETED
    activity.completed_at = datetime.now(timezone.utc)
    if remarks:
        activity.remarks = remarks
    session.flush()
    return activity


def mark_skipped(session: Session, activity: ScheduleActivity, remarks: str | None = None) -> ScheduleActivity:
    activity.status = ActivityStatus.SKIPPED
    if remarks:
        activity.remarks = remarks
    session.flush()
    return activity


def reopen(session: Session, activity: ScheduleActivity) -> ScheduleActivity:
    activity.status = ActivityStatus.PENDING
    activity.completed_at = None
    session.flush()
    return activity


def update_activity(
    session: Session,
    activity: ScheduleActivity,
    activity_date: date | None = None,
    remarks: str | None = None,
    name: str | None = None,
    category: ActivityCategory | None = None,
) -> ScheduleActivity:
    if activity_date is not None:
        activity.activity_date = activity_date
    if remarks is not None:
        activity.remarks = remarks
    if name is not None:
        activity.name = name
    if category is not None:
        activity.category = category
    session.flush()
    return activity


def add_custom_activity(
    session: Session,
    season_id: uuid.UUID,
    activity_date: date,
    das: int,
    name: str,
    category: ActivityCategory,
    remarks: str | None = None,
) -> ScheduleActivity:
    activity = ScheduleActivity(
        season_id=season_id,
        template_id=None,
        activity_date=activity_date,
        das=das,
        name=name,
        category=category,
        status=ActivityStatus.PENDING,
        remarks=remarks,
        is_custom=True,
    )
    session.add(activity)
    session.flush()
    return activity


def delete_activity(session: Session, activity: ScheduleActivity) -> None:
    session.delete(activity)
