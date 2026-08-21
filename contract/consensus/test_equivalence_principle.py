"""
Consensus tests — verify Equivalence Principle behaviour.

These tests simulate leader and validator running independently and check
that the equivalence checks produce correct verification decisions across
a range of audit proposals.
"""

import pytest


def make_mock_proposal(spec_id: str, spec_digest: str, telemetry_digest: str, state: str, metrics: list) -> dict:
    """Build a mock consensus proposal dict."""
    return {
        "spec_id": spec_id,
        "spec_digest": spec_digest,
        "telemetry_digest": telemetry_digest,
        "state": state,
        "source_observations": [
            {
                "source_index": 0,
                "url": "https://metrics.luminode.dev/nodes/lumi-node-prod-01.json",
                "status_class": "OK",
                "available": True,
                "media_accepted": True,
                "redirect_blocked": False,
                "content_digest": "a" * 64,
            }
        ],
        "observation_digest": "b" * 64,
        "metrics": metrics,
    }


def validator_check(leader: dict, expected: dict) -> bool:
    """
    Mirrors the validator_fn exact-match comparative logic from audit_node().
    Returns True if validator accepts leader's result.
    """
    return leader == expected


# ── Straightforward consensus ─────────────────────────────────────────────────

class TestEquivalencePrinciple:

    def test_both_agree_verified(self):
        """Both leader and validator generate the exact same verified audit proposal."""
        metrics = [
            {"metric_id": "uptime_check", "status": "PASS"},
            {"metric_id": "cpu_check", "status": "PASS"},
        ]
        leader = make_mock_proposal("spec-1", "spec-digest-a", "telem-digest-a", "FINALIZED", metrics)
        expected = make_mock_proposal("spec-1", "spec-digest-a", "telem-digest-a", "FINALIZED", metrics)
        
        assert validator_check(leader, expected) is True

    def test_both_agree_failed(self):
        """Both agree on failing metrics."""
        metrics = [
            {"metric_id": "uptime_check", "status": "FAIL"},
            {"metric_id": "cpu_check", "status": "PASS"},
        ]
        leader = make_mock_proposal("spec-1", "spec-digest-a", "telem-digest-a", "FINALIZED", metrics)
        expected = make_mock_proposal("spec-1", "spec-digest-a", "telem-digest-a", "FINALIZED", metrics)
        
        assert validator_check(leader, expected) is True

    def test_mismatch_fails_consensus(self):
        """If validator generates different metrics status, consensus is rejected."""
        leader_metrics = [
            {"metric_id": "uptime_check", "status": "PASS"},
            {"metric_id": "cpu_check", "status": "PASS"},
        ]
        validator_metrics = [
            {"metric_id": "uptime_check", "status": "UNRESOLVED"},
            {"metric_id": "cpu_check", "status": "PASS"},
        ]
        
        leader = make_mock_proposal("spec-1", "spec-digest-a", "telem-digest-a", "FINALIZED", leader_metrics)
        expected = make_mock_proposal("spec-1", "spec-digest-a", "telem-digest-a", "FINALIZED", validator_metrics)
        
        assert validator_check(leader, expected) is False
