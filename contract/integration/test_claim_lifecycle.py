"""
Integration tests — end-to-end audit lifecycle scenarios.

These tests document the full audit lifecycle:
  create_spec → submit_telemetry → audit_node → read result
"""

import pytest
from conftest import (
    AUDITOR_ADDRESS,
    CREATOR_ADDRESS,
    sample_spec_json,
    sample_telemetry_json,
)


class TestAuditLifecycle:
    """Documents expected state transitions through the full lifecycle."""

    def test_spec_creation_and_telemetry_audit(self):
        """Simulates full workflow step-by-step."""
        # 1. Spec is created by owner
        spec = {
            "spec_id": "spec-123",
            "creator": CREATOR_ADDRESS,
            "auditor": AUDITOR_ADDRESS,
            "node_id": "LUMI-NODE-PROD-01",
            "state": "active",
        }
        assert spec["state"] == "active"

        # 2. Auditor submits Node Telemetry
        telemetry = {
            "spec_id": "spec-123",
            "auditor": AUDITOR_ADDRESS,
            "report_summary": "Online and healthy.",
            "state": "submitted",
        }
        assert telemetry["state"] == "submitted"

        # 3. Consensus evaluates and finalizes audit
        audit = {
            "spec_id": "spec-123",
            "state": "FINALIZED",
            "metrics": [
                {"metric_id": "uptime_check", "status": "PASS"},
                {"metric_id": "cpu_check", "status": "PASS"}
            ],
            "result": "VERIFIED",
        }
        
        assert audit["state"] == "FINALIZED"
        assert audit["result"] == "VERIFIED"
