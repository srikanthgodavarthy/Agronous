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
from i18n import t
from seed.crop_master_seed import seed_crop_master
from seed.bhendi_physiology_v2 import seed_bhendi_v2
from seed.bhendi_physiology_v3 import seed_bhendi_v3
from seed.toor_dal_v1 import seed_toor_dal_v1

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button(t("Synchronize Crop Master")):
        seed_crop_master()
        st.success(t("Crop Master synchronized successfully."))

with col2:
    if st.button(t("🌿 Apply Bhendi Physiology Engine (v3)")):
        try:
            seed_bhendi_v3()
            st.success(t("Bhendi v3 physiology engine applied. New seasons will use the updated schedule."))
        except Exception as e:
            st.error(t("Failed: {error}", error=e))

with col3:
    if st.button(t("🌱 Apply Toor Dal Full Schedule (v1)")):
        try:
            seed_toor_dal_v1()
            st.success(
                t(
                    "Toor Dal full schedule (v1) applied. New seasons will use the "
                    "updated 12-stage/60-activity template; existing seasons keep "
                    "the version they were created against -- recreate the season "
                    "to pick up the new schedule."
                )
            )
        except Exception as e:
            st.error(t("Failed: {error}", error=e))

st.divider()

with st.expander(t("⚠️ Danger Zone")):
    st.warning(t("This will permanently delete **all farms, seasons, schedules, expenses, revenue, and observations**. This cannot be undone."))
    confirm = st.text_input(t("Type DELETE to confirm"), key="delete_confirm")
    if st.button(t("🗑️ Delete All Farms & Seasons"), type="primary", disabled=confirm != "DELETE"):
        try:
            from db.base import session_scope
            from db.models import Farm
            with session_scope() as session:
                deleted = session.query(Farm).delete(synchronize_session=False)
            st.success(t("Deleted {n} farm(s) and all associated data.", n=deleted))
        except Exception as e:
            st.error(t("Failed: {error}", error=e))

ctx = require_active_season()
dashboard_view.render(ctx)
