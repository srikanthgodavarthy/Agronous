"""
Observations: log field notes and photos against the active season, and
optionally run AI analysis on a photo for a quick pest/disease/nutrient
read. This page is the only place in the app that touches services/ai_engine.py
-- everything else just reads the ai_* columns it writes.
"""
from __future__ import annotations

import uuid

import streamlit as st

from app.ui_helpers import require_active_season
from auth.supabase_auth import SINGLE_USER_ID
from db.base import session_scope
from i18n import t
from repositories import observation_repo
from services.ai_engine import analyze_observation, is_ai_configured

st.set_page_config(page_title="Observations - Cultivation", page_icon="📸", layout="wide")


def _upload_photo(image_bytes: bytes, media_type: str, season_id) -> tuple[str | None, str | None]:
    """
    Upload a photo to the Supabase Storage 'observations' bucket and return
    its public URL. Returns (url, None) on success, or (None, error_message)
    on any failure -- including the bucket simply not existing yet, which is
    expected until an operator creates it (Storage -> New Bucket
    'observations', public or with a signed-URL policy, in the Supabase
    dashboard). This is a real upload, not a placeholder: when the bucket
    isn't configured it fails loudly here rather than silently faking a URL.
    """
    import uuid as _uuid

    try:
        from auth.supabase_auth import get_supabase_client

        client = get_supabase_client()
        ext = "jpg" if "jpeg" in media_type or "jpg" in media_type else "png"
        path = f"{season_id}/{_uuid.uuid4()}.{ext}"
        client.storage.from_("observations").upload(
            path, image_bytes, file_options={"content-type": media_type}
        )
        public_url = client.storage.from_("observations").get_public_url(path)
        return public_url, None
    except Exception as exc:  # noqa: BLE001 - any storage failure must degrade, not crash the page
        return None, str(exc)


ctx = require_active_season()
season_id = ctx["season_id"]

st.title(t("📸 Observations"))
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))
st.caption(
    t(
        "Log what you see in the field -- a quick note, a photo, or both. "
        "Optionally get an AI read on a photo for a second opinion."
    )
)

if not is_ai_configured():
    st.info(
        t(
            "AI analysis is not configured in this environment (no ANTHROPIC_API_KEY set). "
            "You can still log notes and photos -- just without the AI read."
        ),
        icon="ℹ️",
    )

st.divider()

# ---------------------------------------------------------------------------
# Add a new observation
# ---------------------------------------------------------------------------
st.subheader(t("➕ Add Observation"))
with st.form("add_observation_form", clear_on_submit=True):
    note = st.text_area(t("Note"), placeholder=t("e.g. Yellowing on lower leaves near the east bund"))
    photo = st.file_uploader(t("Photo (optional)"), type=["jpg", "jpeg", "png"])
    run_ai = st.checkbox(
        t("Run AI analysis on this photo"), value=False, disabled=(photo is None) or not is_ai_configured()
    )

    submitted = st.form_submit_button(t("Save Observation"), type="primary")

    if submitted:
        if not note.strip() and photo is None:
            st.error(t("Add a note, a photo, or both."))
        else:
            image_bytes = photo.getvalue() if photo is not None else None
            media_type = photo.type if photo is not None else None
            image_url = None

            if photo is not None:
                image_url, upload_error = _upload_photo(image_bytes, media_type, season_id)
                if upload_error:
                    st.warning(
                        t(
                            "Photo couldn't be uploaded to storage ({error}) -- "
                            "saving the note without it. The photo can still be analyzed below before saving.",
                            error=upload_error,
                        )
                    )

            with session_scope() as session:
                observation = observation_repo.create_observation(
                    session,
                    season_id=season_id,
                    user_id=SINGLE_USER_ID,
                    note=note.strip() or None,
                    image_url=image_url,
                )

                if run_ai and image_bytes:
                    with st.spinner(t("Analyzing photo...")):
                        result = analyze_observation(
                            image_bytes=image_bytes,
                            media_type=media_type,
                            crop_name=ctx["crop_name"],
                            stage_name=ctx["stage"],
                            farmer_note=note.strip() or None,
                        )
                    observation_repo.save_ai_analysis(
                        session,
                        observation,
                        ai_analysis=result.analysis,
                        ai_category=result.category,
                        ai_confidence=result.confidence,
                        ai_recommendation=result.recommendation,
                        ai_raw_response=result.raw_response,
                    )
                    if result.succeeded:
                        st.success(t("Observation saved. AI read: **{category}**.", category=result.category))
                    else:
                        st.warning(t("Observation saved, but AI analysis was unavailable this time."))
                else:
                    st.success(t("Observation saved."))

            if photo is not None:
                st.image(photo, caption=t("Saved photo"), width=300)
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Observation log
# ---------------------------------------------------------------------------
st.subheader(t("🗒️ Observation Log"))

with session_scope() as session:
    observations = observation_repo.list_observations(session, season_id)
    observations_data = [
        {
            "id": o.id,
            "observed_at": o.observed_at,
            "note": o.note,
            "image_url": o.image_url,
            "ai_analysis": o.ai_analysis,
            "ai_category": o.ai_category,
            "ai_confidence": float(o.ai_confidence) if o.ai_confidence is not None else None,
            "ai_recommendation": o.ai_recommendation,
        }
        for o in observations
    ]

if not observations_data:
    st.info(t("No observations logged yet for this season."))
else:
    category_colors = {
        "Pest": "#D32F2F",
        "Disease": "#C62828",
        "Nutrient Deficiency": "#F9A825",
        "Water Stress": "#1565C0",
        "Weed Pressure": "#6A1B9A",
        "Healthy / No Issue": "#2E7D32",
        "Unclear": "#757575",
    }

    for row in observations_data:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            c1.markdown(f"**{row['observed_at'].strftime('%d %b %Y')}**")
            c1.caption(row["observed_at"].strftime("%H:%M"))

            if row["note"]:
                c2.markdown(row["note"])
            if row["image_url"]:
                c2.image(row["image_url"], width=240)

            if row["ai_category"]:
                color = category_colors.get(row["ai_category"], "#757575")
                confidence_pct = f"{row['ai_confidence'] * 100:.0f}%" if row["ai_confidence"] is not None else "—"
                ai_category_label = t(row["ai_category"])
                c2.markdown(
                    f"<div style='margin-top:8px; padding:10px 12px; border-radius:8px; "
                    f"background:{color}14; border-left:4px solid {color};'>"
                    f"<strong>{t('AI read: {category}', category=ai_category_label)}</strong> "
                    f"({t('confidence {pct}', pct=confidence_pct)})<br>"
                    f"{row['ai_analysis']}<br>"
                    f"<em>{t('Recommendation: {rec}', rec=row['ai_recommendation'])}</em>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            if st.button(t("🗑️ Delete"), key=f"del_obs_{row['id']}"):
                with session_scope() as session:
                    obs_obj = observation_repo.get_observation(session, row["id"])
                    if obs_obj:
                        observation_repo.delete_observation(session, obs_obj)
                st.rerun()
