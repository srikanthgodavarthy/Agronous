"""
ORM models for Cultivation.

Design notes
------------
Two clearly separated halves:

1. MASTER DATA (crop-driven engine, admin-curated, shared across all users):
   - CropMaster, CropTemplateVersion, CropStage, ActivityTemplate
   These tables encode "what happens, generically, during a tomato crop" etc.
   The application never hardcodes a crop name, stage name, fertilizer name,
   or day offset in Python -- it is all rows in these tables.

   CropMaster is versioned: CropStage and ActivityTemplate rows belong to a
   specific CropTemplateVersion, not directly to a CropMaster. This lets
   agronomic recommendations evolve over time (e.g. a revised fertilizer
   dose next season) without rewriting the schedule that was actually
   generated for a season sown under last year's recommendations. Exactly
   one version per crop is marked `is_current`; new seasons always pick up
   the current version at creation time, while existing seasons keep
   pointing at whichever version they were generated from, forever.

2. TENANT DATA (per-user, per-farm, per-season):
   - Farm, Season, ScheduleActivity, Expense, Revenue, Observation, Alert
   ScheduleActivity rows are *generated* from ActivityTemplate rows when a
   Season is created (see services/schedule_engine.py), then become
   independently editable (mark complete, reschedule, add remarks, or insert
   ad-hoc custom activities not present in any template).

   Observation rows capture free-form field notes and optional photos,
   independent of the fixed schedule -- the raw material an AI engine
   (services/ai_engine.py) can later analyze for pest/disease detection or
   recommendations, without that analysis ever overwriting what the farmer
   actually typed or photographed.

All tenant tables carry a `user_id` (UUID, matching Supabase auth.users.id)
either directly or transitively through farm/season, and Supabase Row Level
Security policies (see migrations) enforce isolation at the database level
as defense-in-depth alongside application-level filtering.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ActivityCategory(str, enum.Enum):
    LAND_PREPARATION = "LAND_PREPARATION"
    SOWING = "SOWING"
    IRRIGATION = "IRRIGATION"
    FERTILIZER = "FERTILIZER"
    SPRAY = "SPRAY"
    WEEDING = "WEEDING"
    HARVEST = "HARVEST"
    OTHER = "OTHER"

    # Human-readable labels for display in UI
    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


class ActivityStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"

    @property
    def label(self) -> str:
        return self.name.title()


class ExpenseCategory(str, enum.Enum):
    SEED = "SEED"
    FERTILIZER = "FERTILIZER"
    CHEMICALS = "CHEMICALS"
    LABOUR = "LABOUR"
    IRRIGATION = "IRRIGATION"
    MACHINERY = "MACHINERY"
    TRANSPORT = "TRANSPORT"
    MISCELLANEOUS = "MISCELLANEOUS"

    @property
    def label(self) -> str:
        return self.name.title()


class SeasonStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"

    @property
    def label(self) -> str:
        return self.name.title()


class AlertPriority(str, enum.Enum):
    GREEN = "GREEN"     # Upcoming
    YELLOW = "YELLOW"  # Due soon
    RED = "RED"         # Overdue

    @property
    def label(self) -> str:
        return self.name.title()


class ObservationSource(str, enum.Enum):
    FARMER = "FARMER"   # Manually logged note/photo
    AI = "AI"           # Derived/added by the AI engine (e.g. auto-tagged category)

    @property
    def label(self) -> str:
        return self.name.title()


class TriggerCondition(str, enum.Enum):
    """
    Closed vocabulary the Decision Engine matches against a season's live
    CultivationContext. Specific pest/disease identities (not generic
    "PEST_DETECTED") so the evaluator never has to re-classify a vague tag
    -- the AI vision prompt and the trigger vocabulary use the same names.
    Stage and pest/disease evidence are independent condition families,
    never conflated in one assessment row.
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

    # Nutrient deficiency identity -- specific
    DEFICIENCY_MAGNESIUM = "DEFICIENCY_MAGNESIUM"
    DEFICIENCY_IRON = "DEFICIENCY_IRON"
    DEFICIENCY_POD_TIP_CALCIUM = "DEFICIENCY_POD_TIP_CALCIUM"

    # Weather-derived -- reads a future weather service integration
    RAIN_FORECAST = "RAIN_FORECAST"
    HOT_DRY_SPELL = "HOT_DRY_SPELL"
    HIGH_HUMIDITY = "HIGH_HUMIDITY"

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


class TriggerLogic(str, enum.Enum):
    ALL = "ALL"  # every condition in trigger_conditions must hold (AND)
    ANY = "ANY"  # at least one condition must hold (OR)


class RecoveryStrategy(str, enum.Enum):
    """
    What to do with a PENDING activity once it's overdue AND has passed its
    own valid_until_stage/max_delay_days window (evaluated by
    services.decisions.recovery_engine). Never set for an activity that's
    simply late-but-still-valid -- that case is always "do it now, just
    late" and needs no authored strategy at all.
    """
    REPLACE  = "REPLACE"   # swap in replacement_template instead
    SKIP     = "SKIP"      # auto-skip; nothing left to recommend
    ESCALATE = "ESCALATE"  # needs a human/agronomist decision; raise an alert


# ---------------------------------------------------------------------------
# MASTER DATA -- the "Crop Master Template" engine (versioned)
# ---------------------------------------------------------------------------

class CropMaster(Base):
    """
    A crop type, e.g. 'Tomato', 'Cotton', 'Rice'. Independent of variety --
    variety is a free-text attribute on the Season, since stage timing is
    driven by days-after-sowing offsets that are usually similar across
    varieties of the same crop. (Extensible later to per-variety templates
    via an optional variety_id column without breaking this schema.)

    Holds no schedule data itself -- that lives in versioned
    CropTemplateVersion rows below, so agronomic recommendations can evolve
    over time without altering what was actually recommended in the past.
    """
    __tablename__ = "crop_master"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_duration_days: Mapped[int] = mapped_column(nullable=False, default=120)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["CropTemplateVersion"]] = relationship(
        back_populates="crop", cascade="all, delete-orphan", order_by="CropTemplateVersion.version_number"
    )
    seasons: Mapped[list["Season"]] = relationship(back_populates="crop")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CropMaster {self.name}>"


class CropTemplateVersion(Base):
    """
    One immutable snapshot of "how we recommend growing this crop", as of a
    point in time. CropStage and ActivityTemplate rows hang off a specific
    version, not directly off CropMaster.

    Exactly one version per crop should have `is_current = True` at any
    time -- that's the version offered when a farmer starts a *new* Season.
    Existing seasons keep referencing whichever version they were created
    against (Season.crop_template_version_id), so revising next year's
    fertilizer dose never rewrites the historical record of what an
    in-progress or completed season was actually told to do.

    Superseding a version is additive: create a new CropTemplateVersion row
    with version_number + 1, copy/adjust its stages and templates, then flip
    is_current. The old version row, and everything generated from it,
    stays untouched forever -- this is what makes the design safe for
    retrospective analysis ("did following the schedule correlate with
    yield?") even as recommendations change.
    """
    __tablename__ = "crop_template_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop_master.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    label: Mapped[str | None] = mapped_column(String(150), nullable=True)  # e.g. "2026 Rabi revision"
    change_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crop: Mapped["CropMaster"] = relationship(back_populates="versions")
    stages: Mapped[list["CropStage"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="CropStage.sequence"
    )
    activity_templates: Mapped[list["ActivityTemplate"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="ActivityTemplate.day_offset"
    )
    seasons: Mapped[list["Season"]] = relationship(back_populates="crop_template_version")

    __table_args__ = (
        UniqueConstraint("crop_id", "version_number", name="uq_crop_template_version_number"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CropTemplateVersion crop_id={self.crop_id} v{self.version_number}>"


class CropStage(Base):
    """
    A growth stage of a crop, e.g. 'Germination', 'Vegetative', 'Flowering',
    'Maturity'. Defined by a day-after-sowing (DAS) range. Used to compute
    "Current Stage" on the dashboard purely by looking up which stage's
    range contains today's DAS -- no stage logic lives in Python.
    """
    __tablename__ = "crop_stage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crop_template_version.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)  # display/order
    start_day: Mapped[int] = mapped_column(nullable=False)  # DAS start (inclusive)
    end_day: Mapped[int] = mapped_column(nullable=False)    # DAS end (inclusive)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped["CropTemplateVersion"] = relationship(back_populates="stages")

    __table_args__ = (UniqueConstraint("version_id", "sequence", name="uq_crop_stage_sequence"),)


class ActivityTemplate(Base):
    """
    A single recurring/scheduled activity definition for a crop template
    version, expressed purely as an offset in days-after-sowing. This is
    what gets "exploded" into concrete ScheduleActivity rows (with real
    calendar dates) the moment a farmer creates a Season against this
    version.

    Examples of rows (data, not code):
      (v1, day_offset=0,  category=SOWING,    name='Transplanting')
      (v1, day_offset=21, category=FERTILIZER,name='CAN Top Dressing')
      (v1, day_offset=45, category=SPRAY,     name='Pest Spray - Stem Borer')
      (v1, day_offset=110,category=HARVEST,   name='Harvest')

    repeat_interval_days + repeat_count optionally generate multiple
    occurrences (e.g. irrigation every 7 days, 10 times) from a single
    template row, keeping the master table compact.
    """
    __tablename__ = "activity_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crop_template_version.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ActivityCategory] = mapped_column(
        Enum(ActivityCategory, name="activity_category", native_enum=False, length=30), nullable=False
    )
    day_offset: Mapped[int] = mapped_column(nullable=False)  # DAS the first occurrence falls on
    repeat_interval_days: Mapped[int | None] = mapped_column(nullable=True)  # e.g. every 7 days
    repeat_count: Mapped[int] = mapped_column(default=1, nullable=False)    # how many occurrences total
    default_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Layer 1.5 / Layer 2 fields (decision-oriented advisory engine) ---
    is_conditional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True  -> Layer 2: never auto-materializes at season creation; the
    #          Decision Engine (services/decision_engine.py) materializes it
    #          only when trigger_conditions are satisfied by evidence.
    # False -> Layer 1 or Layer 1.5 (the default, and the only value every
    #          pre-v3 row has -- zero behavior change for past seasons).

    feeds_context: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True on Layer 1.5 rows only: this activity is always scheduled and
    # completed like any Layer 1 row, but its purpose is to produce
    # structured evidence (an Observation tied to it) that the Decision
    # Engine reads, rather than to perform a corrective operation itself.
    # False for ordinary Layer 1 operations and for Layer 2 rows.

    trigger_logic: Mapped["TriggerLogic | None"] = mapped_column(
        Enum(TriggerLogic, name="trigger_logic", native_enum=False, length=10), nullable=True
    )
    trigger_conditions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # JSONB list of TriggerCondition.value strings, e.g.
    # ["PEST_FRUIT_SHOOT_BORER", "STAGE_VEGETATIVE"] with trigger_logic=ALL.
    # A list column, not a join table: trigger sets are small (1-3
    # conditions), always read as a whole by the evaluator, never queried
    # independently at the SQL level today. Composite rules are supported
    # from day one without any further schema change -- just more list
    # entries.
    #
    # NOTE -- growth path: if conditional logic grows substantially richer
    # (e.g. numeric thresholds, time-windowed evidence decay, multi-step
    # rule chains, per-farm overrides), introduce a dedicated `DecisionRule`
    # entity (its own table, FK'd from ActivityTemplate) rather than
    # continuing to bolt more columns onto ActivityTemplate. The current
    # trigger_logic/trigger_conditions pair is intentionally the simplest
    # thing that works for closed-vocabulary AND/OR matching; it is not
    # meant to grow into a general rule engine in place.

    # --- Recovery metadata (services/decisions/recovery_engine.py) ---
    # Together these answer "what should happen if this activity is still
    # PENDING once it's overdue" -- read by the Recovery Engine, never by
    # the schedule/decision engines directly. All nullable: a template with
    # none of these set behaves exactly as before (recovery_engine falls
    # back to a generic category-based heuristic) -- zero behavior change
    # for existing/legacy rows.
    valid_until_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Name of the last CropStage (within the same version) this activity is
    # still agronomically valid to perform in. Once the plant's current
    # stage is later than this one, the activity's window has closed. NULL
    # means "no stage-based expiry" (e.g. harvest/record-keeping rows).
    max_delay_days: Mapped[int | None] = mapped_column(nullable=True)
    # Alternative/complementary grace period, in days past this activity's
    # own planned date, after which it's considered expired even if the
    # stage check alone wouldn't yet say so. NULL = no day-based cap.
    recovery_type: Mapped["RecoveryStrategy | None"] = mapped_column(
        Enum(RecoveryStrategy, name="recovery_strategy", native_enum=False, length=20), nullable=True
    )
    # What to do once the window above has closed. NULL = no recovery
    # strategy authored yet (legacy fallback heuristic applies).
    replacement_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_template.id", ondelete="SET NULL"), nullable=True
    )
    # Only meaningful when recovery_type == REPLACE: the ActivityTemplate
    # (within the same version) to recommend instead, e.g. a vegetative
    # Nitrogen top-dressing whose window closed points here at a Flowering
    # Nutrition Program template.
    expected_impact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Short human-readable note surfaced on the recommendation card
    # explaining the consequence of the recovery/replacement decision, e.g.
    # "Vegetative N window closed; flowering nutrition partially compensates."

    replacement_template: Mapped["ActivityTemplate | None"] = relationship(
        remote_side=[id], foreign_keys=[replacement_template_id]
    )

    version: Mapped["CropTemplateVersion"] = relationship(back_populates="activity_templates")


# ---------------------------------------------------------------------------
# TENANT DATA -- per-user farms, seasons, schedules, money
# ---------------------------------------------------------------------------

class Farm(Base):
    __tablename__ = "farm"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_area: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    area_unit: Mapped[str] = mapped_column(String(20), default="Acres", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    seasons: Mapped[list["Season"]] = relationship(back_populates="farm", cascade="all, delete-orphan")


class Season(Base):
    """
    A single cultivation cycle: one crop, one variety, one sowing date, one
    area, on one farm. This is the unit the whole dashboard revolves around.

    Pins crop_template_version_id at creation time (the CropMaster's
    is_current version as of that moment). The schedule engine always reads
    templates through this version, never through crop_id directly, so a
    later revision to the crop's recommended schedule cannot retroactively
    alter what an existing season was told to do. crop_id is kept alongside
    purely for convenient filtering/display ("seasons of Rice across all
    versions") without an extra join.
    """
    __tablename__ = "season"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm.id", ondelete="CASCADE"), nullable=False)
    crop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop_master.id"), nullable=False)
    crop_template_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crop_template_version.id"), nullable=False
    )

    variety: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sowing_date: Mapped[date] = mapped_column(Date, nullable=False)
    area: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    area_unit: Mapped[str] = mapped_column(String(20), default="Acres", nullable=False)
    status: Mapped[SeasonStatus] = mapped_column(
        Enum(SeasonStatus, name="season_status", native_enum=False, length=20),
        default=SeasonStatus.ACTIVE,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    farm: Mapped["Farm"] = relationship(back_populates="seasons")
    crop: Mapped["CropMaster"] = relationship(back_populates="seasons")
    crop_template_version: Mapped["CropTemplateVersion"] = relationship(back_populates="seasons")
    activities: Mapped[list["ScheduleActivity"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", order_by="ScheduleActivity.activity_date"
    )
    expenses: Mapped[list["Expense"]] = relationship(back_populates="season", cascade="all, delete-orphan")
    revenues: Mapped[list["Revenue"]] = relationship(back_populates="season", cascade="all, delete-orphan")
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", order_by="Observation.observed_at.desc()"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="season", cascade="all, delete-orphan")


class ScheduleActivity(Base):
    """
    A concrete, dated activity on a specific season's timeline. Generated in
    bulk from ActivityTemplate rows at season-creation time, then lives
    independently -- editable, completable, deletable, or insertable ad hoc
    (template_id is NULL for user-added custom activities).
    """
    __tablename__ = "schedule_activity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_template.id", ondelete="SET NULL"), nullable=True
    )

    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    das: Mapped[int] = mapped_column(nullable=False)  # days after sowing, snapshot at generation/edit time
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ActivityCategory] = mapped_column(
        Enum(ActivityCategory, name="activity_category", native_enum=False, length=30), nullable=False
    )
    status: Mapped[ActivityStatus] = mapped_column(
        Enum(ActivityStatus, name="activity_status", native_enum=False, length=20),
        default=ActivityStatus.PENDING,
        nullable=False,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- Provenance for Layer 2 (Decision Engine-materialized) activities ---
    # Both NULL for every ordinary Layer 1-generated or user-added custom
    # activity. Populated only when services.decision_engine.evaluate_and_activate
    # materializes a Layer 2 ActivityTemplate, so a farmer (or support) can
    # always answer "why did this show up on my schedule?" without guessing.
    triggered_by_condition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The specific TriggerCondition.value that satisfied this row's trigger
    # (for ANY logic with multiple satisfied conditions, the first matched;
    # the full required set is still recoverable from the template).
    triggered_by_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observation.id", ondelete="SET NULL"), nullable=True
    )
    # The specific Observation row whose evidence (ai_category / farmer note)
    # produced the matched condition, where the trigger came from an
    # observation rather than a pure stage lookup. Nullable because
    # stage-only triggers (e.g. STAGE_FLOWERING) have no originating
    # Observation to point to.

    season: Mapped["Season"] = relationship(back_populates="activities")


class Expense(Base):
    __tablename__ = "expense"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        Enum(ExpenseCategory, name="expense_category", native_enum=False, length=30), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    season: Mapped["Season"] = relationship(back_populates="expenses")


class Revenue(Base):
    __tablename__ = "revenue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    buyer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(20), default="Quintal", nullable=False)
    price_per_unit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # quantity * price_per_unit, stored for audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    season: Mapped["Season"] = relationship(back_populates="revenues")


class Observation(Base):
    """
    A field observation: a free-form note and/or photo logged against a
    season, independent of the fixed cultivation schedule. This is the raw
    material an AI engine (services/ai_engine.py) can analyze for
    pest/disease detection, growth-stage confirmation, or recommendations.

    Design intent: the farmer's own input (notes, photo) and any AI-derived
    output (ai_analysis, ai_confidence, ai_recommendation) are stored in
    separate columns, never overwriting one another. A farmer's photo and
    caption stay exactly as entered even after an AI pass runs against it;
    re-running analysis (e.g. with an improved model) only ever updates the
    ai_* columns, never the farmer's own words. `source` records who created
    the row -- a farmer-logged note enriched by AI stays source=FARMER, since
    the row's authorship doesn't change; AI-only writes (e.g. a fully
    automated satellite-imagery check with no farmer input) would use
    source=AI.
    """
    __tablename__ = "observation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[ObservationSource] = mapped_column(
        Enum(ObservationSource, name="observation_source", native_enum=False, length=10),
        default=ObservationSource.FARMER,
        nullable=False,
    )

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Supabase Storage object path/URL

    # AI-derived fields, populated by services/ai_engine.py. Always nullable
    # and always additive -- never required for an Observation to exist, and
    # never overwriting farmer-entered `note`/`image_url` above.
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)        # human-readable summary
    ai_category: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "Pest", "Nutrient Deficiency"
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)  # 0.000-1.000
    ai_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # full provider payload, for audit/debug
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    season: Mapped["Season"] = relationship(back_populates="observations")


class Alert(Base):
    """
    Materialized alerts derived from ScheduleActivity. Recomputed (upserted)
    each time the dashboard/alerts page loads rather than via a background
    job, since Streamlit has no persistent worker by default. Storing them
    lets us track dismissed/seen state if needed later.
    """
    __tablename__ = "alert"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id", ondelete="CASCADE"), nullable=False)
    schedule_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_activity.id", ondelete="CASCADE"), nullable=True
    )
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[AlertPriority] = mapped_column(
        Enum(AlertPriority, name="alert_priority", native_enum=False, length=10), nullable=False
    )
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    season: Mapped["Season"] = relationship(back_populates="alerts")
