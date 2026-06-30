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
from seed.bhendi_physiology_v2 import seed_bhendi_v2

col1, col2 = st.columns([1, 1])

with col1:
    if st.button("Synchronize Crop Master"):
        seed_crop_master()
        st.success("Crop Master synchronized successfully.")

with col2:
    if st.button("🌿 Apply Bhendi Physiology Engine (v2)"):
        try:
            seed_bhendi_v2()
            st.success("Bhendi v2 physiology engine applied. New seasons will use the updated schedule.")
        except Exception as e:
            st.error(f"Failed: {e}")

ctx = require_active_season()
dashboard_view.render(ctx)
