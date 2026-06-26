# 🌱 Cultivation — Farm Cultivation Management

A clean, modern, production-quality web app that helps farmers answer four
questions every season:

1. **What should I do today?**
2. **What is due this week?**
3. **How much have I spent?**
4. **Am I making a profit?**

Built with **Streamlit, SQLAlchemy, Alembic, PostgreSQL (Supabase), Supabase
Auth, and Plotly.**

---

## Core philosophy: crop-driven, not hardcoded

The application contains **zero crop-specific logic in Python**. Every
activity, fertilizer dose, spray, irrigation cycle, and harvest window for
every crop is *data* in the `crop_master`, `crop_template_version`,
`crop_stage`, and `activity_template` tables — not `if crop == "Rice"`
branches in code.

When a farmer creates a **Season** (Farm + Crop + Variety + Sowing Date +
Area), the schedule engine (`services/schedule_engine.py`) reads the
`ActivityTemplate` rows for that crop's *current template version* and
projects each one's `day_offset` (days-after-sowing) onto the real calendar
using the sowing date. Repeating templates (e.g. "irrigate every 7 days, 10
times") explode into individual, independently-completable rows. Adding a
new crop means inserting rows — **no application code changes.**

Four crops ship pre-seeded as a working example: **Rice, Cotton, Tomato, and
Maize** (`seed/crop_master_seed.py`), each with realistic stage timing and
~13–17 activities spanning land prep through harvest.

### Versioned templates

Crop recommendations change over time -- a revised fertilizer dose, an extra
spray round, a corrected stage boundary. `CropMaster` itself holds no
schedule data; instead, `CropStage` and `ActivityTemplate` rows belong to a
specific `CropTemplateVersion`. Exactly one version per crop is marked
`is_current`, and that's the version offered when a farmer starts a *new*
season. Every `Season` pins `crop_template_version_id` at creation time and
keeps pointing at it forever -- revising a crop's recommendations (via
`seed.crop_master_seed.create_new_version`) only affects seasons created
*after* the revision. This makes retrospective analysis ("did following the
schedule correlate with yield?") trustworthy even as agronomic practice
evolves, since the historical record of what was actually recommended is
never silently rewritten.

### Field observations + AI analysis

`Observation` rows capture free-form field notes and optional photos against
a season, independent of the fixed schedule. `services/ai_engine.py` is the
single integration point for image analysis: given a photo, it returns a
structured read (category, confidence, plain-language analysis, and a
recommendation) which gets stored in the `ai_*` columns on the Observation --
never overwriting the farmer's own note or photo. The actual model call is
isolated behind a small `AIProvider` interface (default implementation uses
the Anthropic API) so it's swappable and fully mockable in tests; any
provider failure degrades to a clearly-labeled "unavailable" result rather
than raising, so a flaky AI integration can never break the core flow of
just saving a note and a photo.

---

## Architecture

```
Home.py                  Entry point: auth gate, routes into dashboard
pages/                   Streamlit native multipage app
  1_Farms_and_Seasons.py   Manage farms; create seasons (triggers schedule generation)
  2_Cultivation_Schedule.py Timeline: mark complete/skip, edit, add custom activities
  3_Weekly_Alerts.py        Red/Yellow/Green alerts derived from the schedule
  4_Expenses.py              Log + visualize cultivation costs
  5_Revenue.py                Log + visualize harvest sales
  6_Profit_and_Loss.py         Net P&L, cost/profit per acre, charts
  7_Observations.py             Field notes/photos + optional AI analysis

app/
  dashboard_view.py        The main dashboard (KPIs, alerts, charts)
  ui_helpers.py             Sidebar Farm/Season selector, formatting, Plotly theme

auth/
  supabase_auth.py          Supabase Auth wrapper (sign up/in/out, session state)

db/
  base.py                    SQLAlchemy engine/session
  models.py                  ORM models — the schema is the source of truth

services/                  Pure business logic, no Streamlit/DB-session coupling
  schedule_engine.py          Template -> dated ScheduleActivity projection
  alert_engine.py              Date-arithmetic alert derivation (no crop logic)
  pnl_engine.py                 Expense/Revenue -> P&L aggregation
  ai_engine.py                   Single integration point for image analysis

repositories/             Data-access layer (CRUD), one module per entity
  farm_repo.py / season_repo.py / crop_repo.py / schedule_repo.py
  expense_repo.py / revenue_repo.py / observation_repo.py

migrations/               Alembic migrations
  versions/..._initial_schema.py        All tables (incl. versioned templates, observations)
  versions/..._enable_row_level_security.py  Row Level Security policies

seed/
  crop_master_seed.py       Rice / Cotton / Tomato / Maize crop templates;
                              create_new_version() demonstrates safe revision
```

**Why this layering?** `services/` contains pure functions you can unit test
without a database or Streamlit (see the inline examples in each module's
docstring). `repositories/` is the only place that writes SQLAlchemy
queries. Pages only call repositories/services and render — no business
logic lives in a `.py` file under `pages/`.

---

## Database schema

Two clearly separated halves:

**Master data** (admin-curated, shared by all users, read-only to the app):
- `crop_master` — crop types (Rice, Cotton, Tomato, Maize, ...)
- `crop_template_version` — versioned snapshots of a crop's recommended
  schedule; exactly one version per crop is `is_current` at any time
- `crop_stage` — growth stages per version, defined by DAS ranges
- `activity_template` — the schedule "recipe" per version: DAS offset,
  category, name, optional repeat interval/count

**Tenant data** (per-user, isolated by Supabase Auth `user_id`):
- `farm`, `season` (pins `crop_template_version_id`), `schedule_activity`,
  `expense`, `revenue`, `observation`, `alert`

**Row Level Security** is enabled on every table (`migrations/versions/..._enable_row_level_security.py`)
as defense-in-depth: even though every repository query is explicitly
scoped by `user_id`, RLS policies enforce the same isolation at the
database level using `auth.uid()`, protecting against application bugs and
direct API/SQL access.

---

## Setup

### 1. Create a Supabase project
Create a project at supabase.com. You'll need, from
**Project Settings → API**: the Project URL and `anon` public key; and from
**Project Settings → Database → Connection string**: the pooled connection
URI (port 6543).

### 2. Configure secrets
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your Supabase URL, anon key, and DATABASE_URL
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run database migrations
```bash
export DATABASE_URL="<your Supabase pooled connection string>"
alembic upgrade head
```

### 5. Seed the Crop Master templates
```bash
python -m seed.crop_master_seed
```
This is idempotent for master data only — it clears and reloads
`crop_master`/`crop_stage`/`activity_template`, never touching farms,
seasons, or any tenant data.

### 6. (Optional) Configure AI analysis for Observations
To enable the AI photo-analysis feature on the Observations page, set an
Anthropic API key:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
Without it, the Observations page still works fully for logging notes and
photos -- it just skips the AI read and says so in the UI.

To store uploaded photos, create a `observations` bucket in your Supabase
project (**Storage → New Bucket**). Without it, photo uploads will show a
warning and the note is still saved without the photo.

### 7. Run the app
```bash
streamlit run Home.py
```

---

## Adding a new crop (no code changes required)

Add an entry to the `CROPS` list in `seed/crop_master_seed.py` following the
existing examples, then re-run:

```bash
python -m seed.crop_master_seed
```

This only adds crops that don't already exist (matched by name) -- it never
touches an existing crop's versions, so it's safe to run repeatedly against
an environment with live tenant data. The new crop's version 1 is
automatically marked current, and will appear in the "Create Season"
dropdown immediately.

## Revising an existing crop's schedule

**Never edit existing `CropStage`/`ActivityTemplate` rows in place** -- that
would retroactively change what past seasons were told to do. Instead, use
`seed.crop_master_seed.create_new_version()`:

```python
from seed.crop_master_seed import create_new_version
from db.models import ActivityCategory

create_new_version(
    crop_name="Rice (Paddy)",
    label="2027 Revised Nitrogen Schedule",
    change_notes="Split urea top-dressing into 3 doses per updated guidance.",
    stages=[...],      # same shape as CROPS[i]["stages"] in crop_master_seed.py
    activities=[...],  # same shape as CROPS[i]["activities"]
)
```

This creates version 2, marks it current, and demotes version 1 -- but
leaves version 1 and every season generated from it completely untouched.

---

## Testing

- `services/*.py` are pure functions — see the docstrings for inline
  example assertions you can paste into a REPL.
- `smoke_test.py` uses Streamlit's official `AppTest` framework to render
  every page against a real database with seeded data and assert no
  unhandled exceptions occur. Run with:
  ```bash
  python smoke_test.py
  ```

---

## Notes on extensibility (by design, not yet built)

- **Real photo storage in production**: the Observations page already
  attempts a real Supabase Storage upload (`pages/7_Observations.py:_upload_photo`)
  and degrades honestly with a warning if the `observations` bucket doesn't
  exist yet -- create the bucket to enable it fully.
- **Per-variety templates**: `activity_template` could gain an optional
  `variety` filter without schema changes elsewhere.
- **Multi-currency**: `format_currency` in `app/ui_helpers.py` is the single
  place a currency symbol is chosen.
- **Notifications** (SMS/WhatsApp/push for alerts): `alert_engine.py`
  already materializes `Alert` rows independent of the UI; a background
  job could read unread alerts and dispatch them.
- **Admin UI for Crop Master**: today templates are seeded/versioned via
  Python (`seed/crop_master_seed.py`); a simple CRUD page over
  `crop_master`/`crop_template_version`/`crop_stage`/`activity_template`
  (gated to an admin role) would let non-engineers manage crops and publish
  new versions without touching code.
- **Alternate AI providers**: `services/ai_engine.py`'s `AIProvider`
  protocol means swapping in a different vision model/provider (or an
  offline/on-device model for low-connectivity areas) only requires a new
  class implementing `analyze_image()` -- no changes to
  `analyze_observation()` or any page that calls it.
