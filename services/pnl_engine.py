"""
Profit & Loss calculation engine.

Pure, side-effect-free aggregation over Expense/Revenue rows for a season
(or set of seasons). Kept separate from repositories so the math is unit
testable without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from db.models import Expense, ExpenseCategory, Revenue


@dataclass
class PnLSummary:
    total_expenses: Decimal
    total_revenue: Decimal
    net_profit: Decimal
    area: Decimal
    profit_per_acre: Decimal
    cost_per_acre: Decimal
    expense_by_category: dict[str, Decimal] = field(default_factory=dict)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calculate_pnl(expenses: list[Expense], revenues: list[Revenue], area: float | Decimal) -> PnLSummary:
    area_dec = _to_decimal(area) if area else Decimal("0")

    total_expenses = sum((_to_decimal(e.amount) for e in expenses), Decimal("0"))
    total_revenue = sum((_to_decimal(r.amount) for r in revenues), Decimal("0"))
    net_profit = total_revenue - total_expenses

    by_category: dict[str, Decimal] = {}
    for e in expenses:
        key = e.category.value if isinstance(e.category, ExpenseCategory) else str(e.category)
        by_category[key] = by_category.get(key, Decimal("0")) + _to_decimal(e.amount)

    if area_dec > 0:
        profit_per_acre = net_profit / area_dec
        cost_per_acre = total_expenses / area_dec
    else:
        profit_per_acre = Decimal("0")
        cost_per_acre = Decimal("0")

    return PnLSummary(
        total_expenses=total_expenses,
        total_revenue=total_revenue,
        net_profit=net_profit,
        area=area_dec,
        profit_per_acre=profit_per_acre,
        cost_per_acre=cost_per_acre,
        expense_by_category=by_category,
    )
