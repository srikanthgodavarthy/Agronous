# AgroNous Bhindi Physiology Engine v3 — Final Design
Three-layer architecture: Layer 1 (planned operations) / Layer 1.5 (mandatory
assessments, evidence-producing) / Layer 2 (conditional operations,
evidence-gated) / Layer 3 (knowledge cards). This file is the single source
of truth for the v3 build: schema changes, the Decision Engine, and the
complete Bhindi template content reclassified against this model.

---

## PART A — Schema Changes

### A.1 — db/models.py additions

```python
class TriggerCondition(str, enum.Enum):
    """
    Closed vocabulary the Decision Engine matches against a season's live
    CultivationContext. Specific pest/disease identities (not generic
    "PEST_DETECTED") so the evaluator never has to re-classify a vague tag
    -- the AI vision prompt and the trigger vocabulary use the same names.
    Stage and pest/disease evidence are independent condition families,
    never conflated in one assessment row (see Part C).
    """
    # Stage-based -- pure DAS/CropStage lookup, cheapest to evaluate
    STAGE_VEGETATIVE = "STAGE_VEGETATIVE"
    STAGE_FLOWERING = "STAGE_FLOWERING"
    STAGE_FRUITING = "STAGE_FRUITING"
    STAGE_HARVEST = "STAGE_HARVEST"

    # Pest identity -- specific, not generic, populated from a Layer 1.5
    # assessment's Observation.ai_category / farmer note
    PEST_CUTWORM_DAMPING_OFF = "PEST_CUTWORM_DAMPING_OFF"
    PEST_APHID_WHITEFLY_VECTOR = "PEST_APHID_WHITEFLY_VECTOR"
    PEST_FRUIT_SHOOT_BORER = "PEST_FRUIT_SHOOT_BORER"
    PEST_MITE_WHITEFLY = "PEST_MITE_WHITEFLY"
    PEST_SUCKING_COMPLEX = "PEST_SUCKING_COMPLEX"  # thrips/jassids/whitefly bundle

    # Disease identity -- specific
    DISEASE_POWDERY_MILDEW = "DISEASE_POWDERY_MILDEW"
    DISEASE_CERCOSPORA_LEAF_SPOT = "DISEASE_CERCOSPORA_LEAF_SPOT"
    DISEASE_YVMV = "DISEASE_YVMV"
    DISEASE_AGEING_CANOPY = "DISEASE_AGEING_CANOPY"  # late-stage generic watch; the
    # original card text itself is generic ("as needed"), so this stays broad

    # Nutrient deficiency identity -- specific, supports the Mg/Fe additions
    # from the prior agronomic review
    DEFICIENCY_MAGNESIUM = "DEFICIENCY_MAGNESIUM"
    DEFICIENCY_IRON = "DEFICIENCY_IRON"
    DEFICIENCY_POD_TIP_CALCIUM = "DEFICIENCY_POD_TIP_CALCIUM"

    # Weather-derived -- reads a future weather service integration
    RAIN_FORECAST = "RAIN_FORECAST"
    HOT_DRY_SPELL = "HOT_DRY_SPELL"
    HIGH_HUMIDITY = "HIGH_HUMIDITY"


class TriggerLogic(str, enum.Enum):
    ALL = "ALL"  # every condition in trigger_conditions must hold (AND)
    ANY = "ANY"  # at least one condition must hold (OR)
```

### A.2 — ActivityTemplate additions

```python
class ActivityTemplate(Base):
    # ...existing columns unchanged (id, version_id, name, category,
    # day_offset, repeat_interval_days, repeat_count, default_remarks,
    # is_active)...

    is_conditional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True  -> Layer 2: never auto-materializes at season creation; the
    #          Decision Engine materializes it only when trigger_conditions
    #          are satisfied by evidence.
    # False -> Layer 1 or Layer 1.5 (the default, and the only value every
    #          existing v1/v2 row has after migration -- zero behavior
    #          change for past seasons).

    feeds_context: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True on Layer 1.5 rows only: this activity is always scheduled and
    # completed like any Layer 1 row, but its purpose is to produce
    # structured evidence (an Observation tied to it) that the Decision
    # Engine reads, rather than to perform a corrective operation itself.
    # False for ordinary Layer 1 operations and for Layer 2 rows.

    trigger_logic: Mapped[TriggerLogic | None] = mapped_column(
        Enum(TriggerLogic, name="trigger_logic", native_enum=False, length=10), nullable=True
    )
    trigger_conditions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # JSONB list of TriggerCondition.value strings, e.g.
    # ["PEST_FRUIT_SHOOT_BORER", "STAGE_VEGETATIVE"] with trigger_logic=ALL.
    # A list column, not a join table: trigger sets are small (1-3
    # conditions), always read as a whole by the evaluator, never queried
    # independently at the SQL level today. Composite rules (the
    # MG_DEFICIENCY AND VEGETATIVE_STAGE example) are supported from day
    # one without any further schema change -- just more list entries.
```

### A.3 — Migration

```python
"""add layer1.5/layer2 fields to activity_template

Revision ID: <generated>
Revises: 3f27468c5c56
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.add_column('activity_template', sa.Column('is_conditional', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('activity_template', sa.Column('feeds_context', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('activity_template', sa.Column('trigger_logic', sa.String(length=10), nullable=True))
    op.add_column('activity_template', sa.Column('trigger_conditions', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('activity_template', 'trigger_conditions')
    op.drop_column('activity_template', 'trigger_logic')
    op.drop_column('activity_template', 'feeds_context')
    op.drop_column('activity_template', 'is_conditional')
```

`server_default=sa.false()` makes every existing v1/v2 row become
`is_conditional=False, feeds_context=False` (plain Layer 1) with no
behavior change until v3 rows explicitly opt into Layer 1.5/2.

### A.4 — `_parse_remarks` label addition (UI)

`pages/2_Cultivation_Schedule.py`, line 73 — unchanged from the prior
agronomic-review pass, still required so Priority/Indicator render as card
rows rather than falling into "Notes":

```python
REMARK_LABELS = ["Priority", "Product", "Composition", "Dose", "Water", "Method", "Timing", "Indicator", "Objective", "Why", "Precautions", "Purpose", "Benefit", "Notes"]
```

### A.5 — `create_new_version()` extension (seed/crop_master_seed.py)

The activities tuple shape must grow from 6 fields to 9 to carry the new
columns. This is the one place that needs editing outside the new seed
file itself.

```python
# Before
def create_new_version(
    crop_name: str,
    label: str,
    change_notes: str,
    stages: list[tuple[str, int, int, int, str]],
    activities: list[tuple[int, ActivityCategory, str, int | None, int, str]],
) -> None:
    ...
    for day_offset, category, name, repeat_interval, repeat_count, remarks in activities:
        session.add(
            ActivityTemplate(
                version_id=new_version.id,
                name=name,
                category=category,
                day_offset=day_offset,
                repeat_interval_days=repeat_interval,
                repeat_count=repeat_count,
                default_remarks=remarks,
            )
        )

# After
def create_new_version(
    crop_name: str,
    label: str,
    change_notes: str,
    stages: list[tuple[str, int, int, int, str]],
    activities: list[tuple[
        int, ActivityCategory, str, int | None, int, str,
        bool, bool, TriggerLogic | None, list[str] | None,
    ]],
) -> None:
    """
    activities tuple shape (9 trailing fields beyond the original 6):
        (day_offset, category, name, repeat_interval, repeat_count, remarks,
         is_conditional, feeds_context, trigger_logic, trigger_conditions)
    Existing crops seeded before v3 (Tomato, Rice, etc. in CROPS) keep using
    the old 6-tuple shape via a thin wrapper -- see crop_master_seed._activity()
    below -- so this change is additive, not a breaking rewrite of every
    other crop's seed data.
    """
    ...
    for (day_offset, category, name, repeat_interval, repeat_count, remarks,
         is_conditional, feeds_context, trigger_logic, trigger_conditions) in activities:
        session.add(
            ActivityTemplate(
                version_id=new_version.id,
                name=name,
                category=category,
                day_offset=day_offset,
                repeat_interval_days=repeat_interval,
                repeat_count=repeat_count,
                default_remarks=remarks,
                is_conditional=is_conditional,
                feeds_context=feeds_context,
                trigger_logic=trigger_logic,
                trigger_conditions=trigger_conditions,
            )
        )
```

To avoid touching every other crop's existing 6-tuple seed data, add one
small helper alongside `create_new_version` that other crops' seed files
can keep using unchanged:

```python
def _activity(day_offset, category, name, repeat_interval, repeat_count, remarks):
    """Back-compat wrapper: builds a plain Layer-1 9-tuple from the old 6-tuple
    shape, for crops that haven't adopted Layer 1.5/2 yet."""
    return (day_offset, category, name, repeat_interval, repeat_count, remarks,
            False, False, None, None)
```

---

## PART B — services/decision_engine.py (new module)

```python
"""
Decision Engine: evaluates is_conditional=True ActivityTemplate rows
against a season's live CultivationContext and materializes a real
ScheduleActivity the moment a trigger fires -- never before, never
speculatively. Deterministic rules decide; AI/observations only ever
supply facts into CultivationContext. The engine itself makes no model
calls and has no network dependency, so it's fully unit-testable with
hand-built contexts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from db.models import ActivityStatus, ActivityTemplate, ScheduleActivity, Season, TriggerLogic


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
    active_conditions: set[str] = field(default_factory=set)
    # e.g. {"STAGE_VEGETATIVE", "PEST_FRUIT_SHOOT_BORER"}, populated by the
    # caller from CropStage lookup + recent Layer 1.5 Observation.ai_category
    # values + (later) a weather service. The engine never computes these
    # itself -- it only matches against what it's given.


def _trigger_satisfied(template: ActivityTemplate, ctx: CultivationContext) -> bool:
    if not template.is_conditional or not template.trigger_conditions:
        return False
    required = set(template.trigger_conditions)
    if template.trigger_logic == TriggerLogic.ANY:
        return bool(required & ctx.active_conditions)
    return required.issubset(ctx.active_conditions)  # default ALL


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
        new_activities.append(
            ScheduleActivity(
                season_id=ctx.season.id,
                template_id=template.id,
                activity_date=date.today(),
                das=ctx.das,
                name=f"{template.name} (AI Triggered)",
                category=template.category,
                status=ActivityStatus.PENDING,
                remarks=template.default_remarks,
                is_custom=False,
            )
        )

    session.add_all(new_activities)
    session.flush()
    return new_activities


def build_context_from_observations(session: Session, season: Season, das: int) -> CultivationContext:
    """
    Convenience builder: reads recent Observation.ai_category /
    ai_analysis rows for this season and maps them onto TriggerCondition
    values. This is the one place where AI-derived text gets translated
    into the engine's closed vocabulary -- keep that translation here, not
    scattered through UI pages, so it stays a single auditable mapping.
    """
    from db.models import Observation  # local import to avoid circulars

    AI_CATEGORY_TO_CONDITION = {
        # Maps Observation.ai_category (broad, from ai_engine.ALLOWED_CATEGORIES)
        # combined with keyword hints in ai_analysis text to a specific
        # TriggerCondition. A real implementation would refine this with
        # NLP/keyword matching against ai_analysis; shown here as the
        # integration seam, not a finished classifier.
    }

    conditions: set[str] = set()
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

    return CultivationContext(season=season, das=das, active_conditions=conditions)
```

---

## PART C — Bhindi v3 Content: Full Reclassification

50 v2 template rows reclassified. 6 hybrid SPRAY rows split into
assessment (Layer 1.5) + conditional operation (Layer 2) pairs, per the
approved refinement. Stage confirmation and pest scouting are never
combined in one row.

### C.1 — Layer 1 (Planned Operations) — 38 rows, unchanged from v2

Sowing, seed treatment, basal P+K, all irrigation cycles, thinning,
weeding, earthing up, all scheduled fertilizer top-dressings and foliar
nutrition, the two scheduled (non-conditional) FSB-prevention sprays at
DAS 48 and DAS 59 (preventive, pollinator-timed, mode-of-action-rotated --
deliberately Layer 1, not consolidated into the Layer 2 conditional FSB
control; see rationale below), staking/sanitation, residue removal, deep
ploughing, seed collection, season close. No content changes beyond the
prior agronomic-review fixes (DAS overlap correction, explicit
source-sink reasoning text) -- see Part D.

**Why DAS 48/59 stay Layer 1 and are not merged with the Layer 2 "Fruit &
Shoot Borer Control" row**: those two are preventive, calendar-fixed,
mode-of-action-rotated sprays scheduled specifically because flowering and
peak harvest are *known* high-risk windows regardless of confirmed
infestation -- merging them into the evidence-gated Layer 2 control would
remove the rotation discipline that prevents resistance buildup, which
depends on a fixed sequence, not on evidence timing.

### C.2 — Layer 1.5 (Mandatory Assessments) — 8 rows

| DAS | Activity name | feeds_context produces |
|---|---|---|
| 8 | Confirm Stand Establishment – Germination Check & Gap Filling | `PEST_CUTWORM_DAMPING_OFF` (if damage noted) |
| 9 | Seedling Base Inspection – Cutworm/Damping-Off Scouting *(split)* | `PEST_CUTWORM_DAMPING_OFF` |
| 18 | Vector Pest Scouting – Aphid/Whitefly *(split)* | `PEST_APHID_WHITEFLY_VECTOR` |
| 31 | Fruit & Shoot Borer Scouting – Dead Heart Check *(split)* | `PEST_FRUIT_SHOOT_BORER` |
| 39 | Pre-Flowering Mite/Whitefly Scouting *(split)* | `PEST_MITE_WHITEFLY` |
| 40 | Confirm Flowering Onset *(split from old combined DAS-40 row — stage-only, no pest evidence)* | `STAGE_FLOWERING` |
| 58 | Pre-Harvest Sucking Pest Scouting *(split)* | `PEST_SUCKING_COMPLEX` |
| 100 | Ageing Canopy Disease Scouting *(split)* | `DISEASE_AGEING_CANOPY` |

Each Layer 1.5 row's `_card()` Priority is `Essential` (always scheduled,
always completed) and its Indicator field states what evidence to
log: e.g. for DAS 31, `Indicator: "Record presence/absence of wilting
shoot tips (dead hearts) as an Observation note or photo before moving on."`

### C.3 — Layer 2 (Conditional Operations) — 6 rows, crop-operation-named

| Trigger DAS (earliest-eligible) | Activity name (crop-operation oriented) | trigger_conditions | trigger_logic | Specific chemistry (Layer 3 knowledge card only) |
|---|---|---|---|---|
| 9 | **Cutworm & Damping-Off Control** | `["PEST_CUTWORM_DAMPING_OFF"]` | ALL | Chlorpyrifos 20 EC soil drench (unchanged from v2 card) |
| 18 | **Vector Pest Control (Aphid/Whitefly)** | `["PEST_APHID_WHITEFLY_VECTOR"]` | ALL | Neem Oil + Teepol foliar |
| 31 | **Fruit & Shoot Borer Control** | `["PEST_FRUIT_SHOOT_BORER", "STAGE_VEGETATIVE"]` | ALL | Chlorantraniliprole 0.3 ml/L evening spray |
| 39 | **Mite & Whitefly Control** | `["PEST_MITE_WHITEFLY"]` | ALL | Neem Oil evening spray |
| 58 | **Sucking Pest Control** | `["PEST_SUCKING_COMPLEX"]` | ALL | threshold-based, product per scouting severity |
| 100 | **Disease Control – Ageing Canopy** | `["DISEASE_AGEING_CANOPY"]` | ALL | Wettable Sulphur or Propiconazole, as per v2 card |

Activity `name` carries zero chemistry — only the crop-operation intent.
`default_remarks` (Layer 3) carries the full original `_card()` content
(Product/Composition/Dose/Water/Method/Timing/Indicator/Objective/Why/
Precautions) exactly as in v2, meaning the chemical recommendation can be
revised in a future CropTemplateVersion bump without ever touching the
operation name a farmer sees, and without that revision reading as a
different *kind* of task.

### C.4 — Row count summary

| Layer | v2 (before) | v3 (after) |
|---|---|---|
| Layer 1 (planned) | 50 (undifferentiated) | 38 |
| Layer 1.5 (assessment) | 0 (folded into Layer 1) | 8 |
| Layer 2 (conditional) | 0 (was scheduled regardless) | 6 |
| **Total template rows** | **50** | **52** |
| **Always-on calendar rows a farmer sees by default** | **50** | **46** (38 + 8) |

The farmer's default schedule drops from 50 to 46 always-on rows -- inside
the 45-50 target -- while total template rows rise slightly to 52, because
splitting hybrid scouting+spray rows into separate assessment and
conditional-operation rows is, correctly, additive at the data level even
as it's subtractive at the calendar level the farmer actually experiences.

---

## PART D — Carried-forward content fixes (from the prior agronomic review)

Unchanged in substance, applied to the new Layer 1 rows in v3:
- DAS overlap bug fix (Stage 6 "Fruit Development" day_offset corrected
  from 52→63 for the three misfiled Peak Harvest rows; stage description
  prose corrected to match its own DAS 56-62 tuple).
- Conditional Magnesium foliar added to Stage 2 (DAS 22, `Priority:
  Conditional`, gated in v3 properly as a Layer 2 row:
  `trigger_conditions=["DEFICIENCY_MAGNESIUM"]`, with a corresponding
  Layer 1.5 visual-symptom assessment row preceding it, mirroring the
  pest/disease pattern established in Part C).
- Conditional Iron correction at basal stage (DAS 0, soil-type gated --
  stays a Layer 1 row with `Priority: Conditional` in its knowledge card
  text, since soil type is a farm attribute set once at season creation,
  not an evidence stream the Decision Engine needs to evaluate repeatedly).
- Calcium foliar added to Peak Harvest (DAS 70, now properly a Layer 2 row:
  `trigger_conditions=["DEFICIENCY_POD_TIP_CALCIUM"]`, gated behind a new
  Layer 1.5 "Pod-Tip Browning Check" assessment row at DAS 65).
- Stage descriptions promoted to literal "Before moving to the next stage
  verify: (1)... (2)... (3)..." checklists (Layer 3 stage-level content,
  CropStage.description, zero schema impact).

---

## PART E — seed/bhendi_physiology_v3.py skeleton

```python
"""
Bhindi (Okra) -- Decision-Oriented Crop Advisory Engine (v3)
================================================================
Layer 1 / Layer 1.5 / Layer 2 / Layer 3 architecture per the AgroNous
standard template model. See docs/bhindi_v3_design.md (this file) for the
full reclassification rationale; this module is the executable seed.

Run with:  python -m seed.bhendi_physiology_v3
(Run AFTER seed.crop_master_seed AND the Part A migration.)
"""
from __future__ import annotations

from db.models import ActivityCategory, TriggerLogic
from seed.crop_master_seed import create_new_version

STAGES = [
    # ...9 stages, same shape as v2, with Part D checklist-phrasing applied...
]


def _card(*, priority, category, product, dosage, method, timing,
          purpose, benefit, precautions, composition=None, water_volume=None,
          indicator=None) -> str:
    parts = [f"Priority: {priority}.", f"Product: {product}."]
    if composition:
        parts.append(f"Composition: {composition}.")
    parts.append(f"Dose: {dosage}.")
    if water_volume:
        parts.append(f"Water: {water_volume}.")
    parts.append(f"Method: {method}.")
    parts.append(f"Timing: {timing}.")
    if indicator:
        parts.append(f"Indicator: {indicator}.")
    parts.append(f"Objective: {benefit}")
    parts.append(f"Why: {purpose}")
    parts.append(f"Precautions: {precautions}")
    return " ".join(parts)


def _layer1(day_offset, category, name, repeat_interval, repeat_count, remarks):
    return (day_offset, category, name, repeat_interval, repeat_count, remarks,
            False, False, None, None)


def _layer1_5(day_offset, category, name, remarks):
    """Mandatory assessment: always scheduled, produces evidence, never conditional."""
    return (day_offset, category, name, None, 1, remarks, False, True, None, None)


def _layer2(day_offset, category, name, remarks, trigger_conditions, trigger_logic=TriggerLogic.ALL):
    """Conditional operation: never auto-materializes; Decision Engine gates it."""
    return (day_offset, category, name, None, 1, remarks, True, False, trigger_logic, trigger_conditions)


ACTIVITIES = [
    # === Layer 1 rows (38) — identical to v2 content, DAS-overlap-corrected ===
    _layer1(0, ActivityCategory.SOWING, "Establish Roots - Sowing at Correct Depth", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Direct Seed Sowing",
        dosage="Seed rate 3-4 kg/acre; spacing 60 x 30 cm; depth 2-3 cm",
        method="Dibbling/drilling into moist soil", timing="Morning, into adequate soil moisture",
        purpose="Correct depth and spacing gives the radicle a uniform, undisturbed path "
                "to establish the primary root before lateral branching begins.",
        benefit="Uniform germination and a stand geometry that supports full-season "
                "canopy development and picking access.",
        precautions="Do not sow into waterlogged or crusted soil; uneven depth causes "
                    "staggered, weak emergence.",
    )),
    # ... remaining 37 Layer 1 rows follow the same _layer1(...) pattern,
    # carrying forward all v2 content plus the Priority field and the
    # Part D fixes (DAS 63 for the three corrected Peak Harvest rows,
    # explicit S/source-sink reasoning text, Mg/Fe/Ca additions as their
    # own properly-gated Layer 1/1.5/2 trios) ...

    # === Layer 1.5 rows (8) — mandatory assessments ===
    _layer1_5(9, ActivityCategory.SPRAY, "Seedling Base Inspection - Cutworm/Damping-Off Scouting", _card(
        priority="Essential", category="Pest Monitoring (IPM)", product="Field Scouting",
        dosage="Not applicable", method="Visual check of plant base for cut/wilted seedlings",
        timing="DAS 7-12, daily during establishment",
        indicator="Record presence/absence of cut stems at soil line as an Observation "
                  "note or photo before moving on -- this evidence gates the conditional "
                  "Cutworm & Damping-Off Control operation below.",
        purpose="Cutworms sever the stem at the soil line before lignification; this "
                "scouting pass is the evidence-gathering step the Decision Engine reads "
                "to decide whether the corrective drench is actually needed.",
        benefit="Produces the field evidence that determines whether intervention is warranted.",
        precautions="Inspect a representative sample across the field, not just the edges.",
    )),
    # ... remaining 7 Layer 1.5 rows follow the same pattern (DAS 8, 18,
    # 31, 39, 40 [stage-only], 58, 100, plus the new DAS 65 pod-tip-Ca check) ...

    # === Layer 2 rows (6 original + 1 new Ca, 1 new Mg = 8) — conditional operations ===
    _layer2(9, ActivityCategory.SPRAY, "Cutworm & Damping-Off Control", _card(
        priority="Conditional", category="Insecticide (threshold-based)", product="Chlorpyrifos 20 EC",
        composition="Chlorpyrifos 20% EC", dosage="2.5 ml/L, soil-drench at base",
        water_volume="As needed for spot drenching", method="Soil drench at plant base",
        timing="Only on confirmed cutworm damage from the preceding scouting assessment",
        purpose="Cutworms sever the stem at the soil line, a point of mechanical "
                "vulnerability before the stem lignifies; damage here kills the whole plant.",
        benefit="Prevents stand loss that would otherwise require costly re-sowing.",
        precautions="Spot-treat only where damage is confirmed; avoid blanket spraying. "
                    "Pollinator risk is negligible at this pre-flowering stage.",
    ), trigger_conditions=["PEST_CUTWORM_DAMPING_OFF"]),
    # ... remaining 7 Layer 2 rows follow the same _layer2(...) pattern,
    # per the Part C.3 table, with chemistry confined entirely to the
    # _card() body and never the activity name ...
]


def seed_bhendi_v3() -> None:
    create_new_version(
        crop_name="Bhindi (Okra)",
        label="v3 - Layer 1/1.5/2/3 Decision-Oriented Advisory Engine",
        change_notes=(
            "Introduces the AgroNous standard template architecture: Layer 1 "
            "planned operations, Layer 1.5 mandatory evidence-producing "
            "assessments, Layer 2 conditional operations gated by explicit "
            "TriggerCondition rules evaluated by the new Decision Engine, "
            "and Layer 3 knowledge cards carrying all product/dose/chemistry "
            "detail so it can evolve without touching the cultivation "
            "template. Reduces the farmer's default visible schedule from "
            "50 to 46 rows by moving 6 evidence-gated sprays out of the "
            "always-on calendar. Fixes the Stage 6/7 DAS overlap bug, adds "
            "Magnesium/Iron/Calcium coverage previously missing from the "
            "nutrient sequence, and makes existing product-selection "
            "reasoning explicit in purpose text."
        ),
        stages=STAGES,
        activities=ACTIVITIES,
    )


if __name__ == "__main__":
    seed_bhendi_v3()
```

This skeleton shows the pattern for all 52 rows via one fully-worked
example per layer (Layer 1 sowing, Layer 1.5 cutworm scouting, Layer 2
cutworm control) -- the remaining rows are mechanical applications of the
same `_layer1`/`_layer1_5`/`_layer2` helpers against the Part C.1-C.3
tables and the Part D content fixes, carrying forward all existing v2
`_card()` field values unchanged except for the `priority` and `indicator`
additions.
