"""US Congress data ingest — Phase 3.

Downloads Voteview CSVs and congress-legislators YAML for 119th Congress.
Writes vote rows and member_votes rows from the same source record using
the same id builder function, so vote_id references always match.

Run:
    python -m political_tracker.ingest.us_votes
    US_MAX_VOTES=200 python -m political_tracker.ingest.us_votes
    python -m political_tracker.ingest.us_votes --max-votes 50
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
import yaml
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load .env file
load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

VOTEVIEW_BASE = "https://voteview.com/static/data/out"
LEGISLATORS_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml"

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default: last 100 votes per chamber (disclaimer on about page)
DEFAULT_MAX_VOTES = int(os.environ.get("US_MAX_VOTES", "100"))


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


def download_file(url, cache_name, session=SESSION):
    """Download file with caching, retries, and polite rate limiting."""
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        log.info("Cache hit: %s", cache_name)
        return cache_file.read_bytes()

    log.info("Downloading: %s", url)
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    cache_file.write_bytes(resp.content)
    time.sleep(0.5)  # be polite
    return resp.content


def ingest_legislators():
    """Fetch current legislators from YAML."""
    log.info("Fetching legislators...")
    content = download_file(LEGISLATORS_URL, "legislators-current.yaml")
    legislators = yaml.safe_load(content)

    members = []
    for leg in legislators:
        terms = leg.get("terms", [])
        if not terms:
            continue
        current_term = terms[-1]
        if current_term.get("type") not in ("rep", "sen"):
            continue

        bioguide = leg.get("id", {}).get("bioguide")
        if not bioguide:
            continue

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


def ingest_voteview(max_votes=DEFAULT_MAX_VOTES):
    """Download Voteview CSVs for 119th Congress."""
    log.info("Fetching Voteview data for 119th Congress (max %d votes per chamber)...", max_votes)

    files = {
        "house_members": f"{VOTEVIEW_BASE}/members/HS119_members.csv",
        "house_rollcalls": f"{VOTEVIEW_BASE}/rollcalls/HS119_rollcalls.csv",
        "house_votes": f"{VOTEVIEW_BASE}/votes/HS119_votes.csv",
        "senate_members": f"{VOTEVIEW_BASE}/members/S119_members.csv",
        "senate_rollcalls": f"{VOTEVIEW_BASE}/rollcalls/S119_rollcalls.csv",
        "senate_votes": f"{VOTEVIEW_BASE}/votes/S119_votes.csv",
    }

    data = {}
    for name, url in files.items():
        content = download_file(url, f"voteview_{name}.csv")
        data[name] = content.decode('utf-8', errors='ignore')
        log.info("Downloaded %s (%d bytes)", name, len(content))

    return data


def parse_voteview_members(csv_text):
    """Parse Voteview members CSV."""
    import csv
    import io
    members = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        bioguide = row.get('bioguide') or row.get('bioguide_id')
        if not bioguide:
            continue
        ideol = row.get('nominate_dim1')
        try:
            ideology_score = float(ideol) if ideol and ideol.strip() else None
        except ValueError:
            ideology_score = None

        members.append({
            "bioguide": bioguide,
            "voteview_id": row.get('icpsr'),
            "full_name": row.get('name') or row.get('bioname'),
            "party": row.get('party_code') or row.get('party'),
            "ideology_score": ideology_score,
        })
    return members


def parse_voteview_rollcalls(csv_text, chamber, max_votes=DEFAULT_MAX_VOTES):
    """Parse Voteview rollcalls CSV - only most recent max_votes."""
    import csv
    import io

    votes = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        title = row.get('title') or row.get('desc') or 'Unknown vote'
        votes.append({
            "source_vote_id": row.get('rollnumber') or row.get('rollcall'),
            "vote_date": row.get('date'),
            "title": title,
            "question": row.get('question') or '',
            "result": row.get('result') or '',
            "ayes": int(row.get('yea') or row.get('aye') or 0),
            "noes": int(row.get('nay') or row.get('no') or 0),
            "chamber": chamber,
        })

    votes.sort(key=lambda v: v["vote_date"] or "", reverse=True)
    return votes[:max_votes]


def parse_voteview_votes(csv_text, keep_vote_ids=None):
    """Parse Voteview member votes CSV - optionally filter by vote IDs."""
    import csv
    import io
    votes = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        icpsr = row.get('icpsr')
        rollnumber = row.get('rollnumber') or row.get('rollcall')
        cast_code = row.get('cast_code') or row.get('vote')

        if not icpsr or not rollnumber or not cast_code:
            continue

        if keep_vote_ids is not None and rollnumber not in keep_vote_ids:
            continue

        code = int(cast_code)
        if 1 <= code <= 3:
            position = 1  # Yea
        elif 4 <= code <= 6:
            position = 2  # Nay
        elif code in (7, 8):
            position = 3  # Present/Abstain
        else:
            position = 4  # Not voting/Absent

        votes.append({
            "voteview_id": icpsr,
            "source_vote_id": rollnumber,
            "position": position,
        })
    return votes


def upsert_voteview_members(conn, vv_members):
    """Update members with Voteview data (ideology, voteview_id)."""
    with conn.cursor() as cur:
        for m in vv_members:
            if not m.get("bioguide"):
                continue
            cur.execute("""
                UPDATE political_tracker.members
                SET voteview_id = %s, ideology_score = %s, updated_at = NOW()
                WHERE country = 'US' AND source_id = %s AND congress_or_parliament = 119
            """, (m.get("voteview_id"), m.get("ideology_score"), m["bioguide"]))
    conn.commit()


def upsert_votes(conn, votes, chamber):
    """Insert or update votes from Voteview.

    Uses source_vote_id as the canonical external identifier.
    """
    with conn.cursor() as cur:
        for v in votes:
            cur.execute("""
                INSERT INTO political_tracker.votes
                    (country, chamber, source_vote_id, vote_date, title, question,
                     result, ayes, noes, session_or_congress)
                VALUES ('US', %s, %s, %s, %s, %s, %s, %s, %s, 119)
                ON CONFLICT (country, chamber, source_vote_id, session_or_congress) DO UPDATE SET
                    vote_date = EXCLUDED.vote_date,
                    title = EXCLUDED.title,
                    question = EXCLUDED.question,
                    result = EXCLUDED.result,
                    ayes = EXCLUDED.ayes,
                    noes = EXCLUDED.noes
            """, (
                chamber, v["source_vote_id"], v["vote_date"], v["title"],
                v["question"], v["result"], v["ayes"], v["noes"]
            ))
    conn.commit()


def upsert_member_votes(conn, mv_votes, chamber):
    """Full refresh of US member_votes for one chamber: delete then COPY fresh.

    The vote_id column is the internal votes.id, resolved by joining on
    source_vote_id so vote and member_votes always share the same id.
    Scoped to country='US' and chamber so UK member_votes and the other US
    chamber are not wiped.
    """
    import io
    import csv

    with conn.cursor() as cur:
        # Build vote_id map: source_vote_id -> internal id (this chamber only)
        cur.execute("""
            SELECT id, source_vote_id FROM political_tracker.votes
            WHERE country = 'US' AND chamber = %s AND session_or_congress = 119
        """, (chamber,))
        vote_map = {row[1]: row[0] for row in cur.fetchall()}

        # Build member_id map: voteview_id -> internal id (this chamber only)
        cur.execute("""
            SELECT id, voteview_id FROM political_tracker.members
            WHERE country = 'US' AND chamber = %s AND voteview_id IS NOT NULL AND congress_or_parliament = 119
        """, (chamber,))
        member_map = {row[1]: row[0] for row in cur.fetchall()}

    # Build TSV in memory
    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t')
    total = 0
    skipped = 0

    for mv in mv_votes:
        vote_id = vote_map.get(mv["source_vote_id"])
        member_id = member_map.get(mv["voteview_id"])
        if vote_id and member_id:
            writer.writerow([vote_id, member_id, mv["position"]])
            total += 1
        else:
            skipped += 1

    log.info("Prepared %d member_votes for %s (skipped %d unresolvable)", total, chamber, skipped)

    if total > 0:
        output.seek(0)
        with conn.cursor() as cur:
            old_pipeline = conn.pipeline
            conn.pipeline = False

            try:
                cur.execute("SET statement_timeout = 0")

                # Delete all member_votes for this chamber's members.
                # This removes orphaned rows (vote_id with no matching vote)
                # as well as stale rows, so the COPY starts from a clean slate.
                cur.execute("""
                    DELETE FROM political_tracker.member_votes mv
                    USING political_tracker.members m
                    WHERE mv.member_id = m.id
                      AND m.country = 'US' AND m.chamber = %s
                      AND m.congress_or_parliament = 119
                """, (chamber,))

                with cur.copy("COPY political_tracker.member_votes (vote_id, member_id, position) FROM STDIN") as copy:
                    copy.write(output.getvalue())

                conn.commit()
                log.info("COPY completed %d member_votes for %s", total, chamber)
            finally:
                conn.pipeline = True


def check_vote_integrity(conn):
    """Fail loudly if any member_votes.vote_id has no matching votes row.

    Checks only US congress 119 rows.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*)
            FROM political_tracker.member_votes mv
            JOIN political_tracker.members m ON m.id = mv.member_id
            WHERE m.country = 'US' AND m.congress_or_parliament = 119
              AND NOT EXISTS (
                  SELECT 1 FROM political_tracker.votes v
                  WHERE v.id = mv.vote_id
                    AND v.country = 'US' AND v.session_or_congress = 119
              )
        """)
        orphaned = cur.fetchone()[0]

        cur.execute("""
            SELECT count(*) FROM political_tracker.member_votes mv
            JOIN political_tracker.members m ON m.id = mv.member_id
            WHERE m.country = 'US' AND m.congress_or_parliament = 119
        """)
        total = cur.fetchone()[0]

    if orphaned > 0:
        log.error("INTEGRITY FAILURE: %d of %d member_votes rows have no matching votes row",
                  orphaned, total)
        return False

    log.info("Integrity check passed: %d/%d member_votes rows reference valid votes",
             total, total)
    return True


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


def run(max_votes=DEFAULT_MAX_VOTES):
    log.info("Starting US votes ingest (max_votes=%d)...", max_votes)

    dsn = os.environ.get("DATABASE_URL_INGEST")
    if not dsn:
        log.error("DATABASE_URL_INGEST not set")
        sys.exit(1)

    conn = psycopg.connect(dsn, prepare_threshold=None, sslmode="require")
    try:
        # 1. Legislators (congress-legislators)
        members = ingest_legislators()
        upsert_members(conn, members)

        # 2. Voteview data
        vv_data = ingest_voteview(max_votes=max_votes)

        if vv_data.get("house_members"):
            hv_members = parse_voteview_members(vv_data["house_members"])
            upsert_voteview_members(conn, hv_members)

        if vv_data.get("senate_members"):
            sv_members = parse_voteview_members(vv_data["senate_members"])
            upsert_voteview_members(conn, sv_members)

        if vv_data.get("house_rollcalls"):
            hv_votes = parse_voteview_rollcalls(vv_data["house_rollcalls"], "house", max_votes=max_votes)
            upsert_votes(conn, hv_votes, "house")
            house_vote_ids = {v["source_vote_id"] for v in hv_votes}
            log.info("House: %d votes loaded", len(hv_votes))
        else:
            house_vote_ids = set()

        if vv_data.get("senate_rollcalls"):
            sv_votes = parse_voteview_rollcalls(vv_data["senate_rollcalls"], "senate", max_votes=max_votes)
            upsert_votes(conn, sv_votes, "senate")
            senate_vote_ids = {v["source_vote_id"] for v in sv_votes}
            log.info("Senate: %d votes loaded", len(sv_votes))
        else:
            senate_vote_ids = set()

        if vv_data.get("house_votes"):
            hv_mv = parse_voteview_votes(vv_data["house_votes"], keep_vote_ids=house_vote_ids)
            upsert_member_votes(conn, hv_mv, "house")
            log.info("House: %d member_votes rows prepared", len(hv_mv))

        if vv_data.get("senate_votes"):
            sv_mv = parse_voteview_votes(vv_data["senate_votes"], keep_vote_ids=senate_vote_ids)
            upsert_member_votes(conn, sv_mv, "senate")
            log.info("Senate: %d member_votes rows prepared", len(sv_mv))

        # Integrity check
        if not check_vote_integrity(conn):
            log.error("Aborting due to vote integrity failure")
            sys.exit(1)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO political_tracker.meta (key, value, updated_at)
                VALUES ('us_votes_last_refresh', %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (datetime.now(timezone.utc).isoformat(),))
            conn.commit()

        log.info("US votes ingest complete")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="US Congress Voteview ingest")
    parser.add_argument("--max-votes", type=int, default=DEFAULT_MAX_VOTES,
                        help="Maximum number of recent votes per chamber (default: %(default)s)")
    args = parser.parse_args()
    run(max_votes=args.max_votes)


if __name__ == "__main__":
    main()
