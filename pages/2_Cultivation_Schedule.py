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
from services.schedule_engine import calculate_das, current_stage_name

st.set_page_config(page_title="Cultivation Schedule", page_icon="🌿", layout="wide")

CATEGORY_META = {
    "IRRIGATION":       {"icon": "💧", "accent": "#2E78B7", "soft": "#EAF3FB", "label": "Irrigation"},
    "FERTILIZER":       {"icon": "🌱", "accent": "#2F8F4E", "soft": "#EAF7EE", "label": "Fertilizer"},
    "SPRAY":            {"icon": "🧴", "accent": "#9B3FB5", "soft": "#F6ECFA", "label": "Spray / Pest"},
    "WEEDING":          {"icon": "🌾", "accent": "#C2700E", "soft": "#FBF1E4", "label": "Weeding"},
    "LAND_PREPARATION": {"icon": "🚜", "accent": "#8A5A2B", "soft": "#F4ECE2", "label": "Land Prep"},
    "SOWING":           {"icon": "🌰", "accent": "#3E8E4F", "soft": "#ECF7EE", "label": "Sowing"},
    "HARVEST":          {"icon": "🌾", "accent": "#B68A0E", "soft": "#FAF4E1", "label": "Harvest"},
    "OTHER":            {"icon": "📋", "accent": "#5B6470", "soft": "#EFF1F3", "label": "Other"},
}

# Cards that need an urgent, can't-miss "what to apply" badge on the face —
# this is the #1 thing a farmer needs to act on without tapping in.
ACTIONABLE_CATS = {"SPRAY", "FERTILIZER"}

STATUS_CARD_STYLE = {
    "PENDING":   "background:#FFFFFF; border-color:#EDE6D6;",
    "COMPLETED": "background:#FBFCFA; border-color:#D8E9DD;",
    "SKIPPED":   "background:#FAFAF9; border-color:#E5E3DD;",
    "OVERDUE":   "background:#FFFBFA; border-color:#F0C4BC;",
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

REMARK_LABELS = ["Priority", "Product", "Composition", "Dose", "Water", "Method", "Timing", "Indicator", "Objective", "Why", "Precautions", "Purpose", "Benefit", "Notes"]


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
    One short line shown on the card face.
    New card format: Product + Dose from structured remarks.
    Falls back to PRODUCT_HINTS, then Purpose clause for legacy/custom activities.
    """
    parsed = _parse_remarks(remarks)
    product  = parsed.get("Product", "")
    dose     = parsed.get("Dose", "")
    if product and dose:
        return f"{product} · {dose}"
    if hint:
        return f"{hint['combo']} · {hint['dose']}"
    purpose = parsed.get("Objective") or parsed.get("Purpose") or parsed.get("Notes") or ""
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }

.stApp { background: #FAF8F4; }

.week-pill {
    display: inline-flex; align-items: center; gap: 7px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: #FFFFFF; background: linear-gradient(135deg, #2F5F45, #21462F);
    padding: 6px 14px; border-radius: 8px; margin: 22px 0 6px 0;
    box-shadow: 0 2px 6px rgba(33,70,47,0.25);
}
.stage-line {
    font-size: 13px; color: #6B6456; margin: 0 0 14px 2px;
    padding-bottom: 10px; border-bottom: 1px solid #EDE6D6;
}
.stage-line b { color: #2F5F45; font-weight: 700; }

/* ── Card shell ─────────────────────────────────────────────────────── */
.act-card {
    border-radius: 14px; padding: 0;
    display: flex; flex-direction: column;
    border: 1px solid transparent;
    min-height: 150px; position: relative; box-sizing: border-box;
    box-shadow: 0 1px 2px rgba(30,25,15,0.04), 0 4px 14px rgba(30,25,15,0.05);
}
.act-card-top {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 14px 14px 0 14px;
}
.act-icon {
    flex: none; width: 36px; height: 36px; border-radius: 9px; font-size: 17px;
    display: flex; align-items: center; justify-content: center;
}
.act-name {
    font-size: 13px; font-weight: 700; color: #221F18;
    line-height: 1.3; padding-top: 3px;
}
.act-meta {
    font-size: 10.5px; color: #9A9485; line-height: 1.5; font-weight: 500;
}
.act-cat-tag {
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
}

/* ── The "what to apply" badge — bold, always visible, top priority ── */
.act-action-badge {
    margin: 10px 14px 0 14px; border-radius: 9px;
    padding: 8px 10px; box-sizing: border-box;
}
.act-action-badge .tag {
    font-size: 8.5px; font-weight: 800; letter-spacing: 0.07em; text-transform: uppercase;
    opacity: 0.85; display: block; margin-bottom: 3px;
}
.act-action-badge .product {
    font-size: 12px; font-weight: 700; line-height: 1.35;
}
.act-action-badge .dose {
    font-size: 11px; font-weight: 600; opacity: 0.85; margin-top: 1px;
}

.act-objective {
    font-size: 10.5px; color: #6B6456; text-align: left; line-height: 1.45;
    padding: 8px 14px 0 14px;
}
.act-objective b {
    display: block; font-size: 9px; letter-spacing: 0.05em; text-transform: uppercase;
    color: #9A9485; margin-bottom: 2px; font-weight: 700;
}
.act-spacer { flex: 1; min-height: 8px; }
.act-status-row { display: flex; justify-content: flex-end; padding: 0 14px 12px 14px; }
.act-status {
    font-size: 9px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase;
    border-radius: 20px; padding: 3px 10px;
    display: inline-flex; align-items: center; gap: 4px;
}
.act-status::before {
    content: ''; width: 5px; height: 5px; border-radius: 50%; background: currentColor;
}
.status-PENDING   { background: #FCF3DD; color: #966B0C; }
.status-COMPLETED { background: #E1F2E6; color: #1F7A41; }
.status-SKIPPED   { background: #EEEDE8; color: #79766C; }
.status-OVERDUE   { background: #FBE3DF; color: #C13E2A; }

/* ── card-wrapper: card + buttons share the same rounded shell ── */
.card-wrapper {
    border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
}
.card-wrapper [data-testid="stHorizontalBlock"] {
    padding: 0 !important; gap: 0 !important;
}
.card-wrapper [data-testid="column"] {
    padding: 0 !important;
}
.card-wrapper button[kind="secondary"] {
    border-radius: 0 !important;
    border-top: 1px solid rgba(30,25,15,0.07) !important;
    border-left: none !important; border-right: none !important; border-bottom: none !important;
    background: transparent !important;
    padding: 6px 0 !important;
    font-size: 13px !important;
    min-height: 34px !important;
    height: 34px !important;
    color: #5B5648 !important;
    transition: background 0.15s ease;
}
.card-wrapper button[kind="secondary"]:hover {
    background: rgba(47,95,69,0.06) !important;
    color: #2F5F45 !important;
}
.card-wrapper [data-testid="column"]:not(:last-child) button[kind="secondary"] {
    border-right: 1px solid rgba(30,25,15,0.07) !important;
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
            week_das = items[len(items) // 2]["das"]  # representative DAS for the week

            with session_scope() as session:
                week_stage = current_stage_name(session, ctx["crop_template_version_id"], week_das)

            st.markdown(f"<div class='week-pill'>📅 {wlabel}</div>", unsafe_allow_html=True)
            if week_stage:
                st.markdown(f"<div class='stage-line'>Current Stage: <b>{week_stage}</b></div>", unsafe_allow_html=True)

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
                parsed       = _parse_remarks(row["remarks"])
                objective    = parsed.get("Objective") or parsed.get("Purpose") or parsed.get("Benefit") or parsed.get("Notes") or ""
                status_label = {"OVERDUE": "Overdue"}.get(eff_status, eff_status.title())

                # ── Action badge: the product + dose, always visible on the
                # card face (not hidden behind the ⓘ button) for spray and
                # fertilizer activities, since that's the one thing a farmer
                # needs to read and act on at a glance.
                product = parsed.get("Product") or (hint["combo"] if hint else "")
                dose    = parsed.get("Dose") or (hint["dose"] if hint else "")
                badge_block = ""
                if row["category"] in ACTIONABLE_CATS and (product or dose):
                    badge_tag = "🧴 SPRAY / APPLY" if row["category"] == "SPRAY" else "🌱 APPLY"
                    badge_block = "".join([
                        f"<div class='act-action-badge' style='background:{meta['soft']}; "
                        f"border:1px solid {meta['accent']}33; color:{meta['accent']};'>",
                        f"<span class='tag'>{badge_tag}</span>",
                        f"<div class='product'>{product}</div>" if product else "",
                        f"<div class='dose'>{dose}</div>" if dose else "",
                        "</div>",
                    ])

                obj_block = (
                    f"<div class='act-objective'><b>Why</b>{objective}</div>"
                    if objective else ""
                )

                card_html = "".join([
                    f"<div class='act-card' style='{card_style}'>",
                    "<div class='act-card-top'>",
                    f"<div class='act-icon' style='background:{meta['soft']}'>{meta['icon']}</div>",
                    "<div>",
                    f"<div class='act-name'>{row['name']}</div>",
                    f"<div class='act-meta'>{date_str} · DAS {row['das']} &nbsp;·&nbsp; "
                    f"<span class='act-cat-tag' style='color:{meta['accent']}'>{meta['label']}</span></div>",
                    "</div>",
                    "</div>",
                    badge_block,
                    obj_block,
                    "<div class='act-spacer'></div>",
                    f"<div class='act-status-row'><div class='act-status status-{eff_status}'>{status_label}</div></div>",
                    "</div>",
                ])

                with col:
                    # st.container(border=True) is Streamlit's native card —
                    # anything rendered inside it, including buttons, is
                    # visually enclosed within the card border.
                    with st.container(border=True):
                        st.markdown(card_html, unsafe_allow_html=True)
                        st.markdown(
                            "<hr style='margin:6px 0 4px 0; border:none; "
                            "border-top:1px solid rgba(0,0,0,0.07)'>",
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
                        detail_key = f"detail_{row['id']}"
                        if b3.button("ⓘ", key=f"info_{tab_idx}_{row['id']}", help="Details", use_container_width=True):
                            st.session_state[detail_key] = not st.session_state.get(detail_key, False)
                            st.rerun()

                    # Details panel — full emoji card shown below when ⓘ tapped.
                    if st.session_state.get(f"detail_{row['id']}"):
                        parsed = _parse_remarks(row["remarks"])
                        hint   = _get_hint(row["name"], row["remarks"], row["category"])

                        # Build display values — prefer new structured fields,
                        # fall back to PRODUCT_HINTS for legacy/custom activities.
                        product     = parsed.get("Product") or (hint["combo"] if hint else "")
                        composition = parsed.get("Composition", "")
                        dose        = parsed.get("Dose") or (hint["dose"] if hint else "")
                        water       = parsed.get("Water", "")
                        timing      = parsed.get("Timing", "")
                        objective   = parsed.get("Objective") or parsed.get("Benefit", "")
                        why         = parsed.get("Why") or parsed.get("Purpose", "")
                        precautions = parsed.get("Precautions") or (hint["note"] if hint else "")

                        with st.container(border=True):
                            lines = []
                            if product:
                                lines.append(f"🧪 **Product**  \n{product}" + (f" ({composition})" if composition else ""))
                            if dose:
                                lines.append(f"📦 **Dose**  \n{dose}")
                            if water:
                                lines.append(f"💧 **Water**  \n{water}")
                            if timing:
                                lines.append(f"⏰ **Timing**  \n{timing}")
                            if objective:
                                lines.append(f"🎯 **Objective**  \n{objective}")
                            st.markdown("  \n\n".join(lines))

                            if why or precautions:
                                with st.expander("📖 View Why"):
                                    if why:
                                        st.markdown(f"**Why this matters:**  \n{why}")
                                    if precautions:
                                        st.markdown(f"**⚠️ Precautions:**  \n{precautions}")

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
