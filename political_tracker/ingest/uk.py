"""UK Parliament data ingest — Phase 2.

Fetches current Commons members and divisions from Parliament APIs.

Run:
    python -m political_tracker.ingest.uk
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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from political_tracker.db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MEMBERS_API = "https://members-api.parliament.uk/api/Members/Search"
VOTES_API = "https://commonsvotes-api.parliament.uk/api/v1"

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default scope: current Parliament (since 9 July 2024)
DEFAULT_MAX_DIVISIONS = int(os.environ.get("UK_MAX_DIVISIONS", "0"))  # 0 = all


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


def fetch_with_cache(url, params=None, cache_name=None):
    """Fetch URL with disk cache, retries, and polite rate limiting."""
    if cache_name:
        cache_file = CACHE_DIR / f"{cache_name}.json"
        if cache_file.exists():
            log.info("Cache hit: %s", cache_name)
            import json
            return json.loads(cache_file.read_text())

    headers = {"Accept": "application/json"}
    resp = SESSION.get(url, params=params, headers=headers, timeout=30)
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


def ingest_votes(members_by_source_id, max_divisions=DEFAULT_MAX_DIVISIONS):
    """Fetch all divisions since start of current Parliament (9 July 2024).

    Args:
        max_divisions: Maximum number of recent divisions to load (0 = all).
    """
    log.info("Fetching UK votes...")
    
    # Get all divisions since Parliament start
    divisions_url = "https://commonsvotes-api.parliament.uk/api/v1/Divisions"
    params = {
        "startDate": "2024-07-09",
        "skip": 0,
        "take": 100,
    }
    
    all_divisions = []
    while True:
        data = fetch_with_cache(divisions_url, params, cache_name=f"uk_divisions_p{params['skip']//params['take']+1}")
        items = data.get("items", [])
        if not items:
            break
        all_divisions.extend(items)
        if len(items) < params["take"]:
            break
        params["skip"] += params["take"]
        # Stop if we've reached the max_divisions limit
        if max_divisions > 0 and len(all_divisions) >= max_divisions:
            all_divisions = all_divisions[:max_divisions]
            break
    
    log.info("Fetched %d divisions, fetching details...", len(all_divisions))
    
    votes = []
    member_votes = []
    
    for div in all_divisions:
        div_id = div.get("divisionId") or div.get("id")
        if not div_id:
            continue
            
        # Fetch division detail with member votes
        detail = fetch_with_cache(
            f"https://commonsvotes-api.parliament.uk/api/v1/Divisions/{div_id}",
            cache_name=f"uk_div_{div_id}"
        )
        
        # Parse division
        vote_date = detail.get("date") or detail.get("divisionDate")
        if not vote_date:
            continue
        vote_date = vote_date[:10]  # YYYY-MM-DD
        
        title = detail.get("title") or detail.get("motion") or "Division"
        result = detail.get("result") or detail.get("outcome") or ""
        ayes = detail.get("ayes") or detail.get("ayeCount") or 0
        noes = detail.get("noes") or detail.get("noCount") or 0
        
        # Get member votes
        aye_members = detail.get("ayeMembers") or detail.get("membersAye") or []
        no_members = detail.get("noMembers") or detail.get("membersNo") or []
        abstain_members = detail.get("abstainMembers") or detail.get("membersAbstain") or []
        
        votes.append({
            "source_vote_id": str(div_id),
            "vote_date": vote_date,
            "title": title,
            "question": detail.get("description", ""),
            "result": result,
            "ayes": ayes,
            "noes": noes,
            "session_or_congress": 59,  # Current Parliament number
        })
        
        # Map member votes to positions
        for m in aye_members:
            mid = str(m.get("memberId") or m.get("id"))
            if mid in members_by_source_id:
                member_votes.append({
                    "source_vote_id": str(div_id),
                    "member_source_id": mid,
                    "position": 1,  # Aye
                })
        for m in no_members:
            mid = str(m.get("memberId") or m.get("id"))
            if mid in members_by_source_id:
                member_votes.append({
                    "source_vote_id": str(div_id),
                    "member_source_id": mid,
                    "position": 2,  # No
                })
        for m in abstain_members:
            mid = str(m.get("memberId") or m.get("id"))
            if mid in members_by_source_id:
                member_votes.append({
                    "source_vote_id": str(div_id),
                    "member_source_id": mid,
                    "position": 3,  # Abstain
                })
        
        # Members not in any list = absent (we'll handle this in upsert)
    
    log.info("Parsed %d divisions with %d member votes", len(votes), len(member_votes))
    return votes, member_votes


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


def upsert_votes(conn, votes):
    """Insert or update votes in database."""
    with conn.cursor() as cur:
        for v in votes:
            cur.execute("""
                INSERT INTO political_tracker.votes
                    (country, chamber, source_vote_id, vote_date, title, question,
                     result, ayes, noes, session_or_congress)
                VALUES ('UK', 'commons', %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (country, chamber, source_vote_id, session_or_congress) DO UPDATE SET
                    vote_date = EXCLUDED.vote_date,
                    title = EXCLUDED.title,
                    question = EXCLUDED.question,
                    result = EXCLUDED.result,
                    ayes = EXCLUDED.ayes,
                    noes = EXCLUDED.noes
            """, (
                v["source_vote_id"], v["vote_date"], v["title"], v["question"],
                v["result"], v["ayes"], v["noes"], v["session_or_congress"]
            ))
    conn.commit()


def upsert_member_votes(conn, member_votes, members_by_source_id):
    """Insert member votes, setting absent for those not in lists."""
    # First get vote_id and member_id mappings
    with conn.cursor() as cur:
        # Get vote IDs
        cur.execute("""
            SELECT id, source_vote_id FROM political_tracker.votes
            WHERE country = 'UK' AND chamber = 'commons'
        """)
        vote_map = {row[1]: row[0] for row in cur.fetchall()}
        
        # Get member IDs
        cur.execute("""
            SELECT id, source_id FROM political_tracker.members
            WHERE country = 'UK' AND chamber = 'commons'
        """)
        member_map = {row[1]: row[0] for row in cur.fetchall()}
    
    # Prepare all member_vote records (including absent)
    all_records = []
    for mv in member_votes:
        vote_id = vote_map.get(mv["source_vote_id"])
        member_id = member_map.get(mv["member_source_id"])
        if vote_id and member_id:
            all_records.append((vote_id, member_id, mv["position"]))
    
    # Add absent for members not in any list for each vote
    # This is handled by the ON CONFLICT below - we insert all combinations
    # Actually, simpler: insert only what we have, absent is the default
    # But we need to ensure all members have a record for each vote
    # Let's do a more complete approach: get all members, all votes, cross product
    
    with conn.cursor() as cur:
        # Get all current members and votes
        cur.execute("SELECT id FROM political_tracker.members WHERE country = 'UK' AND chamber = 'commons' AND is_current")
        all_member_ids = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT id FROM political_tracker.votes WHERE country = 'UK' AND chamber = 'commons'")
        all_vote_ids = [row[0] for row in cur.fetchall()]
        
        # Build set of existing (vote_id, member_id) from member_votes
        existing = set()
        for mv in member_votes:
            vote_id = vote_map.get(mv["source_vote_id"])
            member_id = member_map.get(mv["member_source_id"])
            if vote_id and member_id:
                existing.add((vote_id, member_id))
        
        # Insert missing as absent (position 4)
        for vote_id in all_vote_ids:
            for member_id in all_member_ids:
                if (vote_id, member_id) not in existing:
                    cur.execute("""
                        INSERT INTO political_tracker.member_votes
                            (vote_id, member_id, position)
                        VALUES (%s, %s, 4)
                        ON CONFLICT (vote_id, member_id) DO UPDATE SET
                            position = EXCLUDED.position
                    """, (vote_id, member_id))
        
        # Now update positions for those who voted
        for mv in member_votes:
            vote_id = vote_map.get(mv["source_vote_id"])
            member_id = member_map.get(mv["member_source_id"])
            if vote_id and member_id:
                cur.execute("""
                    INSERT INTO political_tracker.member_votes
                        (vote_id, member_id, position)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (vote_id, member_id) DO UPDATE SET
                        position = EXCLUDED.position
                """, (vote_id, member_id, mv["position"]))
    
    conn.commit()
    log.info("Upserted member_votes for %d votes", len(vote_map))


def check_vote_integrity(conn):
    """Fail loudly if any member_votes.vote_id has no matching votes row.

    Checks UK commons parliament 59 rows.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*)
            FROM political_tracker.member_votes mv
            JOIN political_tracker.members m ON m.id = mv.member_id
            WHERE m.country = 'UK' AND m.chamber = 'commons' AND m.congress_or_parliament = 59
              AND NOT EXISTS (
                  SELECT 1 FROM political_tracker.votes v
                  WHERE v.id = mv.vote_id
                    AND v.country = 'UK' AND v.chamber = 'commons' AND v.session_or_congress = 59
              )
        """)
        orphaned = cur.fetchone()[0]

        cur.execute("""
            SELECT count(*) FROM political_tracker.member_votes mv
            JOIN political_tracker.members m ON m.id = mv.member_id
            WHERE m.country = 'UK' AND m.chamber = 'commons' AND m.congress_or_parliament = 59
        """)
        total = cur.fetchone()[0]

    if orphaned > 0:
        log.error("INTEGRITY FAILURE: %d of %d member_votes rows have no matching votes row",
                  orphaned, total)
        return False

    log.info("Integrity check passed: %d/%d member_votes rows reference valid votes",
             total, total)
    return True


def run(max_divisions=DEFAULT_MAX_DIVISIONS):
    """Main entry point for UK ingest.

    Args:
        max_divisions: Maximum number of recent divisions to load (0 = all).
    """
    log.info("Starting UK ingest (max_divisions=%s)...", max_divisions or "all")

    # Use DATABASE_URL_INGEST for write access
    dsn = os.environ.get("DATABASE_URL_INGEST")
    if not dsn:
        log.error("DATABASE_URL_INGEST not set")
        sys.exit(1)

    conn = psycopg.connect(dsn, prepare_threshold=None, sslmode="require")
    try:
        members = ingest_members()
        upsert_members(conn, members)

        # Build member lookup
        members_by_source_id = {m["source_id"]: m for m in members}

        # Fetch and upsert votes
        votes, member_votes = ingest_votes(members_by_source_id, max_divisions=max_divisions)
        if votes:
            upsert_votes(conn, votes)
            upsert_member_votes(conn, member_votes, members_by_source_id)

            # Integrity check
            if not check_vote_integrity(conn):
                log.error("Aborting due to vote integrity failure")
                sys.exit(1)

        # Update meta
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('uk_members_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.now(timezone.utc).isoformat(),))
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('uk_votes_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.now(timezone.utc).isoformat(),))
            conn.commit()

        log.info("UK ingest complete")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="UK Parliament data ingest")
    parser.add_argument("--max-divisions", type=int, default=DEFAULT_MAX_DIVISIONS,
                        help="Maximum number of recent divisions to load (0 = all, default: %(default)s)")
    args = parser.parse_args()
    run(max_divisions=args.max_divisions)


if __name__ == "__main__":
    main()