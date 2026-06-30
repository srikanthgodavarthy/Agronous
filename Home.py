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

st.divider()

with st.expander("⚠️ Danger Zone"):
    st.warning("This will permanently delete **all farms, seasons, schedules, expenses, revenue, and observations**. This cannot be undone.")
    confirm = st.text_input("Type DELETE to confirm", key="delete_confirm")
    if st.button("🗑️ Delete All Farms & Seasons", type="primary", disabled=confirm != "DELETE"):
        try:
            from db.base import session_scope
            from db.models import Farm
            with session_scope() as session:
                deleted = session.query(Farm).delete(synchronize_session=False)
            st.success(f"Deleted {deleted} farm(s) and all associated data.")
        except Exception as e:
            st.error(f"Failed: {e}")

ctx = require_active_season()
dashboard_view.render(ctx)
