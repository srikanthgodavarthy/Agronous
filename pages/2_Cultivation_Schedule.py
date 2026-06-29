"""
Cultivation Schedule — week sections scrolling vertically, portrait cards side by side.
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

STATUS_CARD_STYLE = {
    "PENDING":   "background:#fffbf0; border-color:#f5d98a;",
    "COMPLETED": "background:#f0faf4; border-color:#b6e4cb;",
    "SKIPPED":   "background:#f5f5f4; border-color:#d3d1c7;",
    "OVERDUE":   "background:#fdf2f2; border-color:#f0b4b4;",
}

PRODUCT_HINTS = {
    "dap":                   {"dose": "40 kg/acre", "combo": "DAP 18:46:0 + MOP 35 kg/acre", "note": "Basal placement in furrows before sowing."},
    "mop":                   {"dose": "35 kg/acre", "combo": "MOP 0:0:60 + DAP 40 kg/acre",  "note": "Mix into soil; apply together with DAP at sowing."},
    "urea":                  {"dose": "30 kg/acre", "combo": "Urea 46% N",                    "note": "Broadcast between rows, irrigate immediately."},
    "spinosad":              {"dose": "0.3 ml/L",   "combo": "Spinosad 45 SC",                "note": "FSB control. Evening only. PHI: 1 day."},
    "emamectin":             {"dose": "0.4 ml/L",   "combo": "Emamectin Benzoate 5 SG",       "note": "Rotate from Spinosad. PHI: 5 days."},
    "imidacloprid":          {"dose": "0.5 ml/L",   "combo": "Imidacloprid 17.8 SL",          "note": "YVMV vector control. PHI: 7 days."},
    "mancozeb":              {"dose": "2.5 g/L",    "combo": "Mancozeb 75 WP",                "note": "Cercospora leaf spot. Apply at first sign."},
    "neem":                  {"dose": "5 ml/L",     "combo": "Neem Oil 5000 ppm",             "note": "Broad mite/sucking pests. Evening spray only."},
    # Okra (Bhindi) -- Vikarabad checklist activities, matched by exact
    # activity name. Remarks text is never searched for these (only name),
    # since remarks legitimately describe pests/diseases being scouted for
    # (e.g. "watch for YVMV") without that being a product recommendation.
    "basal dose - dap + potash":   {"dose": "40 + 35 kg/acre", "combo": "DAP 18:46:0 (40 kg/acre) + MOP (35 kg/acre)", "note": "Mix into soil before sowing."},
    "top dressing #1 - ammonium sulphate": {"dose": "75 kg/acre", "combo": "Ammonium Sulphate (AS 20.6% N)", "note": "Broadcast between rows and irrigate immediately."},
    "whitefly / aphid control - imidacloprid": {"dose": "0.5 ml/L", "combo": "Imidacloprid 17.8 SL", "note": "YVMV vector control. If high population."},
    "zinc + boron foliar spray":   {"dose": "0.5 g/L + 1 g/L", "combo": "Zinc Sulphate (ZnSO4) + Borax (Boron)", "note": "Corrects micronutrient deficiency common after maize in red soils."},
    "npk foliar spray":            {"dose": "5 g/L", "combo": "Water Soluble NPK 19:19:19 (Multi-K / Kristalon)", "note": "Vegetative vigour ahead of flowering."},
    "top dressing #2 - can or complex": {"dose": "40 kg/acre", "combo": "CAN 25% N OR Complex Fertilizer 20:20:0", "note": "Broadcast and irrigate."},
    "mite / whitefly control - neem": {"dose": "5 ml/L", "combo": "Neem Oil", "note": "Evening only."},
    "fsb control - spinosad":      {"dose": "0.3 ml/L", "combo": "Spinosad 45 SC", "note": "Evening only. Do not spray 10am-4pm flowering hours."},
    "fruit set spray - boron + calcium": {"dose": "1 g/L + 2 g/L", "combo": "Borax (Boron) + Calcium Nitrate (CaNO3)", "note": "Improves fruit set and reduces flower drop. Spray on leaves and buds."},
    "fsb control (rotation) - emamectin": {"dose": "0.4 ml/L", "combo": "Emamectin Benzoate", "note": "Rotate from Spinosad to avoid resistance build-up."},
    "powdery mildew watch":        {"dose": "3 g/L", "combo": "Wettable Sulphur", "note": "If white powder appears on leaves."},
    "fruiting boost - mkp spray":  {"dose": "3 g/L", "combo": "Mono Potassium Phosphate (MKP 0:52:34)", "note": "Boosts pod setting and early yield."},
    "red spider mite control":     {"dose": "0.5 ml/L or 2 ml/L", "combo": "Abamectin OR Dicofol", "note": "For red spider mite."},
    "cercospora leaf spot control": {"dose": "2.5 g/L", "combo": "Mancozeb", "note": "For Cercospora leaf spot."},
    "top dressing #3 - ammonium sulphate + potash": {"dose": "30 + 20 kg/acre", "combo": "Ammonium Sulphate + MOP", "note": "Extends yield period."},
    "broad spectrum control":      {"dose": "2 ml/L", "combo": "Profenofos", "note": "If multiple pests observed together."},
    "plant stamina - seaweed spray": {"dose": "3 ml/L", "combo": "Seaweed Extract (Seasol / Kelpak / any brand)", "note": "Improves plant stamina and stress tolerance."},
    "fsb control - indoxacarb / chlorpyrifos": {"dose": "0.7 ml/L or 2 ml/L", "combo": "Indoxacarb OR Chlorpyrifos", "note": "Continued FSB rotation."},
    "pod quality spray - potassium nitrate": {"dose": "5 g/L", "combo": "Potassium Nitrate (NOP 13:00:45 / SOP)", "note": "Improves pod size, colour, shelf life and market quality."},
}

import re

REMARK_LABELS = ["Purpose", "Benefit", "Timing", "Weather", "Follow-up"]


def _parse_remarks(remarks: str) -> dict[str, str]:
    """
    Split a structured remarks string like
    'Purpose: ... Benefit: ... Timing: ... Weather: ... Follow-up: ...'
    into a dict keyed by label. Falls back gracefully (everything under
    'Notes') for custom/free-text remarks that don't follow this shape.
    """
    if not remarks:
        return {}
    pattern = r"(" + "|".join(REMARK_LABELS) + r"):\s*"
    parts = re.split(pattern, remarks)
    if len(parts) <= 1:
        return {"Notes": remarks.strip()}
    out: dict[str, str] = {}
    # re.split with a capturing group returns [pre, label, text, label, text, ...]
    it = iter(parts[1:])
    for label, text in zip(it, it):
        out[label] = text.strip()
    if parts[0].strip():
        out["Notes"] = parts[0].strip()
    return out


def _quick_line(name: str, remarks: str, category: str | None, hint: dict | None) -> str:
    """
    One short line that belongs ON the card itself -- the dosage/product if
    there is one, otherwise a trimmed Purpose clause, so a farmer never has
    to open Details just to see what to do today.
    """
    if hint:
        return f"{hint['combo']} · {hint['dose']}"
    parsed = _parse_remarks(remarks)
    purpose = parsed.get("Purpose") or parsed.get("Notes") or ""
    if not purpose:
        return ""
    first_clause = purpose.split(".")[0].strip()
    if len(first_clause) > 70:
        first_clause = first_clause[:67].rstrip() + "..."
    return first_clause


def _get_hint(name: str, remarks: str, category: str | None = None) -> dict | None:
    # Product hints only ever apply to actual spray/fertilizer applications.
    # Monitoring, harvest, irrigation and weeding remarks legitimately
    # mention pest/disease names in prose (e.g. "watch for YVMV symptoms")
    # without that being a product recommendation -- searching remarks text
    # for those categories produces misleading false-positive hints.
    if category is not None and category not in ("FERTILIZER", "SPRAY"):
        return None
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

def _effective_status(row: dict, today: date) -> str:
    if row["status"] == "PENDING" and row["activity_date"] < today:
        return "OVERDUE"
    return row["status"]

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.week-pill {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
    color: #185FA5; background: #E6F1FB;
    border: 0.5px solid #B5D4F4;
    padding: 4px 12px; border-radius: 20px; margin: 18px 0 12px 0;
}
.act-card {
    border-radius: 12px; padding: 14px 12px 10px 12px;
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    border: 0.5px solid transparent;
    min-height: 170px; position: relative; box-sizing: border-box;
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
.act-product {
    font-size: 10px; font-weight: 600; color: #5a4a8a;
    background: rgba(130,60,180,0.08); border: 0.5px solid rgba(130,60,180,0.18);
    border-radius: 6px; padding: 3px 6px; text-align: center; line-height: 1.4;
    width: 100%; box-sizing: border-box;
}
.act-product .dose { font-weight: 400; color: #6a5a98; }
.act-quick {
    font-size: 10px; color: #4a4a4a; text-align: center; line-height: 1.4;
    background: rgba(0,0,0,0.035); border-radius: 6px; padding: 3px 6px;
    width: 100%; box-sizing: border-box;
}
.act-status {
    font-size: 9px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
    border-radius: 8px; padding: 2px 8px; margin-top: 2px;
}
.status-PENDING   { background: #fdf0cf; color: #8a6512; }
.status-COMPLETED { background: #d9f0e2; color: #1c6b41; }
.status-SKIPPED   { background: #e6e5e1; color: #6b6a63; }
.status-OVERDUE   { background: #fadcdc; color: #a32f2f; }
.act-spacer { flex: 1; }
/* ── card-wrapper: card + buttons share the same rounded border ── */
.card-wrapper {
    border-radius: 12px; overflow: hidden;
    display: flex; flex-direction: column;
}
/* ── button row inside the card: flush to card bottom ── */
.card-wrapper [data-testid="stHorizontalBlock"] {
    padding: 0 !important; gap: 0 !important;
}
/* Make the Streamlit column containers flush inside the card */
.card-wrapper [data-testid="column"] {
    padding: 0 !important;
}
/* Small compact buttons that sit inside the card */
.card-wrapper button[kind="secondary"] {
    border-radius: 0 !important;
    border-top: 1px solid rgba(0,0,0,0.08) !important;
    border-left: none !important; border-right: none !important; border-bottom: none !important;
    background: transparent !important;
    padding: 4px 0 !important;
    font-size: 13px !important;
    min-height: 32px !important;
    height: 32px !important;
}
.card-wrapper [data-testid="column"]:not(:last-child) button[kind="secondary"] {
    border-right: 1px solid rgba(0,0,0,0.08) !important;
}
</style>
""", unsafe_allow_html=True)

ctx = require_active_season()
season_id   = ctx["season_id"]
sowing_date = ctx["sowing_date"]
today       = date.today()

st.title("🌿 Cultivation Schedule")
st.caption(
    f"{ctx['farm_name']} · {ctx['crop_name']}"
    + (f" ({ctx['variety']})" if ctx["variety"] else "")
)

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

ALL_CATS   = [c.value for c in ActivityCategory]
TAB_LABELS = ["🗓 All"] + [f"{CATEGORY_META[c]['icon']} {CATEGORY_META[c]['label']}" for c in ALL_CATS]

tabs = st.tabs(TAB_LABELS)

for tab_idx, tab in enumerate(tabs):
    with tab:
        sf = st.radio(
            "Show",
            ["All", "Pending", "Completed", "Skipped"],
            horizontal=True,
            key=f"sf_{tab_idx}",
            label_visibility="collapsed",
        )
        sv = {"All": "All", "Pending": "PENDING", "Completed": "COMPLETED", "Skipped": "SKIPPED"}[sf]

        pool = all_activities if tab_idx == 0 else [a for a in all_activities if a["category"] == ALL_CATS[tab_idx - 1]]
        filtered = pool if sv == "All" else [a for a in pool if a["status"] == sv]

        if not filtered:
            st.info("No activities match this filter.")
            continue

        sorted_acts = sorted(filtered, key=lambda a: a["activity_date"])

        for week_num, group in groupby(sorted_acts, key=lambda a: _week_num(a["activity_date"], sowing_date)):
            items = list(group)
            wlabel = _week_label(sowing_date, items[0]["activity_date"])

            st.markdown(f"<div class='week-pill'>📅 {wlabel}</div>", unsafe_allow_html=True)

            # Render each card in its own Streamlit column so the action
            # buttons (✓ / ⏭ / ⓘ) sit inside the same column as the card,
            # visually contained within the card boundary.
            cols = st.columns(min(len(items), 6))
            for col, row in zip(cols, items):
                eff_status   = _effective_status(row, today)
                card_style   = STATUS_CARD_STYLE.get(eff_status, STATUS_CARD_STYLE["PENDING"])
                meta         = CATEGORY_META.get(row["category"], CATEGORY_META["OTHER"])
                date_str     = row["activity_date"].strftime("%d %b")
                hint         = _get_hint(row["name"], row["remarks"], row["category"])
                quick        = _quick_line(row["name"], row["remarks"], row["category"], hint)
                quick_block  = f"<div class='act-quick'>{quick}</div>" if quick else ""
                status_label = {"OVERDUE": "Overdue"}.get(eff_status, eff_status.title())

                card_html = "".join([
                    f"<div class='act-card' style='{card_style}'>",
                    f"<div class='act-icon' style='background:{meta['bg']}'>{meta['icon']}</div>",
                    f"<div class='act-name'>{row['name']}</div>",
                    f"<div class='act-meta'>{date_str} · DAS {row['das']}<br>{meta['label']}</div>",
                    quick_block,
                    "<div class='act-spacer'></div>",
                    f"<div class='act-status status-{eff_status}'>{status_label}</div>",
                    "</div>",
                ])

                with col:
                    # card-wrapper ties the card HTML and the button row
                    # together inside one rounded, bordered container.
                    st.markdown(
                        f"<div class='card-wrapper'>{card_html}",
                        unsafe_allow_html=True,
                    )
                    b1, b2, b3 = st.columns(3)
                    if b1.button("✓", key=f"done_{tab_idx}_{row['id']}", help="Mark complete", use_container_width=True):
                        with session_scope() as session:
                            act = schedule_repo.get_activity(session, row["id"])
                            if act:
                                schedule_repo.mark_complete(session, act)
                        st.rerun()
                    if b2.button("⏭", key=f"skip_{tab_idx}_{row['id']}", help="Skip", use_container_width=True):
                        with session_scope() as session:
                            act = schedule_repo.get_activity(session, row["id"])
                            if act:
                                schedule_repo.mark_skipped(session, act)
                        st.rerun()
                    if b3.button("ⓘ", key=f"info_{tab_idx}_{row['id']}", help="Details", use_container_width=True):
                        st.session_state[f"detail_{row['id']}"] = True
                    st.markdown("</div>", unsafe_allow_html=True)

                    # Details expander shown inline when ⓘ is pressed
                    if st.session_state.get(f"detail_{row['id']}"):
                        parsed = _parse_remarks(row["remarks"])
                        hint   = _get_hint(row["name"], row["remarks"], row["category"])
                        with st.expander("📋 Details", expanded=True):
                            if hint:
                                st.markdown(f"**Product:** {hint['combo']}  \n**Dose:** {hint['dose']}  \n**Note:** {hint['note']}")
                            for label, text in parsed.items():
                                st.markdown(f"**{label}:** {text}")
                            if st.button("Close", key=f"close_{tab_idx}_{row['id']}"):
                                st.session_state[f"detail_{row['id']}"] = False
                                st.rerun()

# ── Add custom activity ────────────────────────────────────────────────────────
st.divider()
with st.expander("➕ Add Custom Activity"):
    with st.form("add_custom", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        act_name    = c1.text_input("Name *", placeholder="e.g. Soil Testing")
        cat_val     = c2.selectbox(
            "Category *", ALL_CATS,
            format_func=lambda v: f"{CATEGORY_META[v]['icon']} {CATEGORY_META[v]['label']}",
        )
        act_date    = c3.date_input("Date *", value=date.today())
        act_remarks = st.text_input("Remarks / dosage (optional)")
        sub         = st.form_submit_button("Add Activity", type="primary")

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
