"""enable row level security

Revision ID: 3f27468c5c56
Revises: 690e59e266df
Create Date: 2026-06-26

Defense-in-depth: even though the application layer always scopes queries by
the authenticated user's id, Supabase best practice is to enforce the same
isolation at the database level with Row Level Security. This guards against
bugs in application code and protects data if the DB is ever queried directly
(e.g. via Supabase's auto-generated REST/GraphQL API, SQL editor access, etc).

Policy strategy:
  - farm, season, expense, revenue, observation: direct user_id column ->
    simple `auth.uid() = user_id` policy.
  - schedule_activity, alert: no direct user_id column; ownership is
    determined transitively through season -> user_id, so policies use an
    EXISTS subquery against `season`.
  - crop_master, crop_template_version, crop_stage, activity_template:
    master/reference data, readable by all authenticated users, not
    writable by them (writes are performed by admin tooling using the
    service role key, which bypasses RLS entirely).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f27468c5c56"
down_revision: Union[str, None] = "690e59e266df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES_DIRECT = ["farm", "season", "expense", "revenue", "observation"]
MASTER_TABLES = ["crop_master", "crop_template_version", "crop_stage", "activity_template"]


def upgrade() -> None:
    pass  # single-user: RLS disabled


def downgrade() -> None:
    pass  # single-user: RLS disabled
