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
    # Okra (Bhindi) specific
    "basal + 1st top":       {"dose": "50 + 20 kg/acre", "combo": "DAP 18:46:0 + MOP 0:0:60",   "note": "Apply basal at sowing; band-place near root zone."},
    "2nd top dressing":      {"dose": "25 + 15 kg/acre", "combo": "Urea 46% N + MOP 0:0:60",    "note": "Split N+K dose ahead of flowering."},
    "sucking pest":          {"dose": "0.5 g/L",         "combo": "Acetamiprid 20 SP",          "note": "Aphid/jassid/whitefly control. PHI: 5 days."},
    "fruit borer / shoot borer": {"dose": "0.4 ml/L",    "combo": "Emamectin Benzoate 5 SG",    "note": "Targets fruit & shoot borer at flowering. PHI: 5 days."},
    "yellow vein mosaic":    {"dose": "0.3 ml/L",        "combo": "Spinosad 45 SC",             "note": "Whitefly/YVMV vector control. Evening only. PHI: 1 day."},
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
.act-product {
    font-size: 10px; font-weight: 600; color: #5a4a8a;
    background: rgba(130,60,180,0.08); border: 0.5px solid rgba(130,60,180,0.18);
    border-radius: 6px; padding: 3px 6px; text-align: center; line-height: 1.4;
    width: 100%; box-sizing: border-box;
}
.act-product .dose { font-weight: 400; color: #6a5a98; }
.act-spacer { flex: 1; }
.act-btns { display: flex; gap: 8px; justify-content: center; }
.act-btn {
    width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; background: white; font-size: 12px;
    text-decoration: none;
}
.btn-done { border-color: #4caf7d; color: #4caf7d; }
.btn-skip { border-color: #aaa9a2; color: #aaa9a2; }
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

            # Build portrait cards HTML
            cards_html = "<div class='cards-row'>"
            for row in items:
                eff_status = _effective_status(row, today)
                card_style = STATUS_CARD_STYLE.get(eff_status, STATUS_CARD_STYLE["PENDING"])
                meta        = CATEGORY_META.get(row["category"], CATEGORY_META["OTHER"])
                date_str    = row["activity_date"].strftime("%d %b")
                hint        = _get_hint(row["name"], row["remarks"])

                product_block = ""
                if hint and row["category"] in ("FERTILIZER", "SPRAY"):
                    product_block = f"<div class='act-product'>{hint['combo']}<br><span class='dose'>{hint['dose']}</span></div>"

                # Joined with no newlines between parts -- a bare indented blank
                # line inside an unsafe_allow_html block gets treated by the
                # markdown parser as an indented code block, which silently
                # breaks rendering for every card after it. Concatenating
                # strings directly (vs. an f-string with embedded line breaks)
                # avoids that trap entirely.
                card_parts = [
                    f"<div class='act-card' style='{card_style}'>",
                    f"<div class='act-icon' style='background:{meta['bg']}'>{meta['icon']}</div>",
                    f"<div class='act-name'>{row['name']}</div>",
                    f"<div class='act-meta'>{date_str}<br>DAS {row['das']}<br>{meta['label']}</div>",
                    product_block,
                    "<div class='act-spacer'></div>",
                    "<div class='act-btns'>",
                    "<span class='act-btn btn-done' title='Mark done'>✓</span>",
                    "<span class='act-btn btn-skip' title='Skip'>⏭</span>",
                    "</div>",
                    "</div>",
                ]
                cards_html += "".join(card_parts)
            cards_html += "</div>"
            st.markdown(cards_html, unsafe_allow_html=True)

            # Native Streamlit action forms for each card (hidden under expander)
            for row in items:
                eff_status = _effective_status(row, today)
                hint = _get_hint(row["name"], row["remarks"])
                with st.expander(f"⚙ {row['name']}", expanded=False):
                    with st.form(f"manage_{tab_idx}_{row['id']}"):
                        new_date    = st.date_input("Completion date", value=row["activity_date"], key=f"d_{tab_idx}_{row['id']}")
                        new_remarks = st.text_area("Remarks", value=row["remarks"], key=f"r_{tab_idx}_{row['id']}", height=60)
                        sc, cc, skc = st.columns(3)
                        save     = sc.form_submit_button("💾 Save")
                        complete = cc.form_submit_button("✅ Done")
                        skip     = skc.form_submit_button("⏭ Skip")

                        if save or complete or skip:
                            with session_scope() as session:
                                act = schedule_repo.get_activity(session, row["id"])
                                if act:
                                    schedule_repo.update_activity(session, act, activity_date=new_date, remarks=new_remarks or None)
                                    if complete:
                                        schedule_repo.mark_complete(session, act)
                                    elif skip:
                                        schedule_repo.mark_skipped(session, act)
                            st.rerun()

                    if row["status"] != "PENDING":
                        if st.button("↩ Reopen", key=f"reopen_{tab_idx}_{row['id']}"):
                            with session_scope() as session:
                                act = schedule_repo.get_activity(session, row["id"])
                                schedule_repo.reopen(session, act)
                            st.rerun()

                    if row["is_custom"]:
                        if st.button("🗑 Delete", key=f"delete_{tab_idx}_{row['id']}"):
                            with session_scope() as session:
                                act = schedule_repo.get_activity(session, row["id"])
                                schedule_repo.delete_activity(session, act)
                            st.rerun()

                    if hint and row["category"] in ("FERTILIZER", "SPRAY"):
                        st.caption(f"📦 {hint['combo']} · {hint['dose']} · {hint['note']}")

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
