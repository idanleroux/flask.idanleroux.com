-- Political Tracker database schema
-- Run this in Supabase SQL editor as a user with CREATE privileges (e.g., postgres role)
-- Then create the read-only role and grants as shown at the bottom.

-- Create dedicated schema
CREATE SCHEMA IF NOT EXISTS political_tracker;

-- -----------------------------------------------------------------------------
-- Members table
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.members (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    country TEXT NOT NULL CHECK (country IN ('US', 'UK')),
    chamber TEXT NOT NULL CHECK (chamber IN ('house', 'senate', 'commons')),
    source_id TEXT NOT NULL,                       -- Bioguide ID (US) or Parliament member ID (UK)
    voteview_id TEXT,                              -- Voteview ICPSR ID (US only)
    full_name TEXT NOT NULL,
    display_name TEXT NOT NULL,                    -- Short name for display (e.g., "Keir Starmer")
    party TEXT,                                    -- Current party name
    party_code TEXT,                               -- Short party code (e.g., "LAB", "CON", "DEM", "REP")
    state_or_nation TEXT,                          -- US state or UK nation (England, Scotland, Wales, NI)
    district_or_constituency TEXT,                 -- US district or UK constituency name
    ons_code TEXT,                                 -- ONS code for UK constituency
    start_date DATE,                               -- Date member took office
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    image_url TEXT,                                -- Official portrait URL (if licensing allows)
    ideology_score NUMERIC(5, 3),                  -- Voteview NOMINATE dim1 (US only)
    fec_candidate_id TEXT,                         -- FEC candidate ID (US only)
    congress_or_parliament SMALLINT NOT NULL,      -- Congress number (US) or Parliament number (UK)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure unique member per country/chamber/congress
    UNIQUE (country, chamber, source_id, congress_or_parliament)
);

CREATE INDEX idx_members_country_chamber_current ON political_tracker.members (country, chamber, is_current);
CREATE INDEX idx_members_party ON political_tracker.members (party);
CREATE INDEX idx_members_state ON political_tracker.members (state_or_nation);
CREATE INDEX idx_members_district ON political_tracker.members (district_or_constituency);
CREATE INDEX idx_members_name ON political_tracker.members (display_name);
CREATE INDEX idx_members_fec ON political_tracker.members (fec_candidate_id);

-- -----------------------------------------------------------------------------
-- Votes table
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.votes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    country TEXT NOT NULL CHECK (country IN ('US', 'UK')),
    chamber TEXT NOT NULL CHECK (chamber IN ('house', 'senate', 'commons')),
    source_vote_id TEXT NOT NULL,                  -- Division ID (UK) or roll call number (US)
    vote_date DATE NOT NULL,
    title TEXT NOT NULL,                           -- Short title / motion
    question TEXT,                                 -- Full question text
    result TEXT,                                   -- Result: 'Pass', 'Fail', 'Passed', 'Rejected', etc.
    ayes INTEGER,                                  -- Number of Aye/Yes votes
    noes INTEGER,                                  -- Number of No votes
    session_or_congress SMALLINT NOT NULL,         -- Session (UK) or Congress (US)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (country, chamber, source_vote_id, session_or_congress)
);

CREATE INDEX idx_votes_country_chamber_date ON political_tracker.votes (country, chamber, vote_date DESC);
CREATE INDEX idx_votes_session ON political_tracker.votes (session_or_congress);

-- -----------------------------------------------------------------------------
-- Member votes junction table
-- Position mapping (smallint):
--   1 = Aye / Yes
--   2 = No
--   3 = Abstain / Present
--   4 = Absent / Not voting
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.member_votes (
    vote_id BIGINT NOT NULL REFERENCES political_tracker.votes (id) ON DELETE CASCADE,
    member_id BIGINT NOT NULL REFERENCES political_tracker.members (id) ON DELETE CASCADE,
    position SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 4),
    party_at_vote TEXT,                            -- Party at time of vote (for party switchers)
    voted_against_party BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (vote_id, member_id)
);

CREATE INDEX idx_member_votes_member ON political_tracker.member_votes (member_id);
CREATE INDEX idx_member_votes_vote ON political_tracker.member_votes (vote_id);
CREATE INDEX idx_member_votes_position ON political_tracker.member_votes (position);

-- -----------------------------------------------------------------------------
-- Member statistics (computed at ingest time)
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.member_stats (
    member_id BIGINT PRIMARY KEY REFERENCES political_tracker.members (id) ON DELETE CASCADE,
    votes_eligible INTEGER NOT NULL DEFAULT 0,     -- Votes held while member was eligible
    votes_cast INTEGER NOT NULL DEFAULT 0,         -- Votes where member voted Aye or No
    participation_pct NUMERIC(5, 2),               -- votes_cast / votes_eligible * 100
    party_loyalty_pct NUMERIC(5, 2),               -- % of party-line votes (excl. ties, small parties)
    votes_against_party_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Member similarity (computed at ingest time, per chamber)
-- Only stored for pairs with >= 20 shared votes
-- member_a < member_b to store each pair once
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.similarity (
    member_a BIGINT NOT NULL REFERENCES political_tracker.members (id) ON DELETE CASCADE,
    member_b BIGINT NOT NULL REFERENCES political_tracker.members (id) ON DELETE CASCADE,
    shared_votes INTEGER NOT NULL,                 -- Votes where both voted Aye/No
    agreed_votes INTEGER NOT NULL,                 -- Votes where both voted same way (Aye/Aye or No/No)
    agreement_pct NUMERIC(5, 2) NOT NULL,          -- agreed_votes / shared_votes * 100
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (member_a, member_b),
    CHECK (member_a < member_b),
    CHECK (shared_votes >= 20)
);

CREATE INDEX idx_similarity_a ON political_tracker.similarity (member_a);
CREATE INDEX idx_similarity_b ON political_tracker.similarity (member_b);
CREATE INDEX idx_similarity_agreement ON political_tracker.similarity (agreement_pct DESC);

-- -----------------------------------------------------------------------------
-- US campaign finance (openFEC)
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.finance_us (
    member_id BIGINT NOT NULL REFERENCES political_tracker.members (id) ON DELETE CASCADE,
    cycle SMALLINT NOT NULL,                       -- Election cycle (e.g., 2024)
    coverage_end_date DATE,                        -- FEC report coverage end date
    total_receipts BIGINT,                         -- Total receipts in cents
    individual_itemised BIGINT,                    -- Itemised individual contributions
    individual_unitemised BIGINT,                  -- Unitemised (small donor) contributions
    pac BIGINT,                                    -- PAC contributions
    party_committee BIGINT,                        -- Party committee contributions
    candidate_self BIGINT,                         -- Candidate self-funding
    total_disbursements BIGINT,                    -- Total disbursements in cents
    cash_on_hand BIGINT,                           -- Cash on hand in cents
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (member_id, cycle)
);

CREATE INDEX idx_finance_member ON political_tracker.finance_us (member_id);

-- -----------------------------------------------------------------------------
-- Metadata table (last refresh dates, version info)
-- -----------------------------------------------------------------------------
CREATE TABLE political_tracker.meta (
    key TEXT PRIMARY KEY,                          -- e.g., 'uk_members_last_refresh', 'us_votes_last_refresh', 'schema_version'
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Row Level Security: enable on all tables, no policies = no access via Data API
-- -----------------------------------------------------------------------------
ALTER TABLE political_tracker.members ENABLE ROW LEVEL SECURITY;
ALTER TABLE political_tracker.votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE political_tracker.member_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE political_tracker.member_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE political_tracker.similarity ENABLE ROW LEVEL SECURITY;
ALTER TABLE political_tracker.finance_us ENABLE ROW LEVEL SECURITY;
ALTER TABLE political_tracker.meta ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- Read-only role for the web app (Render)
-- Run the following as a superuser (e.g., postgres) in Supabase SQL editor:
--
-- CREATE ROLE tracker_ro LOGIN PASSWORD '<choose-a-password>';
-- GRANT USAGE ON SCHEMA political_tracker TO tracker_ro;
-- GRANT SELECT ON ALL TABLES IN SCHEMA political_tracker TO tracker_ro;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA political_tracker GRANT SELECT ON TABLES TO tracker_ro;
--
-- Use the pooler connection string for this role in DATABASE_URL (Render env var).
--
-- For ingest (write access), use a separate role (or the default postgres role)
-- with its own pooler connection string in DATABASE_URL_INGEST (GitHub Actions secret).
-- -----------------------------------------------------------------------------