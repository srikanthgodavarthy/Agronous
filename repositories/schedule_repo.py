"""Data access for ScheduleActivity entities."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

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


# Categories whose agronomic value is tied to a specific physiological
# window (a stage) -- if the plant has already moved past that stage,
# doing the activity "now" no longer serves the purpose it was scheduled
# for (e.g. a vegetative-stage Nitrogen top-dressing has little point once
# the crop is flowering and drawing on different reserves). HARVEST and
# OTHER are excluded: harvest/record-keeping tasks aren't bound to a
# narrow window the same way, so staying PENDING across a stage boundary
# doesn't make them stale.
STAGE_BOUND_CATEGORIES = {
    ActivityCategory.FERTILIZER,
    ActivityCategory.SPRAY,
    ActivityCategory.IRRIGATION,
    ActivityCategory.WEEDING,
    ActivityCategory.SOWING,
    ActivityCategory.LAND_PREPARATION,
}


def get_schedule_suggestions(
    session: Session,
    season_id: uuid.UUID,
    sowing_date: date,
    crop_template_version_id,
    today: date | None = None,
    limit: int = 5,
) -> tuple[list[ScheduleActivity], list[ScheduleActivity]]:
    """
    NOTE -- superseded: this was the first pass at stage-aware suggestions
    (pure category-based heuristic, no per-template recovery metadata, no
    REPLACE/auto-SKIP, no bundling). The Cultivation Schedule page and
    Dashboard now both call
    services.decisions.recommendation_engine.build_schedule_snapshot
    instead, which layers the Recovery Engine's authored recovery_type/
    valid_until_stage/replacement_template on top of this same stage
    comparison. Left in place (still correct, just coarser) as a simple
    query for any future caller that only needs the plain stage split
    without the full recovery/bundling/Layer-2 pipeline.

    Split still-PENDING activities into (next_up, missed_stage_passed),
    reading completion history implicitly (only PENDING rows are ever
    considered -- anything already COMPLETED/SKIPPED, in or out of order,
    is never re-suggested):

      - next_up: the next PENDING activities, chronologically, whose own
        stage is still at-or-after the plant's *current* stage -- these
        are genuinely still worth doing now.
      - missed_stage_passed: PENDING activities whose stage the plant has
        already grown past. These are NOT included in next_up and should
        never be presented as "do this now" -- the window that made the
        dose/timing agronomically correct has closed. Surface them
        instead as a missed acknowledgement (e.g. offer to log it as
        skipped/missed, or let the farmer explicitly say they did it
        late), never as a fresh recommendation.

    Requires crop_template_version_id (not just season_id) because stage
    boundaries are looked up per-template-version, same as everywhere else
    in this codebase.
    """
    from services.schedule_engine import calculate_das, stage_sequence_for_das

    today = today or date.today()
    current_das = calculate_das(sowing_date, as_of=today)
    current_seq = stage_sequence_for_das(session, crop_template_version_id, current_das)

    pending = (
        session.query(ScheduleActivity)
        .filter(ScheduleActivity.season_id == season_id, ScheduleActivity.status == ActivityStatus.PENDING)
        .order_by(ScheduleActivity.activity_date, ScheduleActivity.das)
        .all()
    )

    next_up: list[ScheduleActivity] = []
    missed: list[ScheduleActivity] = []
    for act in pending:
        if act.category in STAGE_BOUND_CATEGORIES and current_seq is not None:
            own_seq = stage_sequence_for_das(session, crop_template_version_id, act.das)
            if own_seq is not None and own_seq < current_seq:
                missed.append(act)
                continue
        next_up.append(act)

    return next_up[:limit], missed[: max(limit, 10)]


def get_activity(session: Session, activity_id: uuid.UUID) -> ScheduleActivity | None:
    return session.query(ScheduleActivity).filter(ScheduleActivity.id == activity_id).first()


def mark_complete(
    session: Session,
    activity: ScheduleActivity,
    remarks: str | None = None,
    completed_date: date | None = None,
) -> ScheduleActivity:
    """
    Mark an activity complete. `completed_date` is the date the farmer
    actually did the work (asked for in the UI at completion time), which
    may differ from today (e.g. logging yesterday's spray). Defaults to
    "now" only when no date is supplied (e.g. programmatic/test callers).
    Stored at midday UTC on that date so the date itself is unambiguous
    across timezones/date-only displays.
    """
    activity.status = ActivityStatus.COMPLETED
    if completed_date is not None:
        activity.completed_at = datetime.combine(completed_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
    else:
        activity.completed_at = datetime.now(timezone.utc)
    if remarks:
        activity.remarks = remarks
    session.flush()
    return activity


def mark_complete_many(
    session: Session,
    activities: list[ScheduleActivity],
    completed_date: date | None = None,
) -> list[ScheduleActivity]:
    """Complete several activities (a combined same-day operation) at once,
    all stamped with the same farmer-supplied completion date."""
    for activity in activities:
        mark_complete(session, activity, completed_date=completed_date)
    return activities


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
