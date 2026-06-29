"""
Weekly Alerts — redesigned with category grouping, product hints,
and rich fertilizer/pesticide combination cards.
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from app.ui_helpers import ALERT_GREEN, ALERT_RED, ALERT_YELLOW, require_active_season
from db.base import session_scope
from db.models import ActivityStatus, ScheduleActivity, Season
from services.alert_engine import refresh_alerts_for_season, build_alert_views

st.set_page_config(page_title="Weekly Alerts", page_icon="🔔", layout="wide")

CATEGORY_META = {
    "IRRIGATION":       {"icon": "💧", "color": "#1565C0", "bg": "#E3F2FD", "label": "Irrigation"},
    "FERTILIZER":       {"icon": "🌱", "color": "#2E7D32", "bg": "#E8F5E9", "label": "Fertilizer"},
    "SPRAY":            {"icon": "🧴", "color": "#6A1B9A", "bg": "#F3E5F5", "label": "Spray / Pest"},
    "WEEDING":          {"icon": "🌾", "color": "#E65100", "bg": "#FFF3E0", "label": "Weeding"},
    "LAND_PREPARATION": {"icon": "🚜", "color": "#4E342E", "bg": "#EFEBE9", "label": "Land Prep"},
    "SOWING":           {"icon": "🌰", "color": "#558B2F", "bg": "#F1F8E9", "label": "Sowing"},
    "HARVEST":          {"icon": "🌾", "color": "#F9A825", "bg": "#FFFDE7", "label": "Harvest"},
    "OTHER":            {"icon": "📋", "color": "#546E7A", "bg": "#ECEFF1", "label": "Other"},
}

PRODUCT_HINTS = {
    "dap":          {"dose": "40 kg/acre", "combo": "DAP 18:46:0 + MOP 35 kg/acre", "note": "Basal placement in furrows before sowing."},
    "mop":          {"dose": "35 kg/acre", "combo": "MOP 0:0:60 + DAP 40 kg/acre", "note": "Mix into soil; apply together with DAP at sowing."},
    "urea":         {"dose": "30 kg/acre", "combo": "Urea 46% N", "note": "Broadcast between rows, irrigate immediately after."},
    "can":          {"dose": "40 kg/acre", "combo": "CAN 25% N (Calcium Ammonium Nitrate)", "note": "Better than urea on alkaline soils; less N volatilisation."},
    "ammonium sulphate": {"dose": "75 kg/acre (1st TD) / 30 kg/acre (later)", "combo": "AS 20.6% N → acidifying; good for red soils", "note": "Broadcast, irrigate same day."},
    "boron":        {"dose": "1 g/L", "combo": "Borax 1 g/L + Calcium Nitrate 2 g/L", "note": "Spray evening only. Improves fruit set, reduces flower drop."},
    "zinc":         {"dose": "0.5 g/L", "combo": "ZnSO₄ 0.5 g/L + Borax 1 g/L", "note": "Micronutrient combo for red soils after maize. Evening spray."},
    "mkp":          {"dose": "3 g/L", "combo": "MKP 0:52:34 (foliar only)", "note": "Boosts pod setting and early yield. Spray on leaves."},
    "npk 19":       {"dose": "5 g/L", "combo": "NPK 19:19:19 water-soluble (Multi-K)", "note": "Foliar vigour spray. Safe to tank-mix with most fungicides."},
    "seaweed":      {"dose": "3 ml/L", "combo": "Seaweed Extract 3 ml/L + MKP 3 g/L (optional)", "note": "Stress tolerance during peak production. Evening spray."},
    "potassium nitrate": {"dose": "5 g/L", "combo": "Potassium Nitrate NOP 13:0:45", "note": "Improves pod size, colour, shelf-life. Market quality spray."},
    "spinosad":     {"dose": "0.3 ml/L", "combo": "Spinosad 45 SC — solo spray", "note": "FSB control. Evening only. PHI: 1 day. Rotate with Emamectin."},
    "emamectin":    {"dose": "0.4 ml/L", "combo": "Emamectin Benzoate 5 SG — solo spray", "note": "Rotate from Spinosad. PHI: 5 days. Do not mix with alkaline sprays."},
    "imidacloprid": {"dose": "0.5 ml/L", "combo": "Imidacloprid 17.8 SL + Neem Oil 3 ml/L (optional)", "note": "YVMV vector (whitefly) control. PHI: 7 days."},
    "chlorantraniliprole": {"dose": "0.3 ml/L", "combo": "Coragen 18.5 SC — solo or + Thiamethoxam", "note": "Shoot & fruit borer. PHI: 1 day."},
    "profenofos":   {"dose": "2 ml/L", "combo": "Profenofos 50 EC + Cypermethrin 5 EC 1 ml/L", "note": "Broad spectrum — multiple pests. PHI: 7 days."},
    "indoxacarb":   {"dose": "0.7 ml/L", "combo": "Indoxacarb 14.5 SC — solo spray", "note": "FSB late season. PHI: 3 days. Rotate chemicals."},
    "abamectin":    {"dose": "0.5 ml/L", "combo": "Abamectin 1.9 EC + Wettable Sulphur 2 g/L", "note": "Red spider mite + powdery mildew combo. PHI: 3 days."},
    "mancozeb":     {"dose": "2.5 g/L", "combo": "Mancozeb 75 WP + Carbendazim 12 WP 0.5 g/L", "note": "Cercospora leaf spot. Apply at first sign of symptoms."},
    "wettable sulphur": {"dose": "3 g/L", "combo": "Wettable Sulphur 80 WP — solo spray", "note": "Powdery mildew. Do NOT spray when temp > 35°C. PHI: 1 day."},
    "neem":         {"dose": "5 ml/L + Teepol 1 ml/L", "combo": "Neem Oil 5000 ppm + Teepol 1 ml/L as emulsifier", "note": "Broad mite/sucking pests. Evening spray only."},
    "chlorpyrifos": {"dose": "2–2.5 ml/L", "combo": "Chlorpyrifos 20 EC + Cypermethrin 5 EC 1 ml/L", "note": "Cutworm at base / late-season broad spectrum. PHI: 15 days."},
}

def _get_hint(name: str, remarks: str) -> dict | None:
    text = (name + " " + remarks).lower()
    for kw, hint in PRODUCT_HINTS.items():
        if kw in text:
            return hint
    return None


st.markdown("""
<style>
.alert-card {
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    border-left: 5px solid #ccc;
}
.priority-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 18px 0 10px 0;
}
.priority-title {
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: -0.01em;
}
.combo-pill {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 10px;
    margin-right: 4px;
    margin-top: 4px;
}
.pct-bar-wrap {
    height: 6px;
    border-radius: 3px;
    background: #e0e0e0;
    margin: 3px 0 6px 0;
    overflow: hidden;
}
.hint-grid {
    display: grid;
    grid-template-columns: 80px 1fr;
    gap: 4px 10px;
    font-size: 0.8rem;
    margin-top: 6px;
}
.hint-key { font-weight: 700; opacity: 0.6; font-size: 0.72rem; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

ctx = require_active_season()
season_id = ctx["season_id"]

st.title("🔔 Weekly Alerts")
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

# ── Load alerts + raw activities for enrichment ───────────────────────────────
with session_scope() as session:
    season_obj = session.get(Season, season_id)
    alerts = refresh_alerts_for_season(session, season_obj)

    # Also load the actual activity objects for enrichment (remarks, category)
    activity_map = {}
    if alerts:
        act_ids = [a.schedule_activity_id for a in alerts if a.schedule_activity_id]
        raw_acts = session.query(ScheduleActivity).filter(ScheduleActivity.id.in_(act_ids)).all()
        activity_map = {str(a.id): a for a in raw_acts}

    alerts_data = [
        {
            "priority": a.priority.value,
            "message": a.message,
            "activity_id": str(a.schedule_activity_id) if a.schedule_activity_id else None,
        }
        for a in alerts
    ]

red    = [a for a in alerts_data if a["priority"] == "RED"]
yellow = [a for a in alerts_data if a["priority"] == "YELLOW"]
green  = [a for a in alerts_data if a["priority"] == "GREEN"]

# ── Summary metrics ───────────────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
m1.metric("🔴 Overdue",        len(red),    delta=None)
m2.metric("🟡 Due in 3 days",  len(yellow), delta=None)
m3.metric("🟢 This week",      len(green),  delta=None)

if not alerts_data:
    st.success("You're all caught up! No alerts right now. ✅")
    st.stop()

st.divider()


def render_alert_group(
    title: str,
    border_color: str,
    bg_color: str,
    items: list[dict],
) -> None:
    if not items:
        return

    st.markdown(
        f"<div class='priority-header'>"
        f"<span class='priority-title' style='color:{border_color};'>{title}</span>"
        f"<span style='font-size:0.78rem; background:{border_color}18; color:{border_color}; "
        f"padding:2px 10px; border-radius:20px; font-weight:700;'>{len(items)} task{'s' if len(items)!=1 else ''}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    for item in items:
        act = activity_map.get(item["activity_id"]) if item["activity_id"] else None
        cat = act.category.value if act else "OTHER"
        remarks = (act.remarks or "") if act else ""
        name = act.name if act else item["message"]
        cat_meta = CATEGORY_META.get(cat, CATEGORY_META["OTHER"])
        hint = _get_hint(name, remarks) if act else None

        st.markdown(
            f"""<div class='alert-card' style='border-left-color:{border_color}; background:{bg_color};'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span style='font-weight:700; font-size:0.95rem;'>
                        {cat_meta['icon']} {name}
                    </span>
                    <span style='font-size:0.72rem; font-weight:700; padding:2px 9px; border-radius:10px;
                          background:{cat_meta["color"]}18; color:{cat_meta["color"]};'>
                        {cat_meta['label']}
                    </span>
                </div>
                <div style='font-size:0.8rem; color:#666; margin-top:3px;'>{item['message']}</div>
                {f"<div style='font-size:0.78rem; color:#555; margin-top:4px; font-style:italic;'>{remarks}</div>" if remarks else ""}
            </div>""",
            unsafe_allow_html=True,
        )

        # Product hint expander for fertilizer / spray activities
        if hint and act and cat in ("FERTILIZER", "SPRAY"):
            with st.expander(f"📦 {hint['combo'].split('—')[0].strip()} — dosage & mix guide", expanded=False):
                # Combination pills
                parts = [p.strip() for p in hint["combo"].replace("→", "+").split("+") if p.strip()]
                pill_html = ""
                colors = [cat_meta["color"], "#546E7A", "#795548"]
                for pi, part in enumerate(parts[:3]):
                    c = colors[pi % len(colors)]
                    pill_html += f"<span class='combo-pill' style='background:{c}18; color:{c};'>● {part}</span>"

                st.markdown(
                    f"""<div style='background:{cat_meta["bg"]}; border:1px solid {cat_meta["color"]}30;
                               border-radius:9px; padding:12px 16px;'>
                        <div style='margin-bottom:6px;'>{pill_html}</div>
                        <div class='hint-grid'>
                            <span class='hint-key'>Dose</span><span>{hint['dose']}</span>
                            <span class='hint-key'>Note</span><span style='color:#444;'>{hint['note']}</span>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='margin-bottom:6px'></div>", unsafe_allow_html=True)


render_alert_group("🔴 Overdue — act now",         ALERT_RED,    "#FFF5F5", red)
render_alert_group("🟡 Due soon — next 3 days",    ALERT_YELLOW, "#FFFBF0", yellow)
render_alert_group("🟢 Coming up — this week",     ALERT_GREEN,  "#F5FBF5", green)
