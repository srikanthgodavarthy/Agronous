"""
Decision Engine: evaluates is_conditional=True ActivityTemplate rows
(Layer 2) against a season's live CultivationContext and materializes a
real ScheduleActivity the moment a trigger fires -- never before, never
speculatively. Deterministic rules decide; AI/observations only ever
supply facts into CultivationContext. The engine itself makes no model
calls and has no network dependency, so it's fully unit-testable with
hand-built contexts.

Growth note: trigger_conditions/trigger_logic on ActivityTemplate is
intentionally the simplest mechanism that supports today's closed-vocabulary
AND/OR matching. If conditional logic needs to grow substantially richer
(numeric thresholds, evidence decay windows, multi-step rule chains,
per-farm overrides), introduce a dedicated DecisionRule entity rather than
continuing to expand ActivityTemplate -- see the note on
ActivityTemplate.trigger_conditions in db/models.py.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from db.models import ActivityStatus, ActivityTemplate, Observation, ScheduleActivity, Season, TriggerLogic


@dataclass
class CultivationContext:
    """
    The full set of facts the Decision Engine may reason over for one
    season, as of one evaluation moment. Built by the caller (dashboard
    refresh, or right after an Observation is saved) from existing
    repositories -- this dataclass has no DB access of its own.
    """
    season: Season
    das: int
    as_of: date
    # The calendar date this context represents. The engine always derives
    # the materialized ScheduleActivity.activity_date from this field, never
    # from date.today() directly -- this is what makes evaluate_and_activate
    # replayable against a past or simulated date (e.g. backfilling, testing,
    # or re-evaluating "what would have triggered on DAS 31") rather than
    # being silently pinned to whenever the function happens to run.
    active_conditions: set[str] = field(default_factory=set)
    # e.g. {"STAGE_VEGETATIVE", "PEST_FRUIT_SHOOT_BORER"}, populated by the
    # caller from CropStage lookup + recent Layer 1.5 Observation.ai_category
    # values + (later) a weather service. The engine never computes these
    # itself -- it only matches against what it's given.
    condition_sources: dict[str, uuid.UUID] = field(default_factory=dict)
    # Optional: maps a TriggerCondition value -> the Observation.id that
    # produced it, for conditions derived from field evidence rather than a
    # pure stage lookup. Used only to populate
    # ScheduleActivity.triggered_by_observation_id provenance; absence of an
    # entry (e.g. for stage-only conditions) just means that field stays
    # NULL on materialization.


def _trigger_satisfied(template: ActivityTemplate, ctx: CultivationContext) -> bool:
    if not template.is_conditional or not template.trigger_conditions:
        return False
    required = set(template.trigger_conditions)
    if template.trigger_logic == TriggerLogic.ANY:
        return bool(required & ctx.active_conditions)
    return required.issubset(ctx.active_conditions)  # default ALL


def _matched_condition(template: ActivityTemplate, ctx: CultivationContext) -> str | None:
    """
    The specific condition that satisfied this template's trigger, for
    provenance. For ALL logic with multiple required conditions there's no
    single "the" cause, so we record the first (by template order) that's
    also present in ctx -- the full required set is always still
    recoverable from the template itself.
    """
    if not template.trigger_conditions:
        return None
    satisfied = [c for c in template.trigger_conditions if c in ctx.active_conditions]
    return satisfied[0] if satisfied else None


def evaluate_and_activate(session: Session, ctx: CultivationContext) -> list[ScheduleActivity]:
    """
    Check every Layer 2 template for this season's crop_template_version
    against ctx; materialize a ScheduleActivity for any whose trigger just
    became satisfied and that hasn't already been materialized. Idempotent
    via template_id + season_id existence check, so re-running this on
    every dashboard load never creates duplicates.
    """
    templates = (
        session.query(ActivityTemplate)
        .filter(
            ActivityTemplate.version_id == ctx.season.crop_template_version_id,
            ActivityTemplate.is_conditional.is_(True),
            ActivityTemplate.is_active.is_(True),
        )
        .all()
    )

    already_materialized = {
        a.template_id
        for a in session.query(ScheduleActivity)
        .filter(ScheduleActivity.season_id == ctx.season.id)
        .all()
        if a.template_id is not None
    }

    new_activities: list[ScheduleActivity] = []
    for template in templates:
        if template.id in already_materialized:
            continue
        if not _trigger_satisfied(template, ctx):
            continue

        matched_condition = _matched_condition(template, ctx)
        new_activities.append(
            ScheduleActivity(
                season_id=ctx.season.id,
                template_id=template.id,
                activity_date=ctx.as_of,
                das=ctx.das,
                name=f"{template.name} (AI Triggered)",
                category=template.category,
                status=ActivityStatus.PENDING,
                remarks=template.default_remarks,
                is_custom=False,
                triggered_by_condition=matched_condition,
                triggered_by_observation_id=(
                    ctx.condition_sources.get(matched_condition) if matched_condition else None
                ),
            )
        )

    session.add_all(new_activities)
    session.flush()
    return new_activities


def build_context_from_observations(
    session: Session, season: Season, das: int, as_of: date | None = None
) -> CultivationContext:
    """
    Convenience builder: reads recent Observation.ai_category /
    ai_analysis rows for this season and maps them onto TriggerCondition
    values. This is the one place where AI-derived text gets translated
    into the engine's closed vocabulary -- keep that translation here, not
    scattered through UI pages, so it stays a single auditable mapping.

    `as_of` defaults to today only at this convenience-builder boundary
    (the one legitimate place "now" enters the system); the engine itself
    (evaluate_and_activate) always takes as_of from the context handed to
    it and never calls date.today() internally.
    """
    as_of = as_of or date.today()

    AI_CATEGORY_TO_CONDITION = {
        # Maps Observation.ai_category (broad, from ai_engine.ALLOWED_CATEGORIES)
        # combined with keyword hints in ai_analysis text to a specific
        # TriggerCondition. A real implementation would refine this with
        # NLP/keyword matching against ai_analysis; shown here as the
        # integration seam, not a finished classifier.
    }

    conditions: set[str] = set()
    condition_sources: dict[str, uuid.UUID] = {}

    # Stage conditions from CropStage lookup
    from services.schedule_engine import current_stage_name
    stage_name = current_stage_name(session, season.crop_template_version_id, das) or ""
    if "Vegetative" in stage_name:
        conditions.add("STAGE_VEGETATIVE")
    elif "Flower" in stage_name:
        conditions.add("STAGE_FLOWERING")
    elif "Fruit" in stage_name or "Harvest" in stage_name:
        conditions.add("STAGE_FRUITING")

    recent_obs = (
        session.query(Observation)
        .filter(Observation.season_id == season.id, Observation.ai_category.isnot(None))
        .order_by(Observation.observed_at.desc())
        .limit(10)
        .all()
    )
    for obs in recent_obs:
        mapped = AI_CATEGORY_TO_CONDITION.get(obs.ai_category)
        if mapped:
            conditions.add(mapped)
            condition_sources.setdefault(mapped, obs.id)

    return CultivationContext(
        season=season,
        das=das,
        as_of=as_of,
        active_conditions=conditions,
        condition_sources=condition_sources,
    )
