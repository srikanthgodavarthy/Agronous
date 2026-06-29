"""
Cultivation Schedule — redesigned with category tabs, week grouping,
and rich fertilizer/pesticide detail cards.
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from app.ui_helpers import require_active_season
from db.base import session_scope
from db.models import ActivityCategory, ActivityStatus
from repositories import schedule_repo
from services.schedule_engine import calculate_das

st.set_page_config(page_title="Cultivation Schedule", page_icon="🌿", layout="wide")

# ── Design tokens ────────────────────────────────────────────────────────────
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

STATUS_META = {
    "PENDING":   {"icon": "⏳", "color": "#F9A825"},
    "COMPLETED": {"icon": "✅", "color": "#2E7D32"},
    "SKIPPED":   {"icon": "⏭️",  "color": "#90A4AE"},
}

# Fertilizer/spray hints keyed by keywords in activity name (lower-case)
PRODUCT_HINTS = {
    "dap":          {"dose": "40 kg/acre", "mix": "DAP 18:46:0", "note": "Basal placement in furrows before sowing."},
    "mop":          {"dose": "35 kg/acre", "mix": "MOP (Muriate of Potash) 0:0:60", "note": "Mix into soil; can combine with DAP at sowing."},
    "urea":         {"dose": "30 kg/acre", "mix": "Urea 46% N", "note": "Broadcast between rows and irrigate immediately."},
    "can":          {"dose": "40 kg/acre", "mix": "CAN 25% N (Calcium Ammonium Nitrate)", "note": "Better than urea on alkaline soils; less N volatilisation."},
    "ammonium sulphate": {"dose": "75 kg/acre (1st TD) / 30 kg/acre (later)", "mix": "AS 20.6% N", "note": "Acidifying effect — good for Vikarabad red soils."},
    "boron":        {"dose": "1 g/L", "mix": "Borax (Boron 10.5%) 1 g/L + Calcium Nitrate 2 g/L", "note": "Spray in evening only. Improves fruit set, reduces flower drop."},
    "zinc":         {"dose": "0.5 g/L", "mix": "ZnSO₄ 0.5 g/L + Borax 1 g/L", "note": "Corrects micronutrient deficiency common in red soils after maize."},
    "mkp":          {"dose": "3 g/L", "mix": "Mono Potassium Phosphate (MKP 0:52:34)", "note": "Boosts pod setting and early yield. Spray on leaves."},
    "npk 19":       {"dose": "5 g/L", "mix": "Water Soluble NPK 19:19:19 (Multi-K / Kristalon)", "note": "Spray on leaves for vegetative vigour."},
    "seaweed":      {"dose": "3 ml/L", "mix": "Seaweed Extract (Seasol / Kelpak)", "note": "Improves plant stamina and stress tolerance during peak production."},
    "potassium nitrate": {"dose": "5 g/L", "mix": "Potassium Nitrate (NOP 13:0:45 / SOP)", "note": "Improves pod size, colour, shelf-life and market quality."},
    "spinosad":     {"dose": "0.3 ml/L", "mix": "Spinosad 45 SC", "note": "FSB control. Spray in evening only. PHI: 1 day."},
    "emamectin":    {"dose": "0.4 ml/L", "mix": "Emamectin Benzoate 5 SG", "note": "Rotate from Spinosad to avoid resistance. PHI: 5 days."},
    "imidacloprid": {"dose": "0.5 ml/L", "mix": "Imidacloprid 17.8 SL", "note": "Whitefly / YVMV vector control. PHI: 7 days."},
    "chlorantraniliprole": {"dose": "0.3 ml/L", "mix": "Chlorantraniliprole 18.5 SC (Coragen)", "note": "Shoot & fruit borer. PHI: 1 day."},
    "profenofos":   {"dose": "2 ml/L", "mix": "Profenofos 50 EC", "note": "Broad spectrum — multiple pests. PHI: 7 days."},
    "indoxacarb":   {"dose": "0.7 ml/L", "mix": "Indoxacarb 14.5 SC", "note": "FSB late season. Rotate chemicals. PHI: 3 days."},
    "abamectin":    {"dose": "0.5 ml/L", "mix": "Abamectin 1.9 EC", "note": "Red spider mite. PHI: 3 days."},
    "mancozeb":     {"dose": "2.5 g/L", "mix": "Mancozeb 75 WP", "note": "Cercospora leaf spot / fungal protection."},
    "wettable sulphur": {"dose": "3 g/L", "mix": "Wettable Sulphur 80 WP", "note": "Powdery mildew. Do NOT spray when temp > 35°C."},
    "neem":         {"dose": "5 ml/L + Teepol 1 ml/L", "mix": "Neem Oil 5000 ppm EC", "note": "Broad mite / sucking pest / mite. Spray evening only."},
    "chlorpyrifos": {"dose": "2–2.5 ml/L", "mix": "Chlorpyrifos 20 EC", "note": "Cutworm at base / late-season broad spectrum. PHI: 15 days."},
}

def _product_hint(name: str, remarks: str) -> dict | None:
    text = (name + " " + remarks).lower()
    for kw, hint in PRODUCT_HINTS.items():
        if kw in text:
            return hint
    return None


def _week_label(sowing_date: date, activity_date: date) -> str:
    das = (activity_date - sowing_date).days
    week = (das // 7) + 1
    week_start = sowing_date + timedelta(days=(week - 1) * 7)
    week_end   = week_start + timedelta(days=6)
    return f"Week {week}  ({week_start.strftime('%d %b')} – {week_end.strftime('%d %b')})"


st.markdown("""
<style>
.cat-header {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    opacity: 0.65;
    margin-bottom: 2px;
}
.activity-card {
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    border-left: 5px solid #ccc;
    background: #fff;
}
.week-chip {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    padding: 3px 10px;
    border-radius: 20px;
    background: #F0F4F0;
    color: #2E7D32;
    margin-bottom: 10px;
}
.hint-box {
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    margin-top: 6px;
    line-height: 1.5;
}
.hint-row { display: flex; gap: 8px; align-items: baseline; margin-bottom: 3px; }
.hint-label { font-weight: 700; min-width: 70px; font-size: 0.78rem; opacity: 0.7; }
.status-badge {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    padding: 2px 9px;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)


ctx = require_active_season()
season_id = ctx["season_id"]
sowing_date = ctx["sowing_date"]

st.title("🌿 Cultivation Schedule")
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

# ── Fetch all activities ─────────────────────────────────────────────────────
with session_scope() as session:
    activities = schedule_repo.list_activities(session, season_id, status=None)
    activities_data = [
        {
            "id": a.id,
            "activity_date": a.activity_date,
            "das": a.das,
            "name": a.name,
            "category": a.category.value,
            "status": a.status.value,
            "remarks": a.remarks or "",
            "is_custom": a.is_custom,
        }
        for a in activities
    ]

today = date.today()

# ── Category tab navigation ──────────────────────────────────────────────────
ALL_CATS = ["ALL"] + [c.value for c in ActivityCategory]
TAB_LABELS = ["🗓 All"] + [
    f"{CATEGORY_META[c]['icon']} {CATEGORY_META[c]['label']}" for c in ALL_CATS[1:]
]

tabs = st.tabs(TAB_LABELS)

def render_activities(tab_activities: list[dict], status_filter: str) -> None:
    if not tab_activities:
        st.info("No activities in this category.")
        return

    # Apply status filter
    if status_filter != "All":
        tab_activities = [a for a in tab_activities if a["status"] == status_filter]

    if not tab_activities:
        st.info("No activities match this filter.")
        return

    # Group by week
    from itertools import groupby
    def week_key(a):
        das = a["das"]
        return max(0, (das // 7) + 1)

    tab_activities_sorted = sorted(tab_activities, key=lambda a: a["activity_date"])
    groups = groupby(tab_activities_sorted, key=week_key)

    for week_num, group_items in groups:
        items = list(group_items)
        first = items[0]
        wlabel = _week_label(sowing_date, first["activity_date"])
        st.markdown(f"<div class='week-chip'>📅 {wlabel}</div>", unsafe_allow_html=True)

        for row in items:
            meta = CATEGORY_META.get(row["category"], CATEGORY_META["OTHER"])
            smeta = STATUS_META.get(row["status"], STATUS_META["PENDING"])
            is_overdue = row["status"] == "PENDING" and row["activity_date"] < today
            border_color = "#D32F2F" if is_overdue else meta["color"]

            hint = _product_hint(row["name"], row["remarks"])

            with st.container():
                st.markdown(
                    f"""<div class='activity-card' style='border-left-color:{border_color}; background:{meta["bg"]};'>
                        <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                            <div>
                                <span style='font-size:1rem; font-weight:700; color:#1a1a1a;'>
                                    {meta['icon']} {row['name']}
                                    {'&nbsp;🏷️' if row['is_custom'] else ''}
                                </span>
                                {'<span style="font-size:0.75rem; font-weight:700; color:#D32F2F; margin-left:8px;">⚠ OVERDUE</span>' if is_overdue else ''}
                            </div>
                            <span class='status-badge' style='background:{smeta["color"]}22; color:{smeta["color"]};'>
                                {smeta["icon"]} {row['status']}
                            </span>
                        </div>
                        <div style='font-size:0.78rem; color:#555; margin-top:3px;'>
                            <b>{row['activity_date'].strftime('%d %b %Y')}</b> &nbsp;·&nbsp; DAS {row['das']}
                            &nbsp;·&nbsp; <span style='color:{meta["color"]}; font-weight:600;'>{meta['label']}</span>
                        </div>
                        {f"<div style='font-size:0.82rem; color:#444; margin-top:5px;'>{row['remarks']}</div>" if row['remarks'] else ""}
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Product hint panel for fertilizer/spray
                if hint and row["category"] in ("FERTILIZER", "SPRAY"):
                    with st.expander(f"📦 Product & Dosage — {hint['mix'].split('(')[0].strip()}", expanded=False):
                        st.markdown(
                            f"""<div class='hint-box' style='background:{meta["bg"]}; border:1px solid {meta["color"]}33;'>
                                <div class='hint-row'><span class='hint-label'>Mix</span> <span><b>{hint['mix']}</b></span></div>
                                <div class='hint-row'><span class='hint-label'>Dose</span> <span>{hint['dose']}</span></div>
                                <div class='hint-row'><span class='hint-label'>Note</span> <span style='color:#444;'>{hint['note']}</span></div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                # Action buttons
                col_manage, col_space = st.columns([1, 3])
                with col_manage.popover("⚙ Manage", use_container_width=True):
                    with st.form(f"manage_{row['id']}"):
                        new_date = st.date_input("Date", value=row["activity_date"], key=f"date_{row['id']}")
                        new_remarks = st.text_area("Remarks", value=row["remarks"], key=f"rmk_{row['id']}", height=70)
                        sc, cc, skc = st.columns(3)
                        save     = sc.form_submit_button("💾 Save")
                        complete = cc.form_submit_button("✅ Done")
                        skip     = skc.form_submit_button("⏭ Skip")

                        if save or complete or skip:
                            _err = None
                            with session_scope() as session:
                                activity = schedule_repo.get_activity(session, row["id"])
                                if activity is None:
                                    _err = "Activity not found."
                                else:
                                    schedule_repo.update_activity(session, activity, activity_date=new_date, remarks=new_remarks or None)
                                    if complete:
                                        schedule_repo.mark_complete(session, activity)
                                    elif skip:
                                        schedule_repo.mark_skipped(session, activity)
                            if _err:
                                st.error(_err)
                            else:
                                st.rerun()

                    if row["status"] != "PENDING":
                        if st.button("↩ Reopen", key=f"reopen_{row['id']}"):
                            with session_scope() as session:
                                activity = schedule_repo.get_activity(session, row["id"])
                                schedule_repo.reopen(session, activity)
                            st.rerun()

                    if row["is_custom"]:
                        if st.button("🗑 Delete", key=f"delete_{row['id']}"):
                            with session_scope() as session:
                                activity = schedule_repo.get_activity(session, row["id"])
                                schedule_repo.delete_activity(session, activity)
                            st.rerun()

                st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)


# ── Render each tab ──────────────────────────────────────────────────────────
for i, tab in enumerate(tabs):
    with tab:
        # Status sub-filter (compact, inside each tab)
        sf = st.radio(
            "Show",
            ["All", "Pending", "Completed", "Skipped"],
            horizontal=True,
            key=f"sf_{i}",
            label_visibility="collapsed",
        )
        status_val = {"All": "All", "Pending": "PENDING", "Completed": "COMPLETED", "Skipped": "SKIPPED"}[sf]

        if i == 0:
            render_activities(activities_data, status_val)
        else:
            cat = ALL_CATS[i]
            filtered = [a for a in activities_data if a["category"] == cat]
            render_activities(filtered, status_val)

# ── Add custom activity ──────────────────────────────────────────────────────
st.divider()
with st.expander("➕ Add Custom Activity", expanded=False):
    with st.form("add_custom_activity", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        activity_name = c1.text_input("Activity Name *", placeholder="e.g. Soil Testing")
        category = c2.selectbox(
            "Category *",
            [c.value for c in ActivityCategory],
            format_func=lambda v: f"{CATEGORY_META[v]['icon']} {CATEGORY_META[v]['label']}",
        )
        activity_date = c3.date_input("Date *", value=date.today())
        remarks = st.text_input("Remarks / dosage (optional)")
        submitted = st.form_submit_button("Add Activity", type="primary")

    if submitted:
        if not activity_name.strip():
            st.error("Activity name is required.")
        else:
            das = calculate_das(ctx["sowing_date"], as_of=activity_date)
            with session_scope() as session:
                schedule_repo.add_custom_activity(
                    session,
                    season_id=season_id,
                    activity_date=activity_date,
                    das=das,
                    name=activity_name.strip(),
                    category=ActivityCategory(category),
                    remarks=remarks.strip() or None,
                )
            st.rerun()
