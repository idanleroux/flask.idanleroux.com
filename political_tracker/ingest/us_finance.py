"""US campaign finance ingest — Phase 6.

Uses openFEC API to fetch candidate totals by source.
Correct endpoint: /candidate/{candidate_id}/totals/ (ID in URL path).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load .env file
load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FEC_BASE = "https://api.open.fec.gov/v1"
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CYCLES = [2022, 2024]


def build_session() -> requests.Session:
    """Build a requests session with polite retry logic."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = build_session()


def fetch_fec(endpoint, params):
    """Fetch from openFEC with retries, caching, and rate limiting."""
    api_key = os.environ.get("FEC_API_KEY")
    if not api_key:
        log.error("FEC_API_KEY not set")
        return None

    params = {**params, "api_key": api_key}
    url = f"{FEC_BASE}{endpoint}"

    cache_key = f"{endpoint}?{requests.compat.urlencode(params)}"
    cache_file = CACHE_DIR / f"fec_{abs(hash(cache_key))}.json"

    if cache_file.exists():
        import json
        log.info("Cache hit: %s", cache_name := endpoint)
        return json.loads(cache_file.read_text())

    log.info("Fetching openFEC: %s", endpoint)
    resp = SESSION.get(url, params=params, timeout=30)
    if resp.status_code == 429:
        log.warning("Rate limited, waiting 60s...")
        time.sleep(60)
        resp = SESSION.get(url, params=params, timeout=30)

    resp.raise_for_status()
    data = resp.json()

    import json
    cache_file.write_text(json.dumps(data))
    time.sleep(0.1)  # Throttle
    return data


def get_candidate_totals(fec_candidate_id, cycle):
    """Fetch candidate totals for a cycle.

    Uses the correct openFEC endpoint: /candidate/{candidate_id}/totals/
    """
    data = fetch_fec(f"/candidate/{fec_candidate_id}/totals/", {
        "cycle": cycle,
        "per_page": 1,
    })
    if not data or not data.get("results"):
        return None
    return data["results"][0]


# Mapping from openFEC API response fields to finance_us column names
FIELD_MAP = {
    "receipts": "total_receipts",
    "individual_itemized_contributions": "individual_itemised",
    "individual_unitemized_contributions": "individual_unitemised",
    "other_political_committee_contributions": "pac",
    "political_party_committee_contributions": "party_committee",
    "candidate_contribution": "candidate_self",
    "disbursements": "total_disbursements",
    "last_cash_on_hand_end_period": "cash_on_hand",
    "coverage_end_date": "coverage_end_date",
}


def upsert_finance(conn, member_id, cycle, totals):
    """Insert or update finance record."""
    if not totals:
        return

    with conn.cursor() as cur:
        values = {"member_id": member_id, "cycle": cycle}
        for api_field, col_name in FIELD_MAP.items():
            values[col_name] = totals.get(api_field)

        columns = ", ".join(values.keys())
        placeholders = ", ".join(["%s"] * len(values))
        update_clause = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in values.keys()
            if col not in ("member_id", "cycle")
        )

        cur.execute(f"""
            INSERT INTO political_tracker.finance_us
                ({columns})
            VALUES ({placeholders})
            ON CONFLICT (member_id, cycle) DO UPDATE SET
                {update_clause},
                updated_at = NOW()
        """, tuple(values.values()))
    conn.commit()


def run(cycles=None):
    if cycles is None:
        cycles = DEFAULT_CYCLES

    log.info("Starting US finance ingest (cycles=%s)...", cycles)

    api_key = os.environ.get("FEC_API_KEY")
    if not api_key:
        log.error("FEC_API_KEY not set (required for Phase 6)")
        sys.exit(1)

    dsn = os.environ.get("DATABASE_URL_INGEST")
    if not dsn:
        log.error("DATABASE_URL_INGEST not set")
        sys.exit(1)

    conn = psycopg.connect(dsn, prepare_threshold=None, sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, fec_candidate_id FROM political_tracker.members
                WHERE country = 'US' AND is_current AND fec_candidate_id IS NOT NULL
            """)
            members = cur.fetchall()

        log.info("Found %d US members with FEC candidate IDs", len(members))

        for i, (member_id, fec_id) in enumerate(members):
            for cycle in cycles:
                totals = get_candidate_totals(fec_id, cycle)
                if totals:
                    upsert_finance(conn, member_id, cycle, totals)
            if (i + 1) % 50 == 0:
                log.info("Processed %d/%d members", i + 1, len(members))

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('us_finance_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.now(timezone.utc).isoformat(),))
            conn.commit()

        log.info("US finance ingest complete")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="US campaign finance ingest (openFEC)")
    parser.add_argument("--cycles", type=int, nargs="*", default=DEFAULT_CYCLES,
                        help="Election cycles to fetch (default: %(default)s)")
    args = parser.parse_args()
    run(cycles=args.cycles)


if __name__ == "__main__":
    main()
