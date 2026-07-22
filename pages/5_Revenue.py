"""
Revenue: log and review harvest sales for the active season.
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
from i18n import t
from repositories import revenue_repo

st.set_page_config(page_title="Revenue - Cultivation", page_icon="📈", layout="wide")

ctx = require_active_season()
season_id = ctx["season_id"]

st.title(t("📈 Revenue"))
st.caption(f"{ctx['farm_name']} • {ctx['crop_name']}" + (f" ({ctx['variety']})" if ctx["variety"] else ""))

with session_scope() as session:
    revenues = revenue_repo.list_revenues(session, season_id)
    revenues_data = [
        {
            "id": r.id,
            "date": r.sale_date,
            "buyer": r.buyer or "",
            "quantity": float(r.quantity),
            "quantity_unit": r.quantity_unit,
            "price_per_unit": float(r.price_per_unit),
            "amount": float(r.amount),
        }
        for r in revenues
    ]

total = sum(r["amount"] for r in revenues_data)

c1, c2, c3 = st.columns(3)
c1.metric(t("Total Revenue"), format_currency(total))
c2.metric(t("Sale Entries"), len(revenues_data))
total_qty = sum(r["quantity"] for r in revenues_data)
c3.metric(t("Total Quantity Sold"), f"{total_qty:.1f}" if revenues_data else "—")

st.divider()

left, right = st.columns([1.4, 1])

with left:
    st.subheader(t("📜 Sales Log"))
    if revenues_data:
        for row in revenues_data:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([1, 1.3, 1.2, 1.2, 1])
                c1.markdown(row["date"].strftime("%d %b %Y"))
                c2.markdown(f"**{row['buyer'] or t('Unknown Buyer')}**")
                c3.markdown(f"{row['quantity']:.1f} {t(row['quantity_unit'])}")
                c4.markdown(f"@ {format_currency(row['price_per_unit'])}")
                c5.markdown(f"**{format_currency(row['amount'])}**")
                if st.button(t("🗑️ Delete"), key=f"del_rev_{row['id']}"):
                    with session_scope() as session:
                        rev_obj = revenue_repo.get_revenue(session, row["id"])
                        if rev_obj:
                            revenue_repo.delete_revenue(session, rev_obj)
                    st.rerun()
    else:
        st.info(t("No sales logged yet. Add your first one on the right."))

with right:
    st.subheader(t("➕ Add Sale"))
    with st.form("add_revenue_form", clear_on_submit=True):
        sale_date = st.date_input(t("Date *"), value=date.today())
        buyer = st.text_input(t("Buyer"), placeholder=t("e.g. Local Mandi / Trader Name"))
        c1, c2 = st.columns(2)
        quantity = c1.number_input(t("Quantity *"), min_value=0.0, step=1.0, value=0.0)
        quantity_unit = c2.selectbox(t("Unit"), ["Quintal", "Kg", "Tonne", "Bag"], format_func=t)
        price_per_unit = st.number_input(t("Price per Unit *"), min_value=0.0, step=10.0, value=0.0)

        if quantity > 0 and price_per_unit > 0:
            st.caption(t("Amount: {amount}", amount=format_currency(quantity * price_per_unit)))

        submitted = st.form_submit_button(t("Add Sale"), type="primary", use_container_width=True)
        if submitted:
            if quantity <= 0 or price_per_unit <= 0:
                st.error(t("Quantity and price must be greater than zero."))
            else:
                with session_scope() as session:
                    revenue_repo.create_revenue(
                        session,
                        season_id=season_id,
                        user_id=SINGLE_USER_ID,
                        sale_date=sale_date,
                        quantity=quantity,
                        price_per_unit=price_per_unit,
                        buyer=buyer.strip() or None,
                        quantity_unit=quantity_unit,
                    )
                st.success(t("Logged sale of {amount}.", amount=format_currency(quantity * price_per_unit)))
                st.rerun()

if revenues_data:
    st.divider()
    st.subheader(t("📈 Revenue Timeline"))
    df = pd.DataFrame(revenues_data).sort_values("date")
    df["cumulative"] = df["amount"].cumsum()
    fig = px.line(df, x="date", y="cumulative", markers=True)
    fig = apply_plotly_theme(fig)
    fig.update_yaxes(title=t("Cumulative Revenue (₹)"))
    fig.update_xaxes(title=t("Date"))
    st.plotly_chart(fig, use_container_width=True)
