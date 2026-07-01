"""
Cultivation Schedule — week sections scrolling vertically, portrait cards side by side.
"""
from __future__ import annotations

from collections import Counter
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
    "IRRIGATION":       {"icon": "💧", "accent": "#2E78B7", "soft": "#E4F0FA", "tint": "#F2F8FD", "label": "Irrigation"},
    "FERTILIZER":       {"icon": "🌱", "accent": "#2F8F4E", "soft": "#DEF2E5", "tint": "#F1FAF4", "label": "Fertilizer"},
    "SPRAY":            {"icon": "🧴", "accent": "#9B3FB5", "soft": "#F1E1F7", "tint": "#FAF2FC", "label": "Spray / Pest"},
    "WEEDING":          {"icon": "🧹", "accent": "#C2700E", "soft": "#F8E7CC", "tint": "#FCF4E7", "label": "Weeding"},
    "LAND_PREPARATION": {"icon": "🚜", "accent": "#8A5A2B", "soft": "#EFE0CE", "tint": "#F8F1E7", "label": "Land Prep"},
    "SOWING":           {"icon": "🌰", "accent": "#3E8E4F", "soft": "#E0F2E3", "tint": "#F2FAF3", "label": "Sowing"},
    "HARVEST":          {"icon": "🧺", "accent": "#B68A0E", "soft": "#F7EAC4", "tint": "#FCF6E3", "label": "Harvest"},
    "OTHER":            {"icon": "📋", "accent": "#5B6470", "soft": "#E6E8EB", "tint": "#F4F5F6", "label": "Other"},
}

# Categories where the top-left face icon is now redundant, since the
# category watermark already shows in the middle "blank badge" slot for
# every card in this category (they never carry a product/dose badge).
ICON_REDUNDANT_CATS = {"IRRIGATION", "WEEDING", "LAND_PREPARATION", "SOWING", "HARVEST"}

# Same palette as the card's outer-shell status colors (defined in CSS as
# :has(.card-status-X) rules below) -- reused here in Python because the
# detail drawer is a plain st.markdown block outside the border-wrapper,
# so it needs its own inline background rather than a CSS selector.
STATUS_DRAWER_FILL = {
    "PENDING":   "#FBEECB",
    "COMPLETED": "#D9F0E1",
    "SKIPPED":   "#E7E4DA",
    "OVERDUE":   "#F9D8D0",
}

# Cards that need an urgent, can't-miss "what to apply" badge on the face —
# this is the #1 thing a farmer needs to act on without tapping in.
ACTIONABLE_CATS = {"SPRAY", "FERTILIZER"}

# Status now fills the WHOLE outer card shell — the rounded box that holds
# the card content *and* the ✓ / ⏭ / ⓘ button row underneath — not just the
# inner content area. This is done in CSS below via :has(.card-status-X) on
# the Streamlit border-wrapper itself, so the color sits behind everything
# including the action icons. Category color-coding still lives in the icon
# chip, the category-tag label, and (for non-actionable cards) the watermark
# icon slot where the spray/fertilizer badge would otherwise sit.

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


# Some seed/remarks data fills a field with a literal "no answer" placeholder
# instead of leaving it blank -- e.g. a Field Scouting activity mistakenly
# tagged Product: "Field Scouting." / Dose: "Not applicable." These must
# never be treated as a real product/dose (they'd badge a monitoring
# activity as "SPRAY · APPLY NOW" with nonsense contents). Any field value
# that reduces to one of these tokens is treated as empty everywhere.
_NON_ANSWER_TOKENS = {
    "not applicable", "na", "n/a", "n.a.", "none", "nil", "-", "--", "tbd", "n/a.",
}


def _clean_value(value: str) -> str:
    if not value:
        return ""
    stripped = value.strip().rstrip(".").strip().lower()
    if stripped in _NON_ANSWER_TOKENS:
        return ""
    return value.strip()


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


# Pest/insect (or disease) icon shown top-left on SPRAY cards, in place of
# the generic 🧴 bottle -- matched against the activity name only, same
# false-positive rationale as PRODUCT_HINTS above (remarks prose can mention
# a pest without a spray targeting it). Checked in order; first match wins.
PEST_ICON_HINTS = [
    ("whitefly",       "🪰"),
    ("aphid",          "🪲"),
    ("mite",           "🕷️"),
    ("fsb",            "🐛"),
    ("borer",          "🐛"),
    ("cutworm",        "🐛"),
    ("caterpillar",    "🐛"),
    ("mildew",         "🍄"),
    ("cercospora",     "🍄"),
    ("leaf spot",      "🍄"),
    ("yvmv",           "🦠"),
]
PEST_ICON_DEFAULT = "🐞"  # generic fallback for broad-spectrum / unmatched sprays


def _pest_icon(name: str, remarks: str) -> str:
    text = (name + " " + remarks).lower()
    # Scouting/monitoring activities aren't applications -- give them a
    # distinct magnifying-glass icon regardless of which pest they're
    # checking for, so they never look identical to a real spray card.
    if any(kw in text for kw in ("inspection", "scouting", "monitor")):
        return "🔍"
    for kw, icon in PEST_ICON_HINTS:
        if kw in text:
            return icon
    return PEST_ICON_DEFAULT


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

/* ── Equal-height cards: cascade flex-stretch through ALL Streamlit wrappers ──
   Chain: stHorizontalBlock → column → stVerticalBlock → stVerticalBlock>div
          → stVerticalBlockBorderWrapper → its stVerticalBlock
          → stMarkdownContainer (wraps st.markdown(card_html)) → .act-card
   Every level must be display:flex + flex-direction:column + flex:1 or the
   stretch breaks at that level. stMarkdownContainer was the missing link. */
div[data-testid="stHorizontalBlock"] {
    align-items: stretch !important;
    gap: 12px !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    display: flex !important; flex-direction: column !important; min-height: 0;
}
div[data-testid="column"] > div[data-testid="stVerticalBlock"],
div[data-testid="column"] > div[data-testid="stVerticalBlock"] > div,
div[data-testid="column"] > div[data-testid="stVerticalBlock"] > div > div {
    flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    flex: 1 1 auto !important; display: flex !important;
    flex-direction: column !important; min-height: 0 !important;
    border-radius: 14px !important;
}
/* ── Status fill on the OUTER card shell ──────────────────────────────────
   Each card embeds an invisible marker class (.card-status-PENDING etc.)
   inside its markdown content. :has() lets us reach up from that marker to
   color the actual Streamlit border-wrapper div — the box that contains
   both the card content AND the ✓ / ⏭ / ⓘ button row — so the status color
   spans the entire card, buttons included, not just the inner content area. */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-status-PENDING) {
    background: #FBEECB !important;
    border: 1.5px solid rgba(150,107,12,0.35) !important;
    box-shadow: 0 1px 3px rgba(30,25,15,0.05), 0 4px 16px rgba(30,25,15,0.06) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-status-COMPLETED) {
    background: #D9F0E1 !important;
    border: 1.5px solid rgba(31,122,65,0.45) !important;
    box-shadow: 0 1px 3px rgba(30,25,15,0.05), 0 4px 16px rgba(30,25,15,0.06) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-status-SKIPPED) {
    background: #E7E4DA !important;
    border: 1.5px solid rgba(30,25,15,0.2) !important;
    opacity: 0.75 !important;
    box-shadow: 0 1px 3px rgba(30,25,15,0.05) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-status-OVERDUE) {
    background: #F9D8D0 !important;
    border: 1.5px solid #D8503A !important;
    box-shadow: 0 1px 3px rgba(216,80,58,0.15), 0 4px 16px rgba(216,80,58,0.12) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
    flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
}
/* stMarkdownContainer is the direct parent of .act-card — was missing before */
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stMarkdownContainer"]:first-child {
    flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stMarkdownContainer"]:first-child > div {
    flex: 1 1 auto; display: flex; flex-direction: column;
}
/* Fix: inner Streamlit wrappers ship an opaque theme background that sits
   on top of the status-colored border-wrapper above, hiding the fill.
   Force them transparent so the wrapper's :has() color shows through. */
div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"],
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stMarkdownContainer"] {
    background: transparent !important;
}
/* Hide Streamlit tooltip dot leaking through action badges */
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stTooltipIcon"] {
    display: none !important;
}

/* ── Card shell ────────────────────────────────────────────────────────── */
.act-card {
    border-radius: 12px; padding: 0;
    display: flex; flex-direction: column;
    flex: 1 1 auto;
    min-height: 300px; /* solid floor — cards with no badge still look full */
    background: transparent; /* status color now comes from the outer shell */
    box-sizing: border-box;
}
/* Invisible marker read by the :has() rules above — carries no visual style
   of its own. */
.card-status-marker { display: none; }
.act-card-top {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 14px 14px 0 14px;
    /* Fixed header height: icon row + 3-line name + 2 meta rows. Pins the
       badge slot below to the same starting Y on every card, independent
       of whether the face icon is present/redundant for this category. */
    min-height: 96px;
}
.act-card-top:has(> .act-icon) { gap: 10px; }
.act-card-top:not(:has(> .act-icon)) { gap: 0; }
.act-icon {
    flex: none; width: 36px; height: 36px; border-radius: 9px; font-size: 17px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 1px 3px rgba(30,25,15,0.08);
}
.act-name {
    font-size: 13px; font-weight: 700; color: #221F18;
    line-height: 1.3; padding-top: 3px;
    min-height: 40.5px; /* exactly 3 lines at this size — keeps the badge/
                           watermark box below starting at the same height
                           on every card, whether the title wraps to 1, 2,
                           or 3 lines */
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
    overflow: hidden;
}
.act-meta {
    font-size: 10.5px; color: #756F60; line-height: 1.5; font-weight: 500;
    text-align: center; /* horizontally align date and category rows so
                            every card's middle badge starts at the same X */
}
.act-cat-tag {
    font-size: 9.5px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase;
}

/* ── The "what to apply" badge — solid accent fill, can't-miss ───────── */
.act-action-badge {
    margin: 10px 14px 0 14px; border-radius: 9px;
    padding: 8px 10px; box-sizing: border-box;
    color: #FFFFFF;
    min-height: 72px; /* matches .act-action-badge-blank so every card's
                          middle slot is the same size regardless of
                          content */
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    text-align: center;
}
.act-action-badge .tag {
    font-size: 8.5px; font-weight: 800; letter-spacing: 0.07em; text-transform: uppercase;
    opacity: 0.85; display: block; margin-bottom: 3px;
}
.act-action-badge .product {
    font-size: 12px; font-weight: 700; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
.act-action-badge .dose {
    font-size: 11px; font-weight: 600; opacity: 0.9; margin-top: 1px;
    display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical;
    overflow: hidden;
}

/* ── Blank slot for non-actionable cards (no spray/fertilizer to apply) —
   watermarks the category icon in the same footprint the badge would
   occupy, so every card in a row keeps the same visual weight. ───────── */
.act-action-badge-blank {
    margin: 10px 14px 0 14px; border-radius: 9px;
    min-height: 72px; box-sizing: border-box;
    border: 1px solid;
    display: flex; align-items: center; justify-content: center;
}
.act-action-badge-blank span {
    font-size: 28px; opacity: 0.62;
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
.status-PENDING   { background: rgba(255,255,255,0.6); color: #966B0C; }
.status-COMPLETED { background: rgba(255,255,255,0.7); color: #1F7A41; }
.status-SKIPPED   { background: rgba(255,255,255,0.6); color: #79766C; }
.status-OVERDUE   { background: #FFFFFF; color: #C13E2A; }

/* ── card-wrapper: card + buttons share the same rounded shell ── */
.card-wrapper {
    border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
}
/* Pin the action-button row (last stHorizontalBlock inside border wrapper)
   to the bottom by giving all earlier content flex:1 */
div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] > div:last-child {
    margin-top: auto;
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
            week_das = items[len(items) // 2]["das"]

            with session_scope() as session:
                week_stage = current_stage_name(session, ctx["crop_template_version_id"], week_das)

            # ── Week Brief counts ────────────────────────────────────────────
            cat_counts: Counter = Counter()
            overdue_count = 0
            for it in items:
                es = _effective_status(it, today)
                if es not in ("COMPLETED", "SKIPPED"):
                    cat_counts[it["category"]] += 1
                if es == "OVERDUE":
                    overdue_count += 1

            chip_order = ["SPRAY", "FERTILIZER", "IRRIGATION", "WEEDING",
                          "LAND_PREPARATION", "SOWING", "HARVEST", "OTHER"]
            chips_parts = []
            for cat in chip_order:
                cnt = cat_counts.get(cat, 0)
                if cnt == 0:
                    continue
                m = CATEGORY_META[cat]
                chips_parts.append(
                    "<div style='display:inline-flex;align-items:center;gap:5px;"
                    "background:" + m["soft"] + ";border:1.5px solid " + m["accent"] + "44;"
                    "border-radius:8px;padding:5px 10px;margin:0 4px 4px 0;'>"
                    "<span style='font-size:14px'>" + m["icon"] + "</span>"
                    "<span style='font-size:11px;font-weight:700;color:" + m["accent"] + "'>"
                    + str(cnt) + " " + m["label"] + "</span></div>"
                )

            overdue_html = ""
            if overdue_count:
                overdue_html = (
                    "<div style='display:inline-flex;align-items:center;gap:6px;"
                    "background:#FBE3DF;border:1.5px solid #D8503A66;"
                    "border-radius:8px;padding:5px 12px;margin-left:6px;'>"
                    "<span style='font-size:13px'>⚠️</span>"
                    "<span style='font-size:11px;font-weight:800;color:#C13E2A'>"
                    + str(overdue_count) + " OVERDUE</span></div>"
                )

            total_done  = sum(1 for it in items if it["status"] == "COMPLETED")
            total_items = len(items)
            pct         = int(total_done / total_items * 100) if total_items else 0
            bar_color   = "#1F7A41" if pct == 100 else "#2F5F45"

            stage_html = ""
            if week_stage:
                stage_html = (
                    "<div style='font-size:13px;color:#6B6456;font-weight:500;"
                    "margin-top:4px;'>Stage: <b style='color:#2F5F45'>"
                    + week_stage + "</b></div>"
                )

            no_action_html = ""
            if not chips_parts:
                no_action_html = (
                    "<span style='font-size:11px;color:#9A9485;font-style:italic;'>"
                    "All activities completed this week ✓</span>"
                )

            # Build as flat list — no indented multiline to avoid Markdown
            # treating indented lines as code blocks.
            wb = []
            wb.append("<div style='background:#FFFFFF;border:1.5px solid #D5CCB8;border-radius:14px;padding:16px 20px 14px 20px;margin:20px 0 14px 0;box-shadow:0 2px 8px rgba(30,25,15,0.06);'>")
            wb.append("<div style='display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;'>")
            wb.append("<div>")
            wb.append("<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>")
            wb.append("<div style='background:linear-gradient(135deg,#2F5F45,#21462F);color:#FFFFFF;font-size:11px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;padding:4px 12px;border-radius:6px;box-shadow:0 2px 6px rgba(33,70,47,0.30);'>📅 " + wlabel + "</div>")
            wb.append(overdue_html)
            wb.append("</div>")
            wb.append(stage_html)
            wb.append("</div>")
            wb.append("<div style='text-align:right;min-width:80px;'>")
            wb.append("<div style='font-size:24px;font-weight:800;color:" + bar_color + ";line-height:1;'>" + str(pct) + "%</div>")
            wb.append("<div style='font-size:10px;color:#9A9485;font-weight:600;margin-top:2px;'>" + str(total_done) + "/" + str(total_items) + " done</div>")
            wb.append("</div></div>")
            wb.append("<div style='background:#EDE6D6;border-radius:4px;height:4px;margin:10px 0 12px 0;overflow:hidden;'>")
            wb.append("<div style='width:" + str(pct) + "%;background:" + bar_color + ";height:4px;border-radius:4px;'></div>")
            wb.append("</div>")
            wb.append("<div style='display:flex;flex-wrap:wrap;'>")
            wb.extend(chips_parts)
            wb.append(no_action_html)
            wb.append("</div></div>")
            st.markdown("".join(wb), unsafe_allow_html=True)

            # ── Cards: always 4 columns — consistent ~280px width on any crop ──
            # Using len(row_items) columns would give 600px-wide cards when a
            # week has only 2 activities (e.g. Toor Dal). Fixed 4-col grid keeps
            # card width uniform; unused columns are naturally left empty.
            ROW_SIZE = 4
            for row_start in range(0, len(items), ROW_SIZE):
                row_items = items[row_start : row_start + ROW_SIZE]
                cols = st.columns(4)  # always 4 — spare cols stay empty

                for col, row in zip(cols, row_items):
                    eff_status   = _effective_status(row, today)
                    meta         = CATEGORY_META.get(row["category"], CATEGORY_META["OTHER"])
                    date_str     = row["activity_date"].strftime("%d %b")
                    hint         = _get_hint(row["name"], row["remarks"], row["category"])
                    parsed       = _parse_remarks(row["remarks"])
                    status_label = {"OVERDUE": "Overdue"}.get(eff_status, eff_status.title())
                    acc          = meta["accent"]
                    soft         = meta["soft"]
                    tint         = meta["tint"]

                    product = _clean_value(parsed.get("Product") or (hint["combo"] if hint else ""))
                    dose    = _clean_value(parsed.get("Dose") or (hint["dose"] if hint else ""))
                    if row["category"] in ACTIONABLE_CATS and product and dose:
                        badge_tag = "🧴 SPRAY · APPLY NOW" if row["category"] == "SPRAY" else "🌱 FERTILIZER · APPLY"
                        badge_block = "".join([
                            "<div class='act-action-badge' style='background:{a}; box-shadow:0 2px 8px {a}55;'>".format(a=acc),
                            "<span class='tag'>{}</span>".format(badge_tag),
                            "<div class='product'>{}</div>".format(product) if product else "",
                            "<div class='dose'>{}</div>".format(dose) if dose else "",
                            "</div>",
                        ])
                    else:
                        # No spray/fertilizer to apply — fill the slot with a
                        # faint watermark of the category icon instead of
                        # leaving it empty, so every card in a row keeps the
                        # same visual weight.
                        badge_block = (
                            "<div class='act-action-badge-blank' style='background:{s}; border-color:{a}33;'>"
                            "<span style='color:{a};'>{icon}</span>"
                            "</div>"
                        ).format(s=soft, a=acc, icon=meta["icon"])

                    # Top-left face icon: pest/insect icon for Spray cards
                    # (more useful than the generic bottle), a distinct 🔍 for
                    # scouting/inspection activities so they never look like a
                    # real application, hidden for categories whose watermark
                    # already shows the category icon in the middle slot,
                    # unchanged (category icon) for Fertilizer and Other.
                    if row["category"] == "SPRAY":
                        face_icon  = _pest_icon(row["name"], row["remarks"])
                        icon_block = "<div class='act-icon' style='background:{}'>{}</div>".format(soft, face_icon)
                    elif row["category"] in ICON_REDUNDANT_CATS:
                        icon_block = ""
                    else:
                        icon_block = "<div class='act-icon' style='background:{}'>{}</div>".format(soft, meta["icon"])

                    card_html = "".join([
                        "<div class='act-card'>",
                        "<span class='card-status-marker card-status-{}'></span>".format(eff_status),
                        "<div class='act-card-top'>",
                        icon_block,
                        "<div style='flex:1; min-width:0;'>",
                        "<div class='act-name'>{}</div>".format(row["name"]),
                        "<div class='act-meta'>{} &nbsp;·&nbsp; DAS {}</div>".format(date_str, row["das"]),
                        "<div class='act-meta'><span class='act-cat-tag' style='color:{}'>{}</span></div>".format(acc, meta["label"]),
                        "</div></div>",
                        badge_block,
                        "<div class='act-spacer'></div>",
                        "<div class='act-status-row'><div class='act-status status-{}'>{}</div></div>".format(eff_status, status_label),
                        "</div>",
                    ])

                    with col:
                        with st.container(border=True):
                            st.markdown(card_html, unsafe_allow_html=True)
                            st.markdown(
                                "<hr style='margin:6px 0 4px 0;border:none;border-top:1px solid {}33'>".format(acc),
                                unsafe_allow_html=True,
                            )
                            b1, b2, b3 = st.columns(3)
                            if b1.button("✓", key="done_{}_{}".format(tab_idx, row["id"]), help="Mark complete", use_container_width=True):
                                with session_scope() as session:
                                    act = schedule_repo.get_activity(session, row["id"])
                                    if act:
                                        schedule_repo.mark_complete(session, act)
                                st.rerun()
                            if b2.button("⏭", key="skip_{}_{}".format(tab_idx, row["id"]), help="Skip", use_container_width=True):
                                with session_scope() as session:
                                    act = schedule_repo.get_activity(session, row["id"])
                                    if act:
                                        schedule_repo.mark_skipped(session, act)
                                st.rerun()
                            detail_key = "detail_{}".format(row["id"])
                            if b3.button("ⓘ", key="info_{}_{}".format(tab_idx, row["id"]), help="Details", use_container_width=True):
                                st.session_state[detail_key] = not st.session_state.get(detail_key, False)
                                st.rerun()

                        # ── Detail drawer ────────────────────────────────────
                        if st.session_state.get("detail_{}".format(row["id"])):
                            parsed2     = _parse_remarks(row["remarks"])
                            hint2       = _get_hint(row["name"], row["remarks"], row["category"])
                            product2    = _clean_value(parsed2.get("Product") or (hint2["combo"] if hint2 else ""))
                            composition = _clean_value(parsed2.get("Composition", ""))
                            dose2       = _clean_value(parsed2.get("Dose") or (hint2["dose"] if hint2 else ""))
                            water       = _clean_value(parsed2.get("Water", ""))
                            timing      = _clean_value(parsed2.get("Timing", ""))
                            objective2  = _clean_value(parsed2.get("Objective") or parsed2.get("Benefit", ""))
                            why         = _clean_value(parsed2.get("Why") or parsed2.get("Purpose", ""))
                            precautions = _clean_value(parsed2.get("Precautions") or (hint2["note"] if hint2 else ""))

                            detail_rows = []
                            if product2:
                                detail_rows.append(("🧪", "Product", product2 + (" ({})".format(composition) if composition else ""), acc))
                            if dose2:
                                detail_rows.append(("📦", "Dose", dose2, acc))
                            if water:
                                detail_rows.append(("💧", "Water", water, "#2E78B7"))
                            if timing:
                                detail_rows.append(("⏰", "Timing", timing, "#8A5A2B"))
                            if objective2:
                                detail_rows.append(("🎯", "Objective", objective2, acc))

                            d = ["<div style='border-radius:12px;background:{bg};border:1.5px solid {a}44;padding:14px;margin-top:6px;'>".format(bg=STATUS_DRAWER_FILL.get(eff_status, STATUS_DRAWER_FILL["PENDING"]), a=acc)]
                            d.append("<div style='font-size:10px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:{};margin-bottom:10px;'>{} {} — Details</div>".format(acc, meta["icon"], meta["label"]))
                            for icon, lbl, val, clr in detail_rows:
                                d.append(
                                    "<div style='margin-bottom:8px;'>"
                                    "<div style='font-size:9px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;color:{clr};opacity:0.8;'>{icon} {lbl}</div>"
                                    "<div style='font-size:12px;font-weight:600;color:#221F18;line-height:1.4;margin-top:1px;'>{val}</div>"
                                    "</div>".format(clr=clr, icon=icon, lbl=lbl, val=val)
                                )
                            if why or precautions:
                                d.append("<div style='margin-top:4px;padding-top:10px;border-top:1px solid {}33;'>".format(acc))
                                if why:
                                    d.append("<div style='font-size:9px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;color:{};opacity:0.75;'>💡 Why</div><div style='font-size:11.5px;color:#5E594C;line-height:1.5;margin-top:2px;'>{}</div>".format(acc, why))
                                if precautions:
                                    d.append("<div style='margin-top:8px;font-size:9px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;color:#C13E2A;opacity:0.85;'>⚠️ Precautions</div><div style='font-size:11.5px;color:#5E594C;line-height:1.5;margin-top:2px;'>{}</div>".format(precautions))
                                d.append("</div>")
                            d.append("</div>")
                            st.markdown("".join(d), unsafe_allow_html=True)

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
