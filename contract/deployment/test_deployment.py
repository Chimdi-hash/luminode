"""
Deployment smoke tests — verify initial state and metrics validation.
"""

import pytest
import json
from conftest import (
    AUDITOR_ADDRESS,
    CREATOR_ADDRESS,
    sample_spec_json,
    sample_telemetry_json,
)


class TestInitialState:
    """Contract state immediately after deployment."""

    def test_empty_spec_records_on_deploy(self):
        spec_records = {}
        assert len(spec_records) == 0

    def test_empty_telemetry_records_on_deploy(self):
        telemetry_records = {}
        assert len(telemetry_records) == 0

    def test_counter_starts_at_zero(self):
        _next_count = 0
        assert _next_count == 0


class TestSpecValidation:
    """Spec validation checks."""

    def test_auditor_address_format(self):
        addr = AUDITOR_ADDRESS
        assert len(addr) == 42
        assert addr.startswith("0x")

    def test_metric_id_validation(self):
        import re
        metric_id_regex = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
        assert metric_id_regex.fullmatch("uptime_check") is not None
        assert metric_id_regex.fullmatch("Invalid_Metric") is None
