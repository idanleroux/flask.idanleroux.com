"""US Congress data ingest — Phase 3.

Downloads Voteview CSVs and congress-legislators YAML for 119th Congress.
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

import psycopg
import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

VOTEVIEW_BASE = "https://voteview.com/static/data/out"
LEGISLATORS_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml"

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def download_file(url, cache_name):
    """Download file with caching."""
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        log.info("Cache hit: %s", cache_name)
        return cache_file.read_bytes()

    log.info("Downloading: %s", url)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    cache_file.write_bytes(resp.content)
    return resp.content


def ingest_legislators():
    """Fetch current legislators from YAML."""
    log.info("Fetching legislators...")
    content = download_file(LEGISLATORS_URL, "legislators-current.yaml")
    legislators = yaml.safe_load(content)

    members = []
    for leg in legislators:
        # Only current terms
        terms = leg.get("terms", [])
        if not terms:
            continue
        current_term = terms[-1]
        if current_term.get("type") not in ("rep", "sen"):
            continue

        # Get Bioguide ID
        bioguide = leg.get("id", {}).get("bioguide")
        if not bioguide:
            continue

        # Get FEC IDs
        fec_ids = leg.get("id", {}).get("fec", [])

        members.append({
            "bioguide": bioguide,
            "full_name": f"{leg['name']['first']} {leg['name']['last']}",
            "display_name": f"{leg['name']['first']} {leg['name']['last']}",
            "party": current_term.get("party"),
            "state": current_term.get("state"),
            "district": current_term.get("district"),
            "chamber": "house" if current_term.get("type") == "rep" else "senate",
            "fec_candidate_id": fec_ids[0] if fec_ids else None,
            "start_date": current_term.get("start"),
        })

    log.info("Fetched %d current legislators", len(members))
    return members


def ingest_voteview():
    """Download Voteview CSVs for 119th Congress."""
    log.info("Fetching Voteview data for 119th Congress...")
    # TODO: Download members, rollcalls, votes CSVs
    # This is a stub for Phase 3
    return [], [], []


def upsert_members(conn, members):
    """Insert or update US members."""
    with conn.cursor() as cur:
        for m in members:
            cur.execute("""
                INSERT INTO political_tracker.members
                    (country, chamber, source_id, full_name, display_name,
                     party, state_or_nation, district_or_constituency,
                     fec_candidate_id, start_date, is_current, congress_or_parliament)
                VALUES ('US', %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, 119)
                ON CONFLICT (country, chamber, source_id, congress_or_parliament) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    display_name = EXCLUDED.display_name,
                    party = EXCLUDED.party,
                    state_or_nation = EXCLUDED.state_or_nation,
                    district_or_constituency = EXCLUDED.district_or_constituency,
                    fec_candidate_id = EXCLUDED.fec_candidate_id,
                    start_date = EXCLUDED.start_date,
                    is_current = EXCLUDED.is_current,
                    updated_at = NOW()
            """, (
                m["chamber"], m["bioguide"], m["full_name"], m["display_name"],
                m["party"], m["state"], m["district"],
                m["fec_candidate_id"], m["start_date"]
            ))
    conn.commit()


def run():
    log.info("Starting US votes ingest...")

    dsn = os.environ.get("DATABASE_URL_INGEST")
    if not dsn:
        log.error("DATABASE_URL_INGEST not set")
        sys.exit(1)

    conn = psycopg.connect(dsn, prepare_threshold=None, sslmode="require")
    try:
        members = ingest_legislators()
        upsert_members(conn, members)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('us_votes_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.utcnow().isoformat(),))
            conn.commit()

        log.info("US votes ingest complete")
    finally:
        conn.close()


if __name__ == "__main__":
    from datetime import datetime
    run()