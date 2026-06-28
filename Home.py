"""
Cultivation - Farm Cultivation Management
Single-user entry point: no login, goes straight to the dashboard.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Cultivation",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app import dashboard_view
from app.ui_helpers import require_active_season

ctx = require_active_season()
dashboard_view.render(ctx)
