"""
Weekly Alerts: a focused view of everything overdue, due soon, or upcoming,
colour-coded by priority. Purely a presentation layer over alert_engine --
no alert logic lives here.
"""
from __future__ import annotations

import streamlit as st

from app.ui_helpers import ALERT_GREEN, ALERT_RED, ALERT_YELLOW, require_active_season
from db.base import session_scope
from db.models import Season
from services.alert_engine import refresh_alerts_for_season

st.set_page_config(page_title="Weekly Alerts - Cultivation", page_icon="🔔", layout="wide")

ctx = require_active_season()
season_id = ctx["season_id"]

st.title("🔔 Weekly Alerts")
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

with session_scope() as session:
    season_obj = session.get(Season, season_id)
    alerts = refresh_alerts_for_season(session, season_obj)
    alerts_data = [(a.priority.value, a.message, a.created_at) for a in alerts]

red = [a for a in alerts_data if a[0] == "RED"]
yellow = [a for a in alerts_data if a[0] == "YELLOW"]
green = [a for a in alerts_data if a[0] == "GREEN"]

c1, c2, c3 = st.columns(3)
c1.metric("🔴 Overdue", len(red))
c2.metric("🟡 Due Soon", len(yellow))
c3.metric("🟢 Upcoming", len(green))

st.divider()


def render_group(title: str, color: str, items: list[tuple[str, str, object]]) -> None:
    st.subheader(title)
    if not items:
        st.caption("Nothing here. ✨")
        return
    for _, message, _ in items:
        st.markdown(
            f"<div style='padding:10px 14px; border-radius:8px; background:{color}1A; "
            f"border-left:5px solid {color}; margin-bottom:8px; font-size:0.95rem;'>{message}</div>",
            unsafe_allow_html=True,
        )


render_group("🔴 Overdue", ALERT_RED, red)
render_group("🟡 Due Soon (next 3 days)", ALERT_YELLOW, yellow)
render_group("🟢 Upcoming (next 7 days)", ALERT_GREEN, green)

if not alerts_data:
    st.success("You're all caught up! No alerts at this time. ✅")
