"""add recovery engine fields to activity_template

Revision ID: c1a9f3e6b204
Revises: 8a1d4f7c2e90
Create Date: 2026-07-06

Adds recovery metadata to activity_template so the Recovery Engine
(services/decisions/recovery_engine.py) can decide what to do with a
PENDING activity once it's overdue, instead of the app blindly
recommending whatever's oldest:

    valid_until_stage        -- last CropStage name this activity is still
                                 valid in (NULL = never expires by stage)
    max_delay_days           -- grace period in days past the planned date
                                 (NULL = no day-based cap)
    recovery_type            -- REPLACE / SKIP / ESCALATE, applied once the
                                 window above has closed (NULL = no
                                 authored strategy yet -> legacy fallback)
    replacement_template_id  -- self-referential FK, only used when
                                 recovery_type == REPLACE
    expected_impact          -- short note shown on the recommendation card

All columns nullable with no server_default other than NULL, so every
existing activity_template row is completely unaffected until seed data
explicitly opts in -- zero behavior change until a template sets these.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c1a9f3e6b204"
down_revision = "8a1d4f7c2e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity_template",
        sa.Column("valid_until_stage", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "activity_template",
        sa.Column("max_delay_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "activity_template",
        sa.Column("recovery_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "activity_template",
        sa.Column("replacement_template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "activity_template",
        sa.Column("expected_impact", sa.String(length=255), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_template_replacement_template_id",
        "activity_template",
        "activity_template",
        ["replacement_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_activity_template_replacement_template_id",
        "activity_template",
        type_="foreignkey",
    )
    op.drop_column("activity_template", "expected_impact")
    op.drop_column("activity_template", "replacement_template_id")
    op.drop_column("activity_template", "recovery_type")
    op.drop_column("activity_template", "max_delay_days")
    op.drop_column("activity_template", "valid_until_stage")
