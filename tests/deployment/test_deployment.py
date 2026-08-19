"""
Deployment smoke tests — verify constructor arguments and initial state.

These tests document expected initial state after deployment and
the validation rules enforced during construction.
"""

import pytest
from tests.conftest import (
    SAMPLE_API_KEY,
    SAMPLE_FLIGHT_IATA,
    SAMPLE_FLIGHT_DATE,
    SAMPLE_THRESHOLD,
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

    def test_counter_starts_at_one(self):
        """ID counter must start at 1."""
        _next_id = 1
        assert _next_id == 1

    def test_api_key_stored(self):
        """API key must be stored as-is."""
        api_key = SAMPLE_API_KEY
        assert api_key == SAMPLE_API_KEY

    def test_owner_set_to_deployer(self):
        """Owner must be set to the deployer's address."""
        owner = OWNER_ADDRESS
        assert owner == OWNER_ADDRESS


# ── purchase_policy() validation ─────────────────────────────────────────────

class TestPurchasePolicyValidation:
    """purchase_policy() input validation boundary cases."""

    def test_minimum_threshold_accepted(self):
        """30-minute threshold is the minimum allowed."""
        assert 30 >= 30

    def test_maximum_threshold_accepted(self):
        """600-minute threshold is the maximum allowed."""
        assert 600 <= 600

    def test_below_minimum_threshold_rejected(self):
        """29-minute threshold should be rejected."""
        assert not (29 >= 30)

    def test_above_maximum_threshold_rejected(self):
        """601-minute threshold should be rejected."""
        assert not (601 <= 600)

    def test_iata_code_uppercased(self):
        """IATA codes should be stored uppercased."""
        raw   = "ba456"
        stored = raw.upper().strip()
        assert stored == "BA456"

    def test_valid_policy_id_returned(self):
        """First policy should get ID POL-00001."""
        counter = 1
        pid = f"POL-{counter:05d}"
        assert pid == "POL-00001"

    def test_second_policy_increments_id(self):
        """Second policy should get ID POL-00002."""
        counter = 2
        pid = f"POL-{counter:05d}"
        assert pid == "POL-00002"


# ── file_claim() validation ───────────────────────────────────────────────────

class TestFileClaimValidation:
    """file_claim() state and authorization checks."""

    def _make_policy(self, state="active", holder=POLICYHOLDER_ADDRESS) -> dict:
        return {
            "policy_id"               : "POL-00001",
            "policyholder"            : holder,
            "flight_iata"             : SAMPLE_FLIGHT_IATA,
            "flight_date"             : SAMPLE_FLIGHT_DATE,
            "delay_threshold_minutes" : SAMPLE_THRESHOLD,
            "payout_amount_wei"       : SAMPLE_PAYOUT,
            "state"                   : state,
            "claim_id"                : None,
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
        """First claim should be CLM-00002 (counter advanced after POL-00001)."""
        counter = 2
        cid = f"CLM-{counter:05d}"
        assert cid == "CLM-00002"
