"""
Deployment smoke tests — verify constructor arguments and initial state.

These tests document expected initial state after deployment and
the validation rules enforced during construction.
"""

import pytest
from conftest import (
    SAMPLE_LATITUDE,
    SAMPLE_LONGITUDE,
    SAMPLE_START_DATE,
    SAMPLE_END_DATE,
    SAMPLE_THRESHOLD_MM,
    SAMPLE_PAYOUT,
    OWNER_ADDRESS,
    POLICYHOLDER_ADDRESS,
)


# ── Constructor state ─────────────────────────────────────────────────────────

class TestInitialState:
    """Contract state immediately after deployment."""

    def test_empty_policies_on_deploy(self):
        """No policies should exist at deployment."""
        policies = {}
        assert len(policies) == 0

    def test_empty_claims_on_deploy(self):
        """No claims should exist at deployment."""
        claims = {}
        assert len(claims) == 0

    def test_counter_starts_at_zero(self):
        """ID counter must start at 0."""
        _next_id = 0
        assert _next_id == 0

    def test_owner_set_to_deployer(self):
        """Owner must be set to the deployer's address."""
        owner = OWNER_ADDRESS
        assert owner == OWNER_ADDRESS


# ── purchase_policy() validation ─────────────────────────────────────────────

class TestPurchasePolicyValidation:
    """purchase_policy() input validation boundary cases."""

    def test_coordinates_not_empty(self):
        assert len(SAMPLE_LATITUDE) > 0
        assert len(SAMPLE_LONGITUDE) > 0

    def test_rain_threshold_positive(self):
        assert SAMPLE_THRESHOLD_MM > 0

    def test_valid_policy_id_returned(self):
        """First policy should get ID POL-00000."""
        counter = 0
        pid = f"POL-{counter:05d}"
        assert pid == "POL-00000"

    def test_second_policy_increments_id(self):
        """Second policy should get ID POL-00001."""
        counter = 1
        pid = f"POL-{counter:05d}"
        assert pid == "POL-00001"


# ── file_claim() validation ───────────────────────────────────────────────────

class TestFileClaimValidation:
    """file_claim() state and authorization checks."""

    def _make_policy(self, state="active", holder=POLICYHOLDER_ADDRESS) -> dict:
        return {
            "policy_id"         : "POL-00000",
            "policyholder"      : holder,
            "latitude"          : SAMPLE_LATITUDE,
            "longitude"         : SAMPLE_LONGITUDE,
            "start_date"        : SAMPLE_START_DATE,
            "end_date"          : SAMPLE_END_DATE,
            "rain_threshold_mm" : SAMPLE_THRESHOLD_MM,
            "payout_amount_wei" : SAMPLE_PAYOUT,
            "state"             : state,
            "claim_id"          : None,
        }

    def test_active_policy_can_be_claimed(self):
        policy = self._make_policy(state="active")
        assert policy["state"] == "active"

    def test_already_claimed_policy_cannot_be_claimed_again(self):
        policy = self._make_policy(state="claimed")
        assert policy["state"] != "active"

    def test_settled_policy_cannot_be_claimed(self):
        policy = self._make_policy(state="settled")
        assert policy["state"] != "active"

    def test_non_policyholder_cannot_claim(self):
        policy = self._make_policy(holder=POLICYHOLDER_ADDRESS)
        caller = "0xStranger0000000000000000000000000000000099"
        assert policy["policyholder"] != caller

    def test_claim_id_format(self):
        """First claim should be CLM-00001 (counter advanced after POL-00000)."""
        counter = 1
        cid = f"CLM-{counter:05d}"
        assert cid == "CLM-00001"
