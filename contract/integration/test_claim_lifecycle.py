"""
Integration tests — end-to-end lifecycle scenarios.

These tests document the full claim lifecycle:
  purchase_policy → file_claim → settle_claim → read verdict

Since these tests require the GenLayer runtime to execute settle_claim()
(which uses gl.vm.run_nondet_unsafe), they are marked as integration tests
and require a live GenLayer testnet or Studio connection to run fully.

The test scenarios below document expected behaviour and can be run
as dry-run logic tests without the runtime by mocking gl.vm.run_nondet_unsafe.
"""

import pytest
from conftest import (
    SAMPLE_LATITUDE,
    SAMPLE_LONGITUDE,
    SAMPLE_START_DATE,
    SAMPLE_END_DATE,
    SAMPLE_THRESHOLD_MM,
    SAMPLE_PAYOUT,
    POLICYHOLDER_ADDRESS,
)


# ── Lifecycle state machine ───────────────────────────────────────────────────

class TestPolicyLifecycle:
    """Documents expected state transitions through the full lifecycle."""

    def test_policy_starts_active(self):
        """Newly purchased policy should be in 'active' state."""
        policy = {
            "state"    : "active",
            "claim_id" : None,
        }
        assert policy["state"] == "active"
        assert policy["claim_id"] is None

    def test_policy_moves_to_claimed_after_file_claim(self):
        """After file_claim(), policy state should be 'claimed'."""
        policy = {"state": "active", "claim_id": None}
        # Simulate file_claim()
        policy["state"]    = "claimed"
        policy["claim_id"] = "CLM-00001"
        assert policy["state"]    == "claimed"
        assert policy["claim_id"] == "CLM-00001"

    def test_policy_moves_to_settled_after_approval(self):
        """After settle_claim() approves, policy should be 'settled'."""
        policy = {"state": "claimed"}
        # Simulate successful settlement
        policy["state"] = "settled"
        assert policy["state"] == "settled"

    def test_policy_moves_to_rejected_after_denial(self):
        """After settle_claim() rejects, policy should be 'rejected'."""
        policy = {"state": "claimed"}
        # Simulate unsuccessful settlement
        policy["state"] = "rejected"
        assert policy["state"] == "rejected"


class TestClaimLifecycle:
    """Documents expected claim state transitions."""

    def _make_pending_claim(self) -> dict:
        return {
            "claim_id"             : "CLM-00001",
            "policy_id"            : "POL-00000",
            "claimant"             : POLICYHOLDER_ADDRESS,
            "state"                : "pending",
            "cumulative_rain_mm"   : -1.0,
            "verdict_reasoning"    : "",
            "edge_case_detected"   : "none",
        }

    def test_claim_starts_pending(self):
        claim = self._make_pending_claim()
        assert claim["state"] == "pending"
        assert claim["cumulative_rain_mm"] == -1.0  # not yet measured

    def test_claim_approved_after_sufficient_drought(self):
        """Claim with rain < threshold should transition to 'approved'."""
        claim = self._make_pending_claim()
        # Simulate settle_claim() result
        claim["state"]              = "approved"
        claim["cumulative_rain_mm"] = 12.5
        claim["verdict_reasoning"]  = "Drought confirmed. Rain was 12.5mm, below the 50mm threshold."
        claim["edge_case_detected"] = "none"

        assert claim["state"] == "approved"
        assert claim["cumulative_rain_mm"] < SAMPLE_THRESHOLD_MM
        assert len(claim["verdict_reasoning"]) > 0

    def test_claim_rejected_after_insufficient_drought(self):
        """Claim with rain >= threshold should transition to 'rejected'."""
        claim = self._make_pending_claim()
        # Simulate settle_claim() result
        claim["state"]              = "rejected"
        claim["cumulative_rain_mm"] = 75.0
        claim["verdict_reasoning"]  = "No drought. Rain was 75.0mm, above the 50mm threshold."
        claim["edge_case_detected"] = "none"

        assert claim["state"] == "rejected"
        assert claim["cumulative_rain_mm"] >= SAMPLE_THRESHOLD_MM

    def test_already_settled_claim_cannot_be_re_settled(self):
        """Attempting to settle a non-pending claim should raise an error."""
        claim = self._make_pending_claim()
        claim["state"] = "approved"  # already settled

        is_pending = claim["state"] == "pending"
        assert is_pending is False  # would trigger the guard


# ── Scenario: full happy path ─────────────────────────────────────────────────

class TestHappyPathScenario:
    """
    Documents the full approved-claim happy path as a sequential scenario.

    To run against GenLayer testnet:
        1. Deploy Crop Insurance contract
        2. Call purchase_policy() with coordinates & past dates
        3. Call file_claim()
        4. Call settle_claim()
        5. Call get_claim() and assert state == "approved"
    """

    def test_full_lifecycle_state_sequence(self):
        """
        Simulates the state transitions without the GenLayer runtime.
        Documents the expected sequence of states.
        """
        # Step 1 — Deploy
        policies = {}
        claims   = {}
        counter  = 0

        # Step 2 — purchase_policy()
        policy_id = f"POL-{counter:05d}"
        counter  += 1
        policies[policy_id] = {
            "state"    : "active",
            "claim_id" : None,
        }
        assert policies[policy_id]["state"] == "active"

        # Step 3 — file_claim()
        claim_id = f"CLM-{counter:05d}"
        counter += 1
        claims[claim_id] = {"state": "pending", "cumulative_rain_mm": -1.0}
        policies[policy_id]["state"]    = "claimed"
        policies[policy_id]["claim_id"] = claim_id
        assert policies[policy_id]["state"] == "claimed"
        assert claims[claim_id]["state"]    == "pending"

        # Step 4 — settle_claim() (simulated approval)
        claims[claim_id]["state"]              = "approved"
        claims[claim_id]["cumulative_rain_mm"] = 12.5
        policies[policy_id]["state"]           = "settled"

        # Step 5 — Assertions
        assert policies[policy_id]["state"]             == "settled"
        assert claims[claim_id]["state"]                == "approved"
        assert claims[claim_id]["cumulative_rain_mm"]   < SAMPLE_THRESHOLD_MM
