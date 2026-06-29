"""
Cultivation Schedule: full timeline of activities for the active season.
Supports marking activities complete/skipped, editing date/remarks, and
adding ad-hoc custom activities not present in any crop template.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from app.ui_helpers import require_active_season
from db.base import session_scope
from db.models import ActivityCategory, ActivityStatus
from repositories import schedule_repo
from services.schedule_engine import calculate_das

st.set_page_config(page_title="Cultivation Schedule - Cultivation", page_icon="📅", layout="wide")

ctx = require_active_season()
season_id = ctx["season_id"]

st.title("📅 Cultivation Schedule")
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
f1, f2 = st.columns([1, 3])
with f1:
    status_filter = st.selectbox("Status", ["All", "PENDING", "COMPLETED", "SKIPPED"],
                                  format_func=lambda x: x.title() if x != "All" else x)
with f2:
    category_filter = st.multiselect(
        "Categories",
        [c.value for c in ActivityCategory],
        default=[],
        placeholder="All categories",
    )

with session_scope() as session:
    status_enum = None if status_filter == "All" else ActivityStatus(status_filter)
    activities = schedule_repo.list_activities(session, season_id, status=status_enum)
    if category_filter:
        activities = [a for a in activities if a.category.value in category_filter]

    activities_data = [
        {
            "id": a.id,
            "activity_date": a.activity_date,
            "das": a.das,
            "name": a.name,
            "category": a.category.value,
            "status": a.status.value,
            "remarks": a.remarks or "",
            "is_custom": a.is_custom,
        }
        for a in activities
    ]

st.divider()

# ---------------------------------------------------------------------------
# Timeline display
# ---------------------------------------------------------------------------
if not activities_data:
    st.info("No activities match the current filter.")
else:
    today = date.today()
    for row in activities_data:
        status_icon = {"PENDING": "⏳", "COMPLETED": "✅", "SKIPPED": "⏭️"}[row["status"]]
        is_overdue = row["status"] == "PENDING" and row["activity_date"] < today

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.2, 2.3, 1, 1.5])

            date_label = row["activity_date"].strftime("%d %b %Y")
            if is_overdue:
                c1.markdown(f"🔴 **{date_label}**  \nDAS {row['das']}")
            else:
                c1.markdown(f"{date_label}  \nDAS {row['das']}")

            title = f"{status_icon} **{row['name']}**"
            if row["is_custom"]:
                title += " 🏷️"
            c2.markdown(title)
            c2.caption(row["category"] + (f" • {row['remarks']}" if row["remarks"] else ""))

            c3.markdown(f"`{row['status']}`")

            with c4.popover("Manage", use_container_width=True):
                with st.form(f"manage_{row['id']}"):
                    new_date = st.date_input("Date", value=row["activity_date"], key=f"date_{row['id']}")
                    new_remarks = st.text_area(
                        "Remarks", value=row["remarks"], key=f"remarks_{row['id']}", height=80
                    )
                    save_col, complete_col, skip_col = st.columns(3)
                    save = save_col.form_submit_button("💾 Save")
                    complete = complete_col.form_submit_button("✅ Complete")
                    skip = skip_col.form_submit_button("⏭️ Skip")

                    if save or complete or skip:
                        with session_scope() as session:
                            activity = schedule_repo.get_activity(session, row["id"])
                            if activity is None:
                                st.error("Activity not found.")
                            else:
                                schedule_repo.update_activity(
                                    session, activity, activity_date=new_date, remarks=new_remarks or None
                                )
                                if complete:
                                    schedule_repo.mark_complete(session, activity)
                                elif skip:
                                    schedule_repo.mark_skipped(session, activity)
                        st.rerun()

                if row["status"] != "PENDING":
                    if st.button("↩️ Reopen", key=f"reopen_{row['id']}"):
                        with session_scope() as session:
                            activity = schedule_repo.get_activity(session, row["id"])
                            schedule_repo.reopen(session, activity)
                        st.rerun()

                if row["is_custom"]:
                    if st.button("🗑️ Delete", key=f"delete_{row['id']}"):
                        with session_scope() as session:
                            activity = schedule_repo.get_activity(session, row["id"])
                            schedule_repo.delete_activity(session, activity)
                        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Add custom activity
# ---------------------------------------------------------------------------
st.subheader("➕ Add Custom Activity")
with st.form("add_custom_activity", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    activity_name = c1.text_input("Activity Name *", placeholder="e.g. Soil Testing")
    category = c2.selectbox("Category *", [c.value for c in ActivityCategory])
    activity_date = c3.date_input("Date *", value=date.today())
    remarks = st.text_input("Remarks (optional)")

    submitted = st.form_submit_button("Add Activity", type="primary")
    if submitted:
        if not activity_name.strip():
            st.error("Activity name is required.")
        else:
            das = calculate_das(ctx["sowing_date"], as_of=activity_date)
            with session_scope() as session:
                schedule_repo.add_custom_activity(
                    session,
                    season_id=season_id,
                    activity_date=activity_date,
                    das=das,
                    name=activity_name.strip(),
                    category=ActivityCategory(category),
                    remarks=remarks.strip() or None,
                )
            st.success(f"Added custom activity '{activity_name}'.")
            st.rerun()
