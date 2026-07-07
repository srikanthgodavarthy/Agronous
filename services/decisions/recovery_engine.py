"""
Recovery Engine: decides what to do about a still-PENDING ScheduleActivity
once its planned date has arrived or passed.

This sits alongside (not inside) the Decision Engine
(services/decisions/decision_engine.py). That module decides when a NEW
Layer 2 activity should materialize onto the schedule. This module decides
what to do with an EXISTING pending activity once its own timing has
arrived or lapsed -- the two are deliberately separate passes over the
same schedule, run back-to-back by the Recommendation Engine.

Nothing here blindly recommends an overdue activity. Every PENDING,
due-or-overdue row is evaluated against its own ActivityTemplate's
recovery metadata (valid_until_stage / max_delay_days / recovery_type /
replacement_template / expected_impact) before it's ever surfaced:

    Activity
      -> Completed already? -> excluded (evaluator only ever sees PENDING)
      -> Not yet due?        -> ON_TIME (nothing to recommend yet)
      -> Due or overdue:
           -> Still agronomically valid (within its stage/day window)?
                -> YES -> RECOVER   (recommend it now, just flagged if late)
                -> NO  -> REPLACE   (swap in the authored replacement op)
                       -> SKIP      (auto-skip, nothing to recommend)
                       -> ESCALATE  (needs a human/agronomist decision)

For ActivityTemplate rows authored before this metadata existed
(recovery_type is NULL), evaluation falls back to the same category-based
heuristic the Cultivation Schedule page already used: stage-bound
categories (fertilizer/spray/irrigation/weeding/sowing/land prep) whose
own stage has been passed are never silently recommended -- they're
flagged ESCALATE so a person decides, rather than skipped automatically
without any authored basis for that decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Callable

from sqlalchemy.orm import Session

from db.models import ActivityCategory, ActivityTemplate, CropStage, RecoveryStrategy, ScheduleActivity


class RecoveryOutcome(str, Enum):
    ON_TIME  = "ON_TIME"   # not due yet -- nothing to evaluate
    RECOVER  = "RECOVER"   # due/overdue but still within its valid window
    REPLACE  = "REPLACE"   # window closed; a replacement op is recommended
    SKIP     = "SKIP"      # window closed; no replacement -- auto-skip
    ESCALATE = "ESCALATE"  # window closed; needs a human decision


# Legacy fallback only: ActivityTemplate rows with no recovery_type
# authored yet are treated as expirable purely by category. Harvest and
# record-keeping ("Other") activities aren't bound to a narrow
# physiological window the same way a fertilizer/spray application is, so
# they're excluded and stay eligible indefinitely.
LEGACY_STAGE_BOUND_CATEGORIES = {
    ActivityCategory.FERTILIZER,
    ActivityCategory.SPRAY,
    ActivityCategory.IRRIGATION,
    ActivityCategory.WEEDING,
    ActivityCategory.SOWING,
    ActivityCategory.LAND_PREPARATION,
}


@dataclass
class RecoveryDecision:
    activity: ScheduleActivity
    outcome: RecoveryOutcome
    reason: str
    replacement_template: ActivityTemplate | None = None
    expected_impact: str | None = None
    days_late: int = 0


def stage_sequence_by_name(session: Session, version_id, stage_name: str | None) -> int | None:
    """Look up a CropStage's sequence number by name within a version --
    used to resolve ActivityTemplate.valid_until_stage to a comparable
    number. Returns None if stage_name is None or not found."""
    if not stage_name:
        return None
    stage = (
        session.query(CropStage)
        .filter(CropStage.version_id == version_id, CropStage.name == stage_name)
        .first()
    )
    return stage.sequence if stage else None


def evaluate_activity(
    session: Session,
    activity: ScheduleActivity,
    template: ActivityTemplate | None,
    current_stage_seq: int | None,
    version_id,
    today: date,
    stage_seq_for_das: Callable[[Session, object, int], int | None],
) -> RecoveryDecision:
    """
    Evaluate a single PENDING activity. `stage_seq_for_das` is injected
    (services.schedule_engine.stage_sequence_for_das in production) so this
    function has no hard dependency on how DAS-to-stage lookup is done,
    keeping it easy to unit test with a fake.
    """
    if activity.activity_date > today:
        return RecoveryDecision(activity, RecoveryOutcome.ON_TIME, "Not due yet.")

    days_late = (today - activity.activity_date).days

    # ---- Authored recovery metadata path ----
    if template is not None and template.recovery_type is not None:
        still_valid = True
        if template.max_delay_days is not None and days_late > template.max_delay_days:
            still_valid = False
        if still_valid and template.valid_until_stage is not None and current_stage_seq is not None:
            valid_until_seq = stage_sequence_by_name(session, version_id, template.valid_until_stage)
            if valid_until_seq is not None and current_stage_seq > valid_until_seq:
                still_valid = False

        if still_valid:
            reason = "Due today." if days_late == 0 else f"{days_late} day(s) late, still within its valid window."
            return RecoveryDecision(activity, RecoveryOutcome.RECOVER, reason, days_late=days_late)

        window_label = template.valid_until_stage or "its planned window"
        if template.recovery_type == RecoveryStrategy.REPLACE and template.replacement_template is not None:
            return RecoveryDecision(
                activity,
                RecoveryOutcome.REPLACE,
                reason=f"{window_label} has passed -- replaced with a stage-appropriate operation.",
                replacement_template=template.replacement_template,
                expected_impact=template.expected_impact,
                days_late=days_late,
            )
        if template.recovery_type == RecoveryStrategy.SKIP:
            return RecoveryDecision(
                activity, RecoveryOutcome.SKIP,
                reason=f"{window_label} has passed; no recovery is defined -- skipping automatically.",
                expected_impact=template.expected_impact, days_late=days_late,
            )
        # ESCALATE, or REPLACE authored without a resolvable replacement_template
        return RecoveryDecision(
            activity, RecoveryOutcome.ESCALATE,
            reason=f"{window_label} has passed and needs a manual decision.",
            expected_impact=template.expected_impact, days_late=days_late,
        )

    # ---- Legacy fallback: no recovery metadata authored on this template ----
    if activity.category in LEGACY_STAGE_BOUND_CATEGORIES and current_stage_seq is not None:
        own_seq = stage_seq_for_das(session, version_id, activity.das)
        if own_seq is not None and own_seq < current_stage_seq:
            return RecoveryDecision(
                activity, RecoveryOutcome.ESCALATE,
                reason="No recovery rule authored yet, and its stage has passed -- needs a manual decision.",
                days_late=days_late,
            )

    reason = "Due today." if days_late == 0 else f"{days_late} day(s) overdue, still relevant."
    return RecoveryDecision(activity, RecoveryOutcome.RECOVER, reason, days_late=days_late)
