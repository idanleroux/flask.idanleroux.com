"""Compute member_stats and similarity tables from existing DB data.

Uses DATABASE_URL_INGEST (write connection) to read member_votes and
populate political_tracker.member_stats and political_tracker.similarity.

Run: python compute_stats.py
"""
from __future__ import annotations

import os
import sys
from dotenv import load_dotenv
load_dotenv()

import psycopg
import numpy as np

from political_tracker.stats import (
    POS_YES, POS_NO, POS_ABSTAIN, POS_ABSENT,
    is_voting_position, participation_pct, party_loyalty_pct,
)

DSN = os.environ.get("DATABASE_URL_INGEST")
if not DSN:
    print("ERROR: DATABASE_URL_INGEST not set")
    sys.exit(1)


def fetch_chamber_data(conn, country, chamber, congress):
    """Fetch members and their votes for a chamber."""
    with conn.cursor() as cur:
        # Members
        cur.execute("""
            SELECT id, display_name, party, party_code
            FROM political_tracker.members
            WHERE country = %s AND chamber = %s AND congress_or_parliament = %s
            ORDER BY id
        """, (country, chamber, congress))
        members = cur.fetchall()
        member_ids = [m[0] for m in members]

        if not member_ids:
            return members, [], {}, {}

        # Votes
        cur.execute("""
            SELECT v.id
            FROM political_tracker.votes v
            WHERE v.country = %s AND v.chamber = %s AND v.session_or_congress = %s
            ORDER BY v.id
        """, (country, chamber, congress))
        vote_ids = [v[0] for v in cur.fetchall()]

        if not vote_ids:
            return members, [], {}, {}

        # Member votes
        placeholders = ",".join(["%s"] * len(member_ids))
        cur.execute(f"""
            SELECT mv.member_id, mv.vote_id, mv.position, mv.party_at_vote
            FROM political_tracker.member_votes mv
            WHERE mv.member_id IN ({placeholders})
        """, tuple(member_ids))
        mv_rows = cur.fetchall()

    member_votes = {mid: {} for mid in member_ids}
    mv_count = 0
    for mid, vid, pos, patv in mv_rows:
        member_votes[mid][vid] = (pos, patv)
        mv_count += 1
    print(f"  member_votes rows fetched: {mv_count}, members with votes: {sum(1 for v in member_votes.values() if v)}")

    # Build vote_party_majors: {vote_id: {party: (majority_pos, voting_count)}}
    vote_member_positions = {}  # {vote_id: [(position, party_at_vote)]}
    for mid in member_ids:
        for vid, (pos, patv) in member_votes[mid].items():
            if vid not in vote_member_positions:
                vote_member_positions[vid] = []
            vote_member_positions[vid].append((pos, patv))

    vote_party_majors = {}
    for vid, positions in vote_member_positions.items():
        party_counts = {}  # {party: {POS_YES: n, POS_NO: n}}
        for pos, patv in positions:
            if not is_voting_position(pos):
                continue
            party = patv
            if not party:
                continue
            if party not in party_counts:
                party_counts[party] = {POS_YES: 0, POS_NO: 0}
            party_counts[party][pos] += 1

        result = {}
        for party, counts in party_counts.items():
            yes_count = counts[POS_YES]
            no_count = counts[POS_NO]
            if yes_count > no_count:
                result[party] = (POS_YES, yes_count + no_count)
            elif no_count > yes_count:
                result[party] = (POS_NO, yes_count + no_count)
            else:
                result[party] = (0, yes_count + no_count)  # tie
        vote_party_majors[vid] = result

    return members, vote_ids, member_votes, vote_party_majors


def compute_member_stats(conn, members, vote_ids, member_votes, vote_party_majors):
    """Compute and upsert member_stats for a list of members."""
    rows = []
    for mid, display_name, party, party_code in members:
        mv_list = member_votes.get(mid, {})
        member_vote_entries = [
            (vid, pos, patv) for vid, (pos, patv) in mv_list.items()
        ]

        votes_eligible = 0
        votes_cast = 0
        for vid, pos, patv in member_vote_entries:
            if vid not in vote_party_majors:
                continue
            votes_eligible += 1
            if is_voting_position(pos):
                votes_cast += 1

        pct = participation_pct(votes_eligible, votes_cast)
        loyalty = party_loyalty_pct(member_vote_entries, vote_party_majors)

        # Votes against party count
        against_count = 0
        for vid, pos, patv in member_vote_entries:
            if not is_voting_position(pos):
                continue
            party_data = vote_party_majors.get(vid)
            if not party_data:
                continue
            majority_pos, party_count = party_data.get(patv, (0, 0))
            if party_count < 2 or majority_pos == 0:
                continue
            if pos != majority_pos:
                against_count += 1

        rows.append((mid, votes_eligible, votes_cast, pct, loyalty, against_count))

    if rows:
        with conn.cursor() as cur:
            for mid, ve, vc, pp, lp, ac in rows:
                cur.execute("""
                    INSERT INTO political_tracker.member_stats
                        (member_id, votes_eligible, votes_cast, participation_pct,
                         party_loyalty_pct, votes_against_party_count, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (member_id) DO UPDATE SET
                        votes_eligible = EXCLUDED.votes_eligible,
                        votes_cast = EXCLUDED.votes_cast,
                        participation_pct = EXCLUDED.participation_pct,
                        party_loyalty_pct = EXCLUDED.party_loyalty_pct,
                        votes_against_party_count = EXCLUDED.votes_against_party_count,
                        updated_at = NOW()
                """, (mid, ve, vc, pp, lp, ac))
            conn.commit()
    print(f"  member_stats: {len(rows)} rows upserted")
    return rows


def compute_similarity(conn, members, vote_ids, member_votes, country, chamber, congress):
    """Compute and upsert similarity for all member pairs in a chamber."""
    member_ids = [m[0] for m in members]
    if len(member_ids) < 2 or not vote_ids:
        print("  similarity: skipped (< 2 members or no votes)")
        return 0

    n_members = len(member_ids)
    n_votes = len(vote_ids)

    vote_idx = {vid: i for i, vid in enumerate(vote_ids)}
    member_idx = {mid: i for i, mid in enumerate(member_ids)}

    matrix = np.zeros((n_members, n_votes), dtype=np.int16)
    for mid, votes in member_votes.items():
        if mid not in member_idx:
            continue
        mi = member_idx[mid]
        for vid, (pos, patv) in votes.items():
            if vid not in vote_idx:
                continue
            vi = vote_idx[vid]
            if pos == POS_YES:
                matrix[mi, vi] = 1
            elif pos == POS_NO:
                matrix[mi, vi] = -1

    # Shared votes and agreement via matrix products
    voted = (matrix != 0).astype(np.int16)
    shared_matrix = voted @ voted.T
    dot_matrix = matrix @ matrix.T
    agreed_matrix = (dot_matrix + shared_matrix) // 2

    rows = []
    pairs_checked = 0
    pairs_ge20 = 0
    for i in range(n_members):
        for j in range(i + 1, n_members):
            pairs_checked += 1
            shared = int(shared_matrix[i, j])
            if shared >= 20:
                pairs_ge20 += 1
                agreed = int(agreed_matrix[i, j])
                pct = round(agreed / shared * 100, 2)
                ma, mb = member_ids[i], member_ids[j]
                if ma > mb:
                    ma, mb = mb, ma
                rows.append((ma, mb, shared, agreed, pct))
    print(f"  similarity: {pairs_ge20}/{pairs_checked} pairs >= 20 shared votes")

    if rows:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM political_tracker.similarity
                WHERE member_a IN (
                    SELECT id FROM political_tracker.members
                    WHERE country = %s AND chamber = %s AND congress_or_parliament = %s
                )
                OR member_b IN (
                    SELECT id FROM political_tracker.members
                    WHERE country = %s AND chamber = %s AND congress_or_parliament = %s
                )
            """, (country, chamber, congress, country, chamber, congress))
            for ma, mb, shared, agreed, pct in rows:
                cur.execute("""
                    INSERT INTO political_tracker.similarity
                        (member_a, member_b, shared_votes, agreed_votes, agreement_pct, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (member_a, member_b) DO UPDATE SET
                        shared_votes = EXCLUDED.shared_votes,
                        agreed_votes = EXCLUDED.agreed_votes,
                        agreement_pct = EXCLUDED.agreement_pct,
                        updated_at = NOW()
                """, (ma, mb, shared, agreed, pct))
            conn.commit()
    print(f"  similarity: {len(rows)} pairs upserted (>=20 shared votes)")
    return len(rows)


def main():
    conn = psycopg.connect(DSN, prepare_threshold=None, sslmode="require")
    try:
        chambers = [
            ("US", "house", 119),
            ("US", "senate", 119),
            ("UK", "commons", 59),
        ]
        for country, chamber, congress in chambers:
            print(f"\n=== {country} {chamber} ({congress}) ===")
            members, vote_ids, member_votes, vote_party_majors = fetch_chamber_data(
                conn, country, chamber, congress
            )
            print(f"  members: {len(members)}, votes: {len(vote_ids)}")
            compute_member_stats(conn, members, vote_ids, member_votes, vote_party_majors)
            compute_similarity(conn, members, vote_ids, member_votes, country, chamber, congress)
    finally:
        conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
