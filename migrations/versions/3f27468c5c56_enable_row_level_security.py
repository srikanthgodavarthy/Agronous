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
    # --- Direct-ownership tenant tables ---------------------------------
    for table in TENANT_TABLES_DIRECT:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_select_own ON {table} FOR SELECT USING (auth.uid() = user_id);"
        )
        op.execute(
            f"CREATE POLICY {table}_insert_own ON {table} FOR INSERT WITH CHECK (auth.uid() = user_id);"
        )
        op.execute(
            f"CREATE POLICY {table}_update_own ON {table} FOR UPDATE "
            f"USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);"
        )
        op.execute(
            f"CREATE POLICY {table}_delete_own ON {table} FOR DELETE USING (auth.uid() = user_id);"
        )

    # --- schedule_activity: ownership via season.user_id -----------------
    op.execute("ALTER TABLE schedule_activity ENABLE ROW LEVEL SECURITY;")
    sa_condition = (
        "EXISTS (SELECT 1 FROM season s WHERE s.id = schedule_activity.season_id "
        "AND s.user_id = auth.uid())"
    )
    op.execute(
        f"CREATE POLICY schedule_activity_select_own ON schedule_activity "
        f"FOR SELECT USING ({sa_condition});"
    )
    op.execute(
        f"CREATE POLICY schedule_activity_insert_own ON schedule_activity "
        f"FOR INSERT WITH CHECK ({sa_condition});"
    )
    op.execute(
        f"CREATE POLICY schedule_activity_update_own ON schedule_activity "
        f"FOR UPDATE USING ({sa_condition}) WITH CHECK ({sa_condition});"
    )
    op.execute(
        f"CREATE POLICY schedule_activity_delete_own ON schedule_activity "
        f"FOR DELETE USING ({sa_condition});"
    )

    # --- alert: ownership via season.user_id ------------------------------
    op.execute("ALTER TABLE alert ENABLE ROW LEVEL SECURITY;")
    alert_condition = (
        "EXISTS (SELECT 1 FROM season s WHERE s.id = alert.season_id AND s.user_id = auth.uid())"
    )
    op.execute(
        f"CREATE POLICY alert_select_own ON alert FOR SELECT USING ({alert_condition});"
    )
    op.execute(
        f"CREATE POLICY alert_insert_own ON alert FOR INSERT WITH CHECK ({alert_condition});"
    )
    op.execute(
        f"CREATE POLICY alert_update_own ON alert FOR UPDATE USING ({alert_condition}) "
        f"WITH CHECK ({alert_condition});"
    )
    op.execute(
        f"CREATE POLICY alert_delete_own ON alert FOR DELETE USING ({alert_condition});"
    )

    # --- Master/reference data: readable by any authenticated user -------
    for table in MASTER_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_read_all ON {table} "
            f"FOR SELECT USING (auth.role() = 'authenticated');"
        )
        # No INSERT/UPDATE/DELETE policy for regular users -> all writes
        # (including creating a new CropTemplateVersion) must go through the
        # service-role key (used by admin/seed scripts), which bypasses RLS
        # by design in Supabase.


def downgrade() -> None:
    for table in TENANT_TABLES_DIRECT:
        for action in ["select", "insert", "update", "delete"]:
            op.execute(f"DROP POLICY IF EXISTS {table}_{action}_own ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    for action in ["select", "insert", "update", "delete"]:
        op.execute(f"DROP POLICY IF EXISTS schedule_activity_{action}_own ON schedule_activity;")
    op.execute("ALTER TABLE schedule_activity DISABLE ROW LEVEL SECURITY;")

    for action in ["select", "insert", "update", "delete"]:
        op.execute(f"DROP POLICY IF EXISTS alert_{action}_own ON alert;")
    op.execute("ALTER TABLE alert DISABLE ROW LEVEL SECURITY;")

    for table in MASTER_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read_all ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
