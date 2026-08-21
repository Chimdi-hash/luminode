"""
Shared pytest fixtures for LumiNode test suite.

Fixtures provide:
  - Mock Node Telemetry log data responses
  - Mock log repository response builders
  - Sample specification and telemetry config constants
"""

import pytest

VERSION = "1.0"

# Sample addresses
AUDITOR_ADDRESS = "0xholder00000000000000000000000000000000002"
CREATOR_ADDRESS = "0xowner000000000000000000000000000000000001"


def make_mock_log_response(
    cpu_usage_pct: float = 24.5,
    uptime_pct: float = 99.98,
    memory_leak_detected: bool = False,
) -> dict:
    """Build a minimal node log structure in JSON format."""
    return {
        "node_status": "ONLINE",
        "cpu_usage_avg": cpu_usage_pct,
        "memory_leak": memory_leak_detected,
        "uptime": uptime_pct,
    }


@pytest.fixture
def clean_node_telemetry_logs():
    """Telemetry report representing a perfectly healthy, passing node."""
    return make_mock_log_response(
        cpu_usage_pct=15.2,
        uptime_pct=99.99,
        memory_leak_detected=False,
    )


@pytest.fixture
def failing_node_telemetry_logs():
    """Telemetry report representing a failing node (high CPU, memory leaks)."""
    return make_mock_log_response(
        cpu_usage_pct=98.5,
        uptime_pct=84.2,
        memory_leak_detected=True,
    )


@pytest.fixture
def sample_spec_json() -> str:
    """Standard Node Spec JSON payload."""
    import json
    return json.dumps({
        "schema_version": VERSION,
        "auditor": AUDITOR_ADDRESS,
        "node_id": "LUMI-NODE-PROD-01",
        "spec_description": "Production edge validator specification profile.",
        "metrics": [
            {"metric_id": "uptime_check", "description": "Uptime must be >= 99.9%"},
            {"metric_id": "cpu_check", "description": "Average CPU usage must be <= 80%"},
            {"metric_id": "memory_leak_check", "description": "No memory leaks detected"}
        ]
    })


@pytest.fixture
def sample_telemetry_json() -> str:
    """Standard Telemetry submission JSON payload."""
    import json
    return json.dumps({
        "schema_version": VERSION,
        "spec_id": "", # filled dynamically in tests
        "report_summary": "Node audit reports for daily logs. CPU and Memory are stable.",
        "log_urls": ["https://metrics.luminode.dev/nodes/lumi-node-prod-01.json"]
    })
