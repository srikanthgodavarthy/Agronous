"""Data access for Revenue (harvest sale) entities."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from db.models import Revenue


def list_revenues(
    session: Session, season_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None
) -> list[Revenue]:
    query = session.query(Revenue).filter(Revenue.season_id == season_id)
    if date_from is not None:
        query = query.filter(Revenue.sale_date >= date_from)
    if date_to is not None:
        query = query.filter(Revenue.sale_date <= date_to)
    return query.order_by(Revenue.sale_date.desc()).all()


def get_revenue(session: Session, revenue_id: uuid.UUID) -> Revenue | None:
    return session.query(Revenue).filter(Revenue.id == revenue_id).first()


def create_revenue(
    session: Session,
    season_id: uuid.UUID,
    user_id: uuid.UUID,
    sale_date: date,
    quantity: float,
    price_per_unit: float,
    buyer: str | None = None,
    quantity_unit: str = "Quintal",
) -> Revenue:
    amount = float(quantity) * float(price_per_unit)
    revenue = Revenue(
        season_id=season_id,
        user_id=user_id,
        sale_date=sale_date,
        buyer=buyer,
        quantity=quantity,
        quantity_unit=quantity_unit,
        price_per_unit=price_per_unit,
        amount=amount,
    )
    session.add(revenue)
    session.flush()
    return revenue


def update_revenue(session: Session, revenue: Revenue, **fields) -> Revenue:
    for key, value in fields.items():
        if hasattr(revenue, key) and value is not None:
            setattr(revenue, key, value)
    # Recompute amount if quantity or price changed.
    revenue.amount = float(revenue.quantity) * float(revenue.price_per_unit)
    session.flush()
    return revenue


def delete_revenue(session: Session, revenue: Revenue) -> None:
    session.delete(revenue)
