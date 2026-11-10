"""Statistics calculations for Political Tracker.

Implements the exact definitions from the build plan (Section 7).
All functions are pure and testable with hand-built fixtures.
"""

from __future__ import annotations

import numpy as np


# Position constants (matching schema.sql)
POS_YES = 1   # Aye / Yes
POS_NO = 2    # No
POS_ABSTAIN = 3  # Abstain / Present
POS_ABSENT = 4   # Absent / Not voting


def is_voting_position(position: int) -> bool:
    """Return True if position counts as a cast vote (Yes or No)."""
    return position in (POS_YES, POS_NO)


def participation_pct(votes_eligible: int, votes_cast: int) -> float | None:
    """Participation % = votes_cast / votes_eligible * 100.

    votes_cast = count of positions 1 or 2.
    Returns None if votes_eligible is 0.
    """
    if votes_eligible == 0:
        return None
    return round(votes_cast / votes_eligible * 100, 2)


def party_loyalty_pct(
    member_votes: list[tuple[int, str, str]],
    party_votes: dict[int, tuple[int, int]],
) -> float | None:
    """Party-loyalty % calculation.

    Args:
        member_votes: List of (vote_id, member_position, member_party_at_vote)
        party_votes: Dict of vote_id -> (party_majority_position, party_voting_count)
                     party_voting_count = number of party members who voted Yes/No

    Returns:
        Loyalty percentage or None if no eligible votes.
        Excludes ties and votes where party had < 2 voting members.
        Independents (no party) return None.
    """
    if not member_votes:
        return None

    # Check if member has a party (use first vote's party_at_vote as proxy)
    first_party = member_votes[0][2] if member_votes[0][2] else None
    if not first_party:
        return None

    loyal = 0
    eligible = 0

    for vote_id, member_pos, member_party in member_votes:
        if not is_voting_position(member_pos):
            continue

        party_data = party_votes.get(vote_id)
        if not party_data:
            continue

        majority_pos, party_count = party_data
        if party_count < 2:
            continue  # Exclude votes where party had fewer than 2 voting members
        if majority_pos == 0:
            continue  # Tie

        eligible += 1
        if member_pos == majority_pos:
            loyal += 1

    if eligible == 0:
        return None

    return round(loyal / eligible * 100, 2)


def agreement_pct(shared_votes: int, agreed_votes: int) -> float | None:
    """Agreement % = agreed_votes / shared_votes * 100.

    Returns None if shared_votes < 20 (minimum threshold).
    """
    if shared_votes < 20:
        return None
    return round(agreed_votes / shared_votes * 100, 2)


def compute_similarity_matrix(
    member_ids: list[int],
    vote_ids: list[int],
    vote_matrix: np.ndarray,  # shape: (n_members, n_votes) with values +1, -1, 0
) -> list[tuple[int, int, int, int, float]]:
    """Compute pairwise similarity for all member pairs in a chamber.

    Uses matrix multiplication for efficiency:
    - vote_matrix: +1 for Yes, -1 for No, 0 for Abstain/Absent
    - Agreement matrix = (vote_matrix @ vote_matrix.T) -> dot products
      For each pair: agreed = (dot + shared) / 2 where shared = count of non-zero overlap
    - Shared votes matrix = ((vote_matrix != 0) @ (vote_matrix != 0).T)

    Args:
        member_ids: List of member IDs (aligned with vote_matrix rows)
        vote_ids: List of vote IDs (aligned with vote_matrix columns)
        vote_matrix: Numpy array of shape (n_members, n_votes)

    Returns:
        List of (member_a, member_b, shared_votes, agreed_votes, agreement_pct)
        for all pairs with shared_votes >= 20, with member_a < member_b.
    """
    n_members = vote_matrix.shape[0]
    if n_members < 2:
        return []

    # Binary matrix: 1 where member voted Yes/No, 0 otherwise
    voted = (vote_matrix != 0).astype(np.int16)

    # Shared votes for each pair
    shared_matrix = voted @ voted.T  # (n_members, n_members)

    # Agreement: dot product of +1/-1 vectors
    # For each pair: agreed = (dot + shared) / 2
    # Because: same vote (+1*+1=1 or -1*-1=1) -> contributes 1 to dot
    #          different vote (+1*-1=-1) -> contributes -1
    # So: dot = agreed - disagreed, shared = agreed + disagreed
    # agreed = (dot + shared) / 2
    dot_matrix = vote_matrix @ vote_matrix.T
    agreed_matrix = (dot_matrix + shared_matrix) // 2

    results = []
    for i in range(n_members):
        for j in range(i + 1, n_members):
            shared = int(shared_matrix[i, j])
            if shared >= 20:
                agreed = int(agreed_matrix[i, j])
                pct = round(agreed / shared * 100, 2)
                member_a = member_ids[i]
                member_b = member_ids[j]
                if member_a > member_b:
                    member_a, member_b = member_b, member_a
                results.append((member_a, member_b, shared, agreed, pct))

    return results


def build_vote_matrix(
    member_ids: list[int],
    vote_ids: list[int],
    member_votes: dict[int, dict[int, int]],  # member_id -> {vote_id: position}
) -> np.ndarray:
    """Build the member x vote matrix for similarity computation.

    Returns matrix with:
      +1 for Yes (position 1)
      -1 for No (position 2)
      0 for Abstain (3), Absent (4), or not eligible
    """
    n_members = len(member_ids)
    n_votes = len(vote_ids)
    matrix = np.zeros((n_members, n_votes), dtype=np.int8)

    vote_idx = {vid: i for i, vid in enumerate(vote_ids)}
    member_idx = {mid: i for i, mid in enumerate(member_ids)}

    for mid, votes in member_votes.items():
        if mid not in member_idx:
            continue
        mi = member_idx[mid]
        for vid, pos in votes.items():
            if vid not in vote_idx:
                continue
            vi = vote_idx[vid]
            if pos == POS_YES:
                matrix[mi, vi] = 1
            elif pos == POS_NO:
                matrix[mi, vi] = -1
            # else 0 (abstain/absent)

    return matrix