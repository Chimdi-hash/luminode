"""
Consensus tests — verify Comparative Equivalence Principle behaviour.

These tests simulate leader and validator running independently and check
that the equivalence checks produce correct accept/reject decisions across
a range of delay scenarios.
"""

import pytest


THRESHOLD = 120  # Default threshold used in tests


def leader_result(delay: int, threshold: int = THRESHOLD, approved: bool = None) -> dict:
    """Build a mock leader result dict."""
    if approved is None:
        approved = delay >= threshold
    return {
        "approved"                : approved,
        "canonical_delay_minutes" : delay,
        "reasoning"               : "Mock reasoning.",
        "flight_status"           : "landed",
        "edge_case_detected"      : "none",
    }


def validator_check(leader: dict, my_delay: int, threshold: int = THRESHOLD) -> bool:
    """
    Mirrors the validator_fn logic from settle_claim().
    Returns True if validator accepts leader's result.
    """
    leader_delay   = leader["canonical_delay_minutes"]
    leader_ok      = leader["approved"]
    my_ok          = my_delay >= threshold
    delay_agrees   = abs(my_delay - leader_delay) <= 5
    near_threshold = abs(my_delay - threshold) <= 5
    decision_agrees = (my_ok == leader_ok) or near_threshold
    return delay_agrees and decision_agrees


# ── Straightforward consensus ─────────────────────────────────────────────────

class TestStraightforwardConsensus:

    def test_clear_approval_consensus(self):
        """Both leader and validator observe delay well above threshold."""
        lr = leader_result(delay=180)
        assert validator_check(lr, my_delay=179) is True

    def test_clear_rejection_consensus(self):
        """Both observe delay well below threshold."""
        lr = leader_result(delay=60)
        assert validator_check(lr, my_delay=62) is True

    def test_exact_threshold_consensus(self):
        """Delay exactly at threshold — both agree it's approved."""
        lr = leader_result(delay=120)
        assert validator_check(lr, my_delay=120) is True


# ── Variance tolerance ────────────────────────────────────────────────────────

class TestVarianceTolerance:
    """AviationStack can return slightly different values between calls."""

    def test_1_minute_variance_passes(self):
        lr = leader_result(delay=150)
        assert validator_check(lr, my_delay=149) is True
        assert validator_check(lr, my_delay=151) is True

    def test_5_minute_variance_passes(self):
        lr = leader_result(delay=150)
        assert validator_check(lr, my_delay=145) is True
        assert validator_check(lr, my_delay=155) is True

    def test_6_minute_variance_fails(self):
        lr = leader_result(delay=150)
        assert validator_check(lr, my_delay=144) is False
        assert validator_check(lr, my_delay=156) is False


# ── Near-threshold tolerance ──────────────────────────────────────────────────

class TestNearThresholdTolerance:
    """
    When delay is within 5 min of threshold, the decision can legitimately
    go either way. Validator should defer to leader to avoid liveness failure.
    """

    def test_validator_defers_when_leader_just_approved(self):
        """Leader: 121 min (approved). Validator: 118 min (would reject). Near threshold → accept."""
        lr = leader_result(delay=121, approved=True)
        assert validator_check(lr, my_delay=118) is True

    def test_validator_defers_when_leader_just_rejected(self):
        """Leader: 119 min (rejected). Validator: 122 min (would approve). Near threshold → accept."""
        lr = leader_result(delay=119, approved=False)
        assert validator_check(lr, my_delay=122) is True

    def test_no_deference_far_from_threshold(self):
        """Far from threshold, mismatched decision = rejection."""
        lr = leader_result(delay=200, approved=False)  # inconsistent: delay well above threshold
        assert validator_check(lr, my_delay=198) is False


# ── Edge-case flights ─────────────────────────────────────────────────────────

class TestEdgeCaseFlights:

    def test_cancelled_flight_zero_delay_rejected(self):
        """Cancelled flight has 0 delay — claim rejected (below any threshold)."""
        lr = leader_result(delay=0, approved=False)
        assert validator_check(lr, my_delay=0) is True

    def test_very_long_delay_approved(self):
        """Extreme delay (600 min) should always be approved for any standard threshold."""
        lr = leader_result(delay=600)
        assert validator_check(lr, my_delay=598) is True
