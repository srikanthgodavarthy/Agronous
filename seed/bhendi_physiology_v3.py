"""
Bhindi (Okra) -- Decision-Oriented Crop Advisory Engine (v3)
================================================================
Layer 1 (planned operations) / Layer 1.5 (mandatory, evidence-producing
assessments) / Layer 2 (conditional operations, evidence-gated) / Layer 3
(knowledge cards). See docs/bhindi_v3_design.md for the full reclassification
rationale; this module is the executable seed.

This adds a NEW CropTemplateVersion for "Bhindi (Okra)" on top of v2 --
never editing existing CropStage/ActivityTemplate rows in place, per this
codebase's own rule.

Run with:  python -m seed.bhendi_physiology_v3
(Run AFTER seed.crop_master_seed, seed.bhendi_physiology_v2, AND the
 8a1d4f7c2e90 migration that adds is_conditional/feeds_context/trigger_logic/
 trigger_conditions to activity_template.)
"""
from __future__ import annotations

from db.models import ActivityCategory, TriggerLogic
from seed.crop_master_seed import create_new_version


def _card(*, priority, category, product, dosage, method, timing,
          purpose, benefit, precautions, composition=None, water_volume=None,
          indicator=None) -> str:
    """
    Render one Agronous recommendation card as structured text. Field labels
    are parsed by _parse_remarks() in pages/2_Cultivation_Schedule.py:
        Priority / Product / Composition / Dose / Water / Method / Timing /
        Indicator / Objective / Why / Precautions
    """
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
    """Planned operation: always scheduled at season creation, unconditional."""
    return (day_offset, category, name, repeat_interval, repeat_count, remarks,
            False, False, None, None)


def _layer1_5(day_offset, category, name, remarks):
    """Mandatory assessment: always scheduled, produces evidence, never conditional."""
    return (day_offset, category, name, None, 1, remarks, False, True, None, None)


def _layer2(day_offset, category, name, remarks, trigger_conditions, trigger_logic=TriggerLogic.ALL):
    """Conditional operation: never auto-materializes; Decision Engine gates it."""
    return (day_offset, category, name, None, 1, remarks, True, False, trigger_logic, trigger_conditions)


STAGES = [
    (
        "Germination & Establishment", 1, 0, 12,
        "Plant Need: establish strong primary/secondary roots, achieve uniform "
        "stand establishment, protect the germinating seed from soil-borne rot. "
        "Before moving to the next stage verify: (1) 80%+ germination achieved; "
        "(2) healthy true-leaf emergence across the stand; (3) no cutworm/"
        "damping-off damage at the soil line.",
    ),
    (
        "Early Vegetative Growth", 2, 13, 25,
        "Plant Need: build root architecture, develop a healthy initial canopy, "
        "establish efficient nutrient uptake machinery before the growth surge. "
        "Before moving to the next stage verify: (1) even plant spacing after "
        "thinning; (2) dark-green, vigorous first true leaves; (3) no early "
        "sucking-pest buildup on tender growth.",
    ),
    (
        "Rapid Vegetative Growth", 3, 26, 35,
        "Plant Need: maximize photosynthetic leaf area, promote branching, begin "
        "building carbohydrate reserves that will fund flowering. Before moving "
        "to the next stage verify: (1) rapid internode and leaf expansion "
        "underway; (2) dark green foliage free of zinc/boron deficiency "
        "mottling; (3) field drainage channels open ahead of monsoon.",
    ),
    (
        "Flower Bud Initiation", 4, 36, 45,
        "Plant Need: trigger and sustain flower bud formation, build boron and "
        "calcium reserves ahead of fruit set, protect the canopy through the "
        "monsoon-risk window. Before moving to the next stage verify: (1) first "
        "visible flower buds in leaf axils; (2) no waterlogging at the root "
        "zone; (3) shoot/fruit borer dead hearts caught and removed early.",
    ),
    (
        "Flowering & Fruit Set", 5, 46, 55,
        "Plant Need: maximize pollen viability and pollination success, "
        "minimize flower abortion, move calcium and boron to actively dividing "
        "fruit-set tissue, protect open flowers from pests without harming "
        "pollinators. Before moving to the next stage verify: (1) high "
        "fruit-set percentage on tagged flowers; (2) minimal flower drop "
        "observed; (3) all sprays this stage confined to early morning/evening, "
        "never 10 AM-4 PM.",
    ),
    (
        "Fruit Development", 6, 56, 62,
        "Plant Need: drive cell division then cell expansion in the pod, move "
        "carbohydrate to the developing sink, sustain consistent moisture so "
        "pods do not turn fibrous. Before moving to the next stage verify: "
        "(1) uniform pod sizing with no curved/twisted pods (a moisture-stress "
        "symptom); (2) tender pod texture confirmed at first picking size; "
        "(3) staking and lower-canopy sanitation completed ahead of continuous "
        "harvest.",
    ),
    (
        "Peak Harvest", 7, 63, 90,
        "Plant Need: sustain continuous flowering alongside fruiting (a "
        "high-demand dual load), replenish potassium removed by every picking, "
        "keep the canopy photosynthetically active, hold pest and disease "
        "pressure below the economic threshold without disrupting the harvest "
        "interval. Before moving to the next stage verify: (1) steady pod yield "
        "every picking with no yellowing canopy; (2) spray-to-harvest interval "
        "(PHI) respected throughout; (3) no unrogued YVMV-symptomatic plants "
        "remaining in the field.",
    ),
    (
        "Late Harvest", 8, 91, 110,
        "Plant Need: delay senescence, extend the productive picking window as "
        "long as input economics justify, maintain pod quality even as natural "
        "yield decline begins. Before moving to the next stage verify: "
        "(1) gradual, not sudden, decline in picking volume; (2) canopy still "
        "functional with no disease explosion in the ageing lower leaves; "
        "(3) seed-retention pods (if any) tagged and left to mature fully.",
    ),
    (
        "Crop Termination", 9, 111, 120,
        "Plant Need: none -- the plant's economic life is over; the remaining "
        "need is the next crop's. Focus shifts to safe residue removal and "
        "breaking the pest/disease carryover cycle into the following season. "
        "Before moving to the next crop verify: (1) complete uprooting with no "
        "infested residue left on the surface; (2) deep ploughing completed in "
        "dry weather; (3) all Expense/Revenue entries reconciled and the Season "
        "marked Completed.",
    ),
]


ACTIVITIES = [
    # =================================================================
    # STAGE 1 -- GERMINATION & ESTABLISHMENT (DAS 0-12) -- Layer 1
    # =================================================================
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
    _layer1(0, ActivityCategory.OTHER, "Protect Germinating Seed - Seed Treatment", None, 1, _card(
        priority="Essential", category="Biostimulant / Seed Protectant",
        product="Thiram (fungicide) OR Trichoderma viride (biofungicide)",
        composition="Thiram 75% WP or Trichoderma 1% WP",
        dosage="Thiram 2 g/kg seed OR Trichoderma 4 g/kg seed",
        method="Seed coating before sowing", timing="Immediately before sowing, same day",
        purpose="The germinating seed and emerging radicle are highly vulnerable to "
                "soil-borne Pythium/Rhizoctonia rot; a protective barrier on the seed "
                "coat is the only window to prevent this before infection is possible.",
        benefit="Prevents seed rot and damping-off, protecting final stand count.",
        precautions="Do not store treated seed wet; sow the same day. Wear gloves during treatment.",
    )),
    _layer1(0, ActivityCategory.FERTILIZER, "Establish Roots - Basal Phosphorus & Potassium", None, 1, _card(
        priority="Essential", category="Basal Fertilizer",
        product="Di-Ammonium Phosphate (DAP) + Muriate of Potash (MOP)",
        composition="DAP 18:46:0; MOP 0:0:60", dosage="DAP 40 kg/acre + MOP 35 kg/acre",
        water_volume="Not applicable (soil-applied)", method="Broadcast and mix into soil before sowing",
        timing="Before sowing, DAS 0",
        purpose="Phosphorus is immobile in soil and must be positioned at the root zone "
                "before sowing -- roots cannot forage far for it. Potassium at this stage "
                "supports early cell-wall strength and disease resistance in the radicle.",
        benefit="Strong, early root architecture and a sturdy seedling base.",
        precautions="Apply to workable soil, not waterlogged; ensure even mixing to avoid "
                    "localized salt injury to germinating seed.",
    )),
    _layer1(0, ActivityCategory.FERTILIZER, "Correct Soil-Type Iron Deficiency - Basal Iron Correction", None, 1, _card(
        priority="Conditional", category="Micronutrient (Basal)", product="Ferrous Sulphate (soil-applied)",
        composition="FeSO4 19% Fe", dosage="10 kg/acre, only on calcareous/high-pH soils",
        water_volume="Not applicable (soil-applied)", method="Mix into the basal band at sowing",
        timing="Before sowing, DAS 0, only where soil type warrants it",
        purpose="On calcareous or high-pH soils, iron becomes chemically unavailable to "
                "roots regardless of total soil iron content; correcting this at the basal "
                "stage prevents interveinal chlorosis before it ever appears, since soil "
                "type is fixed for the farm and known at season creation, not an evolving "
                "field condition that needs re-checking.",
        benefit="Prevents iron-deficiency chlorosis on soils prone to it, without requiring "
                "ongoing field monitoring.",
        precautions="Apply only on farms with known calcareous/alkaline soil history; "
                    "unnecessary on neutral/acidic soils. Confirm soil type before applying.",
    )),
    _layer1(0, ActivityCategory.IRRIGATION, "Germination Moisture - Pre-Sowing Irrigation", None, 1, _card(
        priority="Essential", category="Irrigation", product="Surface/Flood Irrigation",
        dosage="One irrigation if soil is dry", method="Furrow/flood",
        timing="Just before sowing, only if soil moisture is inadequate",
        purpose="Imbibition (water uptake by the seed) is the trigger for germination; "
                "without adequate moisture the seed cannot begin metabolic activation.",
        benefit="Ensures the moisture threshold needed for germination is met uniformly.",
        precautions="Skip if soil is already moist from recent rain to avoid waterlogging the seed zone.",
    )),
    _layer1(3, ActivityCategory.IRRIGATION, "Sustain Germination Moisture", None, 1, _card(
        priority="Essential", category="Irrigation", product="Light Irrigation",
        dosage="Light, shallow watering", method="Sprinkler or light furrow flow",
        timing="DAS 3, only if no rain has fallen",
        purpose="The seed zone must stay moist (not saturated) through the full "
                "germination window or the emerging radicle desiccates.",
        benefit="Keeps germination uniform across the field without waterlogging risk.",
        precautions="Avoid waterlogging; skip entirely if recent rain has met demand.",
    )),
    _layer1(7, ActivityCategory.IRRIGATION, "Sustain Emergence Moisture", 4, 2, _card(
        priority="Essential", category="Irrigation", product="Light Irrigation",
        dosage="Light irrigation every 4-5 days", method="Furrow/drip", timing="DAS 7-12",
        purpose="Continued even moisture supports the transition from radicle to "
                "true-leaf emergence without root-zone stress.",
        benefit="Maintains stand uniformity through emergence.",
        precautions="Avoid disturbing fragile seedlings; light watering only.",
    )),

    # =================================================================
    # STAGE 1 -- Layer 1.5 (mandatory assessment)
    # =================================================================
    _layer1_5(8, ActivityCategory.OTHER, "Confirm Stand Establishment - Germination Check & Gap Filling", _card(
        priority="Essential", category="Crop Operation", product="Field Scouting + Gap Filling",
        dosage="Not applicable", method="Visual count across representative rows",
        timing="DAS 7-12, before roots intertwine",
        indicator="Record germination percentage and any cut/wilted seedlings at the soil "
                  "line as an Observation note or photo -- this evidence gates the "
                  "conditional Cutworm & Damping-Off Control operation below, alongside "
                  "the dedicated scouting pass on DAS 9.",
        purpose="Final stand count must be confirmed and corrected while gap-filling is "
                "still viable -- after this window, replacement seedlings lag too far "
                "behind to contribute meaningfully to yield.",
        benefit="Confirms target stand (>70% germination); gaps filled now reach harvest "
                "in step with the main stand.",
        precautions="Gap-fill with pre-soaked seed or raised seedlings of the same age class where possible.",
    )),
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

    # =================================================================
    # STAGE 1 -- Layer 2 (conditional operation)
    # =================================================================
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

    # =================================================================
    # STAGE 2 -- EARLY VEGETATIVE GROWTH (DAS 13-25) -- Layer 1
    # =================================================================
    _layer1(14, ActivityCategory.IRRIGATION, "Build Root System - Regular Irrigation", 5, 2, _card(
        priority="Essential", category="Irrigation", product="Furrow/Drip Irrigation",
        dosage="Regular irrigation every 5-6 days", method="Furrow or drip", timing="DAS 14-25",
        purpose="Steady, non-fluctuating moisture drives uninterrupted root elongation; "
                "wet-dry cycling at this stage produces a shallow, stress-prone root system.",
        benefit="Builds the deep, steady root system the plant will draw on through fruiting.",
        precautions="Adjust downward if rainfall has already met crop demand to avoid root suffocation.",
    )),
    _layer1(16, ActivityCategory.OTHER, "Remove Root Competition - Thinning", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Manual Thinning",
        dosage="Retain 1 healthy plant per hill", method="Hand removal of weaker seedlings",
        timing="DAS 14-20, cooler part of the day",
        purpose="Multiple seedlings at one hill compete for the same root volume and light; "
                "without thinning, every retained plant's root and canopy development is suppressed.",
        benefit="The retained plant develops a stronger, undivided root system and canopy.",
        precautions="Thin on a cooler day to reduce transplant-shock-like stress on remaining plants; water lightly after.",
    )),
    _layer1(16, ActivityCategory.WEEDING, "Reduce Nutrient Competition - First Weeding", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Hand Weeding / Shallow Hoeing",
        dosage="Not applicable", method="Hand or hoe", timing="DAS 14-20",
        purpose="Weeds compete directly for the same nitrogen and water the establishing "
                "root system needs; early removal protects the narrow window of root development.",
        benefit="Reduces early competition for nutrients and water during establishment.",
        precautions="Avoid weeding waterlogged soil to prevent compaction and root damage.",
    )),
    _layer1(20, ActivityCategory.FERTILIZER, "Support Early Uptake Machinery - Starter Foliar NPK", None, 1, _card(
        priority="Essential", category="Foliar Nutrition", product="Water Soluble NPK (19:19:19)",
        composition="19:19:19 + micronutrients", dosage="5 g/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Early morning or evening",
        purpose="Foliar feeding bridges the gap while the root system is still developing "
                "its full absorptive capacity, ensuring no nutrient lag during the canopy build-up phase.",
        benefit="Sustains uptake efficiency and supports early leaf area expansion.",
        precautions="Avoid spraying during peak midday heat to prevent leaf scorch.",
    )),
    _layer1(22, ActivityCategory.FERTILIZER, "Correct Magnesium Deficiency - Conditional Foliar", None, 1, _card(
        priority="Conditional", category="Micronutrient (Foliar)", product="Magnesium Sulphate (Epsom Salt)",
        composition="MgSO4.7H2O 9.6% Mg", dosage="5 g/L, only on confirmed interveinal chlorosis",
        water_volume="200 litres/acre", method="Foliar spray", timing="Early morning or evening",
        purpose="Magnesium is the central atom of chlorophyll; interveinal yellowing on "
                "older leaves signals it is already limiting photosynthesis, and correcting "
                "it now protects the canopy build-up this stage depends on.",
        benefit="Restores chlorophyll synthesis and canopy colour where deficiency is confirmed.",
        precautions="Do not apply preventively on healthy green foliage; confirm symptom "
                    "pattern (older-leaf interveinal yellowing) before spraying.",
    )),

    # =================================================================
    # STAGE 2 -- Layer 1.5 / Layer 2
    # =================================================================
    _layer1_5(18, ActivityCategory.SPRAY, "Vector Pest Scouting - Aphid/Whitefly", _card(
        priority="Essential", category="Pest Monitoring (IPM)", product="Field Scouting",
        dosage="Not applicable", method="Inspect leaf undersides for aphid/whitefly colonies",
        timing="DAS 16-22",
        indicator="Record presence/absence and rough colony density of aphids/whitefly on "
                  "leaf undersides as an Observation note or photo -- this evidence gates "
                  "the conditional Vector Pest Control operation below.",
        purpose="Aphids and whitefly are not just direct feeders but vectors of Yellow Vein "
                "Mosaic Virus (YVMV); this scouting pass is the evidence-gathering step the "
                "Decision Engine reads to decide whether vector control is warranted before "
                "the incurable viral disease can establish.",
        benefit="Produces the field evidence that determines whether vector intervention is warranted.",
        precautions="Inspect leaf undersides specifically, not just upper canopy; sample across the field.",
    )),
    _layer2(18, ActivityCategory.SPRAY, "Vector Pest Control (Aphid/Whitefly)", _card(
        priority="Conditional", category="Biological / Botanical Insecticide (threshold-based)",
        product="Neem Oil + Teepol (wetting agent)", composition="Neem oil 1500 ppm",
        dosage="Neem oil 5 ml/L + Teepol 1 ml/L", water_volume="200 litres/acre",
        method="Foliar spray, undersides of leaves", timing="Early morning or evening, on confirmed infestation",
        purpose="Controlling the vector population early prevents an incurable viral "
                "disease later, not just direct feeding damage.",
        benefit="Suppresses sucking pest populations before they can transmit virus.",
        precautions="Threshold-based only; avoid unnecessary blanket spraying. Low pollinator risk pre-flowering.",
    ), trigger_conditions=["PEST_APHID_WHITEFLY_VECTOR"]),

    # =================================================================
    # STAGE 3 -- RAPID VEGETATIVE GROWTH (DAS 26-35) -- Layer 1
    # =================================================================
    _layer1(26, ActivityCategory.IRRIGATION, "Sustain Growth Surge - Regular Irrigation", 5, 2, _card(
        priority="Essential", category="Irrigation", product="Furrow/Drip Irrigation",
        dosage="Every 5-6 days; increase if hot/dry", method="Furrow or drip", timing="DAS 26-35",
        purpose="This is the period of maximum leaf-area expansion rate; moisture stress "
                "now directly truncates final canopy size and the carbohydrate reserves it builds.",
        benefit="Prevents moisture stress during the active vegetative growth surge.",
        precautions="Increase frequency in unusually hot, dry weather; check drainage readiness before monsoon.",
    )),
    _layer1(26, ActivityCategory.FERTILIZER, "Fuel Branching Framework - Top Dressing #1 (Nitrogen)", None, 1, _card(
        priority="Essential", category="Top Dressing", product="Ammonium Sulphate",
        composition="20.6:0:0 + 24S", dosage="75 kg/acre",
        method="Band placement between rows, irrigate immediately", timing="Morning, followed by irrigation",
        purpose="Nitrogen is the building block of new leaf and stem tissue; supplying it "
                "now, paired with the sulphur in this source, fuels the branching framework "
                "that will carry the eventual fruit load.",
        benefit="Drives active vegetative growth and branching that supports later fruiting.",
        precautions="Broadcast evenly and irrigate immediately to avoid surface volatilization losses; "
                    "avoid contact with foliage.",
    )),
    _layer1(28, ActivityCategory.OTHER, "Improve Anchorage - Earthing Up", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Light Hilling",
        dosage="Not applicable", method="Hand hoeing around base", timing="DAS 26-35",
        purpose="As stem height and eventual fruit load increase, the existing root collar "
                "needs additional soil support to resist lodging.",
        benefit="Improves anchorage and root support as plants grow taller.",
        precautions="Avoid in waterlogged soil; re-check before canopy closes.",
    )),
    _layer1(29, ActivityCategory.WEEDING, "Last Weeding Window - Second Weeding", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Hand Weeding + Mulch",
        dosage="Not applicable", method="Hand/hoe, apply mulch between rows if available",
        timing="DAS 26-35, dry soil",
        purpose="This is the last practical weeding window before canopy closure makes "
                "in-row access impossible; mulch conserves moisture into the approaching monsoon.",
        benefit="Removes remaining weed competition; mulch reduces moisture stress later.",
        precautions="Avoid weeding wet soil to prevent compaction.",
    )),
    _layer1(30, ActivityCategory.FERTILIZER, "Correct Micronutrient Deficiency - Zinc + Boron Foliar", None, 1, _card(
        priority="Essential", category="Micronutrient (Foliar)", product="Zinc Sulphate + Borax",
        composition="ZnSO4 21%; Borax 11% B", dosage="ZnSO4 0.5 g/L + Borax 1 g/L",
        water_volume="200 litres/acre", method="Foliar spray", timing="Cooler hours, not midday sun",
        purpose="Zinc is essential for auxin synthesis driving cell elongation, and boron "
                "is required for cell-wall formation and will soon govern pollen tube growth "
                "-- both must be built into plant tissue reserves before flowering begins.",
        benefit="Corrects deficiency before flowering and prepares boron reserves for fruit set.",
        precautions="Do not tank-mix with high-calcium sprays without testing compatibility; "
                    "spray during cooler hours to avoid leaf scorch.",
    )),
    _layer1(30, ActivityCategory.FERTILIZER, "Build Reserves Ahead of Flowering - NPK Foliar Boost", None, 1, _card(
        priority="Essential", category="Foliar Nutrition", product="Water Soluble NPK (19:19:19)",
        composition="19:19:19", dosage="5 g/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Early morning or evening",
        purpose="Carbohydrate and balanced nutrient reserves built now are the source pool "
                "the plant draws from during flower initiation and fruit set, when root uptake "
                "alone may not keep pace with reproductive demand.",
        benefit="Boosts vegetative vigour and reserve buildup ahead of flowering.",
        precautions="Can be combined with the Zn+B spray in the same tank if compatible; test first.",
    )),

    # =================================================================
    # STAGE 3 -- Layer 1.5 / Layer 2
    # =================================================================
    _layer1_5(31, ActivityCategory.SPRAY, "Fruit & Shoot Borer Scouting - Dead Heart Check", _card(
        priority="Essential", category="Pest Monitoring (IPM)", product="Field Scouting",
        dosage="Not applicable", method="Visual check for wilting shoot tips (dead hearts)",
        timing="DAS 26-35, weekly",
        indicator="Record presence/absence of wilting shoot tips (dead hearts) as an "
                  "Observation note or photo before moving on -- this evidence gates the "
                  "conditional Fruit & Shoot Borer Control operation below.",
        purpose="Fruit shoot borer (FSB) larvae bore into the growing tip before fruiting "
                "begins; catching the dead-heart symptom now, before flowering, prevents the "
                "pest population from establishing through the much more damaging fruiting window.",
        benefit="Produces the field evidence that determines whether FSB intervention is warranted.",
        precautions="Check a representative sample of shoot tips across the field, not just the edges.",
    )),
    _layer2(31, ActivityCategory.SPRAY, "Fruit & Shoot Borer Control", _card(
        priority="Conditional", category="Insecticide (threshold-based)", product="Chlorantraniliprole 18.5 SC",
        composition="Chlorantraniliprole 18.5% SC", dosage="0.3 ml/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Evening, only on confirmed dead-heart damage, pre-flowering",
        purpose="Removing/treating infested tips now suppresses the breeding population "
                "before the much more damaging fruiting-stage infestation window opens.",
        benefit="Early removal/treatment of infested tips suppresses the breeding population before flowering.",
        precautions="Spot-treat on confirmed damage only; rotate mode of action across the "
                    "season (see the later Sucking Pest/FSB rotation spray) to manage resistance.",
    ), trigger_conditions=["PEST_FRUIT_SHOOT_BORER", "STAGE_VEGETATIVE"]),

    # =================================================================
    # STAGE 4 -- FLOWER BUD INITIATION (DAS 36-45) -- Layer 1
    # =================================================================
    _layer1(36, ActivityCategory.IRRIGATION, "Prevent Root Zone Waterlogging - Drainage Management", None, 1, _card(
        priority="Essential", category="Irrigation / Crop Operation", product="Drainage Channel Maintenance",
        dosage="Not applicable", method="Open/clear field drainage channels",
        timing="Before expected monsoon rain, DAS 36-45",
        purpose="Flower bud initiation is highly sensitive to root-zone oxygen deprivation; "
                "waterlogging at this stage can abort the developing flower primordia even "
                "without visible wilting above ground.",
        benefit="Prevents waterlogging and root/fruit rot once monsoon rains arrive.",
        precautions="Check channels before rain, not after; re-check after first heavy rain event.",
    )),
    _layer1(37, ActivityCategory.FERTILIZER, "Sustain Bud Formation - Top Dressing #2 (N + Balanced)", None, 1, _card(
        priority="Essential", category="Top Dressing", product="Calcium Ammonium Nitrate (CAN) OR Complex Fertilizer",
        composition="CAN 25% N OR Complex 20:20:0", dosage="40 kg/acre",
        method="Broadcast, irrigate immediately", timing="Morning, ahead of irrigation",
        purpose="Nutrient demand spikes sharply as the plant commits resources to flower "
                "bud formation; nitrogen here also carries calcium (via CAN), supporting "
                "the cell walls of the forming buds.",
        benefit="Supports the nutrient demand spike as flower buds form.",
        precautions="Avoid applying immediately before heavy rain to prevent runoff loss.",
    )),
    _layer1(38, ActivityCategory.FERTILIZER, "Build Boron/Calcium Reserve - Pre-Flowering Boron Spray", None, 1, _card(
        priority="Essential", category="Micronutrient (Foliar)", product="Borax", composition="Borax 11% B",
        dosage="1 g/L", water_volume="200 litres/acre", method="Foliar spray", timing="Early morning or evening",
        purpose="Boron must already be present in plant tissue before flowering, since it "
                "governs pollen tube growth and pollen viability -- there is no time to "
                "correct a deficiency once flowers open.",
        benefit="Builds the boron reserve that will directly support pollen viability at flowering.",
        precautions="Do not exceed labelled dose; boron has a narrow safety margin between "
                    "deficiency and toxicity.",
    )),

    # =================================================================
    # STAGE 4 -- Layer 1.5 / Layer 2
    # =================================================================
    _layer1_5(39, ActivityCategory.SPRAY, "Pre-Flowering Mite/Whitefly Scouting", _card(
        priority="Essential", category="Pest Monitoring (IPM)", product="Field Scouting",
        dosage="Not applicable", method="Inspect leaf undersides for mite/whitefly buildup",
        timing="DAS 36-45, before bud opening",
        indicator="Record presence/absence of mite stippling or whitefly colonies on leaf "
                  "undersides as an Observation note or photo before moving on -- this "
                  "evidence gates the conditional Mite & Whitefly Control operation below.",
        purpose="Populations that build up now will be much harder to control once "
                "daytime spraying is restricted during open flowering; this scouting pass "
                "uses the last low-risk window to decide if treatment is needed.",
        benefit="Produces the field evidence that determines whether pre-flowering pest intervention is warranted.",
        precautions="Inspect leaf undersides specifically; sample across the field, not just the edges.",
    )),
    _layer2(39, ActivityCategory.SPRAY, "Mite & Whitefly Control", _card(
        priority="Conditional", category="Biopesticide", product="Neem Oil", composition="Neem oil 1500 ppm",
        dosage="5 ml/L", water_volume="200 litres/acre", method="Foliar spray", timing="Evening only, on confirmed buildup",
        purpose="Treating before bud opening uses the last low-risk spray window before "
                "daytime spraying becomes restricted by open flowers and foraging pollinators.",
        benefit="Suppresses pest buildup ahead of full flowering with a low-residue option.",
        precautions="Evening application only -- avoid daytime heat and direct sun; low residue protects pollinators arriving next stage.",
    ), trigger_conditions=["PEST_MITE_WHITEFLY"]),
    _layer1_5(40, ActivityCategory.OTHER, "Confirm Flowering Onset", _card(
        priority="Essential", category="Crop Operation", product="Field Scouting",
        dosage="Not applicable", method="Visual check of leaf axils for buds",
        timing="DAS 36-45, ongoing",
        indicator="Record the date first flower buds are visible in leaf axils as an "
                  "Observation note -- this confirms STAGE_FLOWERING for the Decision "
                  "Engine and the field-level spray-timing rule below.",
        purpose="Once flower buds are visible, the spray-timing rule changes permanently for "
                "the rest of the season: open flowers and foraging pollinators are present "
                "during daylight, so any pesticide applied 10 AM-4 PM risks both pollinator "
                "kill and direct flower abortion.",
        benefit="Confirms entry into the most spray-sensitive window of the crop.",
        precautions="From this point on, schedule ALL sprays for early morning or evening only -- never 10 AM-4 PM.",
    )),

    # =================================================================
    # STAGE 5 -- FLOWERING & FRUIT SET (DAS 46-55) -- Layer 1
    # =================================================================
    _layer1(46, ActivityCategory.IRRIGATION, "Prevent Fruit-Set Failure - Critical Flowering Irrigation", None, 1, _card(
        priority="Essential", category="Irrigation", product="Furrow/Drip Irrigation",
        dosage="Irrigate if no rain for 5+ days", method="Furrow or drip", timing="DAS 46-55",
        purpose="Water stress during flowering directly increases flower and young-fruit "
                "abortion via reduced turgor pressure in developing reproductive tissue -- "
                "this is the single most yield-determining irrigation window in the crop cycle.",
        benefit="Protects fruit-set percentage by removing water stress at the most sensitive stage.",
        precautions="Skip if monsoon rain has already met demand; monitor fruit set over the following week.",
    )),
    _layer1(47, ActivityCategory.FERTILIZER, "Maximize Fruit Set - Boron + Calcium Foliar Spray", None, 1, _card(
        priority="Essential", category="Foliar Nutrition", product="Borax + Calcium Nitrate",
        composition="Borax 11% B; Ca(NO3)2 15.5N+19Ca", dosage="Borax 1 g/L + Calcium Nitrate 2 g/L",
        water_volume="200 litres/acre", method="Foliar spray on leaves and open buds",
        timing="Early morning or evening only",
        purpose="Boron drives pollen tube elongation and pollination success, while calcium "
                "is required for cell wall stability in the rapidly dividing cells of the "
                "newly fertilized ovary -- together they are the two nutrients most directly "
                "linked to converting a flower into a retained fruit.",
        benefit="Improves fruit set and reduces flower drop during peak flowering.",
        precautions="Strictly avoid 10 AM-4 PM application -- this protects both pollinators and open flowers; "
                    "do not tank-mix calcium with phosphate or sulphate sources (antagonism/precipitation risk).",
    )),
    _layer1(48, ActivityCategory.SPRAY, "Protect Flowers Without Harming Pollinators - FSB Prevention Spray #1", None, 1, _card(
        priority="Essential", category="Insecticide (preventive, rotation)", product="Spinosad 45 SC",
        composition="Spinosad 45% SC", dosage="0.3 ml/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Evening only",
        purpose="Fruit and shoot borer pressure peaks alongside flowering; this preventive, "
                "calendar-fixed, mode-of-action-rotated spray is scheduled specifically "
                "because flowering is a known high-risk window regardless of confirmed "
                "infestation -- keeping it Layer 1 preserves the rotation discipline that "
                "prevents resistance buildup, which depends on a fixed sequence rather than "
                "evidence timing. Spinosad is selected here for its comparatively lower "
                "acute toxicity to bees relative to broad-spectrum options.",
        benefit="Controls FSB during the highest-risk flowering window while limiting pollinator harm.",
        precautions="Evening application only; never 10 AM-4 PM. Rotated with the DAS 59 "
                    "Emamectin Benzoate spray next cycle to prevent resistance build-up.",
    )),
    _layer1(49, ActivityCategory.OTHER, "Reduce Pest Breeding Population - Remove Dead Hearts", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Manual Removal", dosage="Not applicable",
        method="Hand-pick and destroy off-field", timing="DAS 46-55, weekly",
        purpose="Each surviving FSB-infested shoot tip is a breeding source for the next "
                "generation; removing and destroying it off-field interrupts the pest's "
                "lifecycle right as fruit-set tissue becomes its preferred target.",
        benefit="Reduces breeding population before it can spread into developing fruit.",
        precautions="Destroy removed material away from the field, not by composting on-site.",
    )),

    # =================================================================
    # STAGE 6 -- FRUIT DEVELOPMENT (DAS 56-62) -- Layer 1
    # =================================================================
    _layer1(56, ActivityCategory.IRRIGATION, "Drive Cell Expansion - Consistent Irrigation", None, 1, _card(
        priority="Essential", category="Irrigation", product="Furrow/Drip Irrigation",
        dosage="Maintain consistent soil moisture", method="Furrow or drip, monitor daily",
        timing="DAS 56-62, daily check",
        purpose="Pod growth proceeds through cell division then cell expansion (water "
                "uptake into the cell vacuole); irregular moisture during the expansion "
                "phase produces curved, fibrous, or undersized pods rather than smooth uniform ones.",
        benefit="Irregular watering causes poor pod development -- consistency matters more than total volume.",
        precautions="Adjust daily based on rainfall, not a fixed calendar.",
    )),
    _layer1(57, ActivityCategory.FERTILIZER, "Support Pod Sink Strength - MKP Foliar Spray", None, 1, _card(
        priority="Essential", category="Foliar Nutrition", product="Mono Potassium Phosphate (MKP)",
        composition="0:52:34", dosage="3 g/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Early morning or evening",
        purpose="Phosphorus and potassium together drive carbohydrate movement from leaves "
                "(the source) into the developing pod (the sink); MKP supplies both without "
                "the nitrogen that would otherwise divert energy back into vegetative growth.",
        benefit="Boosts pod setting and early yield right as the harvest window opens.",
        precautions="Spray in early morning or evening; do not combine with calcium sprays in the same tank.",
    )),
    _layer1(59, ActivityCategory.SPRAY, "Early Powdery Mildew Watch", None, 1, _card(
        priority="Conditional", category="Disease Monitoring (IPM)", product="Field Scouting",
        dosage="Not applicable", method="Visual check for white powdery growth on leaves",
        timing="DAS 56-62",
        purpose="Powdery mildew favours the humid, dense canopy conditions typical right as "
                "fruiting begins; catching the first white patches before they spread protects "
                "leaf area that is now being asked to fund continuous fruiting.",
        benefit="Early treatment prevents the disease from spreading across the canopy.",
        precautions="If white powder appears, spray Wettable Sulphur 3 g/L; avoid sulphur in "
                    "extreme heat (leaf phytotoxicity risk).",
    )),
    _layer1(60, ActivityCategory.OTHER, "Prepare for Continuous Harvest - Staking & Sanitation", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Staking + Lower Leaf Removal",
        dosage="Not applicable", method="Stake tall plants; remove yellowing lower leaves",
        timing="DAS 56-62",
        purpose="Fruit load increases lodging risk just as picking access becomes critical; "
                "removing yellowing leaves also improves airflow, reducing the humid "
                "microclimate that favours disease right when continuous harvest begins.",
        benefit="Prevents lodging under fruit load and reduces disease pressure via better airflow.",
        precautions="Ensure plants remain accessible for picking after staking.",
    )),

    # =================================================================
    # STAGE 6 -- Layer 1.5 (new: pod-tip calcium check)
    # =================================================================
    _layer1_5(65, ActivityCategory.OTHER, "Pod-Tip Browning Check", _card(
        priority="Essential", category="Crop Operation", product="Field Scouting",
        dosage="Not applicable", method="Visual check of pod tips for browning/blossom-end necrosis",
        timing="DAS 63-68, weekly during early Peak Harvest",
        indicator="Record presence/absence of pod-tip browning as an Observation note or "
                  "photo before moving on -- this evidence gates the conditional Calcium "
                  "Foliar (Pod-Tip) operation below.",
        purpose="Pod-tip browning is a localized calcium-deficiency symptom in the "
                "fastest-growing, most calcium-demanding tissue; this scouting pass is the "
                "evidence-gathering step the Decision Engine reads before recommending a "
                "corrective spray.",
        benefit="Produces the field evidence that determines whether a pod-tip calcium correction is warranted.",
        precautions="Inspect a representative sample of recently set pods across the field, not just the largest.",
    )),

    # =================================================================
    # STAGE 7 -- PEAK HARVEST (DAS 63-90) -- Layer 1
    # =================================================================
    _layer1(63, ActivityCategory.HARVEST, "Maximize Marketable Yield - Tender Pod Picking", 2, 14, _card(
        priority="Essential", category="Crop Operation", product="Hand Harvest",
        dosage="Pick pods at 7-9 cm length", method="Clean knife or scissors, every 2-3 days",
        timing="Morning, dry conditions",
        purpose="Pod tenderness and marketable grade decline rapidly past the 7-9 cm window "
                "as fibre content increases; picking on a strict 2-3 day interval is the "
                "single largest controllable driver of both grade and price.",
        benefit="Maintains continuous production of premium-grade tender pods.",
        precautions="Avoid picking in wet conditions -- wet handling encourages post-harvest rot. "
                    "Log harvested quantity as Revenue against the sale date.",
    )),
    _layer1(63, ActivityCategory.IRRIGATION, "Sustain Dual Flowering-Fruiting Load - Regular Irrigation", 6, 5, _card(
        priority="Essential", category="Irrigation", product="Furrow/Drip Irrigation",
        dosage="Every 5-6 days if no rain", method="Furrow or drip",
        timing="DAS 63-90, check soil moisture before each cycle",
        purpose="The plant is simultaneously flowering and fruiting through peak harvest, "
                "roughly doubling its concurrent water demand compared to a single-phase crop; "
                "any shortfall shows up as both reduced new fruit set and smaller existing pods.",
        benefit="Sustains pod development now that continuous harvesting has begun.",
        precautions="Adjust for rainfall; do not let soil dry fully between cycles.",
    )),
    _layer1(63, ActivityCategory.OTHER, "Track Crop Status - Weekly Field Observation", 7, 4, _card(
        priority="Essential", category="Crop Operation", product="Photo Observation Upload",
        dosage="Not applicable",
        method="Capture leaf undersides, pod quality, suspect plants; upload to Observations tab",
        timing="Weekly, good morning light",
        purpose="AI-assisted scouting catches emerging pest, disease, or nutrient issues "
                "earlier than periodic visual inspection alone, especially across a large "
                "continuous-picking field.",
        benefit="Earlier detection and intervention on emerging field issues.",
        precautions="Capture in good light; review AI feedback and act before the next harvest.",
    )),
    _layer1(54, ActivityCategory.FERTILIZER, "Replenish Potassium Removed by Picking - Top Dressing #3", None, 1, _card(
        priority="Essential", category="Top Dressing", product="Muriate of Potash (MOP)",
        composition="0:0:60", dosage="25 kg/acre", method="Band placement, irrigate after",
        timing="Morning, before irrigation",
        purpose="Every harvested pod physically removes potassium from the field via the "
                "source-sink pathway; without replenishment, potassium deficiency in the "
                "remaining canopy directly shortens the productive harvest window.",
        benefit="Extends the productive picking period by sustaining potassium supply.",
        precautions="Avoid contact with foliage; irrigate after application.",
    )),
    _layer1(56, ActivityCategory.FERTILIZER, "Sustain Plant Stamina - Potassium Nitrate Foliar Spray", None, 1, _card(
        priority="Essential", category="Foliar Nutrition", product="Potassium Nitrate (KNO3)",
        composition="13:0:45", dosage="5 g/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Early morning or evening",
        purpose="Foliar potassium nitrate gives a fast-acting boost to pod size, colour and "
                "shelf life precisely when the plant's root-supplied potassium is being "
                "outpaced by continuous fruit removal.",
        benefit="Improves pod size, colour, and shelf life during peak picking.",
        precautions="Do not exceed labelled concentration; can cause leaf scorch if applied in heat.",
    )),
    _layer1(59, ActivityCategory.SPRAY, "Rotate Mode of Action - FSB Prevention Spray #2", 12, 2, _card(
        priority="Essential", category="Insecticide (preventive, rotation)", product="Emamectin Benzoate 5 SG",
        composition="Emamectin Benzoate 5% SG", dosage="0.4 g/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Evening, respecting spray-to-harvest interval",
        purpose="Repeated use of one mode of action under continuous pest pressure across "
                "peak harvest is the fastest route to resistance; this preventive, "
                "calendar-fixed spray rotates the chemistry used at flowering (Spinosad, "
                "DAS 48), deliberately kept Layer 1 rather than merged into any evidence-"
                "gated Layer 2 control, since the rotation discipline depends on a fixed "
                "sequence, not on evidence timing.",
        benefit="Maintains pest control efficacy across the full peak-harvest window.",
        precautions="Maintain a 5-7 day spray-to-harvest interval (PHI); never spray within "
                    "this window of a planned picking; evening only.",
    )),
    _layer1(64, ActivityCategory.SPRAY, "Manage Red Spider Mite & Cercospora Leaf Spot", None, 1, _card(
        priority="Conditional", category="Acaricide / Fungicide (threshold-based)",
        product="Wettable Sulphur (mite + early leaf spot) OR Propiconazole (leaf spot)",
        composition="Sulphur 80% WP / Propiconazole 25% EC", dosage="Sulphur 3 g/L OR Propiconazole 1 ml/L",
        water_volume="200 litres/acre", method="Foliar spray", timing="Evening, only if threshold crossed",
        purpose="Hot, dry spells during peak harvest favour red spider mite buildup, while "
                "humid spells favour Cercospora leaf spot -- both directly reduce the "
                "functional leaf area funding continuous fruiting if left unchecked.",
        benefit="Protects canopy photosynthetic capacity through the demanding peak-harvest period.",
        precautions="Avoid sulphur application in extreme heat; rotate fungicide chemistry "
                    "across the season for resistance management.",
    )),
    _layer1(69, ActivityCategory.OTHER, "Break Virus Cycle - YVMV Roguing", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Manual Roguing", dosage="Not applicable",
        method="Identify and remove plants with Yellow Vein Mosaic Virus symptoms",
        timing="DAS 70-90, ongoing",
        purpose="YVMV-infected plants are a continuous reservoir for whitefly-transmitted "
                "spread to healthy plants; physical removal is the only intervention that "
                "stops within-field spread once infection is established.",
        benefit="Limits further virus spread and protects yield on remaining healthy plants.",
        precautions="Remove and destroy infected plants away from the field; do not compost on-site.",
    )),

    # =================================================================
    # STAGE 7 -- Layer 1.5 / Layer 2 (sucking pest pair + Ca pair)
    # =================================================================
    _layer1_5(58, ActivityCategory.SPRAY, "Pre-Harvest Sucking Pest Scouting", _card(
        priority="Essential", category="Pest Monitoring (IPM)", product="Field Scouting",
        dosage="Threshold-based only", method="Inspect leaf undersides for whitefly, thrips, jassids",
        timing="DAS 56-62",
        indicator="Record presence/absence and rough density of whitefly/thrips/jassids on "
                  "leaf undersides as an Observation note or photo -- this evidence gates "
                  "the conditional Sucking Pest Control operation below.",
        purpose="Once picking begins next stage, the spray-to-harvest interval becomes the "
                "binding constraint on pest control; establishing pest pressure now, before "
                "harvest starts, avoids being forced into a rushed spray that violates PHI.",
        benefit="Keeps a 5-7 day spray-to-harvest interval workable once continuous picking begins.",
        precautions="Sample across the field; never plan a spray during projected picking hours.",
    )),
    _layer2(58, ActivityCategory.SPRAY, "Sucking Pest Control", _card(
        priority="Conditional", category="Insecticide (threshold-based)", product="Imidacloprid 17.8 SL",
        composition="Imidacloprid 17.8% SL", dosage="0.5 ml/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Evening, respecting spray-to-harvest interval (PHI)",
        purpose="Threshold-based treatment of confirmed sucking pest pressure protects "
                "canopy and pod quality through continuous picking without resorting to a "
                "preventive blanket spray that would also risk pollinators and PHI compliance.",
        benefit="Controls confirmed sucking pest pressure while respecting harvest interval.",
        precautions="Maintain 5-7 day spray-to-harvest interval; product/dose may be adjusted "
                    "per scouting severity; rotate mode of action with other sprays this season.",
    ), trigger_conditions=["PEST_SUCKING_COMPLEX"]),
    _layer2(70, ActivityCategory.FERTILIZER, "Calcium Foliar (Pod-Tip)", _card(
        priority="Conditional", category="Foliar Nutrition", product="Calcium Nitrate",
        composition="Ca(NO3)2 15.5N+19Ca", dosage="2 g/L", water_volume="200 litres/acre",
        method="Foliar spray", timing="Early morning or evening, on confirmed pod-tip browning",
        purpose="Calcium is required for cell wall stability in the fastest-expanding pod "
                "tissue; once tip browning is confirmed by the preceding scouting "
                "assessment, a direct foliar correction addresses the deficiency at its source.",
        benefit="Corrects confirmed pod-tip calcium deficiency, improving pod quality through peak harvest.",
        precautions="Do not tank-mix with phosphate or sulphate sources (antagonism/precipitation risk).",
    ), trigger_conditions=["DEFICIENCY_POD_TIP_CALCIUM"]),

    # =================================================================
    # STAGE 8 -- LATE HARVEST (DAS 91-110) -- Layer 1
    # =================================================================
    _layer1(91, ActivityCategory.IRRIGATION, "Maintain Minimum Viable Moisture - Reduced Irrigation", 7, 3, _card(
        priority="Essential", category="Irrigation", product="Furrow/Drip Irrigation",
        dosage="Reduce frequency to every 7 days", method="Furrow or drip", timing="DAS 91-110",
        purpose="As natural senescence begins, root water demand declines; matching "
                "irrigation downward avoids wasting water while still delaying senescence "
                "as long as economically useful.",
        benefit="Delays senescence without over-irrigating a declining-demand crop.",
        precautions="Do not stop irrigation abruptly; taper gradually to avoid shocking the "
                    "remaining productive canopy.",
    )),
    _layer1(92, ActivityCategory.FERTILIZER, "Delay Senescence - Maintenance Foliar Feed", None, 1, _card(
        priority="Essential", category="Foliar Nutrition", product="Water Soluble NPK (19:19:19) at reduced rate",
        composition="19:19:19", dosage="3 g/L (reduced from peak-stage rate)", water_volume="200 litres/acre",
        method="Foliar spray", timing="Early morning or evening",
        purpose="A light maintenance feed keeps the remaining functional canopy "
                "photosynthesizing longer without over-investing inputs into a crop whose "
                "yield curve is now declining.",
        benefit="Extends productive canopy life and the picking window economically.",
        precautions="Reduce dose relative to peak-harvest stage; do not over-invest as yield declines.",
    )),
    _layer1(95, ActivityCategory.HARVEST, "Continue Marketable Picking", 3, 5, _card(
        priority="Essential", category="Crop Operation", product="Hand Harvest",
        dosage="Pick remaining marketable pods", method="Clean knife or scissors", timing="Every 3 days, morning",
        purpose="Even as overall yield declines, individual pods still reach marketable "
                "tenderness on the same cell-expansion timeline as before and must be picked "
                "before fibre development sets in.",
        benefit="Captures remaining marketable yield as long as input economics justify it.",
        precautions="Avoid picking in wet conditions; inspect for any disease before bagging for sale.",
    )),
    _layer1(98, ActivityCategory.OTHER, "Begin Seed Collection", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Seed Pod Selection", dosage="Not applicable",
        method="Tag and allow selected healthy pods to mature fully on the plant", timing="DAS 91-110",
        purpose="If farm-saved seed is intended for the next season, pods must be left to "
                "mature fully now rather than picked tender, since seed viability depends on "
                "complete physiological maturity.",
        benefit="Provides viable, farm-saved seed for the following season if desired.",
        precautions="Select only disease-free, true-to-type plants for seed retention.",
    )),

    # =================================================================
    # STAGE 8 -- Layer 1.5 / Layer 2
    # =================================================================
    _layer1_5(100, ActivityCategory.SPRAY, "Ageing Canopy Disease Scouting", _card(
        priority="Essential", category="Disease Monitoring (IPM)", product="Field Scouting",
        dosage="Not applicable", method="Visual check of lower/ageing canopy for active disease symptoms",
        timing="DAS 91-110, only on confirmed disease pressure",
        indicator="Record presence/absence of active disease symptoms (leaf spot, mildew, "
                  "rust) on the ageing lower canopy as an Observation note or photo -- this "
                  "evidence gates the conditional Disease Control operation below.",
        purpose="The ageing lower canopy is more disease-prone, but input economics no "
                "longer justify routine preventive spraying at this stage -- only confirmed, "
                "threshold-crossing disease warrants treatment, which this scouting pass establishes.",
        benefit="Produces the field evidence that determines whether late-season disease intervention is warranted.",
        precautions="Focus inspection on the ageing lower canopy specifically, where disease pressure concentrates.",
    )),
    _layer2(100, ActivityCategory.SPRAY, "Disease Control - Ageing Canopy", _card(
        priority="Conditional", category="Fungicide (threshold-based)",
        product="Wettable Sulphur or Propiconazole, as needed",
        dosage="As per earlier-stage rates, only if disease is active", water_volume="200 litres/acre",
        method="Foliar spray", timing="Evening, only on confirmed disease pressure",
        purpose="Treating only on confirmed, threshold-crossing disease protects remaining "
                "canopy value without overspending inputs on a crop whose yield curve is now declining.",
        benefit="Protects remaining canopy value without overspending on a declining crop.",
        precautions="Spray only on confirmed need; respect PHI relative to remaining pickings.",
    ), trigger_conditions=["DISEASE_AGEING_CANOPY"]),

    # =================================================================
    # STAGE 9 -- CROP TERMINATION (DAS 111-120) -- Layer 1
    # =================================================================
    _layer1(111, ActivityCategory.IRRIGATION, "Stop Irrigation", None, 1, _card(
        priority="Essential", category="Irrigation", product="Irrigation Stoppage",
        dosage="Stop irrigation entirely", method="No further water application", timing="DAS 111",
        purpose="Continued irrigation past this point only delays field clearing and "
                "increases the risk of waterlogged conditions favouring residue-borne disease "
                "carryover into the next season.",
        benefit="Allows the field to dry down ahead of uprooting and tillage.",
        precautions="Confirm no economically viable marketable pods remain before stopping.",
    )),
    _layer1(113, ActivityCategory.HARVEST, "Final Marketable Picking", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Hand Harvest",
        dosage="Pick any remaining marketable pods", method="Clean knife or scissors", timing="DAS 111-118",
        purpose="A final clean-up picking captures any pods that reached tenderness after "
                "the last regular harvest, before the crop is terminated.",
        benefit="Captures the last marketable yield before residue removal.",
        precautions="Inspect carefully -- pods left too long past this point are unsellable; "
                    "do not delay termination waiting for marginal pods.",
    )),
    _layer1(115, ActivityCategory.OTHER, "Break Pest/Disease Carryover - Uproot & Remove Residue", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Manual/Mechanical Uprooting", dosage="Not applicable",
        method="Uproot whole plants and remove from field", timing="DAS 112-118",
        purpose="Standing or fallen crop residue is a direct overwintering reservoir for "
                "FSB, whitefly, and fungal spores; complete removal is the single most "
                "effective non-chemical step to reduce next season's starting pest and "
                "disease load.",
        benefit="Reduces carryover inoculum and pest population into the next crop cycle.",
        precautions="Destroy or compost residue well away from the next planting area, not in-field.",
    )),
    _layer1(118, ActivityCategory.LAND_PREPARATION, "Expose Soil-Borne Pests - Deep Ploughing", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Deep Ploughing", dosage="Not applicable",
        method="Deep tillage, sun exposure", timing="DAS 115-120, dry weather",
        purpose="Deep ploughing exposes soil-dwelling pest pupae and fungal propagules to "
                "sun and predators, and improves soil structure for the next crop -- closing "
                "the loop on the season's pest and disease management.",
        benefit="Reduces soil-borne pest and pathogen carryover; improves tilth for the next crop.",
        precautions="Plough in dry weather for maximum sun-exposure benefit on exposed pests.",
    )),
    _layer1(120, ActivityCategory.OTHER, "Close Season Record", None, 1, _card(
        priority="Essential", category="Crop Operation", product="Season Record-Keeping", dosage="Not applicable",
        method="Finalize Expenses/Revenue entries and mark Season as Completed", timing="DAS 119-120",
        purpose="A closed, accurate season record is what makes next season's "
                "recommendations and yield analysis meaningful -- the data only has value if "
                "captured before details are forgotten.",
        benefit="Preserves an accurate record for profitability review and future planning.",
        precautions="Reconcile all expense and revenue entries before marking the season Completed.",
    )),
]


def seed_bhendi_v3() -> None:
    create_new_version(
        crop_name="Bhindi (Okra)",
        label="v3 - Layer 1/1.5/2/3 Decision-Oriented Advisory Engine",
        change_notes=(
            "Introduces the AgroNous standard template architecture: Layer 1 "
            "planned operations, Layer 1.5 mandatory evidence-producing "
            "assessments, Layer 2 conditional operations gated by explicit "
            "TriggerCondition rules evaluated by the new Decision Engine "
            "(services/decision_engine.py), and Layer 3 knowledge cards "
            "carrying all product/dose/chemistry detail so it can evolve "
            "without touching the cultivation template. Splits 6 hybrid "
            "scouting+spray rows into separate Layer 1.5 assessment + "
            "Layer 2 conditional-operation pairs. Fixes the Stage 6/7 DAS "
            "overlap bug (Peak Harvest rows corrected from DAS 52 to DAS "
            "63 where misfiled), adds Magnesium (conditional foliar), Iron "
            "(basal, soil-type gated) and Calcium (pod-tip, evidence-gated) "
            "coverage previously missing from the nutrient sequence, and "
            "promotes stage descriptions to explicit 'Before moving to the "
            "next stage verify' checklists."
        ),
        stages=STAGES,
        activities=ACTIVITIES,
    )


if __name__ == "__main__":
    seed_bhendi_v3()
