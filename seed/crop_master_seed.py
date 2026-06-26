"""
Crop Master seed data.

This module is the proof of the "crop-driven, not hardcoded" requirement:
every activity, fertilizer dose, spray, irrigation cycle, and harvest window
for every crop is *data* here, not branching logic in the application. Adding
a new crop means adding rows to this file (or, in production, inserting rows
via an admin screen / SQL) -- zero changes to schedule_engine.py, dashboard.py,
or any other application code are required.

Each crop's stages/activities are wrapped in a CropTemplateVersion (version 1,
is_current=True) on first seed. Re-running this script does NOT touch any
crop that already has a CropMaster row -- it only adds crops that don't yet
exist, by name. This means it's safe to run repeatedly in any environment
without ever clobbering a version that real seasons may already reference.
To genuinely revise an existing crop's schedule, use create_new_version()
below (or an admin tool) to add a new version rather than editing rows in
place, preserving the historical record for seasons created against the
old version.

Run with:  python -m seed.crop_master_seed
"""
from __future__ import annotations

from db.base import session_scope
from db.models import ActivityCategory, ActivityTemplate, CropMaster, CropStage, CropTemplateVersion

# ---------------------------------------------------------------------------
# Each crop is defined as: stages (DAS ranges) + activity templates
# (DAS offset, optionally repeating). day_offset = 0 means "on sowing date".
# ---------------------------------------------------------------------------

CROPS = [
    {
        "name": "Rice (Paddy)",
        "description": "Transplanted paddy rice, irrigated lowland cultivation.",
        "default_duration_days": 120,
        "stages": [
            ("Nursery & Land Prep", 1, -15, -1, "Nursery raising and main field preparation before transplanting."),
            ("Transplanting", 2, 0, 5, "Seedlings transplanted into the main field."),
            ("Vegetative / Tillering", 3, 6, 40, "Active tillering and vegetative growth."),
            ("Panicle Initiation", 4, 41, 65, "Reproductive phase begins; nutrient demand peaks."),
            ("Flowering & Grain Filling", 5, 66, 95, "Flowering through grain filling; water-sensitive period."),
            ("Maturity & Harvest", 6, 96, 120, "Grain maturation and harvest window."),
        ],
        "activities": [
            (-15, ActivityCategory.LAND_PREPARATION, "Field Ploughing", None, 1, "First ploughing to break soil."),
            (-10, ActivityCategory.LAND_PREPARATION, "Puddling & Levelling", None, 1, "Puddle and level field, apply basal FYM."),
            (-7, ActivityCategory.OTHER, "Nursery Sowing", None, 1, "Sow pre-germinated seed in nursery bed."),
            (0, ActivityCategory.SOWING, "Transplanting", None, 1, "Transplant 21-25 day old seedlings, 2-3 per hill."),
            (3, ActivityCategory.IRRIGATION, "Irrigation - Establishment", 7, 6, "Maintain 2-3cm standing water for establishment."),
            (10, ActivityCategory.FERTILIZER, "Basal Fertilizer - DAP", None, 1, "Apply DAP as basal dose if not done at transplanting."),
            (21, ActivityCategory.FERTILIZER, "Urea Top Dress - 1st Split", None, 1, "First nitrogen top dressing at active tillering."),
            (25, ActivityCategory.WEEDING, "Hand Weeding / Herbicide", None, 1, "Control weeds during tillering stage."),
            (35, ActivityCategory.SPRAY, "Pest Scouting - Stem Borer", None, 1, "Scout for stem borer/leaf folder, spray if threshold crossed."),
            (45, ActivityCategory.FERTILIZER, "Urea Top Dress - 2nd Split (Panicle Initiation)", None, 1, "Critical nitrogen dose at panicle initiation."),
            (50, ActivityCategory.SPRAY, "Fungicide Spray - Blast/Blight", None, 1, "Preventive spray against leaf blast/bacterial blight."),
            (60, ActivityCategory.IRRIGATION, "Irrigation - Reproductive Phase", 5, 8, "Keep field saturated; avoid water stress at panicle stage."),
            (70, ActivityCategory.SPRAY, "Insecticide - Brown Plant Hopper", None, 1, "Spray if BPH population crosses economic threshold."),
            (85, ActivityCategory.IRRIGATION, "Last Irrigation", None, 1, "Final irrigation before field drain-down for harvest."),
            (90, ActivityCategory.OTHER, "Drain Field", None, 1, "Drain standing water 10-15 days before harvest."),
            (110, ActivityCategory.HARVEST, "Harvesting", None, 1, "Harvest when 80-85% of grains turn golden yellow."),
            (112, ActivityCategory.OTHER, "Threshing & Drying", None, 1, "Thresh and sun-dry grain to safe moisture (~14%)."),
        ],
    },
    {
        "name": "Cotton (Bt Hybrid)",
        "description": "Rainfed/irrigated Bt hybrid cotton, row-sown.",
        "default_duration_days": 180,
        "stages": [
            ("Land Preparation", 1, -20, -1, "Deep ploughing and field preparation."),
            ("Germination & Seedling", 2, 0, 20, "Germination and early seedling establishment."),
            ("Vegetative / Squaring", 3, 21, 55, "Vegetative growth and square formation."),
            ("Flowering & Boll Development", 4, 56, 110, "Flowering through boll development; peak input phase."),
            ("Boll Maturation", 5, 111, 150, "Bolls mature and begin to open."),
            ("Picking", 6, 151, 180, "Multiple harvest pickings as bolls open."),
        ],
        "activities": [
            (-20, ActivityCategory.LAND_PREPARATION, "Deep Ploughing", None, 1, "Deep summer ploughing to expose pests and improve tilth."),
            (-7, ActivityCategory.LAND_PREPARATION, "Ridges & Furrows Formation", None, 1, "Form ridges/furrows per row spacing recommendation."),
            (0, ActivityCategory.SOWING, "Sowing - Bt Hybrid Seed", None, 1, "Dibble treated seed at recommended spacing."),
            (10, ActivityCategory.IRRIGATION, "Life-Saving Irrigation", None, 1, "Light irrigation to ensure uniform germination if no rain."),
            (20, ActivityCategory.FERTILIZER, "Basal Fertilizer Application", None, 1, "Apply basal N:P:K dose at thinning/gap filling."),
            (25, ActivityCategory.WEEDING, "First Weeding / Inter-culture", None, 1, "Remove weeds, light hoeing."),
            (35, ActivityCategory.FERTILIZER, "1st Top Dressing - Nitrogen", None, 1, "Nitrogen split at squaring initiation."),
            (40, ActivityCategory.SPRAY, "Sucking Pest Spray (Aphids/Jassids)", None, 1, "Spray for sucking pests at vegetative-squaring transition."),
            (55, ActivityCategory.IRRIGATION, "Irrigation - Squaring Stage", 12, 5, "Irrigate every ~12 days through squaring/flowering."),
            (60, ActivityCategory.FERTILIZER, "2nd Top Dressing - Flowering", None, 1, "Nitrogen + potash split at flowering onset."),
            (65, ActivityCategory.WEEDING, "Second Weeding / Earthing Up", None, 1, "Earth up and remove weeds before canopy closes."),
            (75, ActivityCategory.SPRAY, "Bollworm Monitoring Spray", None, 1, "Pheromone trap monitoring; spray if pink/American bollworm threshold crossed."),
            (95, ActivityCategory.SPRAY, "Boll Rot Fungicide Spray", None, 1, "Preventive spray during humid flowering-boll phase."),
            (120, ActivityCategory.FERTILIZER, "Foliar Nutrient Spray", None, 1, "Micronutrient foliar spray to support boll development."),
            (155, ActivityCategory.HARVEST, "First Picking", None, 1, "Pick first flush of fully opened bolls."),
            (170, ActivityCategory.HARVEST, "Second Picking", None, 1, "Second picking round as more bolls open."),
            (180, ActivityCategory.HARVEST, "Final Picking", None, 1, "Final clean-up picking."),
        ],
    },
    {
        "name": "Tomato",
        "description": "Transplanted hybrid tomato, staked/trellised.",
        "default_duration_days": 100,
        "stages": [
            ("Nursery & Land Prep", 1, -25, -1, "Raise nursery and prepare main field with beds."),
            ("Transplanting & Establishment", 2, 0, 10, "Transplant seedlings and establish in main field."),
            ("Vegetative Growth", 3, 11, 30, "Vegetative growth and branching."),
            ("Flowering & Fruit Set", 4, 31, 55, "Flowering and initial fruit set; critical input window."),
            ("Fruit Development", 5, 56, 80, "Fruit bulking and development."),
            ("Harvest", 6, 81, 100, "Multiple harvest pickings as fruit ripens."),
        ],
        "activities": [
            (-25, ActivityCategory.OTHER, "Nursery Bed Preparation & Sowing", None, 1, "Prepare raised nursery beds and sow seed."),
            (-7, ActivityCategory.LAND_PREPARATION, "Main Field Bed Preparation", None, 1, "Prepare raised beds with FYM incorporation."),
            (0, ActivityCategory.SOWING, "Transplanting", None, 1, "Transplant 25-30 day old healthy seedlings."),
            (2, ActivityCategory.IRRIGATION, "Irrigation - Establishment", None, 1, "Light irrigation immediately after transplanting."),
            (7, ActivityCategory.IRRIGATION, "Drip Irrigation Cycle", 4, 20, "Regular drip irrigation cycle through crop duration."),
            (15, ActivityCategory.FERTILIZER, "Basal + 1st Fertigation", None, 1, "First fertigation dose of N:P:K via drip."),
            (18, ActivityCategory.OTHER, "Staking / Trellising", None, 1, "Install stakes and tie plants for support."),
            (22, ActivityCategory.WEEDING, "Weeding & Mulch Check", None, 1, "Remove weeds, check mulch film integrity."),
            (28, ActivityCategory.SPRAY, "Preventive Fungicide Spray", None, 1, "Spray against early blight/damping-off."),
            (35, ActivityCategory.FERTILIZER, "2nd Fertigation - Flowering Booster", None, 1, "Boost P & K for flowering and fruit set."),
            (40, ActivityCategory.SPRAY, "Pest Spray - Fruit Borer", None, 1, "Spray against fruit borer at flowering-fruit set."),
            (50, ActivityCategory.OTHER, "Pruning - Sucker Removal", None, 1, "Remove suckers and lower leaves for airflow."),
            (55, ActivityCategory.FERTILIZER, "3rd Fertigation - Fruit Development", None, 1, "Potash-heavy dose to support fruit bulking."),
            (60, ActivityCategory.SPRAY, "Fungicide - Late Blight Control", None, 1, "Preventive spray during humid fruiting phase."),
            (75, ActivityCategory.SPRAY, "Pest Spray - Whitefly/Aphid", None, 1, "Control sucking pests that spread viral disease."),
            (82, ActivityCategory.HARVEST, "First Harvest Picking", None, 1, "Pick first ripe fruits (breaker stage)."),
            (89, ActivityCategory.HARVEST, "Second Harvest Picking", 7, 3, "Subsequent harvest pickings every ~7 days."),
        ],
    },
    {
        "name": "Maize (Hybrid)",
        "description": "Irrigated hybrid maize, direct-seeded.",
        "default_duration_days": 110,
        "stages": [
            ("Land Preparation", 1, -10, -1, "Field preparation and basal fertilizer placement."),
            ("Germination & Seedling", 2, 0, 20, "Germination and 2-3 leaf stage establishment."),
            ("Vegetative / Knee-High", 3, 21, 45, "Rapid vegetative growth, knee-high to pre-tasseling."),
            ("Tasseling & Silking", 4, 46, 65, "Tasseling and silking; pollination-critical phase."),
            ("Grain Filling", 5, 66, 95, "Cob filling and grain development."),
            ("Maturity & Harvest", 6, 96, 110, "Physiological maturity and harvest window."),
        ],
        "activities": [
            (-10, ActivityCategory.LAND_PREPARATION, "Ploughing & Harrowing", None, 1, "Prepare fine seedbed."),
            (-3, ActivityCategory.FERTILIZER, "Basal Fertilizer Placement", None, 1, "Place basal DAP/NPK in furrows before sowing."),
            (0, ActivityCategory.SOWING, "Seed Sowing", None, 1, "Dibble/drill treated hybrid seed at recommended spacing."),
            (5, ActivityCategory.IRRIGATION, "Irrigation - Germination", None, 1, "Light irrigation to ensure even germination."),
            (20, ActivityCategory.FERTILIZER, "1st Top Dressing - Urea", None, 1, "Nitrogen split at knee-high stage."),
            (22, ActivityCategory.WEEDING, "Weeding / Herbicide Application", None, 1, "Post-emergence herbicide or hand weeding."),
            (25, ActivityCategory.IRRIGATION, "Irrigation Cycle", 10, 6, "Irrigate every ~10 days through grain filling."),
            (35, ActivityCategory.SPRAY, "Pest Spray - Fall Armyworm", None, 1, "Scout and spray for fall armyworm in whorl stage."),
            (45, ActivityCategory.FERTILIZER, "2nd Top Dressing - Pre-Tasseling", None, 1, "Final nitrogen split before tasseling."),
            (55, ActivityCategory.SPRAY, "Fungicide - Leaf Blight", None, 1, "Preventive spray during humid tasseling phase."),
            (90, ActivityCategory.OTHER, "Field Drying Check", None, 1, "Reduce irrigation; let cobs dry down in field."),
            (105, ActivityCategory.HARVEST, "Harvesting", None, 1, "Harvest when husk is dry and grain moisture ~20-25%."),
            (107, ActivityCategory.OTHER, "Shelling & Drying", None, 1, "Shell cobs and dry grain to safe storage moisture."),
        ],
    },
]


def seed_crop_master() -> None:
    """
    Insert any crop in CROPS that doesn't already exist (matched by name).
    Existing crops -- and the version(s) real seasons may already
    reference -- are left completely untouched, so this is safe to run
    against an environment that already has live tenant data.
    """
    with session_scope() as session:
        existing_names = {c.name for c in session.query(CropMaster.name).all()}
        created = 0

        for crop_def in CROPS:
            if crop_def["name"] in existing_names:
                continue

            crop = CropMaster(
                name=crop_def["name"],
                description=crop_def["description"],
                default_duration_days=crop_def["default_duration_days"],
            )
            session.add(crop)
            session.flush()  # get crop.id

            version = CropTemplateVersion(
                crop_id=crop.id,
                version_number=1,
                label="Initial version",
                is_current=True,
            )
            session.add(version)
            session.flush()  # get version.id

            for name, sequence, start_day, end_day, desc in crop_def["stages"]:
                session.add(
                    CropStage(
                        version_id=version.id,
                        name=name,
                        sequence=sequence,
                        start_day=start_day,
                        end_day=end_day,
                        description=desc,
                    )
                )

            for day_offset, category, name, repeat_interval, repeat_count, remarks in crop_def["activities"]:
                session.add(
                    ActivityTemplate(
                        version_id=version.id,
                        name=name,
                        category=category,
                        day_offset=day_offset,
                        repeat_interval_days=repeat_interval,
                        repeat_count=repeat_count,
                        default_remarks=remarks,
                    )
                )
            created += 1

        print(f"Seeded {created} new crop master template(s) "
              f"({len(CROPS) - created} already existed and were left untouched).")


def create_new_version(
    crop_name: str,
    label: str,
    change_notes: str,
    stages: list[tuple[str, int, int, int, str]],
    activities: list[tuple[int, ActivityCategory, str, int | None, int, str]],
) -> None:
    """
    Add a new CropTemplateVersion for an existing crop and mark it current,
    demonstrating the intended workflow for revising agronomic
    recommendations: NEVER edit existing CropStage/ActivityTemplate rows in
    place (that would retroactively change what past seasons were told to
    do); instead, create a new version with the revised stages/activities,
    and flip is_current so only *new* seasons pick it up. Every season
    already created keeps pointing at whatever version it was generated
    against, untouched.

    Example:
        create_new_version(
            crop_name="Rice (Paddy)",
            label="2027 Revised Nitrogen Schedule",
            change_notes="Split urea top-dressing into 3 doses per "
                          "updated state agricultural department guidance.",
            stages=[...],       # same shape as CROPS[i]["stages"]
            activities=[...],   # same shape as CROPS[i]["activities"]
        )
    """
    with session_scope() as session:
        crop = session.query(CropMaster).filter(CropMaster.name == crop_name).first()
        if crop is None:
            raise ValueError(f"No crop named {crop_name!r} found. Seed it first via seed_crop_master().")

        latest = (
            session.query(CropTemplateVersion)
            .filter(CropTemplateVersion.crop_id == crop.id)
            .order_by(CropTemplateVersion.version_number.desc())
            .first()
        )
        next_number = (latest.version_number + 1) if latest else 1

        # Demote the previously-current version; it remains fully intact and
        # still referenced by any season that was created against it.
        session.query(CropTemplateVersion).filter(
            CropTemplateVersion.crop_id == crop.id, CropTemplateVersion.is_current.is_(True)
        ).update({"is_current": False})

        new_version = CropTemplateVersion(
            crop_id=crop.id,
            version_number=next_number,
            label=label,
            change_notes=change_notes,
            is_current=True,
        )
        session.add(new_version)
        session.flush()

        for name, sequence, start_day, end_day, desc in stages:
            session.add(
                CropStage(
                    version_id=new_version.id,
                    name=name,
                    sequence=sequence,
                    start_day=start_day,
                    end_day=end_day,
                    description=desc,
                )
            )

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

        print(f"Created version {next_number} for {crop_name!r}: {label}")


if __name__ == "__main__":
    seed_crop_master()
