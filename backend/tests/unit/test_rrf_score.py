"""rrf_score is pure arithmetic: no database, no network."""

import pytest

from app.retrieval import ARM_WEIGHTS, RRF_K, rrf_score


def test_single_arm():
    assert rrf_score({"semantic": 1}) == pytest.approx(ARM_WEIGHTS["semantic"] / (RRF_K + 1))


def test_contributions_sum_across_arms():
    expected = sum(w / (RRF_K + 3) for w in ARM_WEIGHTS.values())
    assert rrf_score({arm: 3 for arm in ARM_WEIGHTS}) == pytest.approx(expected)


def test_missing_or_none_arm_contributes_nothing():
    assert rrf_score({"name": 2, "prose": None}) == rrf_score({"name": 2})
    assert rrf_score({}) == 0


def test_better_rank_scores_higher():
    assert rrf_score({"prose": 1}) > rrf_score({"prose": 2}) > rrf_score({"prose": 30})


def test_name_match_beats_prose_mention():
    """ADR-0012: the bottle named "Eagle Rare" (name #1, prose #2) must beat a
    bottle whose prose merely discusses it (prose #1)."""
    assert rrf_score({"name": 1, "prose": 2}) > rrf_score({"prose": 1})


def test_agreement_beats_a_single_strong_arm():
    """Second place in two arms outscores first place in one."""
    assert rrf_score({"semantic": 2, "prose": 2}) > rrf_score({"semantic": 1})
