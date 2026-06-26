"""
Smoke test: runs every page of the app with a simulated logged-in session
and a pre-selected farm/season, asserting no unhandled exceptions occur.
Not part of the shipped app -- a dev-time verification script.
"""
import os
import sys
import uuid

os.environ["DATABASE_URL"] = "postgresql://cultivation:cultivation@localhost:5432/cultivation"

from streamlit.testing.v1 import AppTest

from db.base import session_scope
from db.models import Farm, Season

with session_scope() as s:
    farm = s.query(Farm).first()
    season = s.query(Season).filter(Season.farm_id == farm.id).first()
    USER_ID = str(season.user_id)
    FARM_ID = season.farm_id
    SEASON_ID = season.id

PAGES = [
    "Home.py",
    "pages/1_Farms_and_Seasons.py",
    "pages/2_Cultivation_Schedule.py",
    "pages/3_Weekly_Alerts.py",
    "pages/4_Expenses.py",
    "pages/5_Revenue.py",
    "pages/6_Profit_and_Loss.py",
    "pages/7_Observations.py",
]

# Fake AuthUser object matching auth.supabase_auth.AuthUser shape
class FakeAuthUser:
    def __init__(self, id, email):
        self.id = id
        self.email = email


failures = []

for page in PAGES:
    at = AppTest.from_file(page, default_timeout=30)
    at.session_state["auth_user"] = FakeAuthUser(id=USER_ID, email="[email protected]")
    at.session_state["active_farm_id"] = FARM_ID
    at.session_state["active_season_id"] = SEASON_ID
    at.run()

    if at.exception:
        failures.append((page, [str(e) for e in at.exception]))
        print(f"❌ {page}: EXCEPTION")
        for e in at.exception:
            print("   ", e)
    else:
        print(f"✅ {page}: OK ({len(at.main)} elements rendered)")

print()
if failures:
    print(f"FAILED: {len(failures)} page(s) raised exceptions.")
    sys.exit(1)
else:
    print("ALL PAGES RENDERED WITHOUT EXCEPTIONS")
