"""
Toor Dal (Pigeon Pea) -- v1 Full DAS-Based Cultivation Schedule
================================================================
A "Toor Dal (Pigeon Pea)" CropMaster row was already created (via the UI)
before this template existed, so seed_crop_master() in crop_master_seed.py
will never populate it (it only inserts crops that don't yet exist by
name). This module instead adds a NEW CropTemplateVersion on top of that
existing crop -- the same create_new_version() pattern used by
seed/bhendi_physiology_v2.py and v3.py -- so it works regardless of
whatever stages/activities (if any) the original UI-created crop already
had, without ever editing those rows in place.

Derived from the Toor Dal Cultivation Tracker: 12 stages (DAS -7 to 237)
and 60 activity templates covering land prep through Rhizobium
inoculation, staged Mo/Zn/Fe/B/Ca/K micronutrient correction, ETL-based
pest scouting, and harvest/storage. All activities use the plain Layer 1
6-tuple shape (day_offset, category, name, repeat_interval, repeat_count,
remarks), wrapped via _activity() into create_new_version()'s 9-tuple
input -- this crop hasn't adopted the Layer 1.5/2 conditional-activity
architecture from the Bhindi v3 engine.

Run with:  python -m seed.toor_dal_v1
(Or, on environments without a Python shell, trigger via the
 "Apply Toor Dal Full Schedule (v1)" button on Home.py.)
"""
from __future__ import annotations

from db.models import ActivityCategory
from seed.crop_master_seed import _activity, create_new_version

STAGES = [
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
]

ACTIVITIES_RAW = [
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
]

ACTIVITIES = [_activity(*row) for row in ACTIVITIES_RAW]


def seed_toor_dal_v1() -> None:
    create_new_version(
        crop_name="Toor Dal (Pigeon Pea)",
        label="v1 - Full DAS-based cultivation schedule",
        change_notes=(
            "Adds the complete 12-stage, 60-activity cultivation schedule "
            "(DAS -7 to 237) derived from the Toor Dal Cultivation Tracker: "
            "land preparation, Rhizobium + PSB seed treatment, basal "
            "SSP/FYM, staged Mo/Zn/Fe/B/Ca/K micronutrient corrections, "
            "ETL-gated pest/disease scouting (cutworm, stem fly, wilt, "
            "sterility mosaic, pod borer, pod fly, Alternaria), pollinator-"
            "safe spray timing during flowering, and harvest/threshing/"
            "storage. Supersedes whatever minimal template the crop had "
            "from its original UI-driven creation."
        ),
        stages=STAGES,
        activities=ACTIVITIES,
    )


if __name__ == "__main__":
    seed_toor_dal_v1()
