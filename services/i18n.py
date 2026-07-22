"""
Minimal i18n layer for English / Telugu.

Usage:
    from i18n import t, language_switcher

    language_switcher()          # call once near the top of every page
    st.title(t("Cultivation Dashboard"))
    st.success(t("Logged {amount} under {category}.", amount=x, category=y))

How it works:
- English text is used directly as the lookup key, so call sites read as
  plain English and there is nothing to keep "in sync" -- the English
  string IS the key. `t()` looks the key up in TRANSLATIONS["te"] when the
  active language is Telugu, and falls back to the key itself (i.e. plain
  English) for any string that hasn't been translated yet, so nothing ever
  breaks or shows a blank/missing string.
- For strings with dynamic values (numbers, names, dates), the English key
  contains `{placeholders}` and the caller passes the values as kwargs,
  e.g. t("Logged {amount} under {category}.", amount=..., category=...).
  Both the English and Telugu strings must define the same placeholders.
"""
from __future__ import annotations

import streamlit as st

LANGUAGES = {"en": "English", "te": "తెలుగు"}


def get_lang() -> str:
    return st.session_state.get("lang", "en")


def t(key: str, **kwargs) -> str:
    lang = get_lang()
    text = TRANSLATIONS.get(lang, {}).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            # A translation is missing/out of date relative to its
            # placeholders -- fall back to the English rather than crash
            # the page over a copy issue.
            return key.format(**kwargs)
    return text


def language_switcher() -> None:
    """Renders a language picker in the sidebar. Call once per page."""
    if "lang" not in st.session_state:
        st.session_state["lang"] = "en"
    codes = list(LANGUAGES.keys())
    choice = st.sidebar.selectbox(
        "🌐 Language / భాష",
        options=codes,
        format_func=lambda c: LANGUAGES[c],
        index=codes.index(st.session_state["lang"]),
        key="lang_selector",
    )
    st.session_state["lang"] = choice


TRANSLATIONS: dict[str, dict[str, str]] = {
    "te": {
        # ---- Common / chrome ----
        "Farm": "పొలం",
        "Farms": "పొలాలు",
        "Farm *": "పొలం *",
        "Season": "సీజన్",
        "Seasons": "సీజన్లు",
        "Crop *": "పంట *",
        "Date": "తేదీ",
        "Date *": "తేదీ *",
        "Category": "వర్గం",
        "Category *": "వర్గం *",
        "Amount": "మొత్తం",
        "Amount *": "మొత్తం *",
        "Amount (₹)": "మొత్తం (₹)",
        "Metric": "కొలమానం",
        "Value": "విలువ",
        "Description": "వివరణ",
        "Location": "ప్రాంతం",
        "Name *": "పేరు *",
        "Unit": "యూనిట్",
        "Buyer": "కొనుగోలుదారు",
        "Note": "గమనిక",
        "Details": "వివరాలు",
        "Cancel": "రద్దు చేయి",
        "sown": "విత్తిన తేదీ",
        "Sown": "విత్తారు",
        "days": "రోజులు",
        "task": "పని",
        "tasks": "పనులు",

        # ---- Language switcher itself uses LANGUAGES dict, not this ----

        # ---- Home.py ----
        "Synchronize Crop Master": "పంట మాస్టర్‌ను సమకాలీకరించండి",
        "Crop Master synchronized successfully.": "పంట మాస్టర్ విజయవంతంగా సమకాలీకరించబడింది.",
        "🌿 Apply Bhendi Physiology Engine (v3)": "🌿 బెండి ఫిజియాలజీ ఇంజన్ (v3) వర్తింపజేయండి",
        "Bhendi v3 physiology engine applied. New seasons will use the updated schedule.": "బెండి v3 ఫిజియాలజీ ఇంజన్ వర్తింపజేయబడింది. కొత్త సీజన్లు నవీకరించిన షెడ్యూల్‌ను ఉపయోగిస్తాయి.",
        "🌱 Apply Toor Dal Full Schedule (v1)": "🌱 కంది పప్పు పూర్తి షెడ్యూల్ (v1) వర్తింపజేయండి",
        "Toor Dal full schedule (v1) applied. New seasons will use the updated 12-stage/60-activity template; existing seasons keep the version they were created against -- recreate the season to pick up the new schedule.": "కంది పప్పు పూర్తి షెడ్యూల్ (v1) వర్తింపజేయబడింది. కొత్త సీజన్లు నవీకరించిన 12-దశలు/60-కార్యకలాపాల టెంప్లేట్‌ను ఉపయోగిస్తాయి; ఇప్పటికే ఉన్న సీజన్లు అవి సృష్టించబడిన వెర్షన్‌నే ఉంచుకుంటాయి -- కొత్త షెడ్యూల్ పొందడానికి సీజన్‌ను మళ్ళీ సృష్టించండి.",
        "Failed: {error}": "విఫలమైంది: {error}",
        "⚠️ Danger Zone": "⚠️ ప్రమాద జోన్",
        "This will permanently delete **all farms, seasons, schedules, expenses, revenue, and observations**. This cannot be undone.": "ఇది **అన్ని పొలాలు, సీజన్లు, షెడ్యూల్‌లు, ఖర్చులు, ఆదాయం మరియు పరిశీలనలను** శాశ్వతంగా తొలగిస్తుంది. దీన్ని రద్దు చేయడం సాధ్యం కాదు.",
        "Type DELETE to confirm": "నిర్ధారించడానికి DELETE అని టైప్ చేయండి",
        "🗑️ Delete All Farms & Seasons": "🗑️ అన్ని పొలాలు & సీజన్లను తొలగించండి",
        "Deleted {n} farm(s) and all associated data.": "{n} పొలం(లు) మరియు వాటికి సంబంధించిన మొత్తం డేటా తొలగించబడింది.",

        # ---- ui_helpers.py ----
        "No farms yet. Add one in **Farms & Seasons**.": "ఇంకా పొలాలు లేవు. **పొలాలు & సీజన్లు** పేజీలో ఒకటి జోడించండి.",
        "No seasons for this farm yet. Add one in **Farms & Seasons**.": "ఈ పొలానికి ఇంకా సీజన్లు లేవు. **పొలాలు & సీజన్లు** పేజీలో ఒకటి జోడించండి.",
        "👋 Welcome to Cultivation": "👋 సాగుకు స్వాగతం",
        "Get started by adding your first **Farm** and **Season** from the **Farms & Seasons** page in the sidebar.": "సైడ్‌బార్‌లోని **పొలాలు & సీజన్లు** పేజీలో మీ మొదటి **పొలం** మరియు **సీజన్**ను జోడించి ప్రారంభించండి.",

        # ---- dashboard_view.py ----
        "🌱 Cultivation Dashboard": "🌱 సాగు డాష్‌బోర్డ్",
        "Current Crop": "ప్రస్తుత పంట",
        "Current Stage": "ప్రస్తుత దశ",
        "Days After Sowing": "విత్తిన తర్వాత రోజులు",
        "{n} days": "{n} రోజులు",
        "Area": "విస్తీర్ణం",
        "Today's Tasks": "ఈరోజు పనులు",
        "Upcoming (7 days)": "రాబోయే (7 రోజులు)",
        "Overdue": "గడువు మీరినవి",
        "Total Expenses": "మొత్తం ఖర్చులు",
        "Total Revenue": "మొత్తం ఆదాయం",
        "Profit": "లాభం",
        "Loss": "నష్టం",
        "Net {label}": "నికర {label}",
        "📋 Today's Tasks": "📋 ఈరోజు పనులు",
        "Nothing scheduled for today. ✅": "ఈరోజు ఏమీ షెడ్యూల్ చేయబడలేదు. ✅",
        "🔔 Upcoming Alerts": "🔔 రాబోయే హెచ్చరికలు",
        "No alerts right now.": "ప్రస్తుతం హెచ్చరికలు లేవు.",
        "📅 This Week": "📅 ఈ వారం",
        "No tasks in the next 7 days.": "రాబోయే 7 రోజుల్లో పనులు లేవు.",
        "🕘 Recent Activity": "🕘 ఇటీవలి కార్యకలాపం",
        "No completed activities yet.": "ఇంకా పూర్తయిన కార్యకలాపాలు లేవు.",
        "📸 Recent Observations": "📸 ఇటీవలి పరిశీలనలు",
        "_(photo only)_": "_(ఫోటో మాత్రమే)_",
        "No field observations logged yet.": "ఇంకా ఏ ఫీల్డ్ పరిశీలనలు నమోదు కాలేదు.",
        "💸 Expense Breakdown": "💸 ఖర్చుల విభజన",
        "No expenses recorded yet.": "ఇంకా ఖర్చులు నమోదు కాలేదు.",
        "📈 Revenue Trend": "📈 ఆదాయ ధోరణి",
        "Cumulative Revenue (₹)": "సంచిత ఆదాయం (₹)",
        "No revenue recorded yet.": "ఇంకా ఆదాయం నమోదు కాలేదు.",
        "🧮 P&L Summary": "🧮 లాభ-నష్టాల సారాంశం",
        "Cost / Acre": "ఎకరానికి ఖర్చు",
        "Net {label} / Acre": "ఎకరానికి నికర {label}",
        "Date": "తేదీ",
        "Activity": "కార్యకలాపం",
        "Category": "వర్గం",

        # ---- Category labels (CATEGORY_META / CATEGORY_LABELS, shared) ----
        "Irrigation": "నీటిపారుదల",
        "Fertilizer": "ఎరువు",
        "Spray / Pest": "స్ప్రే / తెగులు",
        "Spray/Pest": "స్ప్రే / తెగులు",
        "Weeding": "కలుపు తీయుట",
        "Land Prep": "భూమి తయారీ",
        "Sowing": "విత్తడం",
        "Harvest": "కోత",
        "Other": "ఇతర",

        # ---- 1_Farms_and_Seasons.py ----
        "🚜 Farms & Seasons": "🚜 పొలాలు & సీజన్లు",
        "Your Farms": "మీ పొలాలు",
        "_No location set_": "_ప్రాంతం సెట్ చేయలేదు_",
        "🗑️ Delete": "🗑️ తొలగించు",
        "Delete **{name}**? This permanently deletes the farm and ALL its seasons (schedules, expenses, revenues, observations, alerts).": "**{name}** ను తొలగించాలా? ఇది ఆ పొలాన్ని మరియు దాని అన్ని సీజన్లను (షెడ్యూల్‌లు, ఖర్చులు, ఆదాయాలు, పరిశీలనలు, హెచ్చరికలు) శాశ్వతంగా తొలగిస్తుంది.",
        "Yes, delete permanently": "అవును, శాశ్వతంగా తొలగించు",
        "You haven't added any farms yet. Add your first one below.": "మీరు ఇంకా పొలాలను జోడించలేదు. కింద మీ మొదటి దాన్ని జోడించండి.",
        "➕ Add a New Farm": "➕ కొత్త పొలాన్ని జోడించండి",
        "Farm Name *": "పొలం పేరు *",
        "e.g. North Field": "ఉదా. ఉత్తర పొలం",
        "e.g. Nalgonda, Telangana": "ఉదా. నల్గొండ, తెలంగాణ",
        "Total Area": "మొత్తం విస్తీర్ణం",
        "Area Unit": "విస్తీర్ణ యూనిట్",
        "Acres": "ఎకరాలు",
        "Hectares": "హెక్టార్లు",
        "Bigha": "బిఘా",
        "Guntha": "గుంట",
        "Add Farm": "పొలాన్ని జోడించండి",
        "Farm name is required.": "పొలం పేరు తప్పనిసరి.",
        "Your Cultivation Seasons": "మీ సాగు సీజన్లు",
        "🟢 Active": "🟢 యాక్టివ్",
        "✅ Completed": "✅ పూర్తయింది",
        "⚪ Abandoned": "⚪ వదిలివేయబడింది",
        "Mark Completed": "పూర్తయినట్లు గుర్తించండి",
        "Abandon": "వదిలివేయండి",
        "Delete this **{crop_name}** season on **{farm_name}**? This permanently deletes its schedule, expenses, revenues, observations, and alerts.": "**{farm_name}** పై **{crop_name}** సీజన్‌ను తొలగించాలా? ఇది దాని షెడ్యూల్, ఖర్చులు, ఆదాయాలు, పరిశీలనలు మరియు హెచ్చరికలను శాశ్వతంగా తొలగిస్తుంది.",
        "No seasons yet. Start your first cultivation cycle below.": "ఇంకా సీజన్లు లేవు. కింద మీ మొదటి సాగు చక్రాన్ని ప్రారంభించండి.",
        "➕ Start a New Season": "➕ కొత్త సీజన్‌ను ప్రారంభించండి",
        "Add a Farm first (see the Farms tab) before starting a season.": "సీజన్‌ను ప్రారంభించే ముందు ముందుగా ఒక పొలాన్ని జోడించండి (పొలాలు ట్యాబ్ చూడండి).",
        "No Crop Master templates found. An administrator needs to seed crop templates (see seed/crop_master_seed.py) before seasons can be created.": "పంట మాస్టర్ టెంప్లేట్‌లు కనుగొనబడలేదు. సీజన్లు సృష్టించే ముందు నిర్వాహకుడు పంట టెంప్లేట్‌లను సీడ్ చేయాలి (seed/crop_master_seed.py చూడండి).",
        "Variety (optional)": "రకం (ఐచ్ఛికం)",
        "e.g. IR-64, Bt-Hybrid": "ఉదా. IR-64, Bt-హైబ్రిడ్",
        "Sowing Date *": "విత్తిన తేదీ *",
        "Area *": "విస్తీర్ణం *",
        "Notes (optional)": "గమనికలు (ఐచ్ఛికం)",
        "Any additional context for this season": "ఈ సీజన్‌కు సంబంధించిన అదనపు వివరాలు",
        "Create Season & Generate Schedule": "సీజన్‌ను సృష్టించి షెడ్యూల్‌ను తయారు చేయండి",
        "This crop has no current template version configured. An administrator needs to set one before seasons can be created for it.": "ఈ పంటకు ప్రస్తుత టెంప్లేట్ వెర్షన్ కాన్ఫిగర్ చేయబడలేదు. దీనికి సీజన్లు సృష్టించే ముందు నిర్వాహకుడు ఒకదాన్ని సెట్ చేయాలి.",
        "Season created! Generated {n} scheduled activities from the {crop} crop template (version {version}).": "సీజన్ సృష్టించబడింది! {crop} పంట టెంప్లేట్ (వెర్షన్ {version}) నుండి {n} షెడ్యూల్ చేసిన కార్యకలాపాలు తయారయ్యాయి.",

        # ---- 2_Cultivation_Schedule.py ----
        "🌿 Cultivation Schedule": "🌿 సాగు షెడ్యూల్",
        "All": "అన్నీ",
        "Pending": "పెండింగ్‌లో",
        "Completed": "పూర్తయింది",
        "Skipped": "దాటవేయబడింది",
        "No activities match this filter.": "ఈ ఫిల్టర్‌కు సరిపోలే కార్యకలాపాలు లేవు.",
        "Stage:": "దశ:",
        "All activities completed this week ✓": "ఈ వారం అన్ని కార్యకలాపాలు పూర్తయ్యాయి ✓",
        "{done}/{total} done": "{done}/{total} పూర్తయ్యాయి",
        "OVERDUE": "గడువు మీరింది",
        "🧴 SPRAY · APPLY NOW": "🧴 స్ప్రే · ఇప్పుడే వేయండి",
        "🌱 FERTILIZER · APPLY": "🌱 ఎరువు · వేయండి",
        "Mark complete": "పూర్తయినట్లు గుర్తించండి",
        "Skip": "దాటవేయండి",
        "Product": "ఉత్పత్తి",
        "Dose": "మోతాదు",
        "Water": "నీరు",
        "Timing": "సమయం",
        "Objective": "లక్ష్యం",
        "Why": "ఎందుకు",
        "Precautions": "జాగ్రత్తలు",
        "➕ Add Custom Activity": "➕ కస్టమ్ కార్యకలాపాన్ని జోడించండి",
        "Remarks / dosage (optional)": "వ్యాఖ్యలు / మోతాదు (ఐచ్ఛికం)",
        "Add Activity": "కార్యకలాపాన్ని జోడించండి",
        "e.g. Soil Testing": "ఉదా. నేల పరీక్ష",
        "Activity name is required.": "కార్యకలాపం పేరు తప్పనిసరి.",

        # ---- 3_Weekly_Alerts.py ----
        "🔔 Weekly Alerts": "🔔 వారపు హెచ్చరికలు",
        "🔴 Overdue": "🔴 గడువు మీరింది",
        "🟡 Due in 3 days": "🟡 3 రోజుల్లో గడువు",
        "🟢 This week": "🟢 ఈ వారం",
        "You're all caught up! No alerts right now. ✅": "మీరు అన్నీ పూర్తి చేశారు! ప్రస్తుతం హెచ్చరికలు లేవు. ✅",
        "🔴 Overdue — act now": "🔴 గడువు మీరింది — ఇప్పుడే చర్య తీసుకోండి",
        "🟡 Due soon — next 3 days": "🟡 త్వరలో గడువు — తర్వాతి 3 రోజుల్లో",
        "🟢 Coming up — this week": "🟢 రాబోతోంది — ఈ వారం",
        "Mark done": "పూర్తయినట్లు గుర్తించండి",
        "Completion date": "పూర్తి చేసిన తేదీ",
        "Remarks": "వ్యాఖ్యలు",
        "✅ Done": "✅ పూర్తయింది",
        "⏭ Skip": "⏭ దాటవేయండి",

        # ---- 4_Expenses.py ----
        "💸 Expenses": "💸 ఖర్చులు",
        "Entries": "నమోదులు",
        "📜 Expense Log": "📜 ఖర్చుల లాగ్",
        "_No description_": "_వివరణ లేదు_",
        "No expenses logged yet. Add your first one on the right.": "ఇంకా ఖర్చులు నమోదు కాలేదు. కుడివైపు మీ మొదటి దాన్ని జోడించండి.",
        "➕ Add Expense": "➕ ఖర్చును జోడించండి",
        "e.g. Urea 2 bags": "ఉదా. యూరియా 2 బస్తాలు",
        "Amount must be greater than zero.": "మొత్తం సున్నా కంటే ఎక్కువగా ఉండాలి.",
        "Logged {amount} under {category}.": "{category} కింద {amount} నమోదు చేయబడింది.",
        "📊 By Category": "📊 వర్గం వారీగా",
        "📈 Expense Timeline": "📈 ఖర్చుల కాలక్రమం",
        # Title-cased ExpenseCategory enum labels
        "Seed": "విత్తనం",
        "Chemicals": "రసాయనాలు",
        "Labour": "కూలీ",
        "Machinery": "యంత్రాలు",
        "Transport": "రవాణా",
        "Miscellaneous": "ఇతరాలు",

        # ---- 5_Revenue.py ----
        "📈 Revenue": "📈 ఆదాయం",
        "Sale Entries": "అమ్మకపు నమోదులు",
        "Total Quantity Sold": "అమ్మిన మొత్తం పరిమాణం",
        "📜 Sales Log": "📜 అమ్మకాల లాగ్",
        "Unknown Buyer": "తెలియని కొనుగోలుదారు",
        "No sales logged yet. Add your first one on the right.": "ఇంకా అమ్మకాలు నమోదు కాలేదు. కుడివైపు మీ మొదటి దాన్ని జోడించండి.",
        "➕ Add Sale": "➕ అమ్మకాన్ని జోడించండి",
        "e.g. Local Mandi / Trader Name": "ఉదా. స్థానిక మండి / వ్యాపారి పేరు",
        "Quantity *": "పరిమాణం *",
        "Quintal": "క్వింటాల్",
        "Kg": "కేజీ",
        "Tonne": "టన్ను",
        "Bag": "బస్తా",
        "Price per Unit *": "యూనిట్‌కు ధర *",
        "Amount: {amount}": "మొత్తం: {amount}",
        "Add Sale": "అమ్మకాన్ని జోడించండి",
        "Quantity and price must be greater than zero.": "పరిమాణం మరియు ధర సున్నా కంటే ఎక్కువగా ఉండాలి.",
        "Logged sale of {amount}.": "{amount} అమ్మకం నమోదు చేయబడింది.",
        "📈 Revenue Timeline": "📈 ఆదాయ కాలక్రమం",

        # ---- 6_Profit_and_Loss.py ----
        "🧮 Profit & Loss": "🧮 లాభ-నష్టం",
        "Net Profit": "నికర లాభం",
        "Net Loss": "నికర నష్టం",
        "for {area} {area_unit} of {crop}": "{crop} యొక్క {area} {area_unit}కు",
        "{label} / Acre": "ఎకరానికి {label}",
        "💸 Expense Pie Chart": "💸 ఖర్చుల పై చార్ట్",
        "⚖️ Income vs Expense": "⚖️ ఆదాయం vs ఖర్చు",
        "This Season": "ఈ సీజన్",
        "Revenue": "ఆదాయం",
        "Expenses": "ఖర్చులు",
        "Add expenses and revenue to see this comparison.": "ఈ పోలికను చూడటానికి ఖర్చులు మరియు ఆదాయాన్ని జోడించండి.",
        "📋 Detailed Breakdown": "📋 వివరణాత్మక విభజన",
        "Expenses by Category": "వర్గం వారీగా ఖర్చులు",
        "Season Economics": "సీజన్ ఆర్థికాలు",
        "Cost per Acre": "ఎకరానికి ఖర్చు",
        "{label} per Acre": "ఎకరానికి {label}",

        # ---- 7_Observations.py ----
        "📸 Observations": "📸 పరిశీలనలు",
        "Log what you see in the field -- a quick note, a photo, or both. Optionally get an AI read on a photo for a second opinion.": "మీరు పొలంలో చూసిన దాన్ని నమోదు చేయండి -- ఒక చిన్న గమనిక, ఫోటో, లేదా రెండూ. రెండో అభిప్రాయం కోసం ఐచ్ఛికంగా ఫోటోపై AI విశ్లేషణ పొందండి.",
        "AI analysis is not configured in this environment (no ANTHROPIC_API_KEY set). You can still log notes and photos -- just without the AI read.": "ఈ వాతావరణంలో AI విశ్లేషణ కాన్ఫిగర్ చేయబడలేదు (ANTHROPIC_API_KEY సెట్ చేయలేదు). మీరు ఇప్పటికీ గమనికలు మరియు ఫోటోలను నమోదు చేయవచ్చు -- AI విశ్లేషణ లేకుండా మాత్రమే.",
        "➕ Add Observation": "➕ పరిశీలనను జోడించండి",
        "e.g. Yellowing on lower leaves near the east bund": "ఉదా. తూర్పు గట్టు దగ్గర కింది ఆకులపై పసుపు రంగు",
        "Photo (optional)": "ఫోటో (ఐచ్ఛికం)",
        "Run AI analysis on this photo": "ఈ ఫోటోపై AI విశ్లేషణ చేయండి",
        "Save Observation": "పరిశీలనను సేవ్ చేయండి",
        "Add a note, a photo, or both.": "ఒక గమనిక, ఫోటో, లేదా రెండూ జోడించండి.",
        "Photo couldn't be uploaded to storage ({error}) -- saving the note without it. The photo can still be analyzed below before saving.": "ఫోటోను స్టోరేజ్‌కు అప్‌లోడ్ చేయలేకపోయాము ({error}) -- గమనికను దాని లేకుండా సేవ్ చేస్తున్నాము. సేవ్ చేయడానికి ముందు ఫోటోను కింద ఇంకా విశ్లేషించవచ్చు.",
        "Analyzing photo...": "ఫోటోను విశ్లేషిస్తోంది...",
        "Observation saved. AI read: **{category}**.": "పరిశీలన సేవ్ చేయబడింది. AI విశ్లేషణ: **{category}**.",
        "Observation saved, but AI analysis was unavailable this time.": "పరిశీలన సేవ్ చేయబడింది, కానీ ఈసారి AI విశ్లేషణ అందుబాటులో లేదు.",
        "Observation saved.": "పరిశీలన సేవ్ చేయబడింది.",
        "Saved photo": "సేవ్ చేసిన ఫోటో",
        "🗒️ Observation Log": "🗒️ పరిశీలనల లాగ్",
        "No observations logged yet for this season.": "ఈ సీజన్‌కు ఇంకా పరిశీలనలు నమోదు కాలేదు.",
        "AI read: {category}": "AI విశ్లేషణ: {category}",
        "confidence {pct}": "నమ్మకం {pct}",
        "Recommendation: {rec}": "సిఫార్సు: {rec}",
        # AI category values (services/ai_engine.py)
        "Pest": "పురుగు",
        "Disease": "వ్యాధి",
        "Nutrient Deficiency": "పోషక లోపం",
        "Water Stress": "నీటి ఒత్తిడి",
        "Weed Pressure": "కలుపు ఒత్తిడి",
        "Healthy / No Issue": "ఆరోగ్యంగా / సమస్య లేదు",
        "Unclear": "అస్పష్టం",
    }
}
