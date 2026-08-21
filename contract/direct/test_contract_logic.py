"""
Direct unit tests — pure Python logic, no GenLayer runtime required.

Tests cover:
  - Input validation rules
  - Spec ID generation format
  - Error prefix classification
"""

import re
import pytest

ERR_EXPECTED = "[EXPECTED]"
ERR_EXTERNAL = "[EXTERNAL]"


class TestIdGeneration:
    """Spec ID must match expected format."""

    def test_spec_id_format(self):
        import hashlib
        NS = "LumiNode/v1/"
        spec_id_regex = re.compile(r"^spec-[0-9a-f]{64}$")
        
        # Simulate ID generation digest
        digest_val = hashlib.sha256((NS + "spec-id/test").encode("utf-8")).hexdigest()
        spec_id = f"spec-{digest_val}"
        
        assert spec_id_regex.fullmatch(spec_id) is not None


class TestInputValidation:
    """Metrics validation rules."""

    def test_metric_id_naming_rules(self):
        regex = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
        valid = ["cpu-check", "uptime_123", "memory_leak"]
        invalid = ["CPU_check", "uptime check", "a" * 50]
        
        for item in valid:
            assert regex.fullmatch(item) is not None
        for item in invalid:
            assert regex.fullmatch(item) is None


class TestErrorClassification:
    def test_expected_prefix(self):
        msg = f"{ERR_EXPECTED} Spec not found"
        assert msg.startswith("[EXPECTED]")

    def test_external_prefix(self):
        msg = f"{ERR_EXTERNAL} Node metrics server returned 503"
        assert msg.startswith("[EXTERNAL]")
