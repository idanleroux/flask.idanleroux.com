"""US campaign finance ingest — Phase 6.

Uses openFEC API to fetch candidate totals by source.
"""

from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path

import psycopg
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FEC_BASE = "https://api.open.fec.gov/v1"
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_fec(endpoint, params):
    """Fetch from openFEC with rate limiting and caching."""
    api_key = os.environ.get("FEC_API_KEY")
    if not api_key:
        log.error("FEC_API_KEY not set")
        return None

    params = {**params, "api_key": api_key}
    url = f"{FEC_BASE}{endpoint}"

    # Simple in-memory cache for this run
    cache_key = f"{endpoint}?{requests.compat.urlencode(params)}"
    cache_file = CACHE_DIR / f"fec_{hash(cache_key)}.json"

    if cache_file.exists():
        import json
        return json.loads(cache_file.read_text())

    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code == 429:
        log.warning("Rate limited, waiting 60s...")
        time.sleep(60)
        resp = requests.get(url, params=params, timeout=30)

    resp.raise_for_status()
    data = resp.json()

    import json
    cache_file.write_text(json.dumps(data))
    time.sleep(0.1)  # Throttle
    return data


def get_candidate_totals(fec_candidate_id, cycle):
    """Fetch candidate totals for a cycle."""
    data = fetch_fec("/candidate/totals/", {
        "candidate_id": fec_candidate_id,
        "cycle": cycle,
        "per_page": 1,
    })
    if not data or not data.get("results"):
        return None
    return data["results"][0]


def upsert_finance(conn, member_id, cycle, totals):
    """Insert or update finance record."""
    if not totals:
        return

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO political_tracker.finance_us
                (member_id, cycle, coverage_end_date,
                 total_receipts, individual_itemised, individual_unitemised,
                 pac, party_committee, candidate_self,
                 total_disbursements, cash_on_hand)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (member_id, cycle) DO UPDATE SET
                coverage_end_date = EXCLUDED.coverage_end_date,
                total_receipts = EXCLUDED.total_receipts,
                individual_itemised = EXCLUDED.individual_itemised,
                individual_unitemised = EXCLUDED.individual_unitemised,
                pac = EXCLUDED.pac,
                party_committee = EXCLUDED.party_committee,
                candidate_self = EXCLUDED.candidate_self,
                total_disbursements = EXCLUDED.total_disbursements,
                cash_on_hand = EXCLUDED.cash_on_hand,
                updated_at = NOW()
        """, (
            member_id, cycle,
            totals.get("coverage_end_date"),
            totals.get("total_receipts"),
            totals.get("individual_itemized_contributions"),
            totals.get("individual_unitemized_contributions"),
            totals.get("pac_contributions"),
            totals.get("party_committee_contributions"),
            totals.get("candidate_contributions"),
            totals.get("total_disbursements"),
            totals.get("cash_on_hand"),
        ))
    conn.commit()


def run():
    log.info("Starting US finance ingest...")

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
        # Get all current US members with FEC IDs
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, fec_candidate_id FROM political_tracker.members
                WHERE country = 'US' AND is_current AND fec_candidate_id IS NOT NULL
            """)
            members = cur.fetchall()

        cycles = [2022, 2024]  # Two most recent cycles

        for member_id, fec_id in members:
            for cycle in cycles:
                log.info("Fetching finance for member %s cycle %d", fec_id, cycle)
                totals = get_candidate_totals(fec_id, cycle)
                if totals:
                    upsert_finance(conn, member_id, cycle, totals)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('us_finance_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.utcnow().isoformat(),))
            conn.commit()

        log.info("US finance ingest complete")
    finally:
        conn.close()


if __name__ == "__main__":
    from datetime import datetime
    run()