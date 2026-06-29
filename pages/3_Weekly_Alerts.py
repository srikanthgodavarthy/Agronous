"""
Weekly Alerts — portrait cards grouped by priority, scrolling vertically.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from app.ui_helpers import ALERT_GREEN, ALERT_RED, ALERT_YELLOW, require_active_season
from db.base import session_scope
from db.models import ActivityStatus, ScheduleActivity, Season
from services.alert_engine import refresh_alerts_for_season

st.set_page_config(page_title="Weekly Alerts", page_icon="🔔", layout="wide")

CATEGORY_META = {
    "IRRIGATION":       {"icon": "💧", "bg": "rgba(60,130,200,0.10)",  "label": "Irrigation"},
    "FERTILIZER":       {"icon": "🌱", "bg": "rgba(100,170,60,0.10)",  "label": "Fertilizer"},
    "SPRAY":            {"icon": "🧴", "bg": "rgba(130,60,180,0.10)",  "label": "Spray/Pest"},
    "WEEDING":          {"icon": "🌾", "bg": "rgba(200,100,30,0.10)",  "label": "Weeding"},
    "LAND_PREPARATION": {"icon": "🚜", "bg": "rgba(180,120,60,0.10)",  "label": "Land Prep"},
    "SOWING":           {"icon": "🌰", "bg": "rgba(80,160,80,0.10)",   "label": "Sowing"},
    "HARVEST":          {"icon": "🌾", "bg": "rgba(200,160,20,0.10)",  "label": "Harvest"},
    "OTHER":            {"icon": "📋", "bg": "rgba(100,110,120,0.10)", "label": "Other"},
}

PRIORITY_META = {
    "RED":    {"label": "🔴 Overdue — act now",      "card_style": "background:#fdf2f2; border-color:#f0b4b4;", "pill": "background:#fdf2f2; color:#a32d2d; border:0.5px solid #f0b4b4;"},
    "YELLOW": {"label": "🟡 Due soon — next 3 days", "card_style": "background:#fffbf0; border-color:#f5d98a;", "pill": "background:#fffbf0; color:#854f0b; border:0.5px solid #f5d98a;"},
    "GREEN":  {"label": "🟢 Coming up — this week",  "card_style": "background:#f0faf4; border-color:#b6e4cb;", "pill": "background:#f0faf4; color:#3b6d11; border:0.5px solid #b6e4cb;"},
}

PRODUCT_HINTS = {
    "dap":        {"dose": "40 kg/acre", "note": "Basal placement in furrows before sowing."},
    "urea":       {"dose": "30 kg/acre", "note": "Broadcast between rows, irrigate immediately."},
    "spinosad":   {"dose": "0.3 ml/L",  "note": "FSB control. Evening only. PHI: 1 day."},
    "emamectin":  {"dose": "0.4 ml/L",  "note": "Rotate from Spinosad. PHI: 5 days."},
    "mancozeb":   {"dose": "2.5 g/L",   "note": "Cercospora leaf spot. Apply at first sign."},
    "neem":       {"dose": "5 ml/L",    "note": "Broad mite/sucking pests. Evening spray only."},
    # Okra (Bhindi) -- Vikarabad checklist activities, matched by exact
    # activity name. Mirrors 2_Cultivation_Schedule.py's PRODUCT_HINTS.
    "basal dose - dap + potash":   {"dose": "40 + 35 kg/acre", "note": "Mix into soil before sowing."},
    "top dressing #1 - ammonium sulphate": {"dose": "75 kg/acre", "note": "Broadcast between rows and irrigate immediately."},
    "whitefly / aphid control - imidacloprid": {"dose": "0.5 ml/L", "note": "YVMV vector control. If high population."},
    "zinc + boron foliar spray":   {"dose": "0.5 g/L + 1 g/L", "note": "Corrects micronutrient deficiency common after maize in red soils."},
    "npk foliar spray":            {"dose": "5 g/L", "note": "Vegetative vigour ahead of flowering."},
    "top dressing #2 - can or complex": {"dose": "40 kg/acre", "note": "Broadcast and irrigate."},
    "mite / whitefly control - neem": {"dose": "5 ml/L", "note": "Evening only."},
    "fsb control - spinosad":      {"dose": "0.3 ml/L", "note": "Evening only. Do not spray 10am-4pm flowering hours."},
    "fruit set spray - boron + calcium": {"dose": "1 g/L + 2 g/L", "note": "Improves fruit set and reduces flower drop."},
    "fsb control (rotation) - emamectin": {"dose": "0.4 ml/L", "note": "Rotate from Spinosad to avoid resistance build-up."},
    "powdery mildew watch":        {"dose": "3 g/L", "note": "If white powder appears on leaves."},
    "fruiting boost - mkp spray":  {"dose": "3 g/L", "note": "Boosts pod setting and early yield."},
    "red spider mite control":     {"dose": "0.5 ml/L or 2 ml/L", "note": "For red spider mite."},
    "cercospora leaf spot control": {"dose": "2.5 g/L", "note": "For Cercospora leaf spot."},
    "top dressing #3 - ammonium sulphate + potash": {"dose": "30 + 20 kg/acre", "note": "Extends yield period."},
    "broad spectrum control":      {"dose": "2 ml/L", "note": "If multiple pests observed together."},
    "plant stamina - seaweed spray": {"dose": "3 ml/L", "note": "Improves plant stamina and stress tolerance."},
    "fsb control - indoxacarb / chlorpyrifos": {"dose": "0.7 ml/L or 2 ml/L", "note": "Continued FSB rotation."},
    "pod quality spray - potassium nitrate": {"dose": "5 g/L", "note": "Improves pod size, colour, shelf life and market quality."},
}

def _get_hint(name: str, remarks: str, category: str | None = None) -> dict | None:
    # Same guard as 2_Cultivation_Schedule.py: hints only ever apply to
    # actual spray/fertilizer applications. Monitoring, harvest, irrigation
    # and weeding remarks legitimately mention pest/disease names in prose
    # without that being a product recommendation.
    if category is not None and category not in ("FERTILIZER", "SPRAY"):
        return None
    text = (name + " " + remarks).lower()
    for kw, hint in PRODUCT_HINTS.items():
        if kw in text:
            return hint
    return None

st.markdown("""
<style>
.priority-pill {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.05em;
    padding: 4px 12px; border-radius: 20px; margin: 18px 0 12px 0;
}
.cards-row {
    display: flex; flex-direction: row; gap: 10px; flex-wrap: wrap; margin-bottom: 6px;
}
.act-card {
    border-radius: 12px; padding: 14px 12px;
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    border: 0.5px solid transparent;
    width: 140px; min-height: 170px; position: relative; box-sizing: border-box;
}
.act-icon {
    width: 38px; height: 38px; border-radius: 10px; font-size: 18px;
    display: flex; align-items: center; justify-content: center;
}
.act-name {
    font-size: 12px; font-weight: 500; color: #1a1a1a;
    text-align: center; line-height: 1.35;
}
.act-meta {
    font-size: 10px; color: #888; text-align: center; line-height: 1.5;
}
.act-spacer { flex: 1; }
.act-btns { display: flex; gap: 8px; justify-content: center; }
.act-btn {
    width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; background: white; font-size: 12px;
}
.btn-done { border-color: #4caf7d; color: #4caf7d; }
.btn-skip { border-color: #aaa9a2; color: #aaa9a2; }
</style>
""", unsafe_allow_html=True)

ctx = require_active_season()
season_id = ctx["season_id"]

st.title("🔔 Weekly Alerts")
st.caption(f"{ctx['farm_name']} · {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

with session_scope() as session:
    season_obj = session.get(Season, season_id)
    alerts = refresh_alerts_for_season(session, season_obj)

    activity_map = {}
    if alerts:
        act_ids = [a.schedule_activity_id for a in alerts if a.schedule_activity_id]
        raw_acts = session.query(ScheduleActivity).filter(ScheduleActivity.id.in_(act_ids)).all()
        activity_map = {str(a.id): a for a in raw_acts}

    alerts_data = [
        {
            "priority":    a.priority.value,
            "message":     a.message,
            "activity_id": str(a.schedule_activity_id) if a.schedule_activity_id else None,
        }
        for a in alerts
    ]

red    = [a for a in alerts_data if a["priority"] == "RED"]
yellow = [a for a in alerts_data if a["priority"] == "YELLOW"]
green  = [a for a in alerts_data if a["priority"] == "GREEN"]

# Summary metrics
m1, m2, m3 = st.columns(3)
m1.metric("🔴 Overdue",       len(red))
m2.metric("🟡 Due in 3 days", len(yellow))
m3.metric("🟢 This week",     len(green))

if not alerts_data:
    st.success("You're all caught up! No alerts right now. ✅")
    st.stop()

st.divider()

def render_alert_group(priority: str, items: list[dict]) -> None:
    if not items:
        return

    pm = PRIORITY_META[priority]
    st.markdown(
        f"<div class='priority-pill' style='{pm['pill']}'>{pm['label']} · {len(items)} task{'s' if len(items)!=1 else ''}</div>",
        unsafe_allow_html=True,
    )

    cards_html = "<div class='cards-row'>"
    for item in items:
        act     = activity_map.get(item["activity_id"]) if item["activity_id"] else None
        cat     = act.category.value if act else "OTHER"
        name    = act.name if act else item["message"]
        remarks = (act.remarks or "") if act else ""
        das     = act.das if act else ""
        act_date = act.activity_date.strftime("%d %b") if act and act.activity_date else ""
        meta    = CATEGORY_META.get(cat, CATEGORY_META["OTHER"])

        cards_html += f"""
        <div class='act-card' style='{pm["card_style"]}'>
            <div class='act-icon' style='background:{meta["bg"]}'>{meta["icon"]}</div>
            <div class='act-name'>{name}</div>
            <div class='act-meta'>{act_date}{"<br>DAS " + str(das) if das != "" else ""}<br>{meta["label"]}</div>
            <div class='act-spacer'></div>
            <div class='act-btns'>
                <span class='act-btn btn-done' title='Mark done'>✓</span>
                <span class='act-btn btn-skip' title='Skip'>⏭</span>
            </div>
        </div>"""
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    # Action expanders
    from repositories import schedule_repo
    from db.base import session_scope as ss
    for idx, item in enumerate(items):
        act = activity_map.get(item["activity_id"]) if item["activity_id"] else None
        if not act:
            continue
        name    = act.name
        hint    = _get_hint(name, act.remarks or "", act.category.value)
        with st.expander(f"⚙ {name}", expanded=False):
            with st.form(f"alert_{priority}_{idx}_{act.id}"):
                new_date    = st.date_input("Completion date", value=act.activity_date, key=f"ad_{priority}_{idx}")
                new_remarks = st.text_area("Remarks", value=act.remarks or "", key=f"ar_{priority}_{idx}", height=60)
                cc, skc = st.columns(2)
                complete = cc.form_submit_button("✅ Done")
                skip     = skc.form_submit_button("⏭ Skip")

                if complete or skip:
                    with ss() as session:
                        a = schedule_repo.get_activity(session, act.id)
                        if a:
                            schedule_repo.update_activity(session, a, activity_date=new_date, remarks=new_remarks or None)
                            if complete:
                                schedule_repo.mark_complete(session, a)
                            else:
                                schedule_repo.mark_skipped(session, a)
                    st.rerun()

            if hint:
                st.caption(f"📦 {hint['dose']} · {hint['note']}")

render_alert_group("RED",    red)
render_alert_group("YELLOW", yellow)
render_alert_group("GREEN",  green)
