"""
Cultivation Schedule — category tabs, week grouping, product hint expanders.
Cards use native Streamlit components (no unsafe HTML inside containers).
"""
from __future__ import annotations

from datetime import date, timedelta
from itertools import groupby

import streamlit as st

from app.ui_helpers import require_active_season
from db.base import session_scope
from db.models import ActivityCategory, ActivityStatus
from repositories import schedule_repo
from services.schedule_engine import calculate_das

st.set_page_config(page_title="Cultivation Schedule", page_icon="🌿", layout="wide")

# ── Design tokens ─────────────────────────────────────────────────────────────
CATEGORY_META = {
    "IRRIGATION":       {"icon": "💧", "color": "#1565C0", "label": "Irrigation"},
    "FERTILIZER":       {"icon": "🌱", "color": "#2E7D32", "label": "Fertilizer"},
    "SPRAY":            {"icon": "🧴", "color": "#6A1B9A", "label": "Spray / Pest"},
    "WEEDING":          {"icon": "🌿", "color": "#E65100", "label": "Weeding"},
    "LAND_PREPARATION": {"icon": "🚜", "color": "#4E342E", "label": "Land Prep"},
    "SOWING":           {"icon": "🌰", "color": "#558B2F", "label": "Sowing"},
    "HARVEST":          {"icon": "🌾", "color": "#F9A825", "label": "Harvest"},
    "OTHER":            {"icon": "📋", "color": "#546E7A", "label": "Other"},
}

STATUS_ICON = {"PENDING": "⏳", "COMPLETED": "✅", "SKIPPED": "⏭️"}

PRODUCT_HINTS = {
    "dap":                   {"dose": "40 kg/acre", "combo": "DAP 18:46:0 + MOP 35 kg/acre", "note": "Basal placement in furrows before sowing."},
    "mop":                   {"dose": "35 kg/acre", "combo": "MOP 0:0:60 + DAP 40 kg/acre",  "note": "Mix into soil; apply together with DAP at sowing."},
    "urea":                  {"dose": "30 kg/acre", "combo": "Urea 46% N",                    "note": "Broadcast between rows, irrigate immediately."},
    "can":                   {"dose": "40 kg/acre", "combo": "CAN 25% N (Calcium Ammonium Nitrate)", "note": "Better on alkaline soils; less N volatilisation."},
    "ammonium sulphate":     {"dose": "75 kg/acre (1st) · 30 kg/acre (later)", "combo": "AS 20.6% N — acidifying; good for red soils", "note": "Broadcast, irrigate same day."},
    "boron":                 {"dose": "1 g/L",      "combo": "Borax 1 g/L + Calcium Nitrate 2 g/L",      "note": "Evening spray only. Improves fruit set, reduces flower drop."},
    "zinc":                  {"dose": "0.5 g/L",    "combo": "ZnSO₄ 0.5 g/L + Borax 1 g/L",             "note": "Micronutrient combo for red soils after maize."},
    "mkp":                   {"dose": "3 g/L",      "combo": "MKP 0:52:34 (foliar only)",                "note": "Boosts pod setting and early yield."},
    "npk 19":                {"dose": "5 g/L",      "combo": "NPK 19:19:19 water-soluble (Multi-K)",     "note": "Foliar vigour spray. Safe to tank-mix with most fungicides."},
    "seaweed":               {"dose": "3 ml/L",     "combo": "Seaweed Extract 3 ml/L + MKP 3 g/L",      "note": "Stress tolerance during peak production. Evening spray."},
    "potassium nitrate":     {"dose": "5 g/L",      "combo": "Potassium Nitrate NOP 13:0:45",            "note": "Improves pod size, colour, shelf-life."},
    "spinosad":              {"dose": "0.3 ml/L",   "combo": "Spinosad 45 SC — solo",                    "note": "FSB control. Evening only. PHI: 1 day. Rotate with Emamectin."},
    "emamectin":             {"dose": "0.4 ml/L",   "combo": "Emamectin Benzoate 5 SG — solo",          "note": "Rotate from Spinosad. PHI: 5 days."},
    "imidacloprid":          {"dose": "0.5 ml/L",   "combo": "Imidacloprid 17.8 SL + Neem Oil 3 ml/L", "note": "YVMV vector (whitefly) control. PHI: 7 days."},
    "chlorantraniliprole":   {"dose": "0.3 ml/L",   "combo": "Coragen 18.5 SC — solo or + Thiamethoxam","note": "Shoot & fruit borer. PHI: 1 day."},
    "profenofos":            {"dose": "2 ml/L",     "combo": "Profenofos 50 EC + Cypermethrin 5 EC 1 ml/L","note": "Broad spectrum. PHI: 7 days."},
    "indoxacarb":            {"dose": "0.7 ml/L",   "combo": "Indoxacarb 14.5 SC — solo",               "note": "FSB late season. PHI: 3 days."},
    "abamectin":             {"dose": "0.5 ml/L",   "combo": "Abamectin 1.9 EC + Wettable Sulphur 2 g/L","note": "Red spider mite + powdery mildew. PHI: 3 days."},
    "mancozeb":              {"dose": "2.5 g/L",    "combo": "Mancozeb 75 WP + Carbendazim 0.5 g/L",   "note": "Cercospora leaf spot. Apply at first sign."},
    "wettable sulphur":      {"dose": "3 g/L",      "combo": "Wettable Sulphur 80 WP — solo",           "note": "Powdery mildew. Do NOT spray when temp > 35°C."},
    "neem":                  {"dose": "5 ml/L + Teepol 1 ml/L", "combo": "Neem Oil 5000 ppm + Teepol 1 ml/L", "note": "Broad mite/sucking pests. Evening spray only."},
    "chlorpyrifos":          {"dose": "2–2.5 ml/L", "combo": "Chlorpyrifos 20 EC + Cypermethrin 5 EC 1 ml/L","note": "Cutworm / broad spectrum. PHI: 15 days."},
}

def _get_hint(name: str, remarks: str) -> dict | None:
    text = (name + " " + remarks).lower()
    for kw, hint in PRODUCT_HINTS.items():
        if kw in text:
            return hint
    return None

def _week_label(sowing_date: date, activity_date: date) -> str:
    das = (activity_date - sowing_date).days
    week = max(1, (das // 7) + 1)
    ws = sowing_date + timedelta(days=(week - 1) * 7)
    we = ws + timedelta(days=6)
    return f"Week {week}  ·  {ws.strftime('%d %b')} – {we.strftime('%d %b')}"

def _week_num(activity_date: date, sowing_date: date) -> int:
    return max(1, ((activity_date - sowing_date).days // 7) + 1)


# ── Page header ───────────────────────────────────────────────────────────────
ctx = require_active_season()
season_id   = ctx["season_id"]
sowing_date = ctx["sowing_date"]
today       = date.today()

st.title("🌿 Cultivation Schedule")
st.caption(
    f"{ctx['farm_name']} · {ctx['crop_name']}"
    + (f" ({ctx['variety']})" if ctx["variety"] else "")
)

# ── Load all activities once ──────────────────────────────────────────────────
with session_scope() as session:
    raw = schedule_repo.list_activities(session, season_id, status=None)
    all_activities = [
        {
            "id":            a.id,
            "activity_date": a.activity_date,
            "das":           a.das,
            "name":          a.name,
            "category":      a.category.value,
            "status":        a.status.value,
            "remarks":       a.remarks or "",
            "is_custom":     a.is_custom,
        }
        for a in raw
    ]


# ── Render one activity card (pure native Streamlit) ──────────────────────────
def render_card(row: dict) -> None:
    meta      = CATEGORY_META.get(row["category"], CATEGORY_META["OTHER"])
    is_overdue = row["status"] == "PENDING" and row["activity_date"] < today
    hint       = _get_hint(row["name"], row["remarks"])

    with st.container(border=True):
        # ── Title row ────────────────────────────────────────────────────────
        left, right = st.columns([5, 1])
        title_parts = [meta["icon"], f"**{row['name']}**"]
        if row["is_custom"]:
            title_parts.append("🏷️")
        if is_overdue:
            title_parts.append("🔴 *overdue*")
        left.markdown(" ".join(title_parts))
        right.markdown(
            f"`{STATUS_ICON.get(row['status'], '')} {row['status']}`"
        )

        # ── Meta line ────────────────────────────────────────────────────────
        date_str = row["activity_date"].strftime("%d %b %Y")
        st.caption(
            f"📅 {date_str}  ·  DAS {row['das']}  ·  "
            f":{('blue' if row['category']=='IRRIGATION' else 'green' if row['category'] in ('FERTILIZER','SOWING') else 'violet' if row['category']=='SPRAY' else 'orange' if row['category'] in ('WEEDING','HARVEST') else 'gray')}[{meta['label']}]"
        )

        # ── Remarks ──────────────────────────────────────────────────────────
        if row["remarks"]:
            st.markdown(f"<small style='color:#555'>{row['remarks']}</small>", unsafe_allow_html=True)

        # ── Product hint expander ─────────────────────────────────────────────
        if hint and row["category"] in ("FERTILIZER", "SPRAY"):
            with st.expander(f"📦 {hint['combo'].split('—')[0].split('+')[0].strip()} — dosage & mix"):
                c1, c2 = st.columns([1, 2])
                c1.markdown("**Mix / Product**")
                c2.markdown(hint["combo"])
                c1.markdown("**Dose**")
                c2.markdown(hint["dose"])
                c1.markdown("**Field note**")
                c2.markdown(hint["note"])

        # ── Manage popover ───────────────────────────────────────────────────
        with st.popover("⚙ Manage"):
            with st.form(f"manage_{row['id']}"):
                new_date    = st.date_input("Date",    value=row["activity_date"], key=f"d_{row['id']}")
                new_remarks = st.text_area("Remarks",  value=row["remarks"],       key=f"r_{row['id']}", height=70)
                sc, cc, skc = st.columns(3)
                save     = sc.form_submit_button("💾 Save")
                complete = cc.form_submit_button("✅ Done")
                skip     = skc.form_submit_button("⏭ Skip")

                if save or complete or skip:
                    _err = None
                    with session_scope() as session:
                        act = schedule_repo.get_activity(session, row["id"])
                        if act is None:
                            _err = "Activity not found."
                        else:
                            schedule_repo.update_activity(session, act, activity_date=new_date, remarks=new_remarks or None)
                            if complete:
                                schedule_repo.mark_complete(session, act)
                            elif skip:
                                schedule_repo.mark_skipped(session, act)
                    if _err:
                        st.error(_err)
                    else:
                        st.rerun()

            if row["status"] != "PENDING":
                if st.button("↩ Reopen", key=f"reopen_{row['id']}"):
                    with session_scope() as session:
                        act = schedule_repo.get_activity(session, row["id"])
                        schedule_repo.reopen(session, act)
                    st.rerun()

            if row["is_custom"]:
                if st.button("🗑 Delete", key=f"delete_{row['id']}"):
                    with session_scope() as session:
                        act = schedule_repo.get_activity(session, row["id"])
                        schedule_repo.delete_activity(session, act)
                    st.rerun()


# ── Render a filtered + week-grouped list ────────────────────────────────────
def render_list(activities: list[dict], status_val: str) -> None:
    filtered = activities if status_val == "All" else [a for a in activities if a["status"] == status_val]
    if not filtered:
        st.info("No activities match this filter.")
        return

    sorted_acts = sorted(filtered, key=lambda a: a["activity_date"])
    for week_num, group in groupby(sorted_acts, key=lambda a: _week_num(a["activity_date"], sowing_date)):
        items = list(group)
        wlabel = _week_label(sowing_date, items[0]["activity_date"])
        st.markdown(
            f"<div style='display:inline-block; font-size:0.72rem; font-weight:700; "
            f"letter-spacing:0.07em; padding:3px 12px; border-radius:20px; "
            f"background:#F0F4F0; color:#2E7D32; margin:10px 0 6px 0;'>📅 {wlabel}</div>",
            unsafe_allow_html=True,
        )
        for row in items:
            render_card(row)


# ── Category tabs ─────────────────────────────────────────────────────────────
ALL_CATS   = [c.value for c in ActivityCategory]
TAB_LABELS = ["🗓 All"] + [f"{CATEGORY_META[c]['icon']} {CATEGORY_META[c]['label']}" for c in ALL_CATS]

tabs = st.tabs(TAB_LABELS)

for i, tab in enumerate(tabs):
    with tab:
        sf = st.radio(
            "Show",
            ["All", "Pending", "Completed", "Skipped"],
            horizontal=True,
            key=f"sf_{i}",
            label_visibility="collapsed",
        )
        sv = {"All": "All", "Pending": "PENDING", "Completed": "COMPLETED", "Skipped": "SKIPPED"}[sf]

        pool = all_activities if i == 0 else [a for a in all_activities if a["category"] == ALL_CATS[i - 1]]
        render_list(pool, sv)


# ── Add custom activity ───────────────────────────────────────────────────────
st.divider()
with st.expander("➕ Add Custom Activity"):
    with st.form("add_custom", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        act_name     = c1.text_input("Name *", placeholder="e.g. Soil Testing")
        cat_val      = c2.selectbox(
            "Category *",
            ALL_CATS,
            format_func=lambda v: f"{CATEGORY_META[v]['icon']} {CATEGORY_META[v]['label']}",
        )
        act_date     = c3.date_input("Date *", value=date.today())
        act_remarks  = st.text_input("Remarks / dosage (optional)")
        sub          = st.form_submit_button("Add Activity", type="primary")

    if sub:
        if not act_name.strip():
            st.error("Activity name is required.")
        else:
            das = calculate_das(ctx["sowing_date"], as_of=act_date)
            with session_scope() as session:
                schedule_repo.add_custom_activity(
                    session,
                    season_id=season_id,
                    activity_date=act_date,
                    das=das,
                    name=act_name.strip(),
                    category=ActivityCategory(cat_val),
                    remarks=act_remarks.strip() or None,
                )
            st.rerun()
