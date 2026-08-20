"""
Shared pytest fixtures for ParametricCropInsurance test suite.

Fixtures provide:
  - Mock Open-Meteo rainfall response builder
  - Sample policy and claim configuration constants
"""

import pytest

# ── Sample configuration constants ───────────────────────────────────────────

SAMPLE_LATITUDE      = "52.52"
SAMPLE_LONGITUDE     = "13.41"
SAMPLE_START_DATE    = "2023-08-01"
SAMPLE_END_DATE      = "2023-08-15"
SAMPLE_THRESHOLD_MM  = 50   # 50 mm rain threshold for drought
SAMPLE_PAYOUT         = 1_000_000_000_000_000_000  # 1 GEN in wei

OWNER_ADDRESS         = "0xOwner000000000000000000000000000000000001"
POLICYHOLDER_ADDRESS  = "0xHolder00000000000000000000000000000000002"
OTHER_ADDRESS         = "0xOther000000000000000000000000000000000003"


# ── Mock Open-Meteo response builders ────────────────────────────────────────

def make_openmeteo_response(
    rainfall_list: list = None,
) -> dict:
    """Build a minimal Open-Meteo archive API response dict."""
    if rainfall_list is None:
        rainfall_list = [0.0] * 15
    return {
        "daily": {
            "time": [f"2023-08-{i:02d}" for i in range(1, 16)],
            "rain_sum": rainfall_list
        }
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def drought_flight_data():  # keeping fixture names similar or updated
    """Rainfall sum of 12.5mm — below 50mm threshold (drought active)."""
    return make_openmeteo_response(
        rainfall_list=[1.0, 0.5, 0.0, 2.0, 0.0, 4.0, 0.0, 0.0, 1.0, 0.0, 0.0, 3.0, 0.0, 1.0, 0.0]
    )


@pytest.fixture
def non_drought_flight_data():
    """Rainfall sum of 75.0mm — above 50mm threshold (no drought)."""
    return make_openmeteo_response(
        rainfall_list=[5.0, 10.0, 8.0, 2.0, 5.0, 15.0, 0.0, 1.0, 4.0, 5.0, 0.0, 10.0, 5.0, 3.0, 2.0]
    )


@pytest.fixture
def near_threshold_flight_data():
    """Rainfall sum of 49.8mm — just under 50mm threshold."""
    return make_openmeteo_response(
        rainfall_list=[3.0] * 15 + [4.8]
    )


@pytest.fixture
def sample_policy_params() -> dict:
    """Standard crop policy parameters for testing."""
    return {
        "latitude":          SAMPLE_LATITUDE,
        "longitude":         SAMPLE_LONGITUDE,
        "start_date":        SAMPLE_START_DATE,
        "end_date":          SAMPLE_END_DATE,
        "rain_threshold_mm": SAMPLE_THRESHOLD_MM,
        "payout_amount_wei": SAMPLE_PAYOUT,
    }
