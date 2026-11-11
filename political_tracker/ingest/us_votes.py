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
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent.parent.parent / ".env")

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
    
    # Voteview files for 119th Congress (House + Senate)
    # Note: Voteview uses HS119 for House, S119 for Senate
    files = {
        # House
        "house_members": f"{VOTEVIEW_BASE}/members/HS119_members.csv",
        "house_rollcalls": f"{VOTEVIEW_BASE}/rollcalls/HS119_rollcalls.csv",
        "house_votes": f"{VOTEVIEW_BASE}/votes/HS119_votes.csv",
        # Senate
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
        # Voteview fields: icpsr, bioguide, name, party, state, district, ...
        bioguide = row.get('bioguide') or row.get('bioguide_id')
        if not bioguide:
            continue
        # Handle empty ideology score
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


def parse_voteview_rollcalls(csv_text, chamber, max_votes=100):
    """Parse Voteview rollcalls CSV - only most recent max_votes."""
    import csv
    import io
    from datetime import datetime
    
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
    
    # Sort by date descending and take most recent
    votes.sort(key=lambda v: v["vote_date"] or "", reverse=True)
    return votes[:max_votes]


def parse_voteview_votes(csv_text, keep_vote_ids=None):
    """Parse Voteview member votes CSV - optionally filter by vote IDs."""
    import csv
    import io
    votes = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        # Voteview fields: icpsr, rollnumber, cast_code
        # cast_code: 1-3 = yea, 4-6 = nay, 7-8 = present, 9 = not voting
        icpsr = row.get('icpsr')
        rollnumber = row.get('rollnumber') or row.get('rollcall')
        cast_code = row.get('cast_code') or row.get('vote')
        
        if not icpsr or not rollnumber or not cast_code:
            continue
        
        # Filter by keep_vote_ids if provided
        if keep_vote_ids is not None and rollnumber not in keep_vote_ids:
            continue
        
        # Map cast_code to position
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
    """Insert or update votes from Voteview."""
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


def upsert_member_votes(conn, mv_votes):
    """Full refresh: truncate and COPY fresh (no ON CONFLICT overhead)."""
    import io
    import csv
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, source_vote_id FROM political_tracker.votes
            WHERE country = 'US' AND session_or_congress = 119
        """)
        vote_map = {row[1]: row[0] for row in cur.fetchall()}
        
        cur.execute("""
            SELECT id, voteview_id FROM political_tracker.members
            WHERE country = 'US' AND voteview_id IS NOT NULL AND congress_or_parliament = 119
        """)
        member_map = {row[1]: row[0] for row in cur.fetchall()}
    
    # Build TSV in memory
    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t')
    total = 0
    
    for mv in mv_votes:
        vote_id = vote_map.get(mv["source_vote_id"])
        member_id = member_map.get(mv["voteview_id"])
        if vote_id and member_id:
            writer.writerow([vote_id, member_id, mv["position"]])
            total += 1
    
    log.info("Prepared %d member_votes for COPY", total)
    
    if total > 0:
        output.seek(0)
        with conn.cursor() as cur:
            # Disable pipeline for COPY
            old_pipeline = conn.pipeline
            conn.pipeline = False
            
            try:
                # Set statement timeout to 0 (unlimited) for this session
                cur.execute("SET statement_timeout = 0")
                
                # Full refresh: truncate then COPY directly (fastest, no index overhead)
                cur.execute("TRUNCATE political_tracker.member_votes")
                
                with cur.copy("COPY political_tracker.member_votes (vote_id, member_id, position) FROM STDIN") as copy:
                    copy.write(output.getvalue())
                
                conn.commit()
                log.info("COPY completed %d member_votes", total)
            finally:
                conn.pipeline = True


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
    dsn_direct = os.environ.get("DATABASE_URL_INGEST_DIRECT")
    if not dsn:
        log.error("DATABASE_URL_INGEST not set")
        sys.exit(1)

    # Use pooler connection for regular operations
    conn = psycopg.connect(dsn, prepare_threshold=None, sslmode="require")
    try:
        # 1. Legislators (congress-legislators)
        members = ingest_legislators()
        upsert_members(conn, members)

        # 2. Voteview data
        vv_data = ingest_voteview()
        
        # Parse and upsert House
        if vv_data.get("house_members"):
            hv_members = parse_voteview_members(vv_data["house_members"])
            upsert_voteview_members(conn, hv_members)
        
        if vv_data.get("senate_members"):
            sv_members = parse_voteview_members(vv_data["senate_members"])
            upsert_voteview_members(conn, sv_members)
        
        if vv_data.get("house_rollcalls"):
            hv_votes = parse_voteview_rollcalls(vv_data["house_rollcalls"], "house")
            upsert_votes(conn, hv_votes, "house")
            house_vote_ids = {v["source_vote_id"] for v in hv_votes}
        else:
            house_vote_ids = set()
        
        if vv_data.get("senate_rollcalls"):
            sv_votes = parse_voteview_rollcalls(vv_data["senate_rollcalls"], "senate")
            upsert_votes(conn, sv_votes, "senate")
            senate_vote_ids = {v["source_vote_id"] for v in sv_votes}
        else:
            senate_vote_ids = set()
        
        # For bulk member_votes, use direct connection to avoid pooler timeout
        if dsn_direct and (vv_data.get("house_votes") or vv_data.get("senate_votes")):
            log.info("Switching to direct connection for bulk member_votes...")
            conn.close()
            conn = psycopg.connect(dsn_direct, prepare_threshold=None, sslmode="require")
        
        if vv_data.get("house_votes"):
            hv_mv = parse_voteview_votes(vv_data["house_votes"], keep_vote_ids=house_vote_ids)
            upsert_member_votes(conn, hv_mv)
        
        if vv_data.get("senate_votes"):
            sv_mv = parse_voteview_votes(vv_data["senate_votes"], keep_vote_ids=senate_vote_ids)
            upsert_member_votes(conn, sv_mv)

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