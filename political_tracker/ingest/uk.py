"""UK Parliament data ingest — Phase 2.

Fetches current Commons members and divisions from Parliament APIs.
"""

from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path

import psycopg
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from political_tracker.db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MEMBERS_API = "https://members-api.parliament.uk/api/Members/Search"
VOTES_API = "https://commonsvotes-api.parliament.uk/api/v1"

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_with_cache(url, params=None, cache_name=None):
    """Fetch URL with disk cache for resumability."""
    if cache_name:
        cache_file = CACHE_DIR / f"{cache_name}.json"
        if cache_file.exists():
            log.info("Cache hit: %s", cache_name)
            import json
            return json.loads(cache_file.read_text())

    headers = {"Accept": "application/json"}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if cache_name:
        import json
        cache_file.write_text(json.dumps(data))
        log.info("Cached: %s", cache_name)

    time.sleep(0.5)  # Be polite
    return data


def ingest_members():
    """Fetch all current Commons members."""
    log.info("Fetching UK members...")
    all_members = []
    page = 1
    page_size = 20

    while True:
        params = {
            "House": 1,  # Commons
            "IsCurrentMember": "true",
            "skip": (page - 1) * page_size,
            "take": page_size,
        }
        data = fetch_with_cache(MEMBERS_API, params, cache_name=f"uk_members_p{page}")

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            member = item.get("value", {})
            all_members.append({
                "source_id": str(member.get("id")),
                "full_name": member.get("nameDisplayAs", ""),
                "display_name": member.get("nameDisplayAs", ""),
                "party": member.get("party", {}).get("name") if member.get("party") else None,
                "party_code": member.get("party", {}).get("abbreviation") if member.get("party") else None,
                "constituency": member.get("latestHouseMembership", {}).get("membershipFrom", ""),
                "start_date": member.get("latestHouseMembership", {}).get("membershipStartDate"),
            })

        if len(items) < page_size:
            break
        page += 1

    log.info("Fetched %d members", len(all_members))
    return all_members


def ingest_votes(members_by_source_id):
    """Fetch all divisions since start of current Parliament."""
    log.info("Fetching UK votes...")
    # TODO: Implement divisions fetch from commonsvotes-api.parliament.uk
    # This is a stub for Phase 2
    return []


def upsert_members(conn, members):
    """Insert or update members in database."""
    with conn.cursor() as cur:
        for m in members:
            cur.execute("""
                INSERT INTO political_tracker.members
                    (country, chamber, source_id, full_name, display_name,
                     party, party_code, district_or_constituency, start_date,
                     is_current, congress_or_parliament)
                VALUES ('UK', 'commons', %s, %s, %s, %s, %s, %s, %s, TRUE, 59)
                ON CONFLICT (country, chamber, source_id, congress_or_parliament) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    display_name = EXCLUDED.display_name,
                    party = EXCLUDED.party,
                    party_code = EXCLUDED.party_code,
                    district_or_constituency = EXCLUDED.district_or_constituency,
                    start_date = EXCLUDED.start_date,
                    is_current = EXCLUDED.is_current,
                    updated_at = NOW()
            """, (
                m["source_id"], m["full_name"], m["display_name"],
                m["party"], m["party_code"], m["constituency"],
                m["start_date"]
            ))
    conn.commit()


def run():
    """Main entry point for UK ingest."""
    log.info("Starting UK ingest...")

    # Use DATABASE_URL_INGEST for write access
    dsn = os.environ.get("DATABASE_URL_INGEST")
    if not dsn:
        log.error("DATABASE_URL_INGEST not set")
        sys.exit(1)

    conn = psycopg.connect(dsn, prepare_threshold=None, sslmode="require")
    try:
        members = ingest_members()
        upsert_members(conn, members)

        # Update meta
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('uk_members_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.utcnow().isoformat(),))
            conn.commit()

        log.info("UK ingest complete")
    finally:
        conn.close()


if __name__ == "__main__":
    from datetime import datetime
    run()