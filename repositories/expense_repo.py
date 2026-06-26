"""Data access for Expense entities."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from db.models import Expense, ExpenseCategory


def list_expenses(
    session: Session, season_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None
) -> list[Expense]:
    query = session.query(Expense).filter(Expense.season_id == season_id)
    if date_from is not None:
        query = query.filter(Expense.expense_date >= date_from)
    if date_to is not None:
        query = query.filter(Expense.expense_date <= date_to)
    return query.order_by(Expense.expense_date.desc()).all()


def get_expense(session: Session, expense_id: uuid.UUID) -> Expense | None:
    return session.query(Expense).filter(Expense.id == expense_id).first()


def create_expense(
    session: Session,
    season_id: uuid.UUID,
    user_id: uuid.UUID,
    expense_date: date,
    category: ExpenseCategory,
    amount: float,
    description: str | None = None,
) -> Expense:
    expense = Expense(
        season_id=season_id,
        user_id=user_id,
        expense_date=expense_date,
        category=category,
        amount=amount,
        description=description,
    )
    session.add(expense)
    session.flush()
    return expense


def update_expense(session: Session, expense: Expense, **fields) -> Expense:
    for key, value in fields.items():
        if hasattr(expense, key) and value is not None:
            setattr(expense, key, value)
    session.flush()
    return expense


def delete_expense(session: Session, expense: Expense) -> None:
    session.delete(expense)
