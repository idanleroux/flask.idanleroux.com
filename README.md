# Flask Starter

A small Flask website with a reusable Jinja layout, a home page, and local static assets.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:5000>. Flask's debug reloader is enabled for local development.

## Structure

```text
main.py
templates/
  index.html
```

---

# Political Tracker

A module for browsing how current UK MPs and US members of Congress vote, which party they belong to, how similar members are to each other, and (for US members) a summary of campaign money.

## Routes

| Route | Description |
|-------|-------------|
| `GET /political_tracker` | Landing: choose US Congress or British Parliament |
| `GET /political_view_US` | US overview: House/Senate tabs, map/list views, search, filters |
| `GET /political_view_UK` | UK overview: map/list views, search, filters |
| `GET /political_view_US/member/<source_id>` | US member page: voting record, stats, similar members |
| `GET /political_view_UK/member/<member_id>` | UK member page: voting record, stats, similar members |
| `GET /political_view_US/compare` | Compare two US members |
| `GET /political_view_UK/compare` | Compare two UK members |
| `GET /political_tracker/about` | Data sources, definitions, limitations |

## Data sources (all free)

- UK Parliament Members API & Commons Votes API (no key needed)
- Voteview (UCLA) — US members, roll calls, votes (119th Congress)
- unitedstates/congress-legislators — US roster with Bioguide/FEC IDs
- openFEC (api.data.gov) — US campaign finance totals (free API key needed)
- ONS / US Census — boundary GeoJSON for maps

## Environment variables

| Variable | Purpose | Where set |
|----------|---------|-----------|
| `DATABASE_URL` | Supabase pooler string, read-only role (`tracker_ro`) | Render env vars; local `.env` |
| `DATABASE_URL_INGEST` | Supabase pooler string, write role | GitHub Actions secret; local `.env` |
| `FEC_API_KEY` | openFEC API key (api.data.gov) | Render env vars; local `.env` |
| `CONGRESS_API_KEY` | Congress.gov API key (optional, cross-checking) | Render env vars; local `.env` |

## Running ingest scripts

Ingest runs outside Render (locally or via GitHub Actions). It writes to Supabase using `DATABASE_URL_INGEST`.

```powershell
# Install ingest dependencies
pip install -r requirements-ingest.txt

# US Congress votes (Voteview, 119th Congress, last 100 votes per chamber)
python -m political_tracker.ingest.us_votes
US_MAX_VOTES=200 python -m political_tracker.ingest.us_votes --max-votes 200

# UK Parliament divisions (Commons Votes API)
python -m political_tracker.ingest.uk
UK_MAX_DIVISIONS=50 python -m political_tracker.ingest.uk --max-divisions 50

# US campaign finance (openFEC)
python -m political_tracker.ingest.us_finance
python -m political_tracker.ingest.us_finance --cycles 2022 2024
```

## Database setup

The schema lives in a dedicated `political_tracker` schema in Supabase. Run `political_tracker/schema.sql` in the Supabase SQL editor, then create the `tracker_ro` read-only role and grant SELECT on all tables. See `schema.sql` for the exact SQL.

## Refresh cadence

- Votes: weekly while Parliament/Congress is sitting
- Finance: monthly
- Each ingest is idempotent (safe to re-run)

## Deployment

Deployed on Render (free web tier). Data lives in Supabase (free Postgres tier). Render cannot run scheduled jobs, so ingest runs from GitHub Actions or the owner's machine. No redeploy is needed after a data refresh.
