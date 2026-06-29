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
from seed.crop_master_seed import seed_crop_master

if st.button("Synchronize Crop Master"):
    seed_crop_master()
    st.success("Crop Master synchronized successfully.")

ctx = require_active_season()
dashboard_view.render(ctx)
