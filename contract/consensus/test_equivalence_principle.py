"""
Consensus tests — verify Comparative Equivalence Principle behavior.

These tests simulate leader and validator running independently and check
that the equivalence checks produce correct accept/reject decisions across
a range of rainfall scenarios.
"""

import pytest


THRESHOLD = 50  # Default threshold used in tests (50mm rain threshold)


def leader_result(rain: float, threshold: int = THRESHOLD, approved: bool = None) -> dict:
    """Build a mock leader result dict."""
    if approved is None:
        approved = rain < threshold
    return {
        "approved"             : approved,
        "cumulative_rain_mm"   : rain,
        "reasoning"            : "Mock reasoning.",
        "edge_case_detected"   : "none",
    }


def validator_check(leader: dict, my_rain: float, threshold: int = THRESHOLD) -> bool:
    """
    Mirrors the validator_fn logic from settle_claim().
    Returns True if validator accepts leader's result.
    """
    leader_rain    = leader["cumulative_rain_mm"]
    leader_ok      = leader["approved"]
    my_ok          = my_rain < threshold
    rain_agrees    = abs(my_rain - leader_rain) <= 0.2
    near_threshold = abs(my_rain - threshold) <= 0.5
    decision_agrees = (my_ok == leader_ok) or near_threshold
    return rain_agrees and decision_agrees


# ── Straightforward consensus ─────────────────────────────────────────────────

class TestStraightforwardConsensus:

    def test_clear_approval_consensus(self):
        """Both leader and validator observe rainfall well below threshold (drought approved)."""
        lr = leader_result(rain=12.5)
        assert validator_check(lr, my_rain=12.6) is True

    def test_clear_rejection_consensus(self):
        """Both observe rainfall well above threshold (no drought, claim rejected)."""
        lr = leader_result(rain=75.0)
        assert validator_check(lr, my_rain=74.9) is True

    def test_exact_threshold_consensus(self):
        """Rain exactly at threshold — both agree it's rejected."""
        lr = leader_result(rain=50.0)
        assert validator_check(lr, my_rain=50.0) is True


# ── Variance tolerance ────────────────────────────────────────────────────────

class TestVarianceTolerance:
    """Open-Meteo data can return slightly different floats between calls."""

    def test_0_1_mm_variance_passes(self):
        lr = leader_result(rain=25.0)
        assert validator_check(lr, my_rain=24.9) is True
        assert validator_check(lr, my_rain=25.1) is True

    def test_0_2_mm_variance_passes(self):
        lr = leader_result(rain=25.0)
        assert validator_check(lr, my_rain=24.8) is True
        assert validator_check(lr, my_rain=25.2) is True

    def test_0_3_mm_variance_fails(self):
        lr = leader_result(rain=25.0)
        assert validator_check(lr, my_rain=24.7) is False
        assert validator_check(lr, my_rain=25.3) is False


# ── Near-threshold tolerance ──────────────────────────────────────────────────

class TestNearThresholdTolerance:
    """
    When rain is within 0.5mm of threshold, the decision can legitimately
    go either way. Validator should defer to leader to avoid consensus failure.
    """

    def test_validator_defers_when_leader_just_approved(self):
        """Leader: 49.8mm (approved). Validator: 50.1mm (would reject). Near threshold → accept."""
        lr = leader_result(rain=49.8, approved=True)
        assert validator_check(lr, my_rain=50.1) is True

    def test_validator_defers_when_leader_just_rejected(self):
        """Leader: 50.2mm (rejected). Validator: 49.9mm (would approve). Near threshold → accept."""
        lr = leader_result(rain=50.2, approved=False)
        assert validator_check(lr, my_rain=49.9) is True
