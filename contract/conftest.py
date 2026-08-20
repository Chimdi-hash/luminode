"""
Shared pytest fixtures for ParametricFlightInsurance test suite.

Fixtures provide:
  - Mock flight data responses (approved / rejected / edge cases)
  - Mock AviationStack API response builder
  - Sample policy and claim configuration constants
"""

import pytest

# ── Sample configuration constants ───────────────────────────────────────────

SAMPLE_API_KEY = "test_api_key_00000"

SAMPLE_FLIGHT_IATA    = "BA456"
SAMPLE_FLIGHT_DATE    = "2025-03-15"
SAMPLE_THRESHOLD      = 120   # minutes
SAMPLE_PAYOUT         = 1_000_000_000_000_000_000  # 1 GEN in wei

OWNER_ADDRESS         = "0xOwner000000000000000000000000000000000001"
POLICYHOLDER_ADDRESS  = "0xHolder00000000000000000000000000000000002"
OTHER_ADDRESS         = "0xOther000000000000000000000000000000000003"


# ── Mock AviationStack response builders ─────────────────────────────────────

def make_aviationstack_response(
    departure_delay: int = 0,
    arrival_delay: int = 0,
    flight_status: str = "landed",
    flight_iata: str = SAMPLE_FLIGHT_IATA,
) -> dict:
    """Build a minimal AviationStack-style API response dict."""
    return {
        "data": [
            {
                "flight_status": flight_status,
                "flight": {"iata": flight_iata},
                "departure": {"delay": departure_delay},
                "arrival":   {"delay": arrival_delay},
            }
        ]
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def approved_flight_data():
    """Flight with 143-minute arrival delay — above 120-minute threshold."""
    return make_aviationstack_response(
        departure_delay=130,
        arrival_delay=143,
        flight_status="landed",
    )


@pytest.fixture
def rejected_flight_data():
    """Flight with 45-minute arrival delay — below 120-minute threshold."""
    return make_aviationstack_response(
        departure_delay=30,
        arrival_delay=45,
        flight_status="landed",
    )


@pytest.fixture
def cancelled_flight_data():
    """Cancelled flight — edge case, not a standard delay claim."""
    return make_aviationstack_response(
        departure_delay=0,
        arrival_delay=0,
        flight_status="cancelled",
    )


@pytest.fixture
def near_threshold_flight_data():
    """Flight delayed 122 minutes — just over 120-minute threshold."""
    return make_aviationstack_response(
        departure_delay=115,
        arrival_delay=122,
        flight_status="landed",
    )


@pytest.fixture
def sample_policy_params() -> dict:
    """Standard policy parameters for testing."""
    return {
        "flight_iata":             SAMPLE_FLIGHT_IATA,
        "flight_date":             SAMPLE_FLIGHT_DATE,
        "delay_threshold_minutes": SAMPLE_THRESHOLD,
        "payout_amount_wei":       SAMPLE_PAYOUT,
    }
