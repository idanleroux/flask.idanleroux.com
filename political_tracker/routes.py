"""Political Tracker page routes."""

from flask import (
    render_template,
    request,
    current_app,
    abort,
)

from political_tracker import bp
from political_tracker.db import get_db


@bp.get("/political_tracker")
def landing():
    """Landing page: choose US Congress or British Parliament."""
    us_stats = {"current_members": 0, "last_updated": None}
    uk_stats = {"current_members": 0, "last_updated": None}

    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute("""
                    SELECT
                        country,
                        COUNT(*) FILTER (WHERE is_current) AS current_members,
                        MAX(updated_at) AS last_updated
                    FROM political_tracker.members
                    GROUP BY country
                """)
                stats = {row[0]: {"current_members": row[1], "last_updated": row[2]} for row in cur.fetchall()}
                us_stats = stats.get("US", us_stats)
                uk_stats = stats.get("UK", uk_stats)
    except Exception:
        # Database not available - show placeholder data
        pass

    return render_template(
        "political_tracker/landing.html",
        us_stats=us_stats,
        uk_stats=uk_stats,
    )


@bp.get("/political_view_US")
def us_overview():
    """US overview: House/Senate tabs, map/list views, search, filters."""
    chamber = request.args.get("chamber", "house")
    view = request.args.get("view", "list")
    party = request.args.get("party")
    state = request.args.get("state")
    current_only = request.args.get("current", "1") == "1"
    sort = request.args.get("sort", "name")
    page = max(1, int(request.args.get("page", "1")))
    per_page = 50

    # Validate chamber
    if chamber not in ("house", "senate"):
        chamber = "house"

    members = []
    parties = []
    states = []
    total = 0

    try:
        with get_db() as db:
            with db.cursor() as cur:
                # Build WHERE clause
                where = ["country = 'US'", "chamber = %s"]
                params = [chamber]

                if party:
                    where.append("party = %s")
                    params.append(party)
                if state:
                    where.append("state_or_nation = %s")
                    params.append(state)
                if current_only:
                    where.append("is_current")

                where_sql = " AND ".join(where)

                # Total count for pagination
                cur.execute(f"SELECT COUNT(*) FROM political_tracker.members WHERE {where_sql}", params)
                total = cur.fetchone()[0]

                # Get members with stats
                order_map = {
                    "name": "display_name",
                    "state": "state_or_nation, display_name",
                    "participation": "ms.participation_pct DESC NULLS LAST",
                    "loyalty": "ms.party_loyalty_pct DESC NULLS LAST",
                }
                order_sql = order_map.get(sort, "display_name")

                cur.execute(f"""
                    SELECT
                        m.id, m.source_id, m.display_name, m.party, m.party_code,
                        m.state_or_nation, m.district_or_constituency,
                        m.start_date, m.is_current, m.ideology_score,
                        ms.votes_eligible, ms.votes_cast, ms.participation_pct,
                        ms.party_loyalty_pct, ms.votes_against_party_count
                    FROM political_tracker.members m
                    LEFT JOIN political_tracker.member_stats ms ON ms.member_id = m.id
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT %s OFFSET %s
                """, params + [per_page, (page - 1) * per_page])
                members = cur.fetchall()

                # Get filter options
                cur.execute("SELECT DISTINCT party FROM political_tracker.members WHERE country = 'US' AND chamber = %s AND party IS NOT NULL ORDER BY party", (chamber,))
                parties = [r[0] for r in cur.fetchall()]

                cur.execute("SELECT DISTINCT state_or_nation FROM political_tracker.members WHERE country = 'US' AND chamber = %s AND state_or_nation IS NOT NULL ORDER BY state_or_nation", (chamber,))
                states = [r[0] for r in cur.fetchall()]
    except Exception:
        # Database not available - show empty state
        pass

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "political_tracker/list.html",
        country="US",
        chamber=chamber,
        view=view,
        members=members,
        parties=parties,
        states=states,
        current_filters={
            "party": party,
            "state": state,
            "current": current_only,
            "sort": sort,
        },
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    )


@bp.get("/political_view_UK")
def uk_overview():
    """UK overview: map/list views, search, filters."""
    view = request.args.get("view", "list")
    party = request.args.get("party")
    nation = request.args.get("nation")
    current_only = request.args.get("current", "1") == "1"
    sort = request.args.get("sort", "name")
    page = max(1, int(request.args.get("page", "1")))
    per_page = 50

    members = []
    parties = []
    nations = []
    total = 0

    try:
        with get_db() as db:
            with db.cursor() as cur:
                where = ["country = 'UK'", "chamber = 'commons'"]
                params = []

                if party:
                    where.append("party = %s")
                    params.append(party)
                if nation:
                    where.append("state_or_nation = %s")
                    params.append(nation)
                if current_only:
                    where.append("is_current")

                where_sql = " AND ".join(where)

                cur.execute(f"SELECT COUNT(*) FROM political_tracker.members WHERE {where_sql}", params)
                total = cur.fetchone()[0]

                order_map = {
                    "name": "display_name",
                    "constituency": "district_or_constituency, display_name",
                    "participation": "ms.participation_pct DESC NULLS LAST",
                    "against_party": "ms.votes_against_party_count DESC NULLS LAST",
                }
                order_sql = order_map.get(sort, "display_name")

                cur.execute(f"""
                    SELECT
                        m.id, m.source_id, m.display_name, m.party, m.party_code,
                        m.state_or_nation, m.district_or_constituency, m.ons_code,
                        m.start_date, m.is_current,
                        ms.votes_eligible, ms.votes_cast, ms.participation_pct,
                        ms.votes_against_party_count
                    FROM political_tracker.members m
                    LEFT JOIN political_tracker.member_stats ms ON ms.member_id = m.id
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT %s OFFSET %s
                """, params + [per_page, (page - 1) * per_page])
                members = cur.fetchall()

                cur.execute("SELECT DISTINCT party FROM political_tracker.members WHERE country = 'UK' AND chamber = 'commons' AND party IS NOT NULL ORDER BY party")
                parties = [r[0] for r in cur.fetchall()]

                cur.execute("SELECT DISTINCT state_or_nation FROM political_tracker.members WHERE country = 'UK' AND chamber = 'commons' AND state_or_nation IS NOT NULL ORDER BY state_or_nation")
                nations = [r[0] for r in cur.fetchall()]
    except Exception:
        # Database not available - show empty state
        pass

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "political_tracker/list.html",
        country="UK",
        chamber="commons",
        view=view,
        members=members,
        parties=parties,
        nations=nations,
        current_filters={
            "party": party,
            "nation": nation,
            "current": current_only,
            "sort": sort,
        },
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    )


@bp.get("/political_view_US/member/<source_id>")
def us_member(source_id):
    """US member page."""
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT
                    m.id, m.source_id, m.voteview_id, m.full_name, m.display_name,
                    m.party, m.party_code, m.state_or_nation, m.district_or_constituency,
                    m.start_date, m.is_current, m.image_url, m.ideology_score,
                    m.fec_candidate_id, m.congress_or_parliament,
                    ms.votes_eligible, ms.votes_cast, ms.participation_pct,
                    ms.party_loyalty_pct, ms.votes_against_party_count
                FROM political_tracker.members m
                LEFT JOIN political_tracker.member_stats ms ON ms.member_id = m.id
                WHERE m.country = 'US' AND m.source_id = %s
            """, (source_id,))
            member = cur.fetchone()

    if not member:
        abort(404)

    # Convert to dict for easier template access
    cols = [d[0] for d in cur.description] if cur.description else []
    member = dict(zip(cols, member)) if cols else {}

    # Voting record - paginated
    page = max(1, int(request.args.get("page", "1")))
    per_page = 25
    position_filter = request.args.get("position")
    against_party = request.args.get("against_party") == "1"

    with get_db() as db:
        with db.cursor() as cur:
            where = ["mv.member_id = %s"]
            params = [member["id"]]

            if position_filter:
                where.append("mv.position = %s")
                params.append(int(position_filter))
            if against_party:
                where.append("mv.voted_against_party")

            where_sql = " AND ".join(where)

            cur.execute(f"SELECT COUNT(*) FROM political_tracker.member_votes mv JOIN political_tracker.votes v ON v.id = mv.vote_id WHERE {where_sql}", params)
            total_votes = cur.fetchone()[0]

            cur.execute(f"""
                SELECT
                    v.id, v.vote_date, v.title, v.question, v.result,
                    mv.position, mv.party_at_vote, mv.voted_against_party,
                    CASE mv.position WHEN 1 THEN 'Aye' WHEN 2 THEN 'No' WHEN 3 THEN 'Abstain' ELSE 'Absent' END AS position_label
                FROM political_tracker.member_votes mv
                JOIN political_tracker.votes v ON v.id = mv.vote_id
                WHERE {where_sql}
                ORDER BY v.vote_date DESC
                LIMIT %s OFFSET %s
            """, params + [per_page, (page - 1) * per_page])
            votes = cur.fetchall()

            # Similar members
            cur.execute("""
                SELECT
                    m2.id, m2.display_name, m2.party, m2.state_or_nation,
                    s.shared_votes, s.agreed_votes, s.agreement_pct
                FROM political_tracker.similarity s
                JOIN political_tracker.members m2 ON m2.id = s.member_b
                WHERE s.member_a = %s AND s.shared_votes >= 20
                ORDER BY s.agreement_pct DESC
                LIMIT 10
            """, (member["id"],))
            most_similar = cur.fetchall()

            cur.execute("""
                SELECT
                    m2.id, m2.display_name, m2.party, m2.state_or_nation,
                    s.shared_votes, s.agreed_votes, s.agreement_pct
                FROM political_tracker.similarity s
                JOIN political_tracker.members m2 ON m2.id = s.member_b
                WHERE s.member_a = %s AND s.shared_votes >= 20
                ORDER BY s.agreement_pct ASC
                LIMIT 10
            """, (member["id"],))
            least_similar = cur.fetchall()

    total_vote_pages = (total_votes + per_page - 1) // per_page

    return render_template(
        "political_tracker/member.html",
        country="US",
        member=member,
        votes=votes,
        vote_pagination={"page": page, "per_page": per_page, "total": total_votes, "total_pages": total_vote_pages},
        vote_filters={"position": position_filter, "against_party": against_party},
        most_similar=most_similar,
        least_similar=least_similar,
    )


@bp.get("/political_view_UK/member/<int:member_id>")
def uk_member(member_id):
    """UK member page."""
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT
                    m.id, m.source_id, m.full_name, m.display_name,
                    m.party, m.party_code, m.state_or_nation, m.district_or_constituency,
                    m.ons_code, m.start_date, m.is_current,
                    ms.votes_eligible, ms.votes_cast, ms.participation_pct,
                    ms.votes_against_party_count
                FROM political_tracker.members m
                LEFT JOIN political_tracker.member_stats ms ON ms.member_id = m.id
                WHERE m.country = 'UK' AND m.id = %s
            """, (member_id,))
            member = cur.fetchone()

    if not member:
        abort(404)

    cols = [d[0] for d in cur.description] if cur.description else []
    member = dict(zip(cols, member)) if cols else {}

    page = max(1, int(request.args.get("page", "1")))
    per_page = 25
    position_filter = request.args.get("position")
    against_party = request.args.get("against_party") == "1"

    with get_db() as db:
        with db.cursor() as cur:
            where = ["mv.member_id = %s"]
            params = [member_id]

            if position_filter:
                where.append("mv.position = %s")
                params.append(int(position_filter))
            if against_party:
                where.append("mv.voted_against_party")

            where_sql = " AND ".join(where)

            cur.execute(f"SELECT COUNT(*) FROM political_tracker.member_votes mv JOIN political_tracker.votes v ON v.id = mv.vote_id WHERE {where_sql}", params)
            total_votes = cur.fetchone()[0]

            cur.execute(f"""
                SELECT
                    v.id, v.vote_date, v.title, v.question, v.result,
                    mv.position, mv.party_at_vote, mv.voted_against_party,
                    CASE mv.position WHEN 1 THEN 'Aye' WHEN 2 THEN 'No' WHEN 3 THEN 'Abstain' ELSE 'Absent' END AS position_label
                FROM political_tracker.member_votes mv
                JOIN political_tracker.votes v ON v.id = mv.vote_id
                WHERE {where_sql}
                ORDER BY v.vote_date DESC
                LIMIT %s OFFSET %s
            """, params + [per_page, (page - 1) * per_page])
            votes = cur.fetchall()

            cur.execute("""
                SELECT
                    m2.id, m2.display_name, m2.party, m2.district_or_constituency,
                    s.shared_votes, s.agreed_votes, s.agreement_pct
                FROM political_tracker.similarity s
                JOIN political_tracker.members m2 ON m2.id = s.member_b
                WHERE s.member_a = %s AND s.shared_votes >= 20
                ORDER BY s.agreement_pct DESC
                LIMIT 10
            """, (member_id,))
            most_similar = cur.fetchall()

            cur.execute("""
                SELECT
                    m2.id, m2.display_name, m2.party, m2.district_or_constituency,
                    s.shared_votes, s.agreed_votes, s.agreement_pct
                FROM political_tracker.similarity s
                JOIN political_tracker.members m2 ON m2.id = s.member_b
                WHERE s.member_a = %s AND s.shared_votes >= 20
                ORDER BY s.agreement_pct ASC
                LIMIT 10
            """, (member_id,))
            least_similar = cur.fetchall()

    total_vote_pages = (total_votes + per_page - 1) // per_page

    return render_template(
        "political_tracker/member.html",
        country="UK",
        member=member,
        votes=votes,
        vote_pagination={"page": page, "per_page": per_page, "total": total_votes, "total_pages": total_vote_pages},
        vote_filters={"position": position_filter, "against_party": against_party},
        most_similar=most_similar,
        least_similar=least_similar,
    )


@bp.get("/political_view_US/compare")
def us_compare():
    """Compare two US members."""
    a_id = request.args.get("a")
    b_id = request.args.get("b")

    if not a_id or not b_id:
        return render_template("political_tracker/compare.html", country="US", error="Select two members to compare")

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT id, source_id, display_name, party, state_or_nation FROM political_tracker.members WHERE country = 'US' AND source_id IN (%s, %s)", (a_id, b_id))
            members = cur.fetchall()

            if len(members) != 2:
                return render_template("political_tracker/compare.html", country="US", error="One or both members not found")

            m1, m2 = members[0], members[1]

            # Ensure consistent ordering for similarity lookup
            member_a, member_b = sorted([m1[0], m2[0]])

            cur.execute("""
                SELECT shared_votes, agreed_votes, agreement_pct
                FROM political_tracker.similarity
                WHERE member_a = %s AND member_b = %s
            """, (member_a, member_b))
            sim = cur.fetchone()

            # Votes where they differed
            cur.execute("""
                SELECT
                    v.vote_date, v.title, v.question,
                    mv1.position AS pos_a, mv2.position AS pos_b
                FROM political_tracker.member_votes mv1
                JOIN political_tracker.member_votes mv2 ON mv2.vote_id = mv1.vote_id
                JOIN political_tracker.votes v ON v.id = mv1.vote_id
                WHERE mv1.member_id = %s AND mv2.member_id = %s
                  AND mv1.position IN (1, 2) AND mv2.position IN (1, 2)
                  AND mv1.position != mv2.position
                ORDER BY v.vote_date DESC
                LIMIT 50
            """, (m1[0], m2[0]))
            differing_votes = cur.fetchall()

    return render_template(
        "political_tracker/compare.html",
        country="US",
        member_a={"id": m1[0], "source_id": m1[1], "name": m1[2], "party": m1[3], "place": m1[4]},
        member_b={"id": m2[0], "source_id": m2[1], "name": m2[2], "party": m2[3], "place": m2[4]},
        similarity=sim,
        differing_votes=differing_votes,
    )


@bp.get("/political_view_UK/compare")
def uk_compare():
    """Compare two UK members."""
    a_id = request.args.get("a", type=int)
    b_id = request.args.get("b", type=int)

    if not a_id or not b_id:
        return render_template("political_tracker/compare.html", country="UK", error="Select two members to compare")

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT id, display_name, party, district_or_constituency FROM political_tracker.members WHERE country = 'UK' AND id IN (%s, %s)", (a_id, b_id))
            members = cur.fetchall()

            if len(members) != 2:
                return render_template("political_tracker/compare.html", country="UK", error="One or both members not found")

            m1, m2 = members[0], members[1]
            member_a, member_b = sorted([m1[0], m2[0]])

            cur.execute("""
                SELECT shared_votes, agreed_votes, agreement_pct
                FROM political_tracker.similarity
                WHERE member_a = %s AND member_b = %s
            """, (member_a, member_b))
            sim = cur.fetchone()

            cur.execute("""
                SELECT
                    v.vote_date, v.title, v.question,
                    mv1.position AS pos_a, mv2.position AS pos_b
                FROM political_tracker.member_votes mv1
                JOIN political_tracker.member_votes mv2 ON mv2.vote_id = mv1.vote_id
                JOIN political_tracker.votes v ON v.id = mv1.vote_id
                WHERE mv1.member_id = %s AND mv2.member_id = %s
                  AND mv1.position IN (1, 2) AND mv2.position IN (1, 2)
                  AND mv1.position != mv2.position
                ORDER BY v.vote_date DESC
                LIMIT 50
            """, (m1[0], m2[0]))
            differing_votes = cur.fetchall()

    return render_template(
        "political_tracker/compare.html",
        country="UK",
        member_a={"id": m1[0], "name": m1[1], "party": m1[2], "place": m1[3]},
        member_b={"id": m2[0], "name": m2[1], "party": m2[2], "place": m2[3]},
        similarity=sim,
        differing_votes=differing_votes,
    )


@bp.get("/political_tracker/about")
def about():
    """About page: data sources, definitions, limitations, last-updated dates."""
    meta = []
    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute("SELECT key, value, updated_at FROM political_tracker.meta ORDER BY key")
                meta = cur.fetchall()
    except Exception:
        pass

    return render_template("political_tracker/about.html", meta=meta)


# JSON API routes for maps and live search
@bp.get("/political_view_US/api/members")
def us_members_api():
    """JSON endpoint for US member search suggestions."""
    q = request.args.get("q", "").strip()
    chamber = request.args.get("chamber")
    limit = min(int(request.args.get("limit", "20")), 50)

    if not q or len(q) < 2:
        return {"results": []}

    with get_db() as db:
        with db.cursor() as cur:
            where = ["country = 'US'", "is_current", "display_name ILIKE %s"]
            params = [f"%{q}%"]
            if chamber:
                where.append("chamber = %s")
                params.append(chamber)

            cur.execute(f"""
                SELECT source_id, display_name, party, state_or_nation, district_or_constituency, chamber
                FROM political_tracker.members
                WHERE {' AND '.join(where)}
                ORDER BY display_name
                LIMIT %s
            """, params + [limit])
            results = cur.fetchall()

    return {
        "results": [
            {"id": r[0], "name": r[1], "party": r[2], "state": r[3], "district": r[4], "chamber": r[5]}
            for r in results
        ]
    }


@bp.get("/political_view_UK/api/members")
def uk_members_api():
    """JSON endpoint for UK member search suggestions."""
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", "20")), 50)

    if not q or len(q) < 2:
        return {"results": []}

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT source_id, display_name, party, district_or_constituency, state_or_nation
                FROM political_tracker.members
                WHERE country = 'UK' AND is_current AND display_name ILIKE %s
                ORDER BY display_name
                LIMIT %s
            """, (f"%{q}%", limit))
            results = cur.fetchall()

    return {
        "results": [
            {"id": r[0], "name": r[1], "party": r[2], "constituency": r[3], "nation": r[4]}
            for r in results
        ]
    }


@bp.get("/political_view_US/api/map/<chamber>")
def us_map_api(chamber):
    """JSON endpoint for US map data (districts or states)."""
    if chamber not in ("house", "senate"):
        return {"error": "Invalid chamber"}, 400

    with get_db() as db:
        with db.cursor() as cur:
            if chamber == "house":
                cur.execute("""
                    SELECT m.district_or_constituency, m.party, m.display_name, m.source_id
                    FROM political_tracker.members m
                    WHERE m.country = 'US' AND m.chamber = 'house' AND m.is_current
                """)
            else:
                cur.execute("""
                    SELECT m.state_or_nation, m.party, m.display_name, m.source_id
                    FROM political_tracker.members m
                    WHERE m.country = 'US' AND m.chamber = 'senate' AND m.is_current
                """)
            results = cur.fetchall()

    return {
        "features": [
            {"id": r[0], "party": r[1], "name": r[2], "source_id": r[3]}
            for r in results
        ]
    }


@bp.get("/political_view_UK/api/map")
def uk_map_api():
    """JSON endpoint for UK map data (constituencies)."""
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT m.ons_code, m.party, m.display_name, m.source_id
                FROM political_tracker.members m
                WHERE m.country = 'UK' AND m.chamber = 'commons' AND m.is_current
            """)
            results = cur.fetchall()

    return {
        "features": [
            {"id": r[0], "party": r[1], "name": r[2], "source_id": r[3]}
            for r in results
        ]
    }