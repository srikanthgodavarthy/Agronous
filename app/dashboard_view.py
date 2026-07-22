"""
Dashboard: the single screen that answers all four core questions.
  - What should I do today?      -> Today's Tasks KPI + list
  - What is due this week?       -> Upcoming Tasks KPI + Weekly Alerts panel
  - How much have I spent?       -> Total Expenses KPI + breakdown chart
  - Am I making a profit?        -> Profit/Loss KPI + P&L summary chart
"""
from __future__ import annotations

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
from i18n import t
from repositories import expense_repo, observation_repo, revenue_repo, schedule_repo
from services.alert_engine import refresh_alerts_for_season
from services.pnl_engine import calculate_pnl

CATEGORY_LABELS = {
    "IRRIGATION": "Irrigation",
    "FERTILIZER": "Fertilizer",
    "SPRAY": "Spray / Pest",
    "WEEDING": "Weeding",
    "LAND_PREPARATION": "Land Prep",
    "SOWING": "Sowing",
    "HARVEST": "Harvest",
    "OTHER": "Other",
}


def render(ctx: dict) -> None:
    season_id = ctx["season_id"]

    st.title(t("🌱 Cultivation Dashboard"))
    st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

    with session_scope() as session:
        today_tasks = schedule_repo.get_todays_tasks(session, season_id)
        upcoming_tasks = schedule_repo.get_upcoming_tasks(session, season_id, days=7)
        expenses = expense_repo.list_expenses(session, season_id)
        revenues = revenue_repo.list_revenues(session, season_id)
        pnl = calculate_pnl(expenses, revenues, area=ctx["area"])

        # Refresh + fetch alerts (needs the actual Season ORM object).
        season_obj = session.get(Season, season_id)
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
        today_tasks_data = [(t_.name, t_.category.value, t_.remarks) for t_ in today_tasks]
        upcoming_tasks_data = [(t_.activity_date, t_.name, t_.category.value) for t_ in upcoming_tasks]
        alerts_data = [(a.priority.value, a.message) for a in alerts]
        recent_data = [(a.completed_at, a.name, a.category.value) for a in recent_completed]
        expense_rows = [(e.expense_date, e.category.value, float(e.amount)) for e in expenses]
        revenue_rows = [(r.sale_date, float(r.amount)) for r in revenues]
        observation_data = [
            (o.observed_at, o.note, o.ai_category) for o in recent_observations
        ]

    # ---------------- KPI Row 1: Crop status ----------------
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(t("Current Crop"), ctx["crop_name"])
    k2.metric(t("Current Stage"), ctx["stage"] or "—")
    k3.metric(t("Days After Sowing"), t("{n} days", n=ctx["das"]))
    k4.metric(t("Area"), f"{ctx['area']:.1f} {ctx['area_unit']}")

    # ---------------- KPI Row 2: Tasks ----------------
    k5, k6, k7 = st.columns(3)
    k5.metric(t("Today's Tasks"), len(today_tasks_data))
    k6.metric(t("Upcoming (7 days)"), len(upcoming_tasks_data))
    overdue_count = sum(1 for p, _ in alerts_data if p == "RED")
    k7.metric(t("Overdue"), overdue_count, delta=None, delta_color="inverse")

    # ---------------- KPI Row 3: Money ----------------
    k8, k9, k10 = st.columns(3)
    k8.metric(t("Total Expenses"), format_currency(pnl.total_expenses))
    k9.metric(t("Total Revenue"), format_currency(pnl.total_revenue))
    profit_label = t("Profit") if pnl.net_profit >= 0 else t("Loss")
    k10.metric(t("Net {label}", label=profit_label), format_currency(abs(pnl.net_profit)))

    st.divider()

    left, right = st.columns([1.1, 1])

    with left:
        st.subheader(t("📋 Today's Tasks"))
        if today_tasks_data:
            for name, category, remarks in today_tasks_data:
                cat_label = t(CATEGORY_LABELS.get(category, category))
                st.markdown(f"- **{name}** _( {cat_label} )_" + (f" — {remarks}" if remarks else ""))
        else:
            st.success(t("Nothing scheduled for today. ✅"))

        st.subheader(t("🔔 Upcoming Alerts"))
        if alerts_data:
            for priority, message in alerts_data[:8]:
                color = {"RED": ALERT_RED, "YELLOW": ALERT_YELLOW, "GREEN": ALERT_GREEN}[priority]
                st.markdown(
                    f"<div style='padding:8px 12px; border-radius:6px; background:{color}1A; "
                    f"border-left:4px solid {color}; margin-bottom:6px;'>{message}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info(t("No alerts right now."))

    with right:
        st.subheader(t("📅 This Week"))
        if upcoming_tasks_data:
            df_upcoming = pd.DataFrame(upcoming_tasks_data, columns=[t("Date"), t("Activity"), t("Category")])
            st.dataframe(df_upcoming, hide_index=True, use_container_width=True)
        else:
            st.info(t("No tasks in the next 7 days."))

        st.subheader(t("🕘 Recent Activity"))
        if recent_data:
            for completed_at, name, category in recent_data:
                ts = completed_at.strftime("%d %b") if completed_at else ""
                cat_label = t(CATEGORY_LABELS.get(category, category))
                st.markdown(f"- ✅ **{name}** _( {cat_label} )_ — {ts}")
        else:
            st.caption(t("No completed activities yet."))

        st.subheader(t("📸 Recent Observations"))
        if observation_data:
            for observed_at, note, ai_category in observation_data:
                tag = f" `{ai_category}`" if ai_category else ""
                text = note or t("_(photo only)_")
                st.markdown(f"- {observed_at.strftime('%d %b')}: {text}{tag}")
        else:
            st.caption(t("No field observations logged yet."))

    st.divider()

    # ---------------- Charts: Expense Breakdown, Revenue Trend, P&L ----------------
    c1, c2 = st.columns(2)

    with c1:
        st.subheader(t("💸 Expense Breakdown"))
        if expense_rows:
            df_exp = pd.DataFrame(expense_rows, columns=["Date", "Category", "Amount"])
            cat_totals = df_exp.groupby("Category", as_index=False)["Amount"].sum()
            fig = px.pie(cat_totals, names="Category", values="Amount", hole=0.45)
            fig = apply_plotly_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption(t("No expenses recorded yet."))

    with c2:
        st.subheader(t("📈 Revenue Trend"))
        if revenue_rows:
            df_rev = pd.DataFrame(revenue_rows, columns=["Date", "Amount"]).sort_values("Date")
            df_rev["Cumulative"] = df_rev["Amount"].cumsum()
            fig = px.line(df_rev, x="Date", y="Cumulative", markers=True)
            fig = apply_plotly_theme(fig)
            fig.update_yaxes(title=t("Cumulative Revenue (₹)"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption(t("No revenue recorded yet."))

    st.subheader(t("🧮 P&L Summary"))
    p1, p2, p3, p4 = st.columns(4)
    p1.metric(t("Total Expenses"), format_currency(pnl.total_expenses))
    p2.metric(t("Total Revenue"), format_currency(pnl.total_revenue))
    p3.metric(t("Cost / Acre"), format_currency(pnl.cost_per_acre))
    p4.metric(
        t("Net {label} / Acre", label=profit_label),
        format_currency(abs(pnl.profit_per_acre)),
    )
