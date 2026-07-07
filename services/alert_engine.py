"""
Alert generation engine.

Alerts are entirely *derived* from ScheduleActivity rows -- there is no
separate place where "alert rules" are hardcoded per crop. The rule is
generic and date-arithmetic only:

    overdue   -> activity_date < today AND status == Pending           => RED
    due soon  -> activity_date in [today, today + DUE_SOON_WINDOW]      => YELLOW
    upcoming  -> activity_date in (today + DUE_SOON_WINDOW, +UPCOMING]  => GREEN

This module recomputes alerts on demand (called from the dashboard/alerts
page) and upserts them into the `alert` table, keyed by schedule_activity_id,
so dismiss-state survives across recomputation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from db.models import Alert, AlertPriority, ActivityStatus, ScheduleActivity, Season

DUE_SOON_WINDOW_DAYS = 3   # tomorrow..+3 days = Yellow
UPCOMING_WINDOW_DAYS = 7   # +4..+7 days = Green


@dataclass
class AlertView:
    message: str
    priority: AlertPriority
    activity_date: date
    category: str
    schedule_activity_id: str | None = None


def _priority_for(activity_date: date, today: date) -> AlertPriority | None:
    delta = (activity_date - today).days
    if delta < 0:
        return AlertPriority.RED
    if delta <= DUE_SOON_WINDOW_DAYS:
        return AlertPriority.YELLOW
    if delta <= UPCOMING_WINDOW_DAYS:
        return AlertPriority.GREEN
    return None


def _message_for(activity: ScheduleActivity, today: date) -> str:
    delta = (activity.activity_date - today).days
    if delta < 0:
        days_overdue = abs(delta)
        return f"{activity.name} overdue by {days_overdue} day{'s' if days_overdue != 1 else ''}"
    if delta == 0:
        return f"{activity.name} due today"
    if delta == 1:
        return f"{activity.name} due tomorrow"
    return f"{activity.name} due in {delta} days"


def build_alert_views(activities: list[ScheduleActivity], today: date | None = None) -> list[AlertView]:
    """Pure function: pending activities -> alert views, no DB access. Easy to unit test."""
    today = today or date.today()
    views: list[AlertView] = []
    for activity in activities:
        if activity.status != ActivityStatus.PENDING:
            continue
        priority = _priority_for(activity.activity_date, today)
        if priority is None:
            continue
        views.append(
            AlertView(
                message=_message_for(activity, today),
                priority=priority,
                activity_date=activity.activity_date,
                category=activity.category.value if hasattr(activity.category, "value") else str(activity.category),
                schedule_activity_id=str(activity.id),
            )
        )
    # Most urgent first: Red, then Yellow, then Green; within a priority, soonest date first.
    order = {AlertPriority.RED: 0, AlertPriority.YELLOW: 1, AlertPriority.GREEN: 2}
    views.sort(key=lambda v: (order[v.priority], v.activity_date))
    return views


def raise_recovery_alerts(session: Session, season: Season, escalations: list) -> list[Alert]:
    """
    Upsert a RED alert (keyed by schedule_activity_id, same convention as
    refresh_alerts_for_season) for every RecoveryOutcome.ESCALATE decision
    from the Recovery Engine -- an activity whose window has closed with no
    authored REPLACE/SKIP strategy, needing a human decision rather than
    either "just do it late" or a silent auto-skip.

    Additive and separate from refresh_alerts_for_season's due-date-window
    alerts: this never removes or overwrites a due-date alert for an
    activity that isn't also escalated, and vice versa.
    """
    result: list[Alert] = []
    for decision in escalations:
        activity = decision.activity
        existing = (
            session.query(Alert)
            .filter(Alert.season_id == season.id, Alert.schedule_activity_id == activity.id)
            .first()
        )
        message = f"{activity.name}: {decision.reason}"
        if existing:
            existing.message = message
            existing.priority = AlertPriority.RED
            result.append(existing)
        else:
            new_alert = Alert(
                season_id=season.id,
                schedule_activity_id=activity.id,
                message=message,
                priority=AlertPriority.RED,
            )
            session.add(new_alert)
            result.append(new_alert)
    session.flush()
    return result
    """
    Recompute and upsert Alert rows for a season's pending activities.
    Existing dismissed-state is preserved for activities still pending;
    alerts for activities that are no longer pending (completed/skipped) or
    no longer in the alert window are removed.
    """
    today = today or date.today()
    activities = (
        session.query(ScheduleActivity)
        .filter(ScheduleActivity.season_id == season.id, ScheduleActivity.status == ActivityStatus.PENDING)
        .all()
    )
    views = build_alert_views(activities, today)
    relevant_activity_ids = {v.schedule_activity_id for v in views}

    existing = {str(a.schedule_activity_id): a for a in session.query(Alert).filter(Alert.season_id == season.id)}

    # Remove alerts whose activity is no longer in an alert-worthy window.
    for activity_id, alert in list(existing.items()):
        if activity_id not in relevant_activity_ids:
            session.delete(alert)
            existing.pop(activity_id, None)

    result: list[Alert] = []
    for view in views:
        existing_alert = existing.get(view.schedule_activity_id)
        if existing_alert:
            existing_alert.message = view.message
            existing_alert.priority = view.priority
            result.append(existing_alert)
        else:
            new_alert = Alert(
                season_id=season.id,
                schedule_activity_id=view.schedule_activity_id,
                message=view.message,
                priority=view.priority,
            )
            session.add(new_alert)
            result.append(new_alert)

    session.flush()
    return result
