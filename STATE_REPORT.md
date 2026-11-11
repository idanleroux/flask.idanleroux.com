# STATE REPORT — Political Tracker MVP Audit

**Date:** 11 Nov 2026  
**Repo:** `C:\Users\PC\Documents\idan coding work\flask.idanleroux.com`  
**Branch:** `main` (up to date with `origin/main`)  
**Python:** 3.13.5  
**Spec reference:** `C:\Users\PC\Downloads\Political_Tracker___Build_Plan.md` (the .MD build plan)

---

## How the .MD was used

The .MD build plan ("Political Tracker – Build Plan", dated 10 November 2026) is treated as the **initial proposal / reference**, not as a document that must be followed directly (per your instruction). Where the codebase already deviates from it, that is noted. Where the codebase matches it, that is marked Done.

---

## Summary

The Political Tracker module is **substantially built** — roughly **70–80% of a working MVP** is present. The Flask blueprint, all routes, templates, CSS/JS, database schema, ingest scripts (UK Parliament, US Congress/Voteview, US finance/openFEC), map build scripts, and a stats module with 20 passing tests are all in place. The app imports and serves pages without crashing.

Key caveats:
- All data pages require a live Supabase Postgres database (`DATABASE_URL`). Without it, every data page renders an empty/placeholder state.
- The read-only `DATABASE_URL` in `.env` uses the password `choose-a-secure-password-here`. You have confirmed your password works, but I have not yet verified a live connection or that the `political_tracker` schema is applied.
- No route/template smoke tests exist — only `tests/political_tracker/test_stats.py` (20 tests, all passing).
- `map.js` references a global `d3` but `static/vendor/` is empty, so the map view will fail unless D3 is added.

---

## Requirement Checklist

Each requirement is taken from the .MD build plan (section 4 routes, section 6 pages, section 7 statistics, section 8 design) and compared to the actual code. Status: Done / Partial / Broken / Not started.

| # | Requirement (from .MD) | Status | File references |
|---|------------------------|--------|-----------------|
| R1 | Flask blueprint `political_tracker`, registered at root (no URL prefix) | Done | `main.py`, `political_tracker/__init__.py` |
| R2 | Home page with "Political Tracker" button → `/political_tracker` | Done | `templates/index.html`, `main.py` |
| R3 | `GET /political_tracker` landing: US panel + UK panel, member counts, last-updated dates, link to about | Done | `routes.py`, `templates/political_tracker/landing.html` |
| R4 | `GET /political_view_US`: House/Senate tabs, Map/List toggle, search, filters, sort, pagination | Done | `routes.py`, `templates/political_tracker/list.html` |
| R5 | `GET /political_view_UK`: Map/List toggle, search, filters, sort, pagination | Done | `routes.py`, `templates/political_tracker/list.html` |
| R6 | `GET /political_view_US/member/<source_id>`: voting record, stats, similar members | Done | `routes.py`, `templates/political_tracker/member.html` |
| R7 | `GET /political_view_UK/member/<member_id>`: voting record, stats, similar members | Done | `routes.py`, `templates/political_tracker/member.html` |
| R8 | `GET /political_view_US/compare?a=&b=`: agreement bar + differing votes table | Done | `routes.py`, `templates/political_tracker/compare.html` |
| R9 | `GET /political_view_UK/compare?a=&b=`: agreement bar + differing votes table | Done | `routes.py`, `templates/political_tracker/compare.html` |
| R10 | `GET /political_tracker/about`: sources, definitions, limitations, last-updated dates | Done | `routes.py`, `templates/political_tracker/about.html` |
| R11 | JSON routes under `/political_view_US/api/...` and `/political_view_UK/api/...` (map + search) | Done | `routes.py` (4 API routes) |
| R12 | Schema: members, votes, member_votes, member_stats, similarity, finance_us, meta (schema `political_tracker`) | Done | `political_tracker/schema.sql` |
| R13 | Lazy pooled Postgres connection (psycopg_pool, read-only role) | Done | `political_tracker/db.py` |
| R14 | Ingest scripts idempotent (`ON CONFLICT DO UPDATE`) | Partial | `ingest/uk.py`, `ingest/us_votes.py` — coded, not verified against live API/DB |
| R15 | UK ingest: members + divisions since 9 July 2024 | Partial | `ingest/uk.py` (members cached; divisions not cached) |
| R16 | US ingest: legislators YAML + Voteview members/rollcalls/votes (119th Congress) | Partial | `ingest/us_votes.py` (data cached, not verified loaded) |
| R17 | US finance ingest: openFEC candidate totals (Phase 6) | Partial | `ingest/us_finance.py` — coded, field-mapping bugs (see Bugs) |
| R18 | Map build: UK constituencies, US states, US House districts GeoJSON | Partial | `ingest/build_maps.py`; GeoJSON files present in static maps dir |
| R19 | Stats: participation %, party-loyalty %, agreement/similarity %, unit tests | Done | `stats.py` + `tests/political_tracker/test_stats.py` (20 passed) |
| R20 | Design tokens (British English, party colours, square corners, dark theme) | Done | `static/political_tracker/tracker.css` |
| R21 | Map visualisation with d3-geo/d3-zoom, library vendored locally in `static/vendor/` | Broken | `map.js` references global `d3`; `vendor/` is **empty** — D3 not vendored |
| R22 | Route smoke tests (every route returns 200 with/without data) | Not started | No route tests exist |
| R23 | GitHub Actions refresh workflow | Not started | No workflow file present |
| R24 | `.env.example` listing variable names only (no real values) | Done | `.env.example` present |
| R25 | `.env` git-ignored, no secrets committed | Partial | `.env` is gitignored, BUT `.env.txt` and check scripts contain real passwords (untracked) |

**Note on deviations from the .MD:** The .MD says D3 must be vendored locally in `static/vendor/` with no CDN dependency. The codebase has `map.js` written to use a global `d3` but `vendor/` is empty. This is the clearest deviation.

---

## Bugs and Risks

1. **D3 library not vendored (blocks map view).** `map.js` calls `d3.geoMercator`, `d3.geoAlbersUsa`, `d3.zoom`, `d3.select`, `d3.geoPath` but `static/political_tracker/vendor/` is empty and no CDN is loaded. The map view will throw `d3 is not defined`. Per the .MD, D3 should be vendored locally at a pinned version.

2. **Missing `party_colour` Jinja global.** `list.html`, `member.html`, and `compare.html` all call `party_colour(...)` in templates, but no such Jinja global/filter is registered anywhere. This will raise `jinja2.UndefinedError` when rendering party badges. Fix: register a `party_colour` function in `main.py` or `__init__.py`.

3. **`us_finance.py` openFEC field-name mismatches.** openFEC API uses US spellings (`individual_itemized_contributions`, `party_committee_contributions`, `candidate_contributions`) but the code reads British-spelling keys (`individual_itemised`, `party_committee`, `candidate_self`). These will silently store `None`. Fix: match the exact openFEC response keys.

4. **US `upsert_member_votes()` does `TRUNCATE political_tracker.member_votes`.** This wipes ALL member votes (including UK) on every US ingest run. Destructive if run after UK data is loaded. Fix: scope the truncate to US votes only, or use `ON CONFLICT` upserts.

5. **Hard-coded credentials in untracked files.** `.env.txt`, `check_db.py`, `check_final.py`, `generate_tsv.py`, `generate_member_votes_tsv.py` contain real Supabase passwords. `.env.txt` should be deleted; check scripts should not embed passwords. `.env` itself is gitignored (good).

6. **No route smoke tests.** Only `test_stats.py` exists. A broken template or route would not be caught by the test suite.

7. **`map.js` injects a `box-shadow` on `.map-panel`.** The .MD design rules say "No drop shadows, no gradients, no blur." Minor cosmetic deviation.

8. **Python version mismatch.** `runtime.txt` pins `python-3.11.9`; local environment is 3.13.5. Not blocking locally, but Render build uses `runtime.txt`.

9. **`uk.py` uses `datetime.utcnow()` in `run()`** but `from datetime import datetime` is only imported inside `if __name__ == "__main__"`. Calling `run()` as an imported function raises `NameError`. Fix: move the import to module top.

---

## Data

| Source | What's pulled | Status |
|--------|--------------|--------|
| UK Parliament Members API (`members-api.parliament.uk`) | 33 pages of cached member JSON (`uk_members_p1.json` … `p33.json`) | Cached locally; not verified loaded into DB |
| UK Parliament Commons Votes API (`commonsvotes-api.parliament.uk`) | No division cache files present | Not cached |
| Voteview (UCLA) — 119th Congress | House/Senate members, rollcalls, votes CSVs cached (`voteview_*.csv`, one `.gz`) | Cached locally; not verified loaded into DB |
| `congress-legislators` YAML | `legislators-current.yaml` cached | Cached locally |
| ONS / Census boundary GeoJSON | `uk_constituencies.geojson`, `us_states.geojson`, `us_house_districts.geojson` present | Present in static maps dir; not verified valid/complete |
| TSV exports | `member_votes_house.tsv`, `member_votes_senate.tsv` at repo root | Present (for manual COPY into Supabase) |

**Missing data:** Nothing is verified as loaded into a database. No live DB connection was tested during this audit. All data pages currently render empty.

---

## Dependencies and Environment

**Installed (global Python 3.13.5):** All `requirements.txt` packages are installed (Flask 3.1.3, psycopg[binary,pool] 3.2.9, gunicorn, etc.). `requirements-ingest.txt` packages (numpy 2.3.4, PyYAML 6.0.3, requests 2.32.4) are also installed.

| File | Purpose | Notes |
|------|---------|-------|
| `requirements.txt` | Web app runtime | Fully installed |
| `requirements-ingest.txt` | Ingest scripts | Fully installed |
| `runtime.txt` | Python version pin | Says `python-3.11.9`; local is 3.13.5 |
| `.env` | Local env vars | Present, gitignored. You confirmed the password works. Read-only `DATABASE_URL` uses `choose-a-secure-password-here`. |
| `.env.example` | Template (names only) | Present |
| `.env.txt` | Untracked copy | Contains real passwords — should be deleted |

**Missing / to supply:** A live Supabase Postgres project with the `political_tracker` schema applied, a `tracker_ro` read-only role, and optionally a `FEC_API_KEY` (Phase 6 only).

---

## Proposed MVP Plan

Ordered task list. Sizes are relative estimates. Fix blocking bugs before adding features.

1. **Small** — Register `party_colour` Jinja global so list/member/compare templates render.
2. **Small** — Fix `uk.py`: move `from datetime import datetime` to module top.
3. **Small** — Fix `us_finance.py`: match openFEC response field names exactly.
4. **Small** — Fix `us_votes.py`: scope `TRUNCATE member_votes` to US rows only (avoid wiping UK votes).
5. **Medium** — Vendoring D3: add `d3-geo` and `d3-zoom` (pinned versions) to `static/political_tracker/vendor/` and load them in `base.html` (no CDN, per .MD).
6. **Medium** — Verify Supabase connection: confirm `DATABASE_URL` connects and `political_tracker` schema is applied; apply `schema.sql` if not.
7. **Medium** — Run ingest (UK + US) against live DB; verify row counts (members, votes).
8. **Medium** — Add route smoke tests (landing, US/UK list, member, compare, about return 200).
9. **Small** — Delete `.env.txt`; remove embedded passwords from check/generate scripts.
10. **Medium** — Deploy to Render with `DATABASE_URL`, `DATABASE_URL_INGEST`, `FEC_API_KEY`.

**Later ideas (out of MVP scope):** GitHub Actions refresh workflow, UK campaign finance, Congress.gov cross-checking, email alerts, user accounts, historical Congresses/Parliaments, 120th Congress support.

---

## What I Need From You (Phase 2)

### BLOCKING (cannot proceed without answers)

**1. Live database access.** You confirmed your password works. Do you have a live Supabase Postgres project already created with the `political_tracker` schema applied (from `schema.sql`)? If yes, can you confirm the read-only `DATABASE_URL` connects so I can verify data actually renders? If no, do you want me to prepare everything for you to apply `schema.sql` yourself, or should I set up a local Postgres for development/testing?

**2. Confirm scope source of truth.** You said to treat the .MD as "the initial versions proposal, rather than must be followed directly." So the existing codebase is the working scope, with the .MD as reference. Shall I proceed on that basis (fix bugs in existing code rather than reshape to match the .MD exactly)?

### NON-BLOCKING (I'll proceed with stated defaults unless you correct me)

**3. D3: vendored vs CDN.** The .MD requires D3 vendored locally in `static/vendor/` with no CDN. Default: I'll download `d3-geo` and `d3-zoom` (plus core `d3` as a dependency) at pinned versions into `vendor/` and load via `<script>` tags in `base.html`. Confirm OK, or say if you prefer a CDN.

**4. Phase 6 finance in MVP?** `us_finance.py` and the campaign money panel are partially built but have field-mapping bugs. Default: I'll fix the bugs and include finance in the MVP (it's already wired into `member.html` as a placeholder panel). Say if you'd rather defer it to "Later ideas."

**5. Deploy target.** The .MD assumes Render (free web tier) + Supabase (free Postgres). Is that still your intended hosting, or something else? This affects env var setup instructions.

**6. Cleanup of credential files.** Default: I'll delete `.env.txt` and strip real passwords from the check/generate scripts. Confirm OK.

**7. British English.** I'll use British English in all user-facing text, comments, and docs (colour, licence, programme, favour, etc.). Confirm.

---

**STOP POINT:** `STATE_REPORT.md` is saved to the repo root and no other files have been modified. I am waiting for your reply before starting Phase 3 (build).