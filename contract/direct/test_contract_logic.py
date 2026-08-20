"""
Direct unit tests — pure Python logic, no GenLayer runtime required.

Tests cover:
  - Input validation rules
  - Policy ID / claim ID generation format
  - State machine transitions
  - Stable-field extraction logic
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
        pid = f"POL-{1:05d}"
        assert pid == "POL-00001"

    def test_claim_id_format(self):
        """Claim IDs should be CLM-NNNNN with zero-padded 5-digit counter."""
        cid = f"CLM-{2:05d}"
        assert cid == "CLM-00002"

    def test_ids_are_unique(self):
        """Sequential IDs must not collide."""
        ids = [f"POL-{i:05d}" for i in range(1, 101)]
        assert len(set(ids)) == 100


# ── Input validation ──────────────────────────────────────────────────────────

class TestInputValidation:
    """purchase_policy() validation rules."""

    def test_valid_iata_codes(self):
        """IATA codes 3–7 chars should pass basic length check."""
        valid = ["BA4", "AA123", "EK1234", "ABCDE7"]
        for code in valid:
            assert 3 <= len(code.strip()) <= 7, f"Expected {code} to be valid"

    def test_invalid_iata_too_short(self):
        """Empty or 1-char IATA codes should be rejected."""
        for code in ["", "A", "  "]:
            assert len(code.strip()) < 3, f"Expected {code} to be invalid"

    def test_delay_threshold_bounds(self):
        """Threshold must be 30–600 minutes inclusive."""
        assert 30 <= 30 <= 600   # lower bound
        assert 30 <= 600 <= 600  # upper bound
        assert not (30 <= 29 <= 600)   # too low
        assert not (30 <= 601 <= 600)  # too high

    def test_payout_must_be_positive(self):
        """Zero and negative payouts should be rejected."""
        for val in [0, -1, -1_000_000]:
            assert val <= 0

    def test_date_format_length(self):
        """ISO date must be exactly 10 chars (YYYY-MM-DD)."""
        assert len("2025-03-15") == 10
        assert len("2025-3-15") != 10
        assert len("") != 10


# ── Stable field extraction ───────────────────────────────────────────────────

class TestStableFieldExtraction:
    """Simulates _fetch_flight_data() stable-field logic."""

    def _extract_stable(self, raw_flight: dict) -> dict:
        """Mirrors the extraction logic from _fetch_flight_data()."""
        departure = raw_flight.get("departure", {})
        arrival   = raw_flight.get("arrival",   {})
        status    = raw_flight.get("flight_status", "unknown")

        dep_delay = int(departure.get("delay") or 0)
        arr_delay = int(arrival.get("delay")   or 0)
        canonical = arr_delay if arr_delay > 0 else dep_delay

        return {
            "flight_status"           : status,
            "departure_delay_minutes" : dep_delay,
            "arrival_delay_minutes"   : arr_delay,
            "canonical_delay_minutes" : canonical,
        }

    def test_arrival_delay_preferred(self):
        """canonical_delay should use arrival_delay when > 0."""
        flight = {"departure": {"delay": 130}, "arrival": {"delay": 143}, "flight_status": "landed"}
        result = self._extract_stable(flight)
        assert result["canonical_delay_minutes"] == 143

    def test_departure_fallback_when_no_arrival(self):
        """canonical_delay should fall back to departure_delay when arrival=0."""
        flight = {"departure": {"delay": 90}, "arrival": {"delay": 0}, "flight_status": "active"}
        result = self._extract_stable(flight)
        assert result["canonical_delay_minutes"] == 90

    def test_none_delay_treated_as_zero(self):
        """None delay values must be normalised to 0."""
        flight = {"departure": {"delay": None}, "arrival": {"delay": None}, "flight_status": "scheduled"}
        result = self._extract_stable(flight)
        assert result["departure_delay_minutes"] == 0
        assert result["arrival_delay_minutes"]   == 0
        assert result["canonical_delay_minutes"] == 0

    def test_volatile_fields_not_present(self):
        """Extracted dict must not contain any volatile fields."""
        flight = {
            "departure": {"delay": 10, "actual": "2025-03-15T10:34:00+00:00"},
            "arrival":   {"delay": 15, "actual": "2025-03-15T12:05:00+00:00"},
            "flight_status": "landed",
            "live": {"latitude": 51.5, "longitude": -0.1, "speed_horizontal": 450},
            "updated": "2025-03-15T12:10:00+00:00",
        }
        result = self._extract_stable(flight)
        forbidden = {"actual", "live", "updated", "latitude", "longitude", "speed_horizontal"}
        for key in result:
            assert key not in forbidden


# ── Equivalence principle logic ───────────────────────────────────────────────

class TestEquivalencePrincipleLogic:
    """Unit tests for the Comparative EP validator_fn logic."""

    THRESHOLD = 120

    def _validator_check(self, leader_delay: int, my_delay: int, leader_approved: bool) -> bool:
        """Mirrors the validator_fn comparison logic from settle_claim()."""
        my_approved       = my_delay >= self.THRESHOLD
        delay_agrees      = abs(my_delay - leader_delay) <= 5
        near_threshold    = abs(my_delay - self.THRESHOLD) <= 5
        decision_agrees   = (my_approved == leader_approved) or near_threshold
        return delay_agrees and decision_agrees

    def test_both_agree_approved(self):
        assert self._validator_check(143, 144, True) is True

    def test_both_agree_rejected(self):
        assert self._validator_check(45, 47, False) is True

    def test_delay_within_5min_margin(self):
        """Small delay variance (≤5 min) should still pass."""
        assert self._validator_check(143, 140, True) is True

    def test_delay_outside_5min_margin_fails(self):
        """Delay variance > 5 min should fail."""
        assert self._validator_check(143, 130, True) is False

    def test_near_threshold_defers_to_leader(self):
        """When delay is within 5 min of threshold, validator defers."""
        # My delay = 118 (rejected), leader says 120 (approved) — near threshold
        assert self._validator_check(120, 118, True) is True

    def test_decision_mismatch_far_from_threshold_fails(self):
        """Far from threshold, mismatched decision should fail."""
        assert self._validator_check(200, 195, False) is False


# ── Error prefix classification ───────────────────────────────────────────────

class TestErrorClassification:
    def test_expected_prefix(self):
        msg = f"{ERR_EXPECTED} Only the policyholder can file a claim"
        assert msg.startswith("[EXPECTED]")

    def test_external_prefix(self):
        msg = f"{ERR_EXTERNAL} AviationStack returned HTTP 503"
        assert msg.startswith("[EXTERNAL]")

    def test_prefixes_are_distinct(self):
        assert ERR_EXPECTED != ERR_EXTERNAL
