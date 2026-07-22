"""
Profit & Loss: the single page that answers "Am I making a profit?" in full
detail, with per-acre economics and supporting charts.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.ui_helpers import apply_plotly_theme, format_currency, require_active_season
from db.base import session_scope
from i18n import t
from repositories import expense_repo, revenue_repo
from services.pnl_engine import calculate_pnl

st.set_page_config(page_title="Profit & Loss - Cultivation", page_icon="🧮", layout="wide")

ctx = require_active_season()
season_id = ctx["season_id"]

st.title(t("🧮 Profit & Loss"))
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

with session_scope() as session:
    expenses = expense_repo.list_expenses(session, season_id)
    revenues = revenue_repo.list_revenues(session, season_id)
    pnl = calculate_pnl(expenses, revenues, area=ctx["area"])

    expense_rows = [(e.expense_date, e.category.value, float(e.amount)) for e in expenses]
    revenue_rows = [(r.sale_date, float(r.amount)) for r in revenues]

is_profit = pnl.net_profit >= 0
profit_label = t("Net Profit") if is_profit else t("Net Loss")
profit_or_loss = t("Profit") if is_profit else t("Loss")

# ---------------------------------------------------------------------------
# Headline Net Profit Card
# ---------------------------------------------------------------------------
card_color = "#2E7D32" if is_profit else "#C62828"
st.markdown(
    f"""
    <div style="background:{card_color}14; border:2px solid {card_color}; border-radius:14px;
                padding:24px 28px; text-align:center; margin-bottom:1.2rem;">
        <div style="font-size:1rem; color:{card_color}; font-weight:600;">{profit_label}</div>
        <div style="font-size:2.6rem; font-weight:800; color:{card_color};">
            {format_currency(abs(pnl.net_profit))}
        </div>
        <div style="color:#555; font-size:0.95rem;">
            {t("for {area} {area_unit} of {crop}", area=f"{ctx['area']:.1f}", area_unit=ctx['area_unit'], crop=ctx['crop_name'])}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
c1.metric(t("Total Expenses"), format_currency(pnl.total_expenses))
c2.metric(t("Total Revenue"), format_currency(pnl.total_revenue))
c3.metric(t("Cost / Acre"), format_currency(pnl.cost_per_acre))
c4.metric(t("{label} / Acre", label=profit_or_loss), format_currency(abs(pnl.profit_per_acre)))

st.divider()

left, right = st.columns(2)

with left:
    st.subheader(t("💸 Expense Pie Chart"))
    if expense_rows:
        df_exp = pd.DataFrame(expense_rows, columns=["Date", "Category", "Amount"])
        cat_totals = df_exp.groupby("Category", as_index=False)["Amount"].sum()
        fig = px.pie(cat_totals, names="Category", values="Amount", hole=0.45)
        fig = apply_plotly_theme(fig)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption(t("No expenses recorded yet."))

with right:
    st.subheader(t("📈 Revenue Trend"))
    if revenue_rows:
        df_rev = pd.DataFrame(revenue_rows, columns=["Date", "Amount"]).sort_values("Date")
        df_rev["Cumulative"] = df_rev["Amount"].cumsum()
        fig = px.area(df_rev, x="Date", y="Cumulative")
        fig = apply_plotly_theme(fig)
        fig.update_yaxes(title=t("Cumulative Revenue (₹)"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption(t("No revenue recorded yet."))

st.divider()

st.subheader(t("⚖️ Income vs Expense"))
if expense_rows or revenue_rows:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[t("This Season")], y=[float(pnl.total_revenue)], name=t("Revenue"), marker_color="#2E7D32"))
    fig.add_trace(go.Bar(x=[t("This Season")], y=[float(pnl.total_expenses)], name=t("Expenses"), marker_color="#D32F2F"))
    fig.update_layout(barmode="group")
    fig = apply_plotly_theme(fig)
    fig.update_yaxes(title=t("Amount (₹)"))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption(t("Add expenses and revenue to see this comparison."))

st.divider()
st.subheader(t("📋 Detailed Breakdown"))
b1, b2 = st.columns(2)
with b1:
    st.markdown(f"**{t('Expenses by Category')}**")
    if pnl.expense_by_category:
        df = pd.DataFrame(
            [(t(k.title()), format_currency(v)) for k, v in sorted(pnl.expense_by_category.items(), key=lambda x: -x[1])],
            columns=[t("Category"), t("Amount")],
        )
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.caption(t("No expenses recorded yet."))

with b2:
    st.markdown(f"**{t('Season Economics')}**")
    st.dataframe(
        pd.DataFrame(
            [
                [t("Area"), f"{ctx['area']:.2f} {t(ctx['area_unit'])}"],
                [t("Total Expenses"), format_currency(pnl.total_expenses)],
                [t("Total Revenue"), format_currency(pnl.total_revenue)],
                [profit_label, format_currency(abs(pnl.net_profit))],
                [t("Cost per Acre"), format_currency(pnl.cost_per_acre)],
                [t("{label} per Acre", label=profit_or_loss), format_currency(abs(pnl.profit_per_acre))],
            ],
            columns=[t("Metric"), t("Value")],
        ),
        hide_index=True,
        use_container_width=True,
    )
