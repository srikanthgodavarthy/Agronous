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
