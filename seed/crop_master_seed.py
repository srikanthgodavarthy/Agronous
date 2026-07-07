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
from db.models import ActivityCategory, ActivityTemplate, CropMaster, CropStage, CropTemplateVersion, RecoveryStrategy, TriggerLogic

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
        # BHINDI (OKRA) -- Vikarabad commercial cultivation tracker.
        #
        # Rebuilt directly from a real 2-acre Vikarabad grower's week-by-week
        # field checklist (18 weeks, DAS 0-125, 71 tracked tasks) rather than
        # general agronomic knowledge -- DAS ranges, named products, doses,
        # and even specific cautions (e.g. "do not spray 10am-4pm during
        # flowering") are taken directly from that checklist so the in-app
        # schedule matches what the farmer is actually already doing.
        #
        # Mapping notes:
        #   - The source checklist uses two categories ("Pest Control",
        #     "Disease") that don't exist in ActivityCategory. Both map to
        #     SPRAY here (they're both foliar-applied chemical controls);
        #     the specific pest/disease and product stay in the activity
        #     name/remarks so nothing is lost and PRODUCT_HINTS keyword
        #     matching still works per-product.
        #   - "Foliar" rows (nutrition, not pest/disease) map to FERTILIZER,
        #     consistent with how foliar feeds are categorized for the other
        #     seeded crops.
        #   - Harvest cadence is genuinely "every 2-3 days" in the source,
        #     not a fixed interval -- modeled as repeat_interval_days=2
        #     (the tighter, safer bound) so the schedule never lets pods
        #     over-mature; remarks note the 2-3 day farmer judgement window.
        #   - Crop runs through DAS 125 (vs. ~110-115 for the other four
        #     crops here) because this checklist explicitly carries through
        #     uprooting, field clearing and deep ploughing as scheduled
        #     activities, not just the harvest window.
        # ---------------------------------------------------------------
        "name": "Bhindi (Okra)",
        "description": "Commercial hybrid okra (Bhindi), direct-seeded, Vikarabad-style continuous-picking cultivation with full pest/disease rotation calendar.",
        "default_duration_days": 125,
        "stages": [
            ("Sowing & Germination", 1, 0, 6, "Seed sowing, basal fertilizer, and pre/post-sowing irrigation."),
            ("Germination & Emergence", 2, 7, 13, "Germination check, gap filling, early cutworm/damping-off watch."),
            ("Seedling Establishment", 3, 14, 20, "Thinning, first weeding, early aphid/whitefly watch."),
            ("Active Vegetative Growth", 4, 21, 27, "Rapid vegetative growth; first nitrogen top dressing and earthing up."),
            ("Pre-Flowering / Rapid Growth", 5, 28, 34, "Second weeding, micronutrient foliar sprays, early shoot/fruit borer check."),
            ("Flower Bud Initiation", 6, 35, 41, "First flower buds visible; monsoon drainage management begins."),
            ("Full Flowering", 7, 42, 48, "Peak flowering; fruit-set foliar spray and FSB control critical."),
            ("Pod Development", 8, 49, 55, "Pod development begins; powdery mildew watch starts."),
            ("First Harvest", 9, 56, 62, "First tender pod harvest begins; harvest-pest spray interval discipline starts."),
            ("Peak Production", 10, 63, 69, "Peak picking; red spider mite and Cercospora leaf spot watch."),
            ("Sustained Production", 11, 70, 76, "Third top dressing to extend yield period; plant stamina foliar spray."),
            ("Continued Production", 12, 77, 83, "Continued picking; YVMV roguing and canopy management."),
            ("Mid-Late Production", 13, 84, 90, "Pod-quality potassium nitrate spray for size, colour and shelf life."),
            ("Late Production", 14, 91, 97, "Yield begins declining; reduce inputs; start seed collection."),
            ("Winding Down", 15, 98, 104, "Minimal irrigation; collect remaining pods; reduce all inputs."),
            ("Final Harvest", 16, 105, 111, "Stop irrigation; harvest last marketable pods; allow seed pods to mature."),
            ("Crop Removal", 17, 112, 118, "Final picking; uproot and incorporate plant residue."),
            ("Crop End", 18, 119, 125, "Field clearing, deep ploughing, and season record-keeping."),
        ],
        "activities": [
            # ===== Week 1 (DAS 0-6): Sowing & Germination ================
            (0, ActivityCategory.SOWING, "Sowing", None, 1,
             "Purpose: Sow seed at 2-3 cm depth, 60x30 cm spacing. "
             "Benefit: Correct depth and spacing gives uniform germination and easy picking access for the whole season. "
             "Timing: DAS 0, week 1. Seed rate 3-4 kg/acre (6-8 kg for 2 acres total). "
             "Weather: Sow into adequate soil moisture. "
             "Follow-up: Treat seed before sowing; irrigate if soil is dry."),
            (0, ActivityCategory.OTHER, "Seed Treatment", None, 1,
             "Purpose: Treat seeds with Thiram (fungicide powder) 2g/kg OR Trichoderma (biofungicide) 4g/kg before sowing. "
             "Benefit: Protects seed and seedling from soil-borne fungal rot and damping-off during germination. "
             "Timing: Immediately before sowing, DAS 0. "
             "Weather: Treated seed should be sown the same day, not stored wet. "
             "Follow-up: Monitor germination percentage from DAS 7."),
            (0, ActivityCategory.FERTILIZER, "Basal Dose - DAP + Potash", None, 1,
             "Purpose: Apply Di-Ammonium Phosphate (DAP 18:46:0) at 40 kg/acre + Muriate of Potash (MOP) at 35 kg/acre (80 kg DAP + 70 kg MOP for 2 acres). "
             "Benefit: Gives seedlings an early phosphorus and potassium base for root and early growth. "
             "Timing: Mix into soil before sowing, DAS 0. "
             "Weather: Apply to workable, not waterlogged, soil. "
             "Follow-up: Confirm even mixing across the field before sowing."),
            (0, ActivityCategory.IRRIGATION, "Pre-Sowing Irrigation", None, 1,
             "Purpose: One irrigation if soil is dry before sowing. "
             "Benefit: Ensures adequate moisture for seed germination. "
             "Timing: DAS 0, just before sowing. "
             "Weather: Skip if soil is already moist from recent rain. "
             "Follow-up: Sow once soil reaches workable moisture."),
            (3, ActivityCategory.IRRIGATION, "Day 3 Irrigation", None, 1,
             "Purpose: Light irrigation on Day 3 if no rain. "
             "Benefit: Keeps the seed zone moist through the critical germination window without waterlogging. "
             "Timing: DAS 3. "
             "Weather: Avoid waterlogging; skip if rain has fallen. "
             "Follow-up: Check germination from DAS 7."),

            # ===== Week 2 (DAS 7-13): Germination & Emergence =============
            (7, ActivityCategory.IRRIGATION, "Light Irrigation", 4, 2,
             "Purpose: Light irrigation every 4-5 days through germination and emergence. "
             "Benefit: Maintains even soil moisture for germination without disturbing fragile seedlings. "
             "Timing: Every 4-5 days, DAS 7-13. "
             "Weather: Avoid disturbing seedlings; light watering only. "
             "Follow-up: Check germination percentage at each irrigation."),
            (7, ActivityCategory.OTHER, "Check Germination", None, 1,
             "Purpose: Check germination percentage; target above 70%. "
             "Benefit: Confirms stand quality early enough to gap-fill before it's too late to catch up. "
             "Timing: DAS 7-13, week 2. "
             "Weather: No specific precaution. "
             "Follow-up: Do gap filling immediately where seedlings are missing."),
            (10, ActivityCategory.SPRAY, "Cutworm / Damping-Off Watch", None, 1,
             "Purpose: Watch for cutworm damage or damping-off at the seedling base. "
             "Benefit: Early intervention prevents seedling loss that would otherwise need re-sowing. "
             "Timing: DAS 7-13, week 2. "
             "Weather: Pests are more active in humid, overcast conditions. "
             "Follow-up: If cutworm found, apply Chlorpyrifos 2.5 ml/L near the base."),

            # ===== Week 3 (DAS 14-20): Seedling Establishment =============
            (14, ActivityCategory.IRRIGATION, "Regular Irrigation", 5, 1,
             "Purpose: Regular irrigation every 5-6 days during seedling establishment. "
             "Benefit: Builds a steady root system for the vegetative push ahead. "
             "Timing: DAS 14-20, week 3. "
             "Weather: Adjust if rainfall has already met crop demand. "
             "Follow-up: Combine with thinning and first weeding this week."),
            (16, ActivityCategory.OTHER, "Thinning", None, 1,
             "Purpose: Retain 1 healthy plant per hill. "
             "Benefit: Removes competition between seedlings at the same spot so the retained plant develops strongly. "
             "Timing: DAS 14-20, week 3. "
             "Weather: Do on a cooler day to reduce shock. "
             "Follow-up: Water lightly after thinning."),
            (16, ActivityCategory.WEEDING, "First Weeding", None, 1,
             "Purpose: Remove weeds by hand or shallow hoeing. "
             "Benefit: Reduces early competition for nutrients and water during establishment. "
             "Timing: DAS 14-20, week 3. "
             "Weather: Avoid weeding waterlogged soil. "
             "Follow-up: Re-check for regrowth at the second weeding (week 5)."),
            (17, ActivityCategory.SPRAY, "Aphid / Whitefly Early Watch", None, 1,
             "Purpose: Watch for early aphid/whitefly infestation. "
             "Benefit: Treating sucking pests early prevents both direct damage and virus transmission later. "
             "Timing: DAS 14-20, week 3. "
             "Weather: Sucking pest pressure rises in warm, dry weather. "
             "Follow-up: If infestation starts, spray Neem oil 5 ml/L + Teepol 1 ml/L."),

            # ===== Week 4 (DAS 21-27): Active Vegetative Growth ===========
            (21, ActivityCategory.IRRIGATION, "Regular Irrigation - Hot & Dry Period", 5, 1,
             "Purpose: Regular irrigation every 5-6 days; this is a hot and dry critical period. "
             "Benefit: Prevents moisture stress during the active vegetative growth surge. "
             "Timing: DAS 21-27, week 4. "
             "Weather: Increase frequency if conditions are unusually hot and dry. "
             "Follow-up: Pair with the first nitrogen top dressing this week."),
            (21, ActivityCategory.FERTILIZER, "Top Dressing #1 - Ammonium Sulphate", None, 1,
             "Purpose: Apply Ammonium Sulphate (AS 20.6% N) at 75 kg/acre (150 kg for 2 acres). "
             "Benefit: Fuels the active vegetative growth and branching framework that will support fruiting later. "
             "Timing: DAS 21-27, week 4. "
             "Weather: Broadcast between rows and irrigate immediately. "
             "Follow-up: Available at most agri shops as a urea alternative; monitor leaf colour over the next week."),
            (23, ActivityCategory.OTHER, "Earthing Up", None, 1,
             "Purpose: Light hilling around the plant base. "
             "Benefit: Improves anchorage and root support as plants grow taller. "
             "Timing: DAS 21-27, week 4. "
             "Weather: Avoid in waterlogged soil. "
             "Follow-up: Re-check before canopy closes."),
            (24, ActivityCategory.SPRAY, "Whitefly / Aphid Control - Imidacloprid", None, 1,
             "Purpose: Spray Imidacloprid 0.5 ml/L if whitefly/aphid population is high. "
             "Benefit: Controls the whitefly vector that spreads Yellow Vein Mosaic Virus (YVMV) before it can establish. "
             "Timing: DAS 21-27, week 4. "
             "Weather: Avoid spraying in windy conditions. "
             "Follow-up: Re-check population at next monitoring; rotate products if repeated."),

            # ===== Week 5 (DAS 28-34): Pre-Flowering / Rapid Growth =======
            (28, ActivityCategory.IRRIGATION, "Regular Irrigation", 5, 1,
             "Purpose: Regular irrigation every 5 days; monsoon may start around this time. "
             "Benefit: Maintains moisture through rapid pre-flowering growth while watching for monsoon onset. "
             "Timing: DAS 28-34, week 5. "
             "Weather: Be ready to reduce frequency once monsoon rains begin. "
             "Follow-up: Check drainage readiness ahead of week 6."),
            (29, ActivityCategory.WEEDING, "Second Weeding", None, 1,
             "Purpose: Weed thoroughly and apply mulch between rows if available. "
             "Benefit: Last practical weeding window before canopy closes; mulch helps conserve moisture into the monsoon. "
             "Timing: DAS 28-34, week 5. "
             "Weather: Avoid in wet soil to prevent compaction. "
             "Follow-up: After this point, rely on canopy shading and mulch."),
            (30, ActivityCategory.SPRAY, "Shoot & Fruit Borer Early Check", None, 1,
             "Purpose: Check for shoot and fruit borer (FSB) dead hearts. "
             "Benefit: Catching FSB at the dead-heart stage prevents it from establishing through flowering and fruiting. "
             "Timing: DAS 28-34, week 5. "
             "Weather: No specific precaution. "
             "Follow-up: If dead heart found, spray Chlorantraniliprole 0.3 ml/L."),
            (31, ActivityCategory.FERTILIZER, "Zinc + Boron Foliar Spray", None, 1,
             "Purpose: Apply Zinc Sulphate (ZnSO4) 0.5 g/L + Borax (Boron) 1 g/L as a foliar spray. "
             "Benefit: Corrects micronutrient deficiency common after a maize crop in Vikarabad red soils. "
             "Timing: DAS 28-34, week 5. "
             "Weather: Spray during cooler hours, not in direct midday sun. "
             "Follow-up: Watch leaf colour for deficiency correction over the following week."),
            (32, ActivityCategory.FERTILIZER, "NPK Foliar Spray", None, 1,
             "Purpose: Apply Water Soluble NPK 19:19:19 (Multi-K / Kristalon) at 5 g/L as a foliar spray. "
             "Benefit: Boosts vegetative vigour ahead of flowering. "
             "Timing: DAS 28-34, week 5. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Combine with the Zinc + Boron spray this week if convenient."),

            # ===== Week 6 (DAS 35-41): Flower Bud Initiation ==============
            (35, ActivityCategory.IRRIGATION, "Drainage Management", None, 1,
             "Purpose: Ensure drainage channels are open ahead of expected monsoon rain. "
             "Benefit: Prevents waterlogging and root/fruit rot once monsoon rains arrive. "
             "Timing: DAS 35-41, week 6. "
             "Weather: Monsoon expected this week -- check channels before rain, not after. "
             "Follow-up: Re-check after the first heavy rain event."),
            (36, ActivityCategory.FERTILIZER, "Top Dressing #2 - CAN or Complex", None, 1,
             "Purpose: Apply Calcium Ammonium Nitrate (CAN 25% N) at 40 kg/acre OR Complex Fertilizer 20:20:0 at 40 kg/acre (80 kg total for 2 acres). "
             "Benefit: Supports the nutrient demand spike as flower buds form. "
             "Timing: DAS 35-41, week 6. "
             "Weather: Broadcast and irrigate; avoid applying just before heavy rain to prevent runoff loss. "
             "Follow-up: Track flower bud emergence over the following week."),
            (37, ActivityCategory.SPRAY, "Mite / Whitefly Control - Neem", None, 1,
             "Purpose: Spray Neem oil 5 ml/L in the evening only. "
             "Benefit: Suppresses mite and whitefly buildup ahead of full flowering with a low-residue option. "
             "Timing: DAS 35-41, week 6. "
             "Weather: Evening application only -- avoid daytime heat and direct sun. "
             "Follow-up: Re-assess at next monitoring visit."),
            (38, ActivityCategory.OTHER, "Flower Bud Check", None, 1,
             "Purpose: Check for first visible flower buds. "
             "Benefit: Confirms the crop is entering its most spray-sensitive window. "
             "Timing: DAS 35-41, week 6. "
             "Weather: Once buds are visible, do NOT spray between 10 AM and 4 PM (flowering hours) -- this protects pollinators and active flowers. "
             "Follow-up: Schedule any remaining sprays for early morning or evening only from this point on."),

            # ===== Week 7 (DAS 42-48): Full Flowering ======================
            (42, ActivityCategory.IRRIGATION, "Irrigation If No Rain", None, 1,
             "Purpose: Irrigate if there has been no rain for 5+ days. "
             "Benefit: Water stress during flowering directly reduces fruit set -- this is a critical irrigation window. "
             "Timing: DAS 42-48, week 7. "
             "Weather: Skip if monsoon rain has already met demand. "
             "Follow-up: Monitor fruit set over the following week."),
            (43, ActivityCategory.SPRAY, "FSB Control - Spinosad", None, 1,
             "Purpose: Spray Spinosad 45 SC at 0.3 ml/L, evening only. "
             "Benefit: Controls fruit and shoot borer (FSB) during the highest-risk flowering window. "
             "Timing: DAS 42-48, week 7. "
             "Weather: Evening application only; do not spray 10 AM-4 PM during flowering hours. "
             "Follow-up: Rotate to Emamectin Benzoate next cycle (week 8) to avoid resistance build-up."),
            (44, ActivityCategory.FERTILIZER, "Fruit Set Spray - Boron + Calcium", None, 1,
             "Purpose: Apply Borax (Boron) 1 g/L + Calcium Nitrate (CaNO3) 2 g/L as a foliar spray on leaves and buds. "
             "Benefit: Improves fruit set and reduces flower drop during peak flowering. "
             "Timing: DAS 42-48, week 7. "
             "Weather: Spray in early morning or evening, not during 10 AM-4 PM flowering hours. "
             "Follow-up: Watch fruit-set percentage on tagged branches over the following week."),
            (45, ActivityCategory.OTHER, "Remove Dead Hearts", None, 1,
             "Purpose: Remove FSB-affected shoot tips (dead hearts) and destroy them off-field. "
             "Benefit: Removing infested tips reduces the pest's breeding population before it can spread to fruit. "
             "Timing: DAS 42-48, week 7. "
             "Weather: No specific precaution. "
             "Follow-up: Continue checking weekly through pod development."),

            # ===== Week 8 (DAS 49-55): Pod Development =====================
            (49, ActivityCategory.IRRIGATION, "Consistent Irrigation", None, 1,
             "Purpose: Maintain consistent irrigation; monitor daily. "
             "Benefit: Irregular watering at this stage causes poor pod development -- consistency matters more than volume. "
             "Timing: DAS 49-55, week 8. "
             "Weather: Adjust daily based on rainfall, not a fixed calendar. "
             "Follow-up: First harvest approaches next week -- inspect pod size daily."),
            (50, ActivityCategory.SPRAY, "FSB Control (Rotation) - Emamectin", None, 1,
             "Purpose: Spray Emamectin Benzoate 0.4 ml/L, rotated from Spinosad. "
             "Benefit: Rotating chemical classes prevents resistance build-up in the FSB population. "
             "Timing: DAS 49-55, week 8. "
             "Weather: Evening application preferred. "
             "Follow-up: Maintain a 5-7 day spray-to-harvest interval once picking begins next week."),
            (51, ActivityCategory.SPRAY, "Powdery Mildew Watch", None, 1,
             "Purpose: Watch for white powdery growth on leaves (powdery mildew). "
             "Benefit: Early treatment prevents the disease from spreading across the canopy during humid pod-development weather. "
             "Timing: DAS 49-55, week 8. "
             "Weather: Risk rises in humid, overcast conditions. "
             "Follow-up: If white powder appears, spray Wettable Sulphur 3 g/L."),
            (52, ActivityCategory.OTHER, "Stake Tall Plants", None, 1,
             "Purpose: Stake tall plants if needed; remove yellowing lower leaves. "
             "Benefit: Staking prevents lodging under fruit load; removing yellowing leaves improves airflow and reduces disease pressure. "
             "Timing: DAS 49-55, week 8. "
             "Weather: No specific precaution. "
             "Follow-up: First harvest begins next week -- ensure plants are accessible for picking."),

            # ===== Week 9 (DAS 56-62): First Harvest =========================
            (56, ActivityCategory.IRRIGATION, "Regular Irrigation", 5, 1,
             "Purpose: Regular irrigation every 5-6 days if no rain. "
             "Benefit: Sustains pod development now that continuous harvesting has begun. "
             "Timing: DAS 56-62, week 9. "
             "Weather: Adjust for rainfall. "
             "Follow-up: Check soil moisture before each cycle."),
            (58, ActivityCategory.HARVEST, "First Harvest - Tender Pod Picking", 2, 1,
             "Purpose: FIRST HARVEST -- harvest tender pods 7-9 cm long every 2-3 days using a clean knife or scissors. "
             "Benefit: Picking at the correct tender stage and on a strict interval is the single biggest driver of grade and price at market. "
             "Timing: DAS 56-62, week 9, then continuing every 2-3 days for the rest of the season. "
             "Weather: Avoid picking in wet conditions; wet handling encourages post-harvest rot. "
             "Follow-up: Log the harvested quantity as Revenue against today's sale."),
            (59, ActivityCategory.SPRAY, "Whitefly Monitoring", None, 1,
             "Purpose: Inspect underside of leaves for Whitefly, Thrips and Jassids. "
             "Benefit: Keeping a 5-7 day spray-to-harvest interval protects both yield and food safety. "
             "Timing: DAS 58-62, week 9. Threshold-based spray only. "
             "Weather: Spray in the evening, away from picking hours. "
             "Follow-up: Track the interval since the last spray before every harvest."),
            (60, ActivityCategory.FERTILIZER, "Fruiting Boost - MKP Spray", None, 1,
             "Purpose: Apply Mono Potassium Phosphate (MKP 0:52:34) at 3 g/L as a foliar spray. "
             "Benefit: Boosts pod setting and early yield right as the harvest window opens. "
             "Timing: DAS 56-62, week 9. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Continue regular potassium-focused feeding through peak production."),
            (62, ActivityCategory.OTHER, "AI Observation", None, 1,
             "Purpose: Capture field images -- leaf undersides, pod quality, any suspect plants -- and upload to the Observations tab. "
             "Benefit: AI-assisted scouting catches emerging issues faster than visual inspection alone. "
             "Timing: DAS 62, end of week 9. Weekly from here onward. "
             "Weather: Capture in good light; morning preferred. "
             "Follow-up: Review AI feedback and act on any flagged issues before next harvest."),

            # ===== Week 10 (DAS 63-69): Peak Production =======================
            (63, ActivityCategory.IRRIGATION, "Supplement If Dry", None, 1,
             "Purpose: Rely on rain-fed moisture and irrigate only if there is a dry spell. "
             "Benefit: Avoids over-watering during the monsoon while still protecting against dry spells. "
             "Timing: DAS 63-69, week 10. "
             "Weather: Check soil moisture before deciding to irrigate. "
             "Follow-up: Continue every-2-3-day harvest regardless of irrigation timing."),
            (64, ActivityCategory.HARVEST, "Harvest Every 2-3 Days", 2, 3,
             "Purpose: Continue picking every 2-3 days; do NOT let pods over-mature. "
             "Benefit: Over-mature pods become fibrous and unmarketable -- missing a cycle measurably drops quality and price. "
             "Timing: Every 2-3 days through peak production, DAS 63-69 onward. "
             "Weather: Pick as soon as the field is walkable after rain rather than skipping a cycle. "
             "Follow-up: Log each picking's quantity and sale as Revenue the same day."),
            (65, ActivityCategory.SPRAY, "Red Spider Mite Control", None, 1,
             "Purpose: Spray Abamectin 0.5 ml/L OR Dicofol 2 ml/L for red spider mite. "
             "Benefit: Controls mite buildup that thrives in the hot, dry spells between monsoon showers. "
             "Timing: DAS 63-69, week 10. "
             "Weather: Mite pressure rises in hot, dry conditions. "
             "Follow-up: Re-check leaf undersides at next monitoring."),
            (66, ActivityCategory.SPRAY, "Disease Monitoring", None, 1,
             "Purpose: Inspect for YVMV (yellow vein mosaic), Powdery Mildew and Cercospora leaf spot. Capture AI images. "
             "Benefit: Early identification allows targeted intervention before the disease spreads. "
             "Timing: DAS 65-69, week 10. Weekly from here onward. "
             "Weather: Risk of Cercospora and mildew rises in humid, wet-leaf monsoon conditions. "
             "Follow-up: Spray Mancozeb 2.5 g/L if Cercospora appears. Rogue YVMV plants immediately."),
            (67, ActivityCategory.FERTILIZER, "Foliar Nutrition", None, 1,
             "Purpose: Apply Water Soluble NPK 19:19:19 (Multi-K) at 5 g/L as foliar spray. "
             "Benefit: Replenishes nutrients continuously exported by heavy picking. "
             "Timing: DAS 67, week 10. Repeat every 10-12 days through end of season. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Alternate with Calcium + Boron and Potassium Nitrate on subsequent cycles."),
            (68, ActivityCategory.OTHER, "Remove Pest-Damaged Pods", None, 1,
             "Purpose: Destroy pest-damaged pods to reduce FSB load in the field. "
             "Benefit: Removing infested pods breaks the pest's breeding cycle and protects the next flush. "
             "Timing: DAS 63-69, week 10. "
             "Weather: No specific precaution. "
             "Follow-up: Repeat at each harvest round through peak production."),

            # ===== Week 11 (DAS 70-76): Sustained Production ===================
            (70, ActivityCategory.IRRIGATION, "Regular Irrigation", None, 1,
             "Purpose: Regular irrigation -- do not miss. "
             "Benefit: Sustained production depends on uninterrupted moisture; a missed cycle now directly costs yield. "
             "Timing: DAS 70-76, week 11. "
             "Weather: Adjust timing around rainfall but do not skip entirely. "
             "Follow-up: Pair with the third top dressing this week."),
            (71, ActivityCategory.HARVEST, "Harvest Every 2-3 Days", 2, 3,
             "Purpose: Continue regular harvest every 2-3 days. "
             "Benefit: Sustained picking discipline through week 11 keeps pods marketable and maximizes the production window. "
             "Timing: DAS 70-76, week 11. "
             "Weather: Pick in the morning where possible. "
             "Follow-up: Log Revenue for each picking."),
            (72, ActivityCategory.FERTILIZER, "Top Dressing #3 - Ammonium Sulphate + Potash", None, 1,
             "Purpose: Apply Ammonium Sulphate (AS) at 30 kg/acre + Muriate of Potash (MOP) at 20 kg/acre (60 kg AS + 40 kg MOP for 2 acres). "
             "Benefit: Extends the yield period by replenishing nutrients depleted by several weeks of continuous picking. "
             "Timing: DAS 70-76, week 11. "
             "Weather: Broadcast and irrigate; avoid applying just before heavy rain. "
             "Follow-up: Watch plant vigour over the following 1-2 weeks for response."),
            (73, ActivityCategory.FERTILIZER, "Calcium + Boron", None, 1,
             "Purpose: Apply Calcium Nitrate (CaNO3) 2 g/L + Borax 1 g/L as foliar spray. "
             "Benefit: Reduces blossom drop and improves pod set and firmness during sustained production. "
             "Timing: DAS 73, week 11. Repeat every 10-12 days alternating with 19:19:19. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Combine with Boron for maximum fruit set benefit."),
            (74, ActivityCategory.FERTILIZER, "Plant Stamina - Seaweed Spray", None, 1,
             "Purpose: Apply Seaweed Extract (Seasol / Kelpak / any brand) at 3 ml/L as a foliar spray. "
             "Benefit: Improves plant stamina and stress tolerance during the demanding peak-production period. "
             "Timing: DAS 70-76, week 11. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Repeat periodically through continued production if plants show fatigue."),
            (75, ActivityCategory.SPRAY, "Pest Monitoring", None, 1,
             "Purpose: Observe underside of leaves for Whitefly, Thrips, Jassids and Fruit Borer. Threshold-based spray only. "
             "Benefit: Weekly scouting prevents population build-up without over-spraying. "
             "Timing: DAS 75, week 11. Weekly from here through end of season. "
             "Weather: Scout in morning for accurate population count. "
             "Follow-up: Spray Imidacloprid 0.5 ml/L if whitefly threshold crossed; Spinosad 0.3 ml/L for FSB."),

            # ===== Week 12 (DAS 77-83): Continued Production =====================
            (77, ActivityCategory.IRRIGATION, "Regular Irrigation", 5, 1,
             "Purpose: Regular irrigation every 5-6 days. "
             "Benefit: Maintains consistent moisture through continued production. "
             "Timing: DAS 77-83, week 12. "
             "Weather: Adjust for rainfall. "
             "Follow-up: Combine with canopy management this week."),
            (78, ActivityCategory.HARVEST, "Harvest Every 2-3 Days", 2, 3,
             "Purpose: Continue regular harvest every 2-3 days. "
             "Benefit: Maintains market grade through continued production. "
             "Timing: DAS 77-83, week 12. "
             "Weather: Pick in the morning. "
             "Follow-up: Log Revenue for each picking."),
            (79, ActivityCategory.FERTILIZER, "MKP Spray", None, 1,
             "Purpose: Apply Mono Potassium Phosphate (MKP 00:52:34) at 5 g/L as foliar spray. "
             "Benefit: Improves pod size, marketable quality and shelf life heading into late production. "
             "Timing: DAS 79, week 12. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Alternate with 19:19:19 and KNO3 on subsequent nutrition cycles."),
            (80, ActivityCategory.SPRAY, "Disease Monitoring", None, 1,
             "Purpose: Check for YVMV (yellow vein mosaic), Powdery Mildew and Cercospora. Capture AI images. "
             "Benefit: Immediately roguing out YVMV-infected plants prevents the whitefly-borne virus from spreading. "
             "Timing: DAS 77-83, week 12. Weekly monitoring. "
             "Weather: Whitefly vector pressure can rise in specific humidity windows. "
             "Follow-up: Rogue and destroy any plants showing yellow vein mosaic symptoms immediately."),
            (81, ActivityCategory.OTHER, "Canopy Management", None, 1,
             "Purpose: Remove old or unproductive lower branches. "
             "Benefit: Improves airflow through the canopy, reducing humidity-driven disease pressure. "
             "Timing: DAS 77-83, week 12. "
             "Weather: Do on a dry day. "
             "Follow-up: Repeat periodically as the canopy continues to grow."),

            # ===== Week 13 (DAS 84-90): Mid-Late Production =======================
            (84, ActivityCategory.IRRIGATION, "As Needed", None, 1,
             "Purpose: Irrigate as needed based on soil moisture and rainfall. "
             "Benefit: Avoids both moisture stress and waterlogging during mid-late production. "
             "Timing: DAS 84-90, week 13. "
             "Weather: Check soil moisture before each decision. "
             "Follow-up: Continue harvest discipline regardless of irrigation timing."),
            (85, ActivityCategory.HARVEST, "Harvest Every 2-3 Days", 2, 3,
             "Purpose: Continue regular harvest every 2-3 days. "
             "Benefit: Maintains yield and grade through mid-late production. "
             "Timing: DAS 84-90, week 13. "
             "Weather: Pick in the morning. "
             "Follow-up: Log Revenue for each picking."),
            (86, ActivityCategory.SPRAY, "FSB Control - Indoxacarb / Chlorpyrifos", None, 1,
             "Purpose: Spray Indoxacarb 0.7 ml/L OR Chlorpyrifos 2 ml/L for fruit/shoot borer. "
             "Benefit: Continues the rotation discipline that has protected yield through peak and sustained production. "
             "Timing: DAS 84-90, week 13. "
             "Weather: Evening application preferred. "
             "Follow-up: Re-assess pest pressure as the season moves toward late production."),
            (87, ActivityCategory.FERTILIZER, "Pod Quality Spray - Potassium Nitrate", None, 1,
             "Purpose: Apply Potassium Nitrate (NOP 13:00:45 / SOP) at 5 g/L as a foliar spray. "
             "Benefit: Improves pod size, colour, shelf life and market quality during this critical mid-late production window. "
             "Timing: DAS 84-90, week 13. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Sample pods at the next harvest for colour and firmness improvement."),
            (88, ActivityCategory.FERTILIZER, "Seaweed Biostimulant", None, 1,
             "Purpose: Apply Seaweed Extract 3 ml/L as foliar spray. "
             "Benefit: Sustains plant energy and pod quality as the crop enters mid-late production. "
             "Timing: DAS 88, week 13. "
             "Weather: Spray in early morning or evening. "
             "Follow-up: Continue alternating with NPK foliar through week 14."),
            (89, ActivityCategory.SPRAY, "Pest Monitoring", None, 1,
             "Purpose: Observe underside of leaves for Whitefly, Thrips, Jassids and Fruit Borer. Threshold-based spray only. "
             "Benefit: Avoids unnecessary input cost while keeping pest pressure in check as season winds down. "
             "Timing: DAS 89, week 13. Weekly scouting. "
             "Weather: Scout in morning. "
             "Follow-up: Log observations. Spray only if threshold is crossed."),

            # ===== Week 14 (DAS 91-97): Late Production ============================
            (91, ActivityCategory.IRRIGATION, "Reduce Slightly", None, 1,
             "Purpose: Reduce irrigation slightly as the plant enters senescence. "
             "Benefit: Matches water input to the plant's declining demand as production winds down. "
             "Timing: DAS 91-97, week 14. "
             "Weather: Adjust based on remaining canopy and pod load. "
             "Follow-up: Continue reducing gradually through week 15."),
            (92, ActivityCategory.HARVEST, "Harvest - Yield Declining", 2, 3,
             "Purpose: Continue harvesting; yield will drop but pods are still being picked every 2-3 days. "
             "Benefit: Capturing the remaining marketable yield is still worthwhile even as volume declines. "
             "Timing: DAS 91-97, week 14. "
             "Weather: Pick in the morning. "
             "Follow-up: Log Revenue for each picking, even if smaller."),
            (93, ActivityCategory.SPRAY, "Minimal Spray", None, 1,
             "Purpose: Observe economic threshold; spray only if genuinely needed. "
             "Benefit: Avoids unnecessary input cost on a crop that is naturally winding down. "
             "Timing: DAS 91-97, week 14. "
             "Weather: No specific precaution. "
             "Follow-up: Reassess weekly whether any spray is still justified."),
            (94, ActivityCategory.OTHER, "Seed Collection", None, 1,
             "Purpose: Collect seeds from the best-performing pods for next season. "
             "Benefit: Saves proven, locally-adapted seed stock and reduces next season's seed cost. "
             "Timing: DAS 91-97, week 14. "
             "Weather: Allow selected pods to mature fully before collecting seed. "
             "Follow-up: Continue selecting seed pods through weeks 15-16."),

            # ===== Week 15 (DAS 98-104): Winding Down ================================
            (98, ActivityCategory.IRRIGATION, "Minimal Irrigation", None, 1,
             "Purpose: Reduce water significantly as the crop winds down. "
             "Benefit: Matches input to the plant's much-reduced demand, avoiding wasted water. "
             "Timing: DAS 98-104, week 15. "
             "Weather: No specific precaution. "
             "Follow-up: Plan to stop irrigation entirely by week 16."),
            (99, ActivityCategory.HARVEST, "Collect Remaining Pods", 2, 3,
             "Purpose: Harvest remaining tender pods. "
             "Benefit: Captures the last meaningfully marketable pods before the crop is terminated. "
             "Timing: DAS 98-104, week 15. "
             "Weather: Pick in the morning. "
             "Follow-up: Log Revenue for any remaining marketable quantity."),
            (100, ActivityCategory.OTHER, "Reduce All Inputs", None, 1,
             "Purpose: Begin reducing all inputs and start planning for crop termination. "
             "Benefit: Avoids spending on inputs the crop can no longer economically use. "
             "Timing: DAS 98-104, week 15. "
             "Weather: No specific precaution. "
             "Follow-up: Plan the crop removal timeline for weeks 16-17."),

            # ===== Week 16 (DAS 105-111): Final Harvest ================================
            (105, ActivityCategory.IRRIGATION, "Stop Irrigation", None, 1,
             "Purpose: Stop irrigation -- no more is needed. "
             "Benefit: The crop is past the point where irrigation improves yield or quality. "
             "Timing: DAS 105-111, week 16. "
             "Weather: No specific precaution. "
             "Follow-up: Allow soil to dry ahead of crop removal."),
            (107, ActivityCategory.HARVEST, "Final Marketable Pods", None, 1,
             "Purpose: Harvest the last marketable pods. "
             "Benefit: Captures the final economic value from the crop before termination. "
             "Timing: DAS 105-111, week 16. "
             "Weather: Pick in the morning. "
             "Follow-up: Log Revenue for the final marketable harvest."),
            (108, ActivityCategory.OTHER, "Seed Pods", None, 1,
             "Purpose: Allow the best pods to fully mature for seed saving. "
             "Benefit: Completes the seed-selection process started in week 14 with fully matured, high-quality seed. "
             "Timing: DAS 105-111, week 16. "
             "Weather: Let pods dry naturally on the plant. "
             "Follow-up: Collect and store seed pods before crop removal."),

            # ===== Week 17 (DAS 112-118): Crop Removal ================================
            (114, ActivityCategory.HARVEST, "Last Harvest", None, 1,
             "Purpose: Final picking of any remaining pods. "
             "Benefit: Ensures nothing marketable is left in the field before uprooting. "
             "Timing: DAS 112-118, week 17. "
             "Weather: No specific precaution. "
             "Follow-up: Log any final Revenue, then proceed to crop removal."),
            (115, ActivityCategory.OTHER, "Begin Crop Removal", None, 1,
             "Purpose: Uproot plants, chop and incorporate into soil or compost. "
             "Benefit: Returns organic matter to the soil and clears the field for the next season. "
             "Timing: DAS 112-118, week 17. "
             "Weather: Do on dry ground for easier uprooting. "
             "Follow-up: Proceed to field clearing and deep ploughing in week 18."),

            # ===== Week 18 (DAS 119-125): Crop End ====================================
            (120, ActivityCategory.OTHER, "Field Clearing", None, 1,
             "Purpose: Remove all plant debris from the field. "
             "Benefit: Reduces pest and disease carryover into the next crop cycle. "
             "Timing: DAS 119-125, week 18. "
             "Weather: No specific precaution. "
             "Follow-up: Proceed to deep ploughing."),
            (122, ActivityCategory.LAND_PREPARATION, "Deep Ploughing", None, 1,
             "Purpose: Plough the field deeply; apply lime if soil pH is low. "
             "Benefit: Breaks up soil and corrects pH ahead of the next season's crop. "
             "Timing: DAS 119-125, week 18. "
             "Weather: Plough when soil is workable, not waterlogged. "
             "Follow-up: Test soil pH if uncertain before deciding on lime application."),
            (124, ActivityCategory.OTHER, "Record Keeping", None, 1,
             "Purpose: Note yield, pest issues, and variety performance for next season's planning. "
             "Benefit: Builds a season-over-season record that improves decisions for future crops. "
             "Timing: DAS 119-125, week 18, end of season. "
             "Weather: No specific precaution. "
             "Follow-up: Review this record when planning next season's Bhindi crop."),
        ],
    },
    {
        "name": "Toor Dal (Pigeon Pea)",
        "description": "Long-duration pigeon pea (Toor/Arhar Dal), rainfed/irrigated cultivation with Rhizobium inoculation, staged micronutrient correction, and ETL-based pest management.",
        "default_duration_days": 237,
        "stages": [
            ('Pre-Sowing', 1, -7, -1, 'Prepare field and seed for sowing. Root establishment and nodulation depend on a well-prepared seedbed and correctly inoculated seed.'),
            ('Germination & Emergence', 2, 0, 13, 'Achieve uniform crop stand. Ensure even emergence; watch for damping-off and cutworms.'),
            ('Crop Establishment', 3, 14, 27, 'Build healthy seedlings. Support early growth without suppressing nodulation; watch for stem fly and wilt.'),
            ('Root & Nodulation', 4, 28, 41, "Build the plant's nitrogen factory. Support nodulation and nitrogen fixation via phosphorus, molybdenum and zinc."),
            ('Vegetative Growth', 5, 42, 55, 'Build biomass and canopy via potassium and sulphur; control leaf webbers/defoliators.'),
            ('Branch Development', 6, 56, 90, 'Build yield sites through branching; correct nutrient deficiencies, including iron on light soils.'),
            ('Pre-Flowering', 7, 91, 104, 'Prepare for flowering via boron and potassium; scout for pod borer and aphids ahead of bud opening.'),
            ('Flowering', 8, 105, 132, 'Maximise flower retention and fruit set via calcium and boron; protect pollinators by avoiding mid-day sprays.'),
            ('Pod Development', 9, 133, 160, 'Maximise pod set through potassium nutrition; control pod fly and pod borer.'),
            ('Seed Filling', 10, 161, 203, 'Increase seed weight and bold grain; protect foliage from Alternaria through to maturity.'),
            ('Maturity', 11, 203, 223, 'Allow natural drying of pods. Stop irrigation, monitor pod colour, watch for lodging and rain risk.'),
            ('Harvest & Post-Harvest', 12, 224, 237, 'Preserve grain quality through correct harvest timing, drying, threshing and safe storage.'),
        ],
        "activities": [
            (-7, ActivityCategory.LAND_PREPARATION, 'Land Preparation', None, 1,
             'Purpose: Plough field 2-3 times, level, and form drainage channels/ridges. Benefit: Pigeon pea is '
             'highly sensitive to waterlogging; good drainage prevents root rot and wilt later in the season. '
             'Timing: DAS -7, before sowing. Weather: Plough only when soil is workable, not wet. Follow-up: '
             'Proceed to seed treatment and basal fertilizer application.',
            ),
            (0, ActivityCategory.OTHER, 'Seed Treatment - Rhizobium + PSB', None, 1,
             'Purpose: Treat seed with Rhizobium culture 25 g/kg seed + PSB (Phosphate Solubilizing Bacteria) 25 '
             'g/kg seed before sowing. Benefit: Inoculation boosts root nodulation and nitrogen fixation, reducing '
             "the crop's need for nitrogen fertilizer. Timing: DAS 0, immediately before sowing. Weather: Keep "
             'treated seed in shade; sow the same day, do not store wet. Follow-up: Confirm nodule formation from '
             'around DAS 20-25.',
            ),
            (0, ActivityCategory.FERTILIZER, 'Basal Dose - SSP + FYM', None, 1,
             'Purpose: Apply Single Super Phosphate (SSP 16% P2O5, 12% S) at 125 kg/acre + Farm Yard Manure (FYM) '
             'at 5-8 t/acre. Benefit: Gives the crop an early phosphorus, sulphur and organic matter base for root '
             'establishment and nodulation. Timing: DAS 0, mixed into soil before sowing. Weather: Apply to '
             'workable, not waterlogged soil. Follow-up: Confirm even mixing across the field before sowing.',
            ),
            (0, ActivityCategory.SOWING, 'Sowing', None, 1,
             'Purpose: Sow at 4-5 cm depth, row spacing 75-90 cm x plant spacing 20-30 cm (long-duration variety). '
             'Seed rate ~3-4 kg/acre. Benefit: Correct depth and spacing gives uniform germination and enough room '
             "for this crop's eventual large canopy. Timing: DAS 0, week 1. Weather: Sow into adequate soil "
             'moisture. Follow-up: Irrigate lightly if soil is dry and no rain is expected.',
            ),
            (0, ActivityCategory.IRRIGATION, 'Pre-Sowing Irrigation', None, 1,
             'Purpose: One irrigation if soil is dry before sowing. Benefit: Ensures adequate moisture for uniform '
             'seed germination. Timing: DAS 0, just before sowing. Weather: Skip if soil is already moist from '
             'recent rain. Follow-up: Sow once soil reaches workable moisture.',
            ),
            (7, ActivityCategory.IRRIGATION, 'Light Irrigation', None, 1,
             'Purpose: Light irrigation every 4-5 days through germination and emergence, if no rain. Benefit: '
             'Maintains even soil moisture for germination without disturbing fragile seedlings. Timing: Every 4-5 '
             'days, DAS 7-13. Weather: Avoid waterlogging; skip if rain has fallen. Follow-up: Check germination '
             'percentage at each irrigation.',
            ),
            (7, ActivityCategory.OTHER, 'Check Germination', None, 1,
             'Purpose: Check germination percentage; target above 85%. Benefit: Confirms stand quality early '
             'enough to gap-fill before it is too late to catch up. Timing: DAS 7-13, week 2. Weather: No specific '
             'precaution. Follow-up: Do gap filling immediately where seedlings are missing.',
            ),
            (10, ActivityCategory.SPRAY, 'Cutworm / Damping-Off Watch', None, 1,
             'Purpose: Scout the base of seedlings for cutworm damage or damping-off; correct drainage if damping- '
             'off is seen, spot-treat only if cutworm damage is found. Benefit: Early intervention prevents '
             'seedling loss that would otherwise need re-sowing. Timing: DAS 7-13, week 2. Weather: No specific '
             'precaution. Follow-up: Continue weekly scouting through crop establishment.',
            ),
            (14, ActivityCategory.IRRIGATION, 'Regular Irrigation', None, 1,
             'Purpose: Irrigate every 5-6 days depending on rainfall. Benefit: Supports steady root and shoot '
             'growth through crop establishment. Timing: Every 5-6 days, DAS 14-20. Weather: Avoid waterlogging. '
             'Follow-up: Continue through Root & Nodulation stage.',
            ),
            (14, ActivityCategory.WEEDING, 'First Weeding', None, 1,
             'Purpose: Hand weeding or shallow hoeing around 20-25 DAS. Benefit: Removes early weed competition '
             'for light, water and nutrients while plants are still small. Timing: DAS 14-20, week 3. Weather: No '
             'specific precaution. Follow-up: Second weeding follows around DAS 45-50.',
            ),
            (18, ActivityCategory.SPRAY, 'Stem Fly / Wilt Watch', None, 1,
             'Purpose: Scout for stem fly entry holes near the base and for wilting plants; rogue out and destroy '
             'wilt-affected plants. Benefit: Stem fly and Fusarium wilt are the main causes of early stand loss in '
             'pigeon pea; early removal limits spread. Timing: DAS 14-20, week 3. Weather: No specific precaution. '
             'Follow-up: Continue wilt watch through Root & Nodulation.',
            ),
            (21, ActivityCategory.FERTILIZER, 'Starter Nitrogen (only if deficient)', None, 1,
             'Purpose: Urea (46% N) at 15-20 kg/acre, only if plants show pale colour or slow growth. Benefit: A '
             'small starter dose corrects visible nitrogen deficiency before nodules become active, without '
             'suppressing the nodulation that follows. Timing: DAS 21-27, only if needed. Weather: Do not apply if '
             'nodulation is progressing well; excess nitrogen suppresses nodule formation. Follow-up: Reassess '
             'plant vigor before considering any further nitrogen.',
            ),
            (21, ActivityCategory.OTHER, 'Plant Vigor Check', None, 1,
             'Purpose: Check for a uniform, vigorous stand; note any patchy or stunted growth. Benefit: Confirms '
             'the crop is ready to move into active root and nodule development. Timing: DAS 21-27, week 4. '
             'Weather: No specific precaution. Follow-up: Begin nodule assessment from around DAS 28.',
            ),
            (28, ActivityCategory.FERTILIZER, 'Molybdenum + Zinc Foliar Spray', None, 1,
             'Purpose: Sodium Molybdate 2 g/L + Zinc Sulphate (ZnSO4, 21% Zn) 5 g/L (0.5%) foliar, OR ZnSO4 5 '
             'kg/acre soil application. Benefit: Molybdenum and zinc are essential cofactors for nitrogenase '
             'enzyme activity in root nodules, directly supporting nitrogen fixation. Timing: DAS 28-34. Weather: '
             'Spray in the morning or evening, not in peak heat. Follow-up: Dig a few plants around DAS 35 to '
             'check nodule health.',
            ),
            (28, ActivityCategory.IRRIGATION, 'Regular Irrigation', None, 1,
             'Purpose: Irrigate every 6-7 days. Benefit: Maintains steady moisture through the wilt-sensitive Root '
             '& Nodulation window without waterlogging. Timing: Every 6-7 days, DAS 28-41. Weather: Avoid '
             'waterlogging - this is a high wilt/root-rot risk window. Follow-up: Continue into Vegetative Growth.',
            ),
            (35, ActivityCategory.OTHER, 'Nodule Assessment', None, 1,
             'Purpose: Dig up a few plants and check roots for active pink/red nodules, the sign of healthy '
             'nitrogen fixation; pale or white nodules indicate poor fixation. Benefit: Confirms whether the '
             "Rhizobium inoculation and Mo/Zn correction are working before the crop's nitrogen demand rises "
             'further. Timing: DAS 35-41, week 6. Weather: No specific precaution. Follow-up: If nodules are pale, '
             're-check soil pH and Mo/P availability.',
            ),
            (35, ActivityCategory.SPRAY, 'Fusarium Wilt Watch', None, 1,
             'Purpose: Inspect for wilting plants; rogue out and destroy affected plants off-field; confirm field '
             'drainage is adequate. Benefit: Fusarium wilt has no in-season cure once established; removing '
             'affected plants limits spread to neighbours. Timing: DAS 35-41, week 6. Weather: No specific '
             'precaution. Follow-up: Continue periodic wilt scouting through flowering.',
            ),
            (42, ActivityCategory.FERTILIZER, 'MOP + Gypsum', None, 1,
             'Purpose: Muriate of Potash (MOP 0:0:60) at 10-15 kg/acre + Gypsum (18% S) at 25 kg/acre, broadcast '
             'and irrigated in. Benefit: Potassium and sulphur support canopy development and overall plant vigor '
             'heading into the branching phase. Timing: DAS 42-48. Weather: Apply to moist, not waterlogged, soil. '
             'Follow-up: Irrigate immediately after broadcasting.',
            ),
            (42, ActivityCategory.IRRIGATION, 'Regular Irrigation', None, 1,
             'Purpose: Irrigate every 6-7 days. Benefit: Supports canopy and root expansion during the main '
             'vegetative growth phase. Timing: Every 6-7 days, DAS 42-55. Weather: Avoid waterlogging. Follow-up: '
             'Continue into Branch Development.',
            ),
            (49, ActivityCategory.WEEDING, 'Second Weeding', None, 1,
             'Purpose: Weed thoroughly around 45-50 DAS; apply mulch between rows if available. Benefit: Removes '
             'weed competition before canopy closes and access becomes difficult. Timing: DAS 49-55, week 8. '
             'Weather: No specific precaution. Follow-up: This is typically the last weeding needed before canopy '
             'closure.',
            ),
            (49, ActivityCategory.SPRAY, 'Leaf Webber / Defoliator Watch', None, 1,
             'Purpose: Scout canopy for webbing or leaf damage; spray only if economic threshold level (ETL) is '
             'crossed. Benefit: Avoids unnecessary spraying while keeping defoliation from reducing photosynthetic '
             'area ahead of flowering. Timing: DAS 49-55, week 8. Weather: No specific precaution. Follow-up: '
             'Continue general pest scouting through Branch Development.',
            ),
            (56, ActivityCategory.OTHER, 'Canopy Check', None, 1,
             'Purpose: Assess canopy development and the onset of branching. Benefit: Confirms the plant is '
             "building the framework that will carry this season's flowers and pods. Timing: DAS 56-62, week 9. "
             'Weather: No specific precaution. Follow-up: Branch count check follows in week 11.',
            ),
            (63, ActivityCategory.FERTILIZER, 'WSF 19:19:19 Foliar (if needed)', None, 1,
             'Purpose: Water Soluble Fertilizer 19:19:19 at 5 g/L foliar, only if deficiency symptoms are visible. '
             'Benefit: A balanced foliar feed corrects minor nutrient gaps quickly during the branching push. '
             'Timing: DAS 63-69, only if needed. Weather: No specific precaution. Follow-up: Reassess after one '
             'application before repeating.',
            ),
            (63, ActivityCategory.IRRIGATION, 'Regular Irrigation', None, 1,
             'Purpose: Irrigate every 6-7 days. Benefit: Maintains steady growth through branch development. '
             'Timing: Every 6-7 days, DAS 63-83. Weather: Avoid waterlogging. Follow-up: Continue into Pre- '
             'Flowering.',
            ),
            (70, ActivityCategory.FERTILIZER, 'Iron Spray (light/sandy soils only)', None, 1,
             'Purpose: FeSO4 0.5% foliar at around 60 DAS if the field is light-textured/sandy soil and leaf '
             'chlorosis is visible. Benefit: Light soils are prone to iron deficiency chlorosis; a foliar spray '
             'corrects this faster than soil correction. Timing: DAS 70-76, only if chlorosis is seen on light '
             'soils. Weather: No specific precaution. Follow-up: Repeat at DAS 90 and 120 if chlorosis persists.',
            ),
            (70, ActivityCategory.OTHER, 'Branch Count Check', None, 1,
             'Purpose: Count branches per plant; correct deficiency if branching is poor. Benefit: Branch count is '
             'a direct proxy for the number of flowering/podding sites this season. Timing: DAS 70-76, week 11. '
             'Weather: No specific precaution. Follow-up: Move into general pest scouting ahead of flowering.',
            ),
            (77, ActivityCategory.SPRAY, 'General Pest Scouting', None, 1,
             'Purpose: Scout for sucking pests and early pod borer moth activity. Benefit: Early detection ahead '
             'of flowering allows control before bud and flower damage occurs. Timing: DAS 77-83, week 12. '
             'Weather: No specific precaution. Follow-up: Pre-Flowering stage begins next week.',
            ),
            (84, ActivityCategory.FERTILIZER, 'Iron Spray #2 (light soils)', None, 1,
             'Purpose: FeSO4 0.5% foliar at around 90 DAS if chlorosis persists on light soils. Benefit: A second '
             'correction if the first iron spray did not fully resolve chlorosis. Timing: DAS 84-90, only if '
             'chlorosis persists. Weather: No specific precaution. Follow-up: Reassess foliage colour before any '
             'third application.',
            ),
            (84, ActivityCategory.IRRIGATION, 'Regular Irrigation', None, 1,
             'Purpose: Irrigate every 6-7 days. Benefit: Maintains growth through the transition into flower bud '
             'formation. Timing: Every 6-7 days, DAS 84-90. Weather: Avoid waterlogging. Follow-up: Continue into '
             'Pre-Flowering stage.',
            ),
            (91, ActivityCategory.FERTILIZER, 'MKP + Borax Foliar Spray', None, 1,
             'Purpose: Mono Potassium Phosphate (MKP 0:52:34) 5 g/L + Borax (10.5% B) 1 g/L foliar. Benefit: '
             'Phosphorus and boron at this stage improve flower initiation and bud quality ahead of flowering. '
             'Timing: DAS 91-97, week 14. Weather: Spray in the morning or evening. Follow-up: Check for visible '
             'flower buds within 1-2 weeks.',
            ),
            (91, ActivityCategory.OTHER, 'Bud Assessment', None, 1,
             'Purpose: Check for flower bud formation in leaf axils. Benefit: Confirms the crop is transitioning '
             'into the reproductive phase on schedule. Timing: DAS 91-97, week 14. Weather: No specific '
             'precaution. Follow-up: Move to pod borer/aphid watch and avoid mid-day spraying once flowering '
             'starts.',
            ),
            (98, ActivityCategory.SPRAY, 'Pod Borer / Aphid Watch', None, 1,
             'Purpose: Scout buds and shoots for pod borer and aphids; spray only if ETL is crossed. Once '
             'flowering starts, avoid spraying 10 AM-4 PM. Benefit: Protects flower buds while avoiding harm to '
             'pollinators once flowers open. Timing: DAS 98-104, week 15. Weather: Avoid spraying during flowering '
             'hours (10 AM-4 PM). Follow-up: Continue this scouting rhythm through Flowering.',
            ),
            (98, ActivityCategory.FERTILIZER, 'Iron Spray #3 (light soils)', None, 1,
             'Purpose: FeSO4 0.5% foliar at around 120 DAS if chlorosis persists on light soils. Benefit: Final '
             'scheduled correction for soils prone to iron deficiency. Timing: DAS 98-104, only if chlorosis '
             'persists. Weather: No specific precaution. Follow-up: Soil-applied Fe or organic matter addition is '
             'a longer-term fix if chlorosis recurs every season.',
            ),
            (105, ActivityCategory.IRRIGATION, 'Critical Irrigation', None, 1,
             'Purpose: Avoid moisture stress during flowering; irrigate if no rain for 5+ days. Benefit: Flowering '
             'is the most moisture-sensitive stage; stress here directly reduces flower retention and pod set. '
             'Timing: DAS 105-111, week 16. Weather: Avoid waterlogging as well as drought stress. Follow-up: '
             'Maintain consistent soil moisture through Pod Development.',
            ),
            (105, ActivityCategory.OTHER, 'Spray Timing Note', None, 1,
             'Purpose: Do NOT spray 10 AM-4 PM during flowering hours to protect pollinators. Benefit: Pigeon pea '
             'flowers are insect-pollinated; daytime sprays during peak pollinator activity reduce fruit set. '
             'Timing: DAS 105-111, week 16. Weather: No specific precaution. Follow-up: Applies to all spray '
             'activities through the Flowering and Pod Development stages.',
            ),
            (112, ActivityCategory.FERTILIZER, 'Calcium + Boron Foliar Spray', None, 1,
             'Purpose: Calcium Nitrate (15.5% N, 19% Ca) 2 g/L + Borax 1 g/L foliar. Benefit: Calcium and boron '
             'support pollen viability and reduce flower drop, directly improving fruit set percentage. Timing: '
             'DAS 112-118, week 17. Weather: Spray in early morning or evening, never 10 AM-4 PM. Follow-up: '
             'Monitor flower retention over the following week.',
            ),
            (112, ActivityCategory.SPRAY, 'Pod Borer Watch', None, 1,
             'Purpose: Scout pods and buds for pod borer; spray if ETL is crossed, rotating chemistry to avoid '
             'resistance. Benefit: Pod borer is the single largest yield-loss risk in pigeon pea from flowering '
             'through pod development. Timing: DAS 112-118, week 17. Weather: Spray in early morning or evening, '
             'never 10 AM-4 PM. Follow-up: Continue rotation through Pod Development and Seed Filling.',
            ),
            (119, ActivityCategory.SPRAY, 'Sterility Mosaic Watch', None, 1,
             'Purpose: Rogue out and destroy any plants showing bushy, sterile, mosaic-mottled growth (mite- '
             'vectored sterility mosaic disease). Benefit: There is no in-season cure for sterility mosaic; '
             'removing infected plants limits mite-borne spread to healthy plants. Timing: DAS 119-125, week 18. '
             'Weather: No specific precaution. Follow-up: Continue this watch through Pod Development.',
            ),
            (126, ActivityCategory.OTHER, 'Flower Drop Check', None, 1,
             'Purpose: Monitor flower retention on tagged branches; correct nutrition or irrigation if drop is '
             'excessive. Benefit: Confirms whether the calcium/boron correction and irrigation discipline are '
             'translating into retained flowers. Timing: DAS 126-132, week 19. Weather: No specific precaution. '
             'Follow-up: Pod Development stage begins next week.',
            ),
            (133, ActivityCategory.FERTILIZER, 'Potassium Nitrate Foliar Spray', None, 1,
             'Purpose: Potassium Nitrate (13:0:45) at 5 g/L foliar. Benefit: Potassium at pod-set is the key '
             'driver of pod number and pod fill; this is the most yield-sensitive nutrient stage. Timing: DAS '
             '133-139, week 20. Weather: Spray in early morning or evening. Follow-up: Repeat application is '
             'planned for week 23 (Seed Filling).',
            ),
            (133, ActivityCategory.IRRIGATION, 'Consistent Irrigation', None, 1,
             'Purpose: Irrigate every 6-7 days; irregular watering causes poor pod fill. Benefit: Pod Development '
             'is highly sensitive to moisture fluctuation, which directly affects pod and seed size. Timing: Every '
             '6-7 days, DAS 133-153. Weather: Avoid waterlogging as well as drought stress. Follow-up: Taper '
             'irrigation gradually from Seed Filling onward.',
            ),
            (140, ActivityCategory.SPRAY, 'Pod Fly / Pod Borer Control', None, 1,
             'Purpose: Scout pods for entry holes; spray if ETL is crossed, rotating chemistry to avoid resistance '
             'build-up. Benefit: Pod fly and pod borer larvae feed inside developing pods, directly reducing '
             'harvestable seed. Timing: DAS 140-146, week 21. Weather: Observe pre-harvest interval on any product '
             'used. Follow-up: Continue rotation through Seed Filling.',
            ),
            (147, ActivityCategory.OTHER, 'Pod Count Check', None, 1,
             'Purpose: Assess pods per plant. Benefit: A direct early indicator of expected yield, useful for '
             'deciding whether further nutrient correction is worthwhile. Timing: DAS 147-153, week 22. Weather: '
             'No specific precaution. Follow-up: Compare against expected pods/plant for the variety.',
            ),
            (154, ActivityCategory.FERTILIZER, 'Potassium Nitrate Foliar Spray #2', None, 1,
             'Purpose: Potassium Nitrate (13:0:45) at 5 g/L foliar, repeat application. Benefit: A second '
             'potassium application sustains pod fill quality as more pods set. Timing: DAS 154-160, week 23. '
             'Weather: Spray in early morning or evening. Follow-up: Seed Filling stage begins next week.',
            ),
            (161, ActivityCategory.SPRAY, 'Alternaria Leaf Spot Watch', None, 1,
             'Purpose: Spray a Mancozeb-based fungicide if leaf spotting is observed. Benefit: Protects the '
             'remaining leaf area that is fuelling grain fill through senescence-driven yield loss. Timing: DAS '
             '161-167, week 24. Weather: No specific precaution. Follow-up: Continue monitoring through to '
             'Maturity.',
            ),
            (161, ActivityCategory.IRRIGATION, 'Regular Irrigation', None, 1,
             'Purpose: Irrigate every 6-7 days; avoid moisture stress during grain filling. Benefit: Moisture '
             'stress during seed fill directly reduces final seed/grain weight. Timing: Every 6-7 days, DAS '
             '161-189. Weather: Avoid waterlogging as well as drought stress. Follow-up: Begin tapering irrigation '
             'from around DAS 189.',
            ),
            (168, ActivityCategory.FERTILIZER, 'Potassium Nitrate Foliar Spray #3', None, 1,
             'Purpose: Potassium Nitrate (13:0:45) at 5 g/L foliar. Benefit: A third potassium application '
             'supports seed weight and bold grain formation. Timing: DAS 168-174, week 25. Weather: Spray in early '
             'morning or evening. Follow-up: This is typically the last scheduled foliar nutrient spray.',
            ),
            (175, ActivityCategory.OTHER, 'Crop Monitoring', None, 1,
             'Purpose: General field walk for pest, disease, and lodging risk. Benefit: Catches any late-season '
             'issue before it affects the harvestable crop. Timing: DAS 175-181, week 26. Weather: No specific '
             'precaution. Follow-up: Continue weekly through to harvest.',
            ),
            (182, ActivityCategory.SPRAY, 'Pod Borer Late-Season Check', None, 1,
             'Purpose: Scout for late infestations; spray only if ETL is crossed, observing pre-harvest interval. '
             'Benefit: Late-season pod borer can still cause significant loss right before harvest if unchecked. '
             'Timing: DAS 182-188, week 27. Weather: Observe pre-harvest interval on any product used. Follow-up: '
             'This is typically the last pest-control intervention before maturity.',
            ),
            (189, ActivityCategory.IRRIGATION, 'Taper Irrigation', None, 1,
             'Purpose: Begin reducing irrigation frequency as pods mature. Benefit: Gradually reducing moisture '
             'supports natural pod drying without inducing premature stress. Timing: DAS 189-195, week 28. '
             'Weather: No specific precaution. Follow-up: Stop irrigation entirely once Maturity stage is reached.',
            ),
            (196, ActivityCategory.OTHER, 'Seed Fill Check', None, 1,
             'Purpose: Check grain filling progress inside pods. Benefit: Confirms grain weight is developing as '
             'expected ahead of the final maturity push. Timing: DAS 196-203, week 29. Weather: No specific '
             'precaution. Follow-up: Maturity stage begins next week.',
            ),
            (203, ActivityCategory.IRRIGATION, 'Stop Irrigation', None, 1,
             'Purpose: Withhold irrigation to allow natural drying of pods. Benefit: Continued irrigation at this '
             'point delays drying and risks pod/grain quality issues. Timing: DAS 203-209, week 30. Weather: No '
             'specific precaution. Follow-up: Begin monitoring pod colour for the harvest signal.',
            ),
            (203, ActivityCategory.OTHER, 'Pod Colour Check', None, 1,
             'Purpose: Monitor pod colour change from green to brown/straw as a maturity indicator. Benefit: Pod '
             'colour is the most reliable field signal for harvest timing in pigeon pea. Timing: DAS 203-209, week '
             '30. Weather: No specific precaution. Follow-up: Plan harvest once 75-80% of pods have changed '
             'colour.',
            ),
            (210, ActivityCategory.OTHER, 'Lodging / Weather Watch', None, 1,
             'Purpose: Watch for lodging risk and unseasonal rain; plan harvest timing accordingly. Benefit: '
             'Lodged or rain-soaked mature pods are prone to shattering and quality loss. Timing: DAS 210-216, '
             'week 31. Weather: Prioritise harvest if heavy rain or strong wind is forecast. Follow-up: Finalise '
             'harvest planning.',
            ),
            (217, ActivityCategory.OTHER, 'Harvest Planning', None, 1,
             'Purpose: Arrange labour and equipment for harvest; prepare the drying/threshing area. Benefit: '
             'Pigeon pea harvest is labour-intensive; advance planning avoids losses from delayed picking. Timing: '
             'DAS 217-223, week 32. Weather: No specific precaution. Follow-up: Harvest begins once 75-80% of pods '
             'are dry.',
            ),
            (224, ActivityCategory.HARVEST, 'Harvest Crop', None, 1,
             'Purpose: Harvest when approximately 75-80% of pods are dry/brown; cut plants or hand-pick dry pods. '
             'Benefit: Harvesting at the right maturity window maximises both yield and grain quality. Timing: DAS '
             '224-230, week 33. Weather: Harvest on a dry day where possible. Follow-up: Sun-dry harvested '
             'pods/plants before threshing.',
            ),
            (224, ActivityCategory.OTHER, 'Drying', None, 1,
             'Purpose: Sun-dry harvested pods or plants before threshing. Benefit: Reduces moisture to a safe '
             'level for threshing and prevents fungal spoilage. Timing: DAS 224-230, week 33. Weather: Spread '
             'thinly and turn regularly for even drying. Follow-up: Thresh once pods are fully dry and brittle.',
            ),
            (231, ActivityCategory.OTHER, 'Threshing & Storage', None, 1,
             'Purpose: Thresh, clean, and dry grain to safe storage moisture (around 10-12%); store in pest-proof '
             'containers. Benefit: Correct storage moisture and containers are the main defence against storage '
             'pest infestation and spoilage. Timing: DAS 231-237, week 34. Weather: No specific precaution. '
             'Follow-up: Inspect stored grain periodically through the storage period.',
            ),
            (231, ActivityCategory.SPRAY, 'Storage Pest Watch', None, 1,
             'Purpose: Inspect stored grain periodically for bruchid/weevil infestation; use hermetic bags or '
             'fumigation as needed. Benefit: Bruchid beetles can heavily damage stored pigeon pea grain if '
             'infestation goes unchecked. Timing: Periodic, through storage. Weather: Follow label safety '
             "precautions for any fumigant used. Follow-up: Carry findings into next season's storage planning.",
            ),
            (231, ActivityCategory.OTHER, 'Record Keeping', None, 1,
             "Purpose: Note yield, pest/disease issues, and variety performance for next season's planning. "
             'Benefit: Builds a season-over-season record that improves decisions for future crops. Timing: DAS '
             '231-237, week 34, end of season. Weather: No specific precaution. Follow-up: Review this record when '
             "planning next season's Toor Dal crop.",
            ),
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


def _activity(day_offset, category, name, repeat_interval, repeat_count, remarks):
    """
    Back-compat wrapper: builds a plain Layer-1 9-tuple from the old 6-tuple
    shape, for crops that haven't adopted Layer 1.5/2 yet. Existing seed
    files (Rice, Cotton, Tomato, etc.) can keep using the 6-tuple shape
    unchanged via create_new_version(activities=[_activity(*row) for row
    in OLD_ACTIVITIES]) -- this function is the only place that needs to
    know about the shape change.
    """
    return (day_offset, category, name, repeat_interval, repeat_count, remarks,
            False, False, None, None,
            None, None, None, None, None)


def create_new_version(
    crop_name: str,
    label: str,
    change_notes: str,
    stages: list[tuple[str, int, int, int, str]],
    activities: list[tuple],
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

    activities tuple shape -- 10 fields (legacy) or 15 fields (adds
    recovery metadata, services/decisions/recovery_engine.py):
        (day_offset, category, name, repeat_interval, repeat_count, remarks,
         is_conditional, feeds_context, trigger_logic, trigger_conditions,
         [valid_until_stage, max_delay_days, recovery_type,
          replacement_operation_name, expected_impact])
    Crops that haven't adopted Layer 1.5/2 can build the 10-field shape from
    their existing 6-tuple seed data via the _activity() wrapper above, with
    zero edits to their own seed data; it now emits 15 fields with the
    trailing 5 defaulted to None, so nothing behaves differently.

    replacement_operation_name is resolved to an actual
    ActivityTemplate.id by *name*, against the other activities in this
    same call/version, in a second pass after every row has been inserted
    (so forward references -- a DAS 26 row pointing at a DAS 46 row -- work
    without needing the target's id up front). A name that doesn't match
    any activity in this version raises ValueError rather than silently
    leaving the replacement unset.

    Example:
        create_new_version(
            crop_name="Rice (Paddy)",
            label="2027 Revised Nitrogen Schedule",
            change_notes="Split urea top-dressing into 3 doses per "
                          "updated state agricultural department guidance.",
            stages=[...],       # same shape as CROPS[i]["stages"]
            activities=[_activity(*row) for row in OLD_ACTIVITIES],
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

        by_name: dict[str, ActivityTemplate] = {}
        pending_replacements: list[tuple[ActivityTemplate, str]] = []

        for row in activities:
            if len(row) == 10:
                (day_offset, category, name, repeat_interval, repeat_count, remarks,
                 is_conditional, feeds_context, trigger_logic, trigger_conditions) = row
                valid_until_stage = max_delay_days = recovery_type = replacement_name = expected_impact = None
            elif len(row) == 15:
                (day_offset, category, name, repeat_interval, repeat_count, remarks,
                 is_conditional, feeds_context, trigger_logic, trigger_conditions,
                 valid_until_stage, max_delay_days, recovery_type, replacement_name, expected_impact) = row
            else:
                raise ValueError(
                    f"Unexpected activity tuple length {len(row)} for {crop_name!r} "
                    f"(expected 10 or 15 fields): {row!r}"
                )

            template = ActivityTemplate(
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
                valid_until_stage=valid_until_stage,
                max_delay_days=max_delay_days,
                recovery_type=recovery_type,
                expected_impact=expected_impact,
            )
            session.add(template)
            session.flush()  # need template.id available for by-name lookup below
            by_name[name] = template
            if replacement_name:
                pending_replacements.append((template, replacement_name))

        for template, replacement_name in pending_replacements:
            target = by_name.get(replacement_name)
            if target is None:
                raise ValueError(
                    f"{crop_name!r} version {next_number}: activity {template.name!r} "
                    f"names a replacement_operation {replacement_name!r} that doesn't "
                    f"match any activity name in this same version."
                )
            template.replacement_template_id = target.id
        session.flush()

        print(f"Created version {next_number} for {crop_name!r}: {label}")


if __name__ == "__main__":
    seed_crop_master()
