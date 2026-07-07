"""
Recommendation Engine: produces the single "what's the best thing to do
today" answer for a season, instead of the app just listing whatever's
scheduled or overdue.

Each call:
  1. Runs the existing Decision Engine (services/decisions/decision_engine.py,
     untouched) so any newly-triggered Layer 2 activity materializes first.
  2. Runs the Recovery Engine (services/decisions/recovery_engine.py) over
     every due/overdue PENDING activity, and applies its side effects:
       RECOVER  -> still worth doing, carries into the recommendation
       REPLACE  -> original auto-skipped, its replacement template is
                   materialized (or reused if already present) and carries
                   into the recommendation instead
       SKIP     -> original auto-skipped, dropped entirely
       ESCALATE -> original left PENDING, raised as an alert, excluded from
                   the recommendation (needs a human decision)
  3. Bundles same-day compatible FERTILIZER/SPRAY rows
     (services/decisions/operation_bundling.py) into single operations.
  4. Picks ONE top RecommendedOperation (most urgent bundle) plus the rest
     as "also pending".

Side effects (auto-skip, materialization, alerts) are applied every call,
but are naturally idempotent: once an activity is no longer PENDING it's
never evaluated again, and replacement materialization is guarded by an
existing-row check -- so calling this on every dashboard/page load never
double-applies anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from db.models import (
    ActivityStatus,
    ActivityTemplate,
    ScheduleActivity,
    Season,
)
from repositories import schedule_repo
from services.alert_engine import raise_recovery_alerts
from services.decisions import operation_bundling
from services.decisions.decision_engine import build_context_from_observations, evaluate_and_activate
from services.decisions.recovery_engine import RecoveryDecision, RecoveryOutcome, evaluate_activity
from services.schedule_engine import calculate_das, current_stage_name, stage_sequence_for_das


def _no_hint(name: str, remarks: str, category: str | None = None) -> dict | None:
    """Recommendation-engine callers have no page-local PRODUCT_HINTS table
    (that's a Streamlit-page concern for legacy free-text remarks); bundling
    here relies purely on the structured 'Label: value.' remarks convention
    already used by every Layer 1/1.5/2 seed row."""
    return None


@dataclass
class RecommendedOperation:
    activity_ids: list
    name: str
    category: str
    recommended_date: date
    priority: str
    products: list[str]
    dosage: list[str]
    water_volume: str | None
    why: str
    expected_benefit: str | None
    recovery_reason: str | None = None
    is_recovery: bool = False
    is_replacement: bool = False
    is_bundled: bool = False


@dataclass
class ScheduleSnapshot:
    recommended: RecommendedOperation | None
    also_actionable: list[RecommendedOperation] = field(default_factory=list)
    escalated: list[RecoveryDecision] = field(default_factory=list)
    auto_skipped_names: list[str] = field(default_factory=list)
    replaced_names: list[tuple[str, str]] = field(default_factory=list)  # (original, replacement)


def _row_from_activity(a: ScheduleActivity) -> dict:
    return {
        "id": a.id,
        "activity_date": a.activity_date,
        "das": a.das,
        "name": a.name,
        "category": a.category.value,
        "status": a.status.value,
        "remarks": a.remarks or "",
        "is_custom": a.is_custom,
    }


def _operation_from_row(row: dict, today: date, is_recovery: bool, is_replacement: bool, recovery_reason: str | None) -> RecommendedOperation:
    parsed = operation_bundling.parse_remarks(row["remarks"])
    priority = operation_bundling.clean_value(parsed.get("Priority")) or "Essential"
    product = operation_bundling.clean_value(parsed.get("Product")) or row["name"]
    dose = operation_bundling.clean_value(parsed.get("Dose"))
    water = operation_bundling.clean_value(parsed.get("Water")) or None
    why = operation_bundling.clean_value(parsed.get("Why")) or operation_bundling.clean_value(parsed.get("Purpose"))
    benefit = operation_bundling.clean_value(parsed.get("Objective")) or operation_bundling.clean_value(parsed.get("Benefit")) or None

    # A bundled row's Product field already lists every member "name — dose"
    # pair semicolon-separated (see operation_bundling.merge_group), so
    # split it back out into per-product/dose lists for the card.
    if row.get("members"):
        products = [p.split(" — ")[0].strip() for p in product.split(";")]
        dosage = [p.split(" — ", 1)[1].strip() if " — " in p else "" for p in product.split(";")]
    else:
        products = [product]
        dosage = [dose] if dose else []

    return RecommendedOperation(
        activity_ids=row.get("ids", [row["id"]]),
        name=row["name"],
        category=row["category"],
        recommended_date=row["activity_date"],
        priority=priority,
        products=products,
        dosage=dosage,
        water_volume=water,
        why=why or "Scheduled as part of the crop's standard cultivation plan.",
        expected_benefit=benefit,
        recovery_reason=recovery_reason,
        is_recovery=is_recovery,
        is_replacement=is_replacement,
        is_bundled=bool(row.get("members")),
    )


def _get_or_materialize_replacement(
    session: Session, season: Season, replacement_template: ActivityTemplate, today: date, current_das: int
) -> ScheduleActivity:
    """Reuse an already-materialized ScheduleActivity for this template if
    one exists for the season (whatever its status); otherwise materialize
    one now, dated today. Recovery-only templates (is_conditional=True,
    trigger_conditions=None) are never touched by the Decision Engine, so
    this is the only path that ever creates a ScheduleActivity for them."""
    existing = (
        session.query(ScheduleActivity)
        .filter(
            ScheduleActivity.season_id == season.id,
            ScheduleActivity.template_id == replacement_template.id,
        )
        .order_by(ScheduleActivity.activity_date.desc())
        .first()
    )
    if existing is not None and existing.status == ActivityStatus.PENDING:
        return existing

    new_activity = ScheduleActivity(
        season_id=season.id,
        template_id=replacement_template.id,
        activity_date=today,
        das=current_das,
        name=replacement_template.name,
        category=replacement_template.category,
        status=ActivityStatus.PENDING,
        remarks=replacement_template.default_remarks,
        is_custom=False,
    )
    session.add(new_activity)
    session.flush()
    return new_activity


def build_schedule_snapshot(session: Session, season: Season, today: date | None = None) -> ScheduleSnapshot:
    today = today or date.today()
    current_das = calculate_das(season.sowing_date, as_of=today)

    # 1. Layer 2: let anything newly-triggered materialize first, using the
    #    existing, untouched Decision Engine.
    ctx = build_context_from_observations(session, season, current_das, as_of=today)
    evaluate_and_activate(session, ctx)

    current_stage_seq = stage_sequence_for_das(session, season.crop_template_version_id, current_das)

    due_or_overdue = (
        session.query(ScheduleActivity)
        .filter(
            ScheduleActivity.season_id == season.id,
            ScheduleActivity.status == ActivityStatus.PENDING,
            ScheduleActivity.activity_date <= today,
        )
        .order_by(ScheduleActivity.activity_date, ScheduleActivity.das)
        .all()
    )

    actionable_rows: list[dict] = []
    escalated: list[RecoveryDecision] = []
    auto_skipped_names: list[str] = []
    replaced_names: list[tuple[str, str]] = []
    recovery_reason_by_id: dict = {}
    recovery_flag_by_id: dict = {}
    replacement_flag_by_id: dict = {}

    for activity in due_or_overdue:
        template = (
            session.get(ActivityTemplate, activity.template_id)
            if activity.template_id is not None else None
        )
        decision = evaluate_activity(
            session, activity, template, current_stage_seq,
            season.crop_template_version_id, today, stage_sequence_for_das,
        )

        if decision.outcome == RecoveryOutcome.RECOVER:
            actionable_rows.append(_row_from_activity(activity))
            if decision.days_late > 0:
                recovery_reason_by_id[activity.id] = decision.reason
                recovery_flag_by_id[activity.id] = True

        elif decision.outcome == RecoveryOutcome.REPLACE:
            schedule_repo.mark_skipped(
                session, activity,
                remarks=f"Auto-replaced: {decision.reason}",
            )
            auto_skipped_names.append(activity.name)
            replacement = _get_or_materialize_replacement(
                session, season, decision.replacement_template, today, current_das
            )
            replaced_names.append((activity.name, replacement.name))
            row = _row_from_activity(replacement)
            actionable_rows.append(row)
            recovery_reason_by_id[replacement.id] = decision.reason
            recovery_flag_by_id[replacement.id] = True
            replacement_flag_by_id[replacement.id] = True

        elif decision.outcome == RecoveryOutcome.SKIP:
            schedule_repo.mark_skipped(session, activity, remarks=f"Auto-skipped: {decision.reason}")
            auto_skipped_names.append(activity.name)

        elif decision.outcome == RecoveryOutcome.ESCALATE:
            escalated.append(decision)
            # Deliberately left PENDING -- ESCALATE means "needs a human
            # decision", not "the system decided for them".

    if escalated:
        raise_recovery_alerts(session, season, escalated)

    bundled = operation_bundling.combine_items(actionable_rows, _no_hint)

    operations: list[RecommendedOperation] = []
    for row in bundled:
        member_ids = row.get("ids", [row["id"]])
        is_recovery = any(recovery_flag_by_id.get(i) for i in member_ids)
        is_replacement = any(replacement_flag_by_id.get(i) for i in member_ids)
        reasons = [recovery_reason_by_id[i] for i in member_ids if i in recovery_reason_by_id]
        recovery_reason = " ".join(dict.fromkeys(reasons)) or None
        operations.append(_operation_from_row(row, today, is_recovery, is_replacement, recovery_reason))

    # Most urgent first: escalation-adjacent (replacement) operations and
    # overdue items before merely-due-today ones, earliest date first.
    operations.sort(key=lambda op: (not op.is_replacement, op.recommended_date))

    recommended = operations[0] if operations else None
    also_actionable = operations[1:] if operations else []

    return ScheduleSnapshot(
        recommended=recommended,
        also_actionable=also_actionable,
        escalated=escalated,
        auto_skipped_names=auto_skipped_names,
        replaced_names=replaced_names,
    )
