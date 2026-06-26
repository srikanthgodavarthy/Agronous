"""
Farms & Seasons: the only page where the user defines structure (farms) and
starts new cultivation cycles (seasons). Creating a Season is the single
moment the crop-driven engine kicks in -- selecting Crop + Variety + Sowing
Date + Area triggers full schedule generation from the Crop Master Template.
"""
from __future__ import annotations

import uuid
from datetime import date

import streamlit as st

from auth.supabase_auth import require_login
from db.base import session_scope
from db.models import SeasonStatus
from repositories import crop_repo, farm_repo, season_repo
from services.schedule_engine import generate_schedule_for_season

st.set_page_config(page_title="Farms & Seasons - Cultivation", page_icon="🌱", layout="wide")

user = require_login()
st.title("🚜 Farms & Seasons")

tab_seasons, tab_farms = st.tabs(["Seasons", "Farms"])

# ---------------------------------------------------------------------------
# FARMS TAB
# ---------------------------------------------------------------------------
with tab_farms:
    st.subheader("Your Farms")

    with session_scope() as session:
        farms = farm_repo.list_farms(session, uuid.UUID(user.id))
        farms_data = [(f.id, f.name, f.location, f.total_area, f.area_unit) for f in farms]

    if farms_data:
        for fid, name, location, total_area, area_unit in farms_data:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.markdown(f"**{name}**")
                c2.markdown(location or "_No location set_")
                c3.markdown(f"{total_area or '—'} {area_unit}" if total_area else "—")
    else:
        st.info("You haven't added any farms yet. Add your first one below.")

    st.divider()
    st.subheader("➕ Add a New Farm")
    with st.form("add_farm_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        farm_name = c1.text_input("Farm Name *", placeholder="e.g. North Field")
        location = c2.text_input("Location", placeholder="e.g. Nalgonda, Telangana")
        c3, c4 = st.columns(2)
        total_area = c3.number_input("Total Area", min_value=0.0, step=0.5, value=0.0)
        area_unit = c4.selectbox("Area Unit", ["Acres", "Hectares", "Bigha", "Guntha"])
        submitted = st.form_submit_button("Add Farm", type="primary")

        if submitted:
            if not farm_name.strip():
                st.error("Farm name is required.")
            else:
                with session_scope() as session:
                    farm_repo.create_farm(
                        session,
                        uuid.UUID(user.id),
                        name=farm_name.strip(),
                        location=location.strip() or None,
                        total_area=total_area or None,
                        area_unit=area_unit,
                    )
                st.success(f"Farm '{farm_name}' added.")
                st.rerun()

# ---------------------------------------------------------------------------
# SEASONS TAB
# ---------------------------------------------------------------------------
with tab_seasons:
    st.subheader("Your Cultivation Seasons")

    with session_scope() as session:
        farms = farm_repo.list_farms(session, uuid.UUID(user.id))
        seasons = season_repo.list_seasons(session, uuid.UUID(user.id))
        seasons_data = [
            (
                s.id,
                s.farm.name,
                s.crop.name,
                s.variety,
                s.sowing_date,
                float(s.area),
                s.area_unit,
                s.status.value,
            )
            for s in seasons
        ]

    if seasons_data:
        for sid, farm_name, crop_name, variety, sowing_date, area, area_unit, status in seasons_data:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1.3, 1, 1])
                c1.markdown(f"**{crop_name}**" + (f" _{variety}_" if variety else ""))
                c2.markdown(f"📍 {farm_name}")
                c3.markdown(f"🗓️ Sown {sowing_date.strftime('%d %b %Y')}")
                c4.markdown(f"{area:.1f} {area_unit}")
                badge = "🟢 Active" if status == "Active" else ("✅ Completed" if status == "Completed" else "⚪ Abandoned")
                c5.markdown(badge)

                if status == "Active":
                    bc1, bc2 = st.columns(2)
                    if bc1.button("Mark Completed", key=f"complete_{sid}"):
                        with session_scope() as session:
                            season_obj = season_repo.get_season(session, uuid.UUID(user.id), sid)
                            season_repo.update_season_status(session, season_obj, SeasonStatus.COMPLETED)
                        st.success("Season marked as completed.")
                        st.rerun()
                    if bc2.button("Abandon", key=f"abandon_{sid}"):
                        with session_scope() as session:
                            season_obj = season_repo.get_season(session, uuid.UUID(user.id), sid)
                            season_repo.update_season_status(session, season_obj, SeasonStatus.ABANDONED)
                        st.warning("Season marked as abandoned.")
                        st.rerun()
    else:
        st.info("No seasons yet. Start your first cultivation cycle below.")

    st.divider()
    st.subheader("➕ Start a New Season")

    if not farms:
        st.warning("Add a Farm first (see the Farms tab) before starting a season.")
    else:
        with session_scope() as session:
            crops = crop_repo.list_active_crops(session)
            crops_data = [(c.id, c.name, c.default_duration_days) for c in crops]

        if not crops_data:
            st.error(
                "No Crop Master templates found. An administrator needs to seed crop templates "
                "(see seed/crop_master_seed.py) before seasons can be created."
            )
        else:
            with st.form("add_season_form"):
                c1, c2 = st.columns(2)
                farm_options = {f.name: f.id for f in farms}
                selected_farm_name = c1.selectbox("Farm *", list(farm_options.keys()))

                crop_options = {f"{name} (~{duration} days)": (cid, duration) for cid, name, duration in crops_data}
                selected_crop_label = c2.selectbox("Crop *", list(crop_options.keys()))

                c3, c4 = st.columns(2)
                variety = c3.text_input("Variety (optional)", placeholder="e.g. IR-64, Bt-Hybrid")
                sowing_date = c4.date_input("Sowing Date *", value=date.today())

                c5, c6 = st.columns(2)
                area = c5.number_input("Area *", min_value=0.1, step=0.5, value=1.0)
                area_unit = c6.selectbox("Area Unit", ["Acres", "Hectares", "Bigha", "Guntha"])

                notes = st.text_area("Notes (optional)", placeholder="Any additional context for this season")

                submitted = st.form_submit_button(
                    "Create Season & Generate Schedule", type="primary", use_container_width=True
                )

                if submitted:
                    farm_id = farm_options[selected_farm_name]
                    crop_id, _ = crop_options[selected_crop_label]

                    with session_scope() as session:
                        current_version = crop_repo.get_current_version(session, crop_id)
                        if current_version is None:
                            st.error(
                                "This crop has no current template version configured. "
                                "An administrator needs to set one before seasons can be created for it."
                            )
                        else:
                            season = season_repo.create_season(
                                session,
                                user_id=uuid.UUID(user.id),
                                farm_id=farm_id,
                                crop_id=crop_id,
                                crop_template_version_id=current_version.id,
                                sowing_date=sowing_date,
                                area=area,
                                variety=variety.strip() or None,
                                area_unit=area_unit,
                                notes=notes.strip() or None,
                            )
                            activities = generate_schedule_for_season(session, season)
                            st.session_state["active_farm_id"] = farm_id
                            st.session_state["active_season_id"] = season.id

                            st.success(
                                f"Season created! Generated {len(activities)} scheduled activities "
                                f"from the {selected_crop_label.split(' (')[0]} crop template "
                                f"(version {current_version.version_number})."
                            )
                            st.rerun()
