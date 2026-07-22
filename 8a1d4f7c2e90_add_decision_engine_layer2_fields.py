"""add layer1.5/layer2 decision engine fields

Revision ID: 8a1d4f7c2e90
Revises: 3f27468c5c56
Create Date: 2026-06-30

Adds the Decision Engine fields to activity_template (Layer 1.5/Layer 2
support: is_conditional, feeds_context, trigger_logic, trigger_conditions)
and provenance fields to schedule_activity (triggered_by_condition,
triggered_by_observation_id) so an AI-triggered conditional activity can
always answer "why did this show up?" without guessing.

server_default values on activity_template make every existing row become
is_conditional=False, feeds_context=False (plain Layer 1) -- zero behavior
change until v3+ template rows explicitly opt into Layer 1.5/2.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "8a1d4f7c2e90"
down_revision = "3f27468c5c56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity_template",
        sa.Column("is_conditional", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "activity_template",
        sa.Column("feeds_context", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "activity_template",
        sa.Column("trigger_logic", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "activity_template",
        sa.Column("trigger_conditions", postgresql.JSONB(), nullable=True),
    )

    op.add_column(
        "schedule_activity",
        sa.Column("triggered_by_condition", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "schedule_activity",
        sa.Column(
            "triggered_by_observation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_schedule_activity_triggered_by_observation_id",
        "schedule_activity",
        "observation",
        ["triggered_by_observation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_schedule_activity_triggered_by_observation_id",
        "schedule_activity",
        type_="foreignkey",
    )
    op.drop_column("schedule_activity", "triggered_by_observation_id")
    op.drop_column("schedule_activity", "triggered_by_condition")
    op.drop_column("activity_template", "trigger_conditions")
    op.drop_column("activity_template", "trigger_logic")
    op.drop_column("activity_template", "feeds_context")
    op.drop_column("activity_template", "is_conditional")
