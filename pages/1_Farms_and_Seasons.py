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

from auth.supabase_auth import SINGLE_USER_ID
from db.base import session_scope
from db.models import SeasonStatus
from i18n import t
from repositories import crop_repo, farm_repo, season_repo
from services.schedule_engine import generate_schedule_for_season

st.set_page_config(page_title="Farms & Seasons - Cultivation", page_icon="🌱", layout="wide")


st.title(t("🚜 Farms & Seasons"))

tab_seasons, tab_farms = st.tabs([t("Seasons"), t("Farms")])

# ---------------------------------------------------------------------------
# FARMS TAB
# ---------------------------------------------------------------------------
with tab_farms:
    st.subheader(t("Your Farms"))

    with session_scope() as session:
        farms = farm_repo.list_farms(session, SINGLE_USER_ID)
        farms_data = [(f.id, f.name, f.location, f.total_area, f.area_unit) for f in farms]

    if farms_data:
        for fid, name, location, total_area, area_unit in farms_data:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                c1.markdown(f"**{name}**")
                c2.markdown(location or t("_No location set_"))
                c3.markdown(f"{total_area or '—'} {area_unit}" if total_area else "—")

                confirm_key = f"confirm_delete_farm_{fid}"
                if not st.session_state.get(confirm_key):
                    if c4.button(t("🗑️ Delete"), key=f"delete_farm_{fid}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning(
                        t(
                            "Delete **{name}**? This permanently deletes the farm and ALL its "
                            "seasons (schedules, expenses, revenues, observations, alerts).",
                            name=name,
                        )
                    )
                    cc1, cc2 = st.columns(2)
                    if cc1.button(t("Yes, delete permanently"), key=f"confirm_yes_{fid}", type="primary"):
                        with session_scope() as session:
                            farm_obj = farm_repo.get_farm(session, SINGLE_USER_ID, fid)
                            if farm_obj is not None:
                                farm_repo.delete_farm(session, farm_obj)
                        del st.session_state[confirm_key]
                        st.rerun()
                    if cc2.button(t("Cancel"), key=f"confirm_no_{fid}"):
                        del st.session_state[confirm_key]
                        st.rerun()
    else:
        st.info(t("You haven't added any farms yet. Add your first one below."))

    st.divider()
    st.subheader(t("➕ Add a New Farm"))
    with st.form("add_farm_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        farm_name = c1.text_input(t("Farm Name *"), placeholder=t("e.g. North Field"))
        location = c2.text_input(t("Location"), placeholder=t("e.g. Nalgonda, Telangana"))
        c3, c4 = st.columns(2)
        total_area = c3.number_input(t("Total Area"), min_value=0.0, step=0.5, value=0.0)
        area_unit = c4.selectbox(t("Area Unit"), ["Acres", "Hectares", "Bigha", "Guntha"], format_func=t)
        submitted = st.form_submit_button(t("Add Farm"), type="primary")

        if submitted:
            if not farm_name.strip():
                st.error(t("Farm name is required."))
            else:
                with session_scope() as session:
                    farm_repo.create_farm(
                        session,
                        SINGLE_USER_ID,
                        name=farm_name.strip(),
                        location=location.strip() or None,
                        total_area=total_area or None,
                        area_unit=area_unit,
                    )
                # rerun OUTSIDE session_scope so RerunException doesn't trigger rollback
                st.rerun()

# ---------------------------------------------------------------------------
# SEASONS TAB
# ---------------------------------------------------------------------------
with tab_seasons:
    st.subheader(t("Your Cultivation Seasons"))

    with session_scope() as session:
        farms = farm_repo.list_farms(session, SINGLE_USER_ID)
        seasons = season_repo.list_seasons(session, SINGLE_USER_ID)
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
                c3.markdown(f"🗓️ {t('Sown')} {sowing_date.strftime('%d %b %Y')}")
                c4.markdown(f"{area:.1f} {area_unit}")
                badge = t("🟢 Active") if status == "ACTIVE" else (t("✅ Completed") if status == "COMPLETED" else t("⚪ Abandoned"))
                c5.markdown(badge)

                if status == "ACTIVE":
                    bc1, bc2, bc3 = st.columns(3)
                    if bc1.button(t("Mark Completed"), key=f"complete_{sid}"):
                        with session_scope() as session:
                            season_obj = season_repo.get_season(session, SINGLE_USER_ID, sid)
                            season_repo.update_season_status(session, season_obj, SeasonStatus.COMPLETED)
                        # rerun OUTSIDE session_scope
                        st.rerun()
                    if bc2.button(t("Abandon"), key=f"abandon_{sid}"):
                        with session_scope() as session:
                            season_obj = season_repo.get_season(session, SINGLE_USER_ID, sid)
                            season_repo.update_season_status(session, season_obj, SeasonStatus.ABANDONED)
                        # rerun OUTSIDE session_scope
                        st.rerun()
                    delete_col = bc3
                else:
                    delete_col = st.columns(3)[2]

                confirm_key = f"confirm_delete_season_{sid}"
                if not st.session_state.get(confirm_key):
                    if delete_col.button(t("🗑️ Delete"), key=f"delete_season_{sid}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning(
                        t(
                            "Delete this **{crop_name}** season on **{farm_name}**? This permanently "
                            "deletes its schedule, expenses, revenues, observations, and alerts.",
                            crop_name=crop_name,
                            farm_name=farm_name,
                        )
                    )
                    cc1, cc2 = st.columns(2)
                    if cc1.button(t("Yes, delete permanently"), key=f"confirm_yes_season_{sid}", type="primary"):
                        with session_scope() as session:
                            season_obj = season_repo.get_season(session, SINGLE_USER_ID, sid)
                            if season_obj is not None:
                                season_repo.delete_season(session, season_obj)
                        del st.session_state[confirm_key]
                        st.rerun()
                    if cc2.button(t("Cancel"), key=f"confirm_no_season_{sid}"):
                        del st.session_state[confirm_key]
                        st.rerun()
    else:
        st.info(t("No seasons yet. Start your first cultivation cycle below."))

    st.divider()
    st.subheader(t("➕ Start a New Season"))

    if not farms:
        st.warning(t("Add a Farm first (see the Farms tab) before starting a season."))
    else:
        with session_scope() as session:
            crops = crop_repo.list_active_crops(session)
            crops_data = [(c.id, c.name, c.default_duration_days) for c in crops]

        if not crops_data:
            st.error(
                t(
                    "No Crop Master templates found. An administrator needs to seed crop templates "
                    "(see seed/crop_master_seed.py) before seasons can be created."
                )
            )
        else:
            with st.form("add_season_form"):
                c1, c2 = st.columns(2)
                farm_options = {f.name: f.id for f in farms}
                selected_farm_name = c1.selectbox(t("Farm *"), list(farm_options.keys()))

                crop_options = {f"{name} (~{duration} {t('days')})": (cid, duration) for cid, name, duration in crops_data}
                selected_crop_label = c2.selectbox(t("Crop *"), list(crop_options.keys()))

                c3, c4 = st.columns(2)
                variety = c3.text_input(t("Variety (optional)"), placeholder=t("e.g. IR-64, Bt-Hybrid"))
                sowing_date = c4.date_input(t("Sowing Date *"), value=date.today())

                c5, c6 = st.columns(2)
                area = c5.number_input(t("Area *"), min_value=0.1, step=0.5, value=1.0)
                area_unit = c6.selectbox(t("Area Unit"), ["Acres", "Hectares", "Bigha", "Guntha"], format_func=t)

                notes = st.text_area(t("Notes (optional)"), placeholder=t("Any additional context for this season"))

                submitted = st.form_submit_button(
                    t("Create Season & Generate Schedule"), type="primary", use_container_width=True
                )

            # Handle submission OUTSIDE the form block so st.rerun() is safe
            if submitted:
                farm_id = farm_options[selected_farm_name]
                crop_id, _ = crop_options[selected_crop_label]

                _success_msg = None
                _error_msg = None

                with session_scope() as session:
                    current_version = crop_repo.get_current_version(session, crop_id)
                    if current_version is None:
                        _error_msg = t(
                            "This crop has no current template version configured. "
                            "An administrator needs to set one before seasons can be created for it."
                        )
                    else:
                        season = season_repo.create_season(
                            session,
                            user_id=SINGLE_USER_ID,
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
                        _success_msg = t(
                            "Season created! Generated {n} scheduled activities "
                            "from the {crop} crop template (version {version}).",
                            n=len(activities),
                            crop=selected_crop_label.split(" (")[0],
                            version=current_version.version_number,
                        )

                # st.rerun() / st.error() called AFTER session_scope has closed and committed
                if _error_msg:
                    st.error(_error_msg)
                elif _success_msg:
                    st.success(_success_msg)
                    st.rerun()
