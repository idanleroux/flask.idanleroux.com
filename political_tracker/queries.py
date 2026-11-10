"""SQL queries for Political Tracker.

All parameterised SQL in one place for maintainability and auditability.
"""

# Member queries
MEMBER_BY_SOURCE_ID = """
    SELECT * FROM political_tracker.members
    WHERE country = %s AND source_id = %s
"""

MEMBER_BY_ID = """
    SELECT * FROM political_tracker.members
    WHERE id = %s
"""

CURRENT_MEMBERS = """
    SELECT * FROM political_tracker.members
    WHERE country = %s AND chamber = %s AND is_current
    ORDER BY display_name
"""

# Vote queries
VOTES_BY_MEMBER = """
    SELECT v.*, mv.position, mv.voted_against_party
    FROM political_tracker.votes v
    JOIN political_tracker.member_votes mv ON mv.vote_id = v.id
    WHERE mv.member_id = %s
    ORDER BY v.vote_date DESC
    LIMIT %s OFFSET %s
"""

# Stats queries
MEMBER_STATS = """
    SELECT * FROM political_tracker.member_stats
    WHERE member_id = %s
"""

# Similarity queries
MOST_SIMILAR = """
    SELECT m.id, m.display_name, m.party, m.state_or_nation, m.district_or_constituency,
           s.shared_votes, s.agreed_votes, s.agreement_pct
    FROM political_tracker.similarity s
    JOIN political_tracker.members m ON m.id = s.member_b
    WHERE s.member_a = %s
    ORDER BY s.agreement_pct DESC
    LIMIT %s
"""

LEAST_SIMILAR = """
    SELECT m.id, m.display_name, m.party, m.state_or_nation, m.district_or_constituency,
           s.shared_votes, s.agreed_votes, s.agreement_pct
    FROM political_tracker.similarity s
    JOIN political_tracker.members m ON m.id = s.member_b
    WHERE s.member_a = %s
    ORDER BY s.agreement_pct ASC
    LIMIT %s
"""

SIMILARITY_PAIR = """
    SELECT shared_votes, agreed_votes, agreement_pct
    FROM political_tracker.similarity
    WHERE member_a = %s AND member_b = %s
"""

# Finance queries
FINANCE_BY_MEMBER_CYCLE = """
    SELECT * FROM political_tracker.finance_us
    WHERE member_id = %s AND cycle = %s
"""

# Meta queries
META_ALL = """
    SELECT key, value, updated_at FROM political_tracker.meta
    ORDER BY key
"""