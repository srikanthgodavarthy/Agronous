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
    {
        # ---------------------------------------------------------------
        # BHINDI (OKRA) -- commercial hybrid cultivation calendar.
        #
        # Modeled on how an experienced commercial grower actually runs a
        # hybrid okra crop for a long, continuous picking window -- not a
        # university practical schedule with one token "Harvest" row.
        # Five things make this template different from the four above:
        #
        #   1. Harvest is NOT a single activity. First picking ~47 DAS,
        #      then every 2 days through ~109 DAS (32 pickings total) via
        #      one ActivityTemplate row with repeat_interval_days=2 -- the
        #      schedule engine explodes this into 32 independently
        #      completable ScheduleActivity rows automatically.
        #   2. Continuous foliar nutrition every ~12 days through fruiting,
        #      because continuous picking drains the plant fast.
        #   3. A parallel "plant recovery" track, offset from the foliar
        #      nutrition dates, focused specifically on rebuilding vigour
        #      after repeated harvesting rather than routine feeding.
        #   4. Fruit-quality-focused sprays (colour, size uniformity,
        #      curvature, shelf life, marketability) -- distinct in intent
        #      from the general nutrition/recovery tracks even though the
        #      action (a foliar spray) looks similar.
        #   5. Weekly pest/disease/stress monitoring (whitefly, jassids,
        #      thrips, fruit borer, YVMV, powdery mildew, nutrient
        #      deficiency, water stress) with an explicit prompt to
        #      photograph the crop for AI analysis via Observations.
        #
        # Every remark below follows the same five-part structure so it
        # reads well as-is AND gives services/ai_engine.py clean material
        # to reason over later: Purpose. Benefit. Timing. Weather caution.
        # Follow-up.
        # ---------------------------------------------------------------
        "name": "Bhindi (Okra)",
        "description": "Commercial hybrid okra (Bhindi), direct-seeded, long continuous-picking cultivation.",
        "default_duration_days": 115,
        "stages": [
            ("Land Preparation", 1, -10, -1, "Deep ploughing, FYM incorporation, and bed/ridge formation before sowing."),
            ("Germination & Establishment", 2, 0, 10, "Seed germination and seedling establishment."),
            ("Vegetative Growth", 3, 11, 24, "Vegetative growth and branching; root and canopy development."),
            ("Flowering Initiation", 4, 25, 44, "Flower bud formation begins; nutrient demand starts rising."),
            ("Peak Flowering & Fruit Set", 5, 45, 54, "Continuous flowering and fruit set begins; first pickings approach."),
            ("Continuous Harvest & Fruiting", 6, 55, 113, "Extended commercial picking window with overlapping flowering, fruiting and harvest."),
        ],
        "activities": [
            # --- Land preparation, sowing, establishment -----------------
            (-10, ActivityCategory.LAND_PREPARATION, "Deep Ploughing & FYM Incorporation", None, 1,
             "Purpose: Open up the soil and work in well-rotted FYM/compost. "
             "Benefit: Improves root penetration, drainage and nutrient-holding capacity for the whole crop. "
             "Timing: 10 days before sowing, while soil is workable. "
             "Weather: Avoid working wet, waterlogged soil. "
             "Follow-up: Level the field and form ridges/beds within 2-3 days."),
            (-5, ActivityCategory.LAND_PREPARATION, "Ridge/Bed Formation & Basal Fertilizer", None, 1,
             "Purpose: Form ridges or raised beds and place the basal NPK dose. "
             "Benefit: Ensures good drainage, easy picking access later, and gives seedlings an early nutrient base. "
             "Timing: 4-5 days before sowing. "
             "Weather: Complete before any heavy rain to prevent ridge erosion. "
             "Follow-up: Confirm spacing matches the hybrid's recommended plant population."),
            (0, ActivityCategory.SOWING, "Seed Sowing - Hybrid Okra", None, 1,
             "Purpose: Direct-sow treated hybrid seed at recommended spacing. "
             "Benefit: Correct spacing now directly drives fruit size uniformity and ease of picking for the entire season. "
             "Timing: Day of sowing (DAS 0). "
             "Weather: Sow into adequate soil moisture; avoid sowing just before a heavy downpour that can cause crusting. "
             "Follow-up: Check germination by DAS 6-7 and plan gap-filling."),
            (5, ActivityCategory.IRRIGATION, "Irrigation - Germination Support", None, 1,
             "Purpose: Keep the seed zone moist for uniform germination. "
             "Benefit: Even germination means an even, easier-to-manage stand and fewer gaps to fill later. "
             "Timing: Around DAS 5, light and frequent rather than heavy. "
             "Weather: Skip or reduce if recent rainfall has kept soil moist. "
             "Follow-up: Inspect germination percentage and mark patches needing gap-filling."),
            (10, ActivityCategory.OTHER, "Thinning & Gap Filling", None, 1,
             "Purpose: Remove weak/excess seedlings and fill visible gaps. "
             "Benefit: Maintains the target plant population so light, nutrients and water are not wasted on overcrowded clumps. "
             "Timing: DAS 10, once true leaves are visible. "
             "Weather: Do this on a cooler day to reduce transplant shock for gap-filled seedlings. "
             "Follow-up: Water lightly after thinning to settle remaining roots."),
            (15, ActivityCategory.WEEDING, "First Weeding / Inter-culture", None, 1,
             "Purpose: Remove early weed competition and lightly loosen the topsoil. "
             "Benefit: Reduces competition for nutrients and water during the critical early vegetative push. "
             "Timing: DAS 15, before weeds set seed. "
             "Weather: Avoid weeding in waterlogged soil to prevent root damage. "
             "Follow-up: Re-check for regrowth weekly until canopy closes."),
            (18, ActivityCategory.IRRIGATION, "Irrigation Cycle - Vegetative Stage", 6, 4,
             "Purpose: Maintain steady soil moisture through active vegetative growth. "
             "Benefit: Consistent moisture (not flood-dry cycles) builds the strong root and branch framework that supports a long harvest window later. "
             "Timing: Every ~6 days through the vegetative stage; adjust if rain falls. "
             "Weather: Reduce frequency during rainy spells to avoid waterlogging and root rot. "
             "Follow-up: Watch for wilting between cycles as a sign the interval is too long."),
            (20, ActivityCategory.FERTILIZER, "1st Top Dressing - Nitrogen", None, 1,
             "Purpose: Apply the first nitrogen split to fuel vegetative growth. "
             "Benefit: Builds the canopy and branching framework needed to support heavy, continuous fruiting later. "
             "Timing: DAS 20, just before the vegetative growth surge. "
             "Weather: Apply to moist soil, ideally just before or after light irrigation, not in standing water. "
             "Follow-up: Monitor leaf colour over the next week to gauge response."),

            # --- Weekly crop-health monitoring (pest/disease/stress) -----
            (21, ActivityCategory.SPRAY, "Weekly Crop Health Monitoring", 7, 13,
             "Purpose: Walk the field and inspect leaves, undersides, flowers and fruit for whitefly, jassids, thrips, fruit borer, "
             "Yellow Vein Mosaic Virus (YVMV) symptoms, powdery mildew, nutrient deficiency patterns and water stress. "
             "Benefit: Catching pest, disease or nutrient problems in the first week of onset is far cheaper and more effective than treating an established outbreak. "
             "Timing: Every 7 days, ideally in the cooler morning hours when pests are most visible on the underside of leaves. "
             "Weather: Note recent rain/humidity, since whitefly and YVMV pressure and powdery mildew risk both rise in specific weather windows. "
             "Follow-up: Capture images of affected and healthy leaves, flowers and fruit and log them as Observations for AI analysis; treat only if a threshold pest/disease is confirmed."),

            # --- Flowering initiation, fertigation, foliar nutrition -----
            (25, ActivityCategory.FERTILIZER, "2nd Top Dressing - Pre-Flowering", None, 1,
             "Purpose: Apply nitrogen + potash split as flower bud formation begins. "
             "Benefit: Supports strong, synchronized flowering, which is what eventually drives a high first-flush harvest. "
             "Timing: DAS 25, at flower initiation. "
             "Weather: Apply with adequate soil moisture; avoid during heavy rain to prevent runoff loss. "
             "Follow-up: Track flower bud emergence over the following 5-7 days."),
            (28, ActivityCategory.FERTILIZER, "Foliar Nutrition - Balanced NPK + Calcium", 12, 7,
             "Purpose: Apply a balanced NPK foliar spray with added calcium through flowering and fruiting. "
             "Benefit: Improves plant vigour, supports steady flowering and strengthens fruit cell walls for firmer, better-quality pods. "
             "Timing: Every 10-15 days from pre-flowering through late fruiting (this cycle: every 12 days). "
             "Weather: Spray during early morning or late evening; avoid spraying during high temperatures, bright sun or ahead of rainfall, which both reduce uptake and waste the spray. "
             "Follow-up: Watch new flush of leaves and flowers for response; adjust to a micronutrient mixture if specific deficiency symptoms (yellowing, interveinal chlorosis) are observed instead of generic NPK."),
            (30, ActivityCategory.WEEDING, "Second Weeding / Earthing Up", None, 1,
             "Purpose: Final round of weeding and light earthing up before canopy closes. "
             "Benefit: Keeps root competition low and improves plant anchorage against wind once the crop becomes top-heavy with fruit. "
             "Timing: DAS 30, just before canopy closure makes inter-row access difficult. "
             "Weather: Avoid in wet soil to prevent compaction and root injury. "
             "Follow-up: After this point, rely on mulch/canopy shading rather than further inter-culture."),
            (32, ActivityCategory.SPRAY, "Preventive Spray - Early Sucking Pest & Disease Check", None, 1,
             "Purpose: Preventive spray targeting early aphid/jassid/whitefly buildup and early fungal leaf spots. "
             "Benefit: Suppresses the vectors that spread Yellow Vein Mosaic Virus before flowering, when an outbreak would be most damaging. "
             "Timing: DAS 32, just ahead of peak flowering. "
             "Weather: Avoid spraying in windy conditions or ahead of rain. "
             "Follow-up: Re-assess at the next weekly monitoring visit; escalate only if population crosses threshold."),

            # --- Plant recovery / strength track (offset from foliar) ----
            (34, ActivityCategory.FERTILIZER, "Plant Recovery & Strength Management", 12, 7,
             "Purpose: Apply micronutrients, calcium and potassium-rich foliar feed aimed specifically at plant recovery rather than routine feeding. "
             "Benefit: Continuous harvesting steadily removes nutrients from the plant; this recovery dose maintains vigour, supports new flower flushes and sustains fruit quality through a long picking season. "
             "Timing: Every 10-15 days from late vegetative stage through the end of harvest (this cycle: every 12 days), timed to follow periods of heavy picking. "
             "Weather: Spray in early morning or late evening; skip or delay if rain is expected within a few hours. "
             "Follow-up: Do a quick plant health assessment after each application -- leaf colour, new flowering, fruit set -- and shorten the interval if plants show fatigue (pale leaves, reduced flowering, thin fruit)."),

            # --- Fertigation / irrigation through reproductive phase -----
            (38, ActivityCategory.FERTILIZER, "3rd Fertigation - Flowering Booster", None, 1,
             "Purpose: Phosphorus + potassium-heavy fertigation to support flowering and early fruit set. "
             "Benefit: Reduces flower drop and supports more fruit set per flush, directly raising total marketable yield. "
             "Timing: DAS 38, during peak flowering. "
             "Weather: Fertigate when soil is at field capacity, not during waterlogging. "
             "Follow-up: Check fruit-set percentage on tagged branches over the following week."),
            (40, ActivityCategory.IRRIGATION, "Irrigation Cycle - Flowering to Fruiting", 5, 14,
             "Purpose: Maintain steady soil moisture through flowering and the entire harvest window. "
             "Benefit: Even moisture prevents flower drop and fruit drop and keeps pods tender rather than fibrous -- critical for marketable quality. "
             "Timing: Every ~5 days from flowering through the end of harvest; shorten the interval in hot, dry weather. "
             "Weather: Suspend or skip a cycle if rainfall has already met crop water demand, to avoid waterlogging and root/fruit rot. "
             "Follow-up: Check soil moisture at root depth before each cycle rather than irrigating on a fixed calendar alone."),

            # --- Fruit-quality-focused sprays -----------------------------
            (44, ActivityCategory.SPRAY, "Fruit Quality Management - Colour & Uniformity", 15, 5,
             "Purpose: Apply a potassium-rich and micronutrient (boron, magnesium) foliar spray timed to the fruiting flush, specifically targeting fruit colour, size uniformity and reduced curvature. "
             "Benefit: Improves pod colour and shape consistency, reduces curved/misshapen pods, and improves shelf life after picking -- all of which directly raise the price the produce fetches in the market. "
             "Timing: Every 15 days from early fruiting through late harvest. "
             "Weather: Spray in early morning or late evening; avoid hot, sunny conditions or rain within a few hours, both of which reduce leaf uptake. "
             "Follow-up: Sample a few pods at the next harvest for colour, straightness and size, and note any improvement or deficiency symptom for the next AI/Observation review."),

            # --- First harvest and the long picking cycle -----------------
            (47, ActivityCategory.HARVEST, "First Harvest - Tender Pod Picking", None, 1,
             "Purpose: First picking of tender okra pods, approximately 8-10 cm long. "
             "Benefit: Picking at the correct tender stage (not overgrown/fibrous) is the single biggest driver of grade and price realized at market. "
             "Timing: Approximately 45-50 DAS; pick in the morning while pods are firm and before the day heats up. "
             "Weather: Avoid picking in wet conditions (rain/heavy dew) since wet handling encourages post-harvest rot and reduces shelf life. "
             "Follow-up: Log the harvested quantity as Revenue against today's sale, and inspect plants for the next flush of flowers while picking."),
            (49, ActivityCategory.HARVEST, "Harvest Cycle - Tender Pod Picking", 2, 31,
             "Purpose: Continue picking tender pods (8-10 cm) every 2 days through the full harvest window. "
             "Benefit: A strict 2-day picking interval is what commercial growers use to prevent pods from crossing into the fibrous, lower-grade stage -- missing even one cycle measurably drops quality and price. "
             "Timing: Every 2 days from approximately 49 DAS through 100-110 DAS; always pick in the morning. "
             "Weather: If heavy rain falls on a picking day, pick as soon as the field is walkable rather than skipping, since pods keep maturing regardless of weather. "
             "Follow-up: Record each picking's quantity and sale as Revenue on the same day -- revenue entries should track the harvest calendar one-to-one rather than being batched up later."),

            # --- Late-season fruit quality / shelf-life focus -------------
            (60, ActivityCategory.SPRAY, "Fruit Quality Management - Shelf Life & Market Grade", 15, 4,
             "Purpose: Calcium and potassium-focused foliar application aimed at firmer pod texture and longer post-harvest shelf life. "
             "Benefit: Firmer, better-holding pods reduce rejection at the market and allow a one-day transport/storage buffer without quality loss. "
             "Timing: Every 15 days from mid-harvest through late fruiting. "
             "Weather: Apply in cooler parts of the day; avoid application right before expected rain. "
             "Follow-up: Grade a sample of the next 2-3 harvests for firmness and note any softening or blemish patterns."),

            # --- Continued plant health assessment late in the season ----
            (70, ActivityCategory.OTHER, "Plant Health Assessment - Mid Harvest", 14, 4,
             "Purpose: Walk-through assessment of overall plant vigour, leaf health, flowering rate and fruit load after repeated harvesting. "
             "Benefit: Confirms whether nutrition and recovery sprays are keeping pace with the demands of continuous picking, so adjustments can be made before yield actually drops. "
             "Timing: Every 14 days from mid-harvest onward. "
             "Weather: Conduct on a dry day for an accurate read on leaf condition (wet foliage can mask early disease/deficiency signs). "
             "Follow-up: If vigour is declining, shorten the foliar nutrition/recovery interval and capture photos as an Observation for AI review."),
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
