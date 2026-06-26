"""
Schedule generation engine.

This is the single place where ActivityTemplate rows (DAS offsets, data) get
converted into ScheduleActivity rows (real calendar dates) for a specific
Season. It contains NO crop-specific branching whatsoever -- it just reads
whatever templates exist for season.crop_template_version_id and projects
them onto the calendar using sowing_date + day_offset (+ repeat_interval_days * i).

Reading templates by version_id (not crop_id) is what makes the engine safe
under evolving agronomic recommendations: a season generated last year keeps
referencing the version it was created against, so revising the crop's
schedule today can never retroactively rewrite what an existing season was
told to do.

Because this is the one place that "knows" how a season gets built, it is
also where we put the (also generic) re-generation logic: if a user wants to
regenerate the schedule (e.g. after fixing a wrong sowing date), we remove
only the non-custom, non-completed activities and rebuild from templates --
custom activities and anything already marked Completed/Skipped are left
untouched so user work is never silently lost.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from db.models import ActivityStatus, ActivityTemplate, ScheduleActivity, Season


def generate_schedule_for_season(session: Session, season: Season) -> list[ScheduleActivity]:
    """
    Build ScheduleActivity rows for `season` from the ActivityTemplate rows
    belonging to season.crop_template_version_id. Pure function of
    (templates, sowing_date) -- no hardcoded crop knowledge here.
    """
    templates: list[ActivityTemplate] = (
        session.query(ActivityTemplate)
        .filter(
            ActivityTemplate.version_id == season.crop_template_version_id,
            ActivityTemplate.is_active.is_(True),
        )
        .order_by(ActivityTemplate.day_offset)
        .all()
    )

    new_activities: list[ScheduleActivity] = []
    for template in templates:
        occurrences = max(1, template.repeat_count)
        interval = template.repeat_interval_days or 0

        for i in range(occurrences):
            das = template.day_offset + (interval * i)
            activity_date = season.sowing_date + timedelta(days=das)

            # For repeating templates, disambiguate the name with an occurrence
            # number so e.g. "Drip Irrigation Cycle" appears as separate,
            # individually completable rows rather than one giant blob.
            name = template.name
            if occurrences > 1:
                name = f"{template.name} (#{i + 1}/{occurrences})"

            new_activities.append(
                ScheduleActivity(
                    season_id=season.id,
                    template_id=template.id,
                    activity_date=activity_date,
                    das=das,
                    name=name,
                    category=template.category,
                    status=ActivityStatus.PENDING,
                    remarks=template.default_remarks,
                    is_custom=False,
                )
            )

    session.add_all(new_activities)
    session.flush()
    return new_activities


def regenerate_schedule_for_season(session: Session, season: Season) -> list[ScheduleActivity]:
    """
    Rebuild the template-derived portion of a season's schedule (e.g. after
    correcting the sowing date). Custom (user-added) activities and any
    activity already marked Completed or Skipped are preserved untouched,
    since they represent real-world history that must not be erased by a
    re-projection of the template. Always rebuilds against
    season.crop_template_version_id -- the version the season was created
    with -- never against whatever the crop's current version happens to be.
    """
    session.query(ScheduleActivity).filter(
        ScheduleActivity.season_id == season.id,
        ScheduleActivity.is_custom.is_(False),
        ScheduleActivity.status == ActivityStatus.PENDING,
    ).delete(synchronize_session=False)
    session.flush()

    return generate_schedule_for_season(session, season)


def calculate_das(sowing_date: date, as_of: date | None = None) -> int:
    """Days After Sowing as of a given date (defaults to today)."""
    as_of = as_of or date.today()
    return (as_of - sowing_date).days


def current_stage_name(session: Session, version_id, das: int) -> str | None:
    """
    Look up which CropStage's [start_day, end_day] range contains `das`,
    scoped to a specific crop_template_version_id (the version the season
    was generated against). If DAS falls before the first stage or after
    the last, returns the nearest boundary stage's name (so the dashboard
    always shows something sensible rather than blank, e.g. before sowing
    or post-harvest).
    """
    from db.models import CropStage  # local import to avoid circulars at module load

    stages = (
        session.query(CropStage)
        .filter(CropStage.version_id == version_id)
        .order_by(CropStage.sequence)
        .all()
    )
    if not stages:
        return None

    for stage in stages:
        if stage.start_day <= das <= stage.end_day:
            return stage.name

    if das < stages[0].start_day:
        return stages[0].name
    return stages[-1].name
