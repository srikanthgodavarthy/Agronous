"""
Expenses: log and review cultivation costs for the active season.
"""
from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui_helpers import apply_plotly_theme, format_currency, require_active_season
from auth.supabase_auth import SINGLE_USER_ID
from db.base import session_scope
from db.models import ExpenseCategory
from repositories import expense_repo

st.set_page_config(page_title="Expenses - Cultivation", page_icon="💸", layout="wide")

ctx = require_active_season()
season_id = ctx["season_id"]

st.title("💸 Expenses")
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

with session_scope() as session:
    expenses = expense_repo.list_expenses(session, season_id)
    expenses_data = [
        {
            "id": e.id,
            "date": e.expense_date,
            "category": e.category.value,
            "description": e.description or "",
            "amount": float(e.amount),
        }
        for e in expenses
    ]

total = sum(e["amount"] for e in expenses_data)

c1, c2, c3 = st.columns(3)
c1.metric("Total Expenses", format_currency(total))
c2.metric("Entries", len(expenses_data))
c3.metric("Cost / Acre", format_currency(total / ctx["area"]) if ctx["area"] else "—")

st.divider()

left, right = st.columns([1.4, 1])

with left:
    st.subheader("📜 Expense Log")
    if expenses_data:
        for row in expenses_data:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1, 1.2, 2, 1])
                c1.markdown(row["date"].strftime("%d %b %Y"))
                c2.markdown(f"**{row['category']}**")
                c3.markdown(row["description"] or "_No description_")
                c4.markdown(f"**{format_currency(row['amount'])}**")
                if st.button("🗑️ Delete", key=f"del_exp_{row['id']}"):
                    with session_scope() as session:
                        expense_obj = expense_repo.get_expense(session, row["id"])
                        if expense_obj:
                            expense_repo.delete_expense(session, expense_obj)
                    st.rerun()
    else:
        st.info("No expenses logged yet. Add your first one on the right.")

with right:
    st.subheader("➕ Add Expense")
    with st.form("add_expense_form", clear_on_submit=True):
        expense_date = st.date_input("Date *", value=date.today())
        category = st.selectbox("Category *", [c.value for c in ExpenseCategory])
        description = st.text_input("Description", placeholder="e.g. Urea 2 bags")
        amount = st.number_input("Amount *", min_value=0.0, step=50.0, value=0.0)

        submitted = st.form_submit_button("Add Expense", type="primary", use_container_width=True)
        if submitted:
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                with session_scope() as session:
                    expense_repo.create_expense(
                        session,
                        season_id=season_id,
                        user_id=SINGLE_USER_ID,
                        expense_date=expense_date,
                        category=ExpenseCategory(category),
                        amount=amount,
                        description=description.strip() or None,
                    )
                st.success(f"Logged {format_currency(amount)} under {category}.")
                st.rerun()

    if expenses_data:
        st.subheader("📊 By Category")
        df = pd.DataFrame(expenses_data)
        cat_totals = df.groupby("category", as_index=False)["amount"].sum()
        fig = px.pie(cat_totals, names="category", values="amount", hole=0.45)
        fig = apply_plotly_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

if expenses_data:
    st.divider()
    st.subheader("📈 Expense Timeline")
    df = pd.DataFrame(expenses_data).sort_values("date")
    df["cumulative"] = df["amount"].cumsum()
    fig = px.bar(df, x="date", y="amount", color="category", title=None)
    fig = apply_plotly_theme(fig)
    fig.update_yaxes(title="Amount (₹)")
    fig.update_xaxes(title="Date")
    st.plotly_chart(fig, use_container_width=True)
