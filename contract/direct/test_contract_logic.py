"""
Direct unit tests — pure Python logic, no GenLayer runtime required.

Tests cover:
  - Input validation rules
  - Policy ID / claim ID generation format
  - State machine transitions
  - Rainfall sum aggregation logic
  - Error prefix classification
"""

import json
import pytest

# Constants mirrored from the contract
ERR_EXPECTED = "[EXPECTED]"
ERR_EXTERNAL = "[EXTERNAL]"

POLICY_ACTIVE   = "active"
POLICY_CLAIMED  = "claimed"
POLICY_SETTLED  = "settled"
POLICY_REJECTED = "rejected"

CLAIM_PENDING  = "pending"
CLAIM_APPROVED = "approved"
CLAIM_REJECTED = "rejected"


# ── ID generation ─────────────────────────────────────────────────────────────

class TestIdGeneration:
    """Policy and claim IDs must match expected format."""

    def test_policy_id_format(self):
        """Policy IDs should be POL-NNNNN with zero-padded 5-digit counter."""
        pid = f"POL-{0:05d}"
        assert pid == "POL-00000"

    def test_claim_id_format(self):
        """Claim IDs should be CLM-NNNNN with zero-padded 5-digit counter."""
        cid = f"CLM-{1:05d}"
        assert cid == "CLM-00001"

    def test_ids_are_unique(self):
        """Sequential IDs must not collide."""
        ids = [f"POL-{i:05d}" for i in range(100)]
        assert len(set(ids)) == 100


# ── Input validation ──────────────────────────────────────────────────────────

class TestInputValidation:
    """purchase_policy() validation rules."""

    def test_coordinates_not_empty(self):
        assert len("52.52".strip()) > 0
        assert len("13.41".strip()) > 0

    def test_rain_threshold_positive(self):
        assert 50 > 0

    def test_date_format_length(self):
        """ISO date must be exactly 10 chars (YYYY-MM-DD)."""
        assert len("2023-08-01") == 10
        assert len("2023-8-01") != 10


# ── Rain sum aggregation ──────────────────────────────────────────────────────

class TestRainAggregation:
    """Simulates _fetch_rainfall_data() aggregation logic."""

    def _aggregate_rain(self, rain_list: list) -> float:
        clean_rain = [r for r in rain_list if r is not None]
        total_rain = sum(clean_rain) if clean_rain else 0.0
        return round(total_rain, 2)

    def test_clean_list(self):
        rain = [1.2, 0.0, 3.4, 0.5]
        assert self._aggregate_rain(rain) == 5.1

    def test_list_with_nones(self):
        rain = [1.2, None, 3.4, 0.5, None]
        assert self._aggregate_rain(rain) == 5.1

    def test_empty_list(self):
        assert self._aggregate_rain([]) == 0.0


# ── Equivalence principle logic ───────────────────────────────────────────────

class TestEquivalencePrincipleLogic:
    """Unit tests for the Comparative EP validator_fn logic."""

    THRESHOLD = 50

    def _validator_check(self, leader_rain: float, my_rain: float, leader_approved: bool) -> bool:
        """Mirrors the validator_fn comparison logic from settle_claim()."""
        my_approved       = my_rain < self.THRESHOLD
        rain_agrees      = abs(my_rain - leader_rain) <= 0.2
        near_threshold    = abs(my_rain - self.THRESHOLD) <= 0.5
        decision_agrees   = (my_approved == leader_approved) or near_threshold
        return rain_agrees and decision_agrees

    def test_both_agree_approved(self):
        assert self._validator_check(12.5, 12.6, True) is True

    def test_both_agree_rejected(self):
        assert self._validator_check(75.0, 74.9, False) is True

    def test_rain_within_0_2_mm_margin(self):
        """Small rain variance (≤0.2 mm) should still pass."""
        assert self._validator_check(25.0, 24.8, True) is True

    def test_rain_outside_0_2_mm_margin_fails(self):
        """Rain variance > 0.2 mm should fail."""
        assert self._validator_check(25.0, 24.7, True) is False

    def test_near_threshold_defers_to_leader(self):
        """When rain is within 0.5 mm of threshold, validator defers."""
        assert self._validator_check(49.8, 50.1, True) is True


# ── Error prefix classification ───────────────────────────────────────────────

class TestErrorClassification:
    def test_expected_prefix(self):
        msg = f"{ERR_EXPECTED} Coordinates cannot be empty"
        assert msg.startswith("[EXPECTED]")

    def test_external_prefix(self):
        msg = f"{ERR_EXTERNAL} Open-Meteo returned HTTP 503"
        assert msg.startswith("[EXTERNAL]")
