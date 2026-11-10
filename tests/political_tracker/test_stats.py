"""Tests for Political Tracker statistics module."""

import pytest
from political_tracker.stats import (
    POS_YES, POS_NO, POS_ABSTAIN, POS_ABSENT,
    is_voting_position,
    participation_pct,
    party_loyalty_pct,
    agreement_pct,
)


class TestPositionConstants:
    def test_position_values(self):
        assert POS_YES == 1
        assert POS_NO == 2
        assert POS_ABSTAIN == 3
        assert POS_ABSENT == 4


class TestIsVotingPosition:
    def test_yes_is_voting(self):
        assert is_voting_position(POS_YES) is True

    def test_no_is_voting(self):
        assert is_voting_position(POS_NO) is True

    def test_abstain_not_voting(self):
        assert is_voting_position(POS_ABSTAIN) is False

    def test_absent_not_voting(self):
        assert is_voting_position(POS_ABSENT) is False


class TestParticipationPct:
    def test_normal_case(self):
        assert participation_pct(100, 80) == 80.0

    def test_zero_eligible(self):
        assert participation_pct(0, 0) is None

    def test_full_participation(self):
        assert participation_pct(50, 50) == 100.0

    def test_no_votes_cast(self):
        assert participation_pct(100, 0) == 0.0


class TestPartyLoyaltyPct:
    def test_independent_no_party(self):
        member_votes = [(1, POS_YES, None), (2, POS_NO, None)]
        party_votes = {1: (POS_YES, 5), 2: (POS_NO, 5)}
        assert party_loyalty_pct(member_votes, party_votes) is None

    def test_all_loyal(self):
        member_votes = [
            (1, POS_YES, "Party A"),
            (2, POS_YES, "Party A"),
            (3, POS_NO, "Party A"),
        ]
        party_votes = {
            1: (POS_YES, 10),
            2: (POS_YES, 10),
            3: (POS_NO, 10),
        }
        assert party_loyalty_pct(member_votes, party_votes) == 100.0

    def test_mixed_loyalty(self):
        member_votes = [
            (1, POS_YES, "Party A"),
            (2, POS_NO, "Party A"),
            (3, POS_YES, "Party A"),
        ]
        party_votes = {
            1: (POS_YES, 10),
            2: (POS_YES, 10),  # Member voted against party
            3: (POS_YES, 10),
        }
        # 2 out of 3 loyal = 66.67%
        assert party_loyalty_pct(member_votes, party_votes) == 66.67

    def test_excludes_abstain_and_absent(self):
        member_votes = [
            (1, POS_YES, "Party A"),
            (2, POS_ABSTAIN, "Party A"),
            (3, POS_ABSENT, "Party A"),
            (4, POS_NO, "Party A"),
        ]
        party_votes = {
            1: (POS_YES, 10),
            4: (POS_NO, 10),
        }
        # Only votes 1 and 4 count (2 eligible), both loyal = 100%
        assert party_loyalty_pct(member_votes, party_votes) == 100.0

    def test_excludes_ties(self):
        member_votes = [(1, POS_YES, "Party A")]
        party_votes = {1: (0, 10)}  # Tie = majority_pos 0
        assert party_loyalty_pct(member_votes, party_votes) is None

    def test_excludes_small_party(self):
        member_votes = [(1, POS_YES, "Party A")]
        party_votes = {1: (POS_YES, 1)}  # Only 1 party member voted
        assert party_loyalty_pct(member_votes, party_votes) is None


class TestAgreementPct:
    def test_below_threshold(self):
        assert agreement_pct(19, 15) is None

    def test_at_threshold(self):
        assert agreement_pct(20, 15) == 75.0

    def test_full_agreement(self):
        assert agreement_pct(50, 50) == 100.0

    def test_no_agreement(self):
        assert agreement_pct(50, 0) == 0.0

    def test_partial_agreement(self):
        assert agreement_pct(40, 30) == 75.0