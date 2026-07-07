"""
Dashboard: the single screen that answers the core questions -- led by
"what's the single best thing to do today" (services.decisions.
recommendation_engine.build_schedule_snapshot), not a raw list of whatever
happens to be scheduled or overdue. Below that: completed-recently,
other actionable items, money.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui_helpers import (
    ALERT_GREEN,
    ALERT_RED,
    ALERT_YELLOW,
    apply_plotly_theme,
    format_currency,
)
from db.base import session_scope
from db.models import ActivityStatus, ScheduleActivity, Season
from repositories import expense_repo, observation_repo, revenue_repo, schedule_repo
from services.alert_engine import refresh_alerts_for_season
from services.decisions.recommendation_engine import RecommendedOperation, build_schedule_snapshot
from services.pnl_engine import calculate_pnl

CATEGORY_ICON = {
    "FERTILIZER": "🌱", "SPRAY": "🧴", "IRRIGATION": "💧", "WEEDING": "🌾",
    "SOWING": "🌰", "LAND_PREPARATION": "🚜", "HARVEST": "🧺", "OTHER": "📌",
}


def _render_operation_card(op: RecommendedOperation, today: date, key_prefix: str) -> None:
    icon = CATEGORY_ICON.get(op.category, "📌")
    when = "Today" if op.recommended_date == today else (
        "Overdue" if op.recommended_date < today else op.recommended_date.strftime("%d %b")
    )

    lines = [f"**{icon} {op.name}**", f"`{op.priority}` · {when}"]
    if op.products:
        for i, prod in enumerate(op.products):
            dose = op.dosage[i] if i < len(op.dosage) else ""
            lines.append(f"- {prod}" + (f" — {dose}" if dose else ""))
    if op.water_volume:
        lines.append(f"💧 Water: {op.water_volume}")
    lines.append(f"**Why:** {op.why}")
    if op.expected_benefit:
        lines.append(f"**Expected benefit:** {op.expected_benefit}")
    if op.recovery_reason:
        tag = "🔁 Replaced" if op.is_replacement else "⏰ Recovery"
        lines.append(f"**{tag}:** {op.recovery_reason}")

    st.markdown("\n\n".join(lines))

    ask_key = f"{key_prefix}_ask_date_{op.activity_ids[0]}"
    b1, b2 = st.columns(2)
    if b1.button("✓ Mark Complete", key=f"{key_prefix}_done_{op.activity_ids[0]}", use_container_width=True, type="primary"):
        st.session_state[ask_key] = True
        st.rerun()
    if b2.button("⏭ Skip", key=f"{key_prefix}_skip_{op.activity_ids[0]}", use_container_width=True):
        with session_scope() as s:
            for aid in op.activity_ids:
                act = schedule_repo.get_activity(s, aid)
                if act:
                    schedule_repo.mark_skipped(s, act)
        st.rerun()

    if st.session_state.get(ask_key):
        with st.form(key=f"{key_prefix}_form_{op.activity_ids[0]}"):
            chosen_date = st.date_input("Completion date", value=today, max_value=today,
                                         key=f"{key_prefix}_date_{op.activity_ids[0]}")
            fc1, fc2 = st.columns(2)
            confirm = fc1.form_submit_button("✓ Confirm", type="primary", use_container_width=True)
            cancel = fc2.form_submit_button("Cancel", use_container_width=True)
        if confirm:
            with session_scope() as s:
                for aid in op.activity_ids:
                    act = schedule_repo.get_activity(s, aid)
                    if act:
                        schedule_repo.mark_complete(s, act, completed_date=chosen_date)
            st.session_state[ask_key] = False
            st.rerun()
        if cancel:
            st.session_state[ask_key] = False
            st.rerun()


def render(ctx: dict) -> None:
    season_id = ctx["season_id"]
    today = date.today()

    st.title("🌱 Cultivation Dashboard")
    st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

    with session_scope() as session:
        season_obj = session.get(Season, season_id)

        snapshot = build_schedule_snapshot(session, season_obj, today=today)

        upcoming_tasks = schedule_repo.get_upcoming_tasks(session, season_id, days=7)
        expenses = expense_repo.list_expenses(session, season_id)
        revenues = revenue_repo.list_revenues(session, season_id)
        pnl = calculate_pnl(expenses, revenues, area=ctx["area"])

        alerts = refresh_alerts_for_season(session, season_obj)

        recent_completed = (
            session.query(ScheduleActivity)
            .filter_by(season_id=season_id, status=ActivityStatus.COMPLETED)
            .order_by(ScheduleActivity.completed_at.desc())
            .limit(6)
            .all()
        )

        recent_observations = observation_repo.list_observations(session, season_id, limit=3)

        # Snapshot plain data before the session closes.
        upcoming_tasks_data = [(t.activity_date, t.name, t.category.value) for t in upcoming_tasks]
        alerts_data = [(a.priority.value, a.message) for a in alerts]
        recent_data = [(a.completed_at, a.name, a.category.value) for a in recent_completed]
        expense_rows = [(e.expense_date, e.category.value, float(e.amount)) for e in expenses]
        revenue_rows = [(r.sale_date, float(r.amount)) for r in revenues]
        observation_data = [
            (o.observed_at, o.note, o.ai_category) for o in recent_observations
        ]
        recommended = snapshot.recommended
        also_actionable = snapshot.also_actionable
        escalated = snapshot.escalated
        replaced_names = snapshot.replaced_names

    # ---------------- KPI Row 1: Crop status ----------------
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Current Crop", ctx["crop_name"])
    k2.metric("Current Stage", ctx["stage"] or "—")
    k3.metric("Days After Sowing", f"{ctx['das']} days")
    k4.metric("Area", f"{ctx['area']:.1f} {ctx['area_unit']}")

    st.divider()

    # ---------------- PRIMARY: Recommended Next Operation ----------------
    st.subheader("🎯 Recommended Next Operation")
    if replaced_names:
        for original, replacement in replaced_names:
            st.caption(f"🔁 {original} missed its window — replaced with **{replacement}**.")

    if recommended:
        _render_operation_card(recommended, today, key_prefix="primary")
    else:
        st.success("Nothing actionable right now — the crop is fully on track. ✅")

    if escalated:
        with st.expander(f"⚠️ {len(escalated)} item(s) need a manual decision", expanded=False):
            for decision in escalated:
                st.markdown(f"- **{decision.activity.name}** — {decision.reason}")

    if also_actionable:
        with st.expander(f"📋 Also pending ({len(also_actionable)})", expanded=False):
            for i, op in enumerate(also_actionable):
                st.markdown(f"**{i + 1}. {op.name}** · `{op.priority}` · due {op.recommended_date.strftime('%d %b')}")

    st.divider()

    left, right = st.columns([1.1, 1])

    with left:
        st.subheader("🕘 Completed Recently")
        if recent_data:
            for completed_at, name, category in recent_data:
                ts = completed_at.strftime("%d %b") if completed_at else ""
                st.markdown(f"- ✅ **{name}** _( {category} )_ — {ts}")
        else:
            st.caption("No completed activities yet.")

        st.subheader("🔔 Alerts")
        if alerts_data:
            for priority, message in alerts_data[:8]:
                color = {"RED": ALERT_RED, "YELLOW": ALERT_YELLOW, "GREEN": ALERT_GREEN}[priority]
                st.markdown(
                    f"<div style='padding:8px 12px; border-radius:6px; background:{color}1A; "
                    f"border-left:4px solid {color}; margin-bottom:6px;'>{message}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No alerts right now.")

    with right:
        st.subheader("📅 Upcoming (7 days)")
        if upcoming_tasks_data:
            df_upcoming = pd.DataFrame(upcoming_tasks_data, columns=["Date", "Activity", "Category"])
            st.dataframe(df_upcoming, hide_index=True, use_container_width=True)
        else:
            st.info("No tasks in the next 7 days.")

        st.subheader("📸 Recent Observations")
        if observation_data:
            for observed_at, note, ai_category in observation_data:
                tag = f" `{ai_category}`" if ai_category else ""
                text = note or "_(photo only)_"
                st.markdown(f"- {observed_at.strftime('%d %b')}: {text}{tag}")
        else:
            st.caption("No field observations logged yet.")

    st.divider()

    # ---------------- Charts: Expense Breakdown, Revenue Trend, P&L ----------------
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("💸 Expense Breakdown")
        if expense_rows:
            df_exp = pd.DataFrame(expense_rows, columns=["Date", "Category", "Amount"])
            cat_totals = df_exp.groupby("Category", as_index=False)["Amount"].sum()
            fig = px.pie(cat_totals, names="Category", values="Amount", hole=0.45)
            fig = apply_plotly_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No expenses recorded yet.")

    with c2:
        st.subheader("📈 Revenue Trend")
        if revenue_rows:
            df_rev = pd.DataFrame(revenue_rows, columns=["Date", "Amount"]).sort_values("Date")
            df_rev["Cumulative"] = df_rev["Amount"].cumsum()
            fig = px.line(df_rev, x="Date", y="Cumulative", markers=True)
            fig = apply_plotly_theme(fig)
            fig.update_yaxes(title="Cumulative Revenue (₹)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No revenue recorded yet.")

    st.subheader("🧮 P&L Summary")
    profit_label = "Profit" if pnl.net_profit >= 0 else "Loss"
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Total Expenses", format_currency(pnl.total_expenses))
    p2.metric("Total Revenue", format_currency(pnl.total_revenue))
    p3.metric("Cost / Acre", format_currency(pnl.cost_per_acre))
    p4.metric(
        f"Net {profit_label} / Acre",
        format_currency(abs(pnl.profit_per_acre)),
    )

