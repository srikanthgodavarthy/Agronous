"""
Shared helpers: currency formatting, sidebar Farm/Season selector, Plotly theming.
Single-user mode: no auth guard, user_id comes from auth.supabase_auth.SINGLE_USER_ID.
"""
from __future__ import annotations

import uuid
from datetime import date

import streamlit as st

from auth.supabase_auth import SINGLE_USER_ID
from db.base import session_scope
from repositories import farm_repo, season_repo
from services.schedule_engine import calculate_das, current_stage_name

BRAND_GREEN = "#2E7D32"
BRAND_GREEN_LIGHT = "#66BB6A"
ALERT_RED = "#D32F2F"
ALERT_YELLOW = "#F9A825"
ALERT_GREEN = "#43A047"

PLOTLY_PALETTE = ["#2E7D32", "#F9A825", "#1565C0", "#D32F2F", "#6A1B9A", "#00897B", "#EF6C00", "#5D4037"]


def format_currency(amount, symbol: str = "₹") -> str:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return f"{symbol}0"
    return f"{symbol}{value:,.0f}"


def apply_plotly_theme(fig):
    fig.update_layout(
        font_family="sans-serif",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        colorway=PLOTLY_PALETTE,
    )
    return fig


def render_sidebar_context() -> dict | None:
    """
    Renders the Farm -> Season picker in the sidebar and returns the
    currently selected season as a dict of useful derived fields, or None
    if there are no farms/seasons yet.
    """
    with session_scope() as session:
        farms = farm_repo.list_farms(session, SINGLE_USER_ID)
        if not farms:
            st.sidebar.info("No farms yet. Add one in **Farms & Seasons**.")
            return None

        farm_options = {f.name: f.id for f in farms}
        default_farm_id = st.session_state.get("active_farm_id")
        default_farm_name = next((name for name, fid in farm_options.items() if fid == default_farm_id), None)
        farm_names = list(farm_options.keys())
        farm_index = farm_names.index(default_farm_name) if default_farm_name in farm_names else 0

        selected_farm_name = st.sidebar.selectbox("Farm", farm_names, index=farm_index, key="farm_selector")
        selected_farm_id = farm_options[selected_farm_name]
        st.session_state["active_farm_id"] = selected_farm_id

        seasons = season_repo.list_seasons(session, SINGLE_USER_ID)
        seasons = [s for s in seasons if s.farm_id == selected_farm_id]

        if not seasons:
            st.sidebar.info("No seasons for this farm yet. Add one in **Farms & Seasons**.")
            return None

        def season_label(s):
            tag = "🟢" if s.status.value == "ACTIVE" else "⚪"
            return f"{tag} {s.crop.name} - sown {s.sowing_date.strftime('%d %b %Y')}"

        season_options = {season_label(s): s.id for s in seasons}
        default_season_id = st.session_state.get("active_season_id")
        default_season_name = next((name for name, sid in season_options.items() if sid == default_season_id), None)
        season_names = list(season_options.keys())
        season_index = season_names.index(default_season_name) if default_season_name in season_names else 0

        selected_season_name = st.sidebar.selectbox("Season", season_names, index=season_index, key="season_selector")
        selected_season_id = season_options[selected_season_name]
        st.session_state["active_season_id"] = selected_season_id

        season = next(s for s in seasons if s.id == selected_season_id)
        das = calculate_das(season.sowing_date, as_of=date.today())
        stage = current_stage_name(session, season.crop_template_version_id, das)

        return {
            "season_id": season.id,
            "farm_id": season.farm_id,
            "farm_name": season.farm.name,
            "crop_id": season.crop_id,
            "crop_template_version_id": season.crop_template_version_id,
            "crop_name": season.crop.name,
            "variety": season.variety,
            "sowing_date": season.sowing_date,
            "area": float(season.area),
            "area_unit": season.area_unit,
            "status": season.status.value,
            "das": das,
            "stage": stage,
        }


def require_active_season() -> dict:
    """Stops the page with a welcome message if no season is selected."""
    ctx = render_sidebar_context()
    if ctx is None:
        st.title("👋 Welcome to Cultivation")
        st.markdown(
            "Get started by adding your first **Farm** and **Season** "
            "from the **Farms & Seasons** page in the sidebar."
        )
        st.stop()
    return ctx
