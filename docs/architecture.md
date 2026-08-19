# Architecture — ParametricFlightInsurance

## Overview

`ParametricFlightInsurance` is a GenLayer Intelligent Contract that automatically settles parametric flight-delay insurance claims. It combines:

- **On-chain state** — Policies and claims stored in contract storage
- **Live web access** — AviationStack API fetched at settlement time by every validator independently
- **LLM reasoning** — Policy edge-case interpretation (cancellations, diversions)
- **Comparative Equivalence Principle** — Validators re-fetch and compare numeric delay values

---

## Repository Structure

```
parametric-flight-insurance/
├── contract/
│   └── parametric_flight_insurance.py   # The Intelligent Contract
├── docs/
│   └── architecture.md                  # This file
├── schemas/
│   └── settlement-verdict-v1.schema.json # JSON schema for the LLM verdict
├── tests/
│   ├── __init__.py
│   ├── conftest.py                       # Shared fixtures
│   ├── direct/                           # Unit tests for pure logic
│   ├── consensus/                        # Equivalence Principle tests
│   ├── deployment/                       # Deploy + method smoke tests
│   └── integration/                      # End-to-end lifecycle tests
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## Contract Components

### State

```
ParametricFlightInsurance
 ├── policies  : dict[policy_id → policy_record]
 ├── claims    : dict[claim_id  → claim_record]
 ├── api_key   : str   (AviationStack access key, set at deployment)
 ├── owner     : str   (deployer address)
 └── _next_id  : int   (monotonic counter)
```

### Policy record schema

| Field | Type | Description |
|---|---|---|
| `policy_id` | str | Unique ID, e.g. `POL-00001` |
| `policyholder` | str | Wallet address of buyer |
| `flight_iata` | str | IATA flight code, e.g. `BA456` |
| `flight_date` | str | ISO-8601 date `YYYY-MM-DD` |
| `delay_threshold_minutes` | int | Trigger threshold (30–600 min) |
| `payout_amount_wei` | int | Coverage amount in wei units |
| `state` | str | `active` / `claimed` / `settled` / `rejected` |
| `claim_id` | str \| None | Linked claim if one exists |

### Claim record schema

| Field | Type | Description |
|---|---|---|
| `claim_id` | str | Unique ID, e.g. `CLM-00002` |
| `policy_id` | str | Parent policy |
| `claimant` | str | Wallet address |
| `state` | str | `pending` / `approved` / `rejected` |
| `actual_delay_minutes` | int | Measured delay from API |
| `verdict_reasoning` | str | LLM-generated explanation |
| `flight_status` | str | `landed` / `cancelled` / `diverted` / … |
| `edge_case_detected` | str | `none` or description of edge case |

---

## Data Flow — `settle_claim()`

```
settle_claim(claim_id)
│
├── [DETERMINISTIC] Validate claim exists and is pending
│
├── [NON-DETERMINISTIC — Leader]
│    ├── _fetch_flight_data(flight_iata, flight_date)
│    │    └── AviationStack API → extract stable fields only
│    │         (departure_delay, arrival_delay, flight_status)
│    │         NOT: updated_at, coordinates, speed, cache headers
│    │
│    ├── Derive canonical_delay_minutes
│    │    = arrival_delay if > 0, else departure_delay
│    │
│    ├── Programmatic check: canonical_delay >= threshold?
│    │    → This is the GROUND TRUTH, injected into LLM prompt
│    │
│    ├── LLM prompt (response_format="json")
│    │    → Reads policy terms + flight data
│    │    → Detects edge cases (cancellation ≠ delay, premature claim)
│    │    → MUST NOT override the programmatic approval
│    │    → Returns: {approved, canonical_delay_minutes, reasoning, edge_case}
│    │
│    └── Returns leader result dict
│
├── [NON-DETERMINISTIC — Each Validator]
│    ├── Independently fetches same AviationStack endpoint
│    ├── Derives own canonical_delay_minutes
│    └── Comparative Equivalence Principle:
│         (a) |validator_delay − leader_delay| ≤ 5 min  ← within API variance
│         (b) validator_approved == leader_approved      ← same decision
│         (c) Near-threshold tolerance: if |delay − threshold| ≤ 5, defer to leader
│
└── [DETERMINISTIC] Persist outcome to contract state
     → claim.state = approved | rejected
     → policy.state = settled | rejected
```

---

## Equivalence Principle Choice

This contract uses the **Comparative Equivalence Principle** (not Non-Comparative) because:

1. The primary output is **quantitative** — minutes of delay. This is measurable and directly comparable across validators.
2. The AviationStack API provides the same underlying data to all callers; small differences (1–3 min) arise only from update-boundary effects, not genuine disagreement.
3. A 5-minute tolerance comfortably absorbs API update variance while being negligible at the typical 60–180 minute threshold.

Non-Comparative EP (validators assess the leader's verdict without re-running) would be appropriate if the output were purely qualitative — e.g. a text summary where regeneration would be expensive and pointless. For a numeric delay check, re-fetching and comparing is both cheap and provides stronger security guarantees.

---

## Error Classification

| Prefix | Meaning | Examples |
|---|---|---|
| `[EXPECTED]` | Deterministic business error; all nodes agree to fail | Wrong policyholder, invalid IATA code, non-pending claim |
| `[EXTERNAL]` | Transient external failure; safe to retry | AviationStack 500, no flight records found |

---

## Stable-Field Extraction

AviationStack responses include many volatile fields that change between independent validator calls:

| Field | Stable? | Reason |
|---|---|---|
| `departure.delay` | ✅ | Updates infrequently once flight is in-progress |
| `arrival.delay` | ✅ | Same |
| `flight_status` | ✅ | State machine: scheduled→active→landed |
| `departure.actual` | ⚠️ | Timestamp string — excluded |
| `live.latitude` | ❌ | Changes every second |
| `live.speed_horizontal` | ❌ | Changes every second |
| `updated` | ❌ | Always changes between calls |

Only the ✅ fields are extracted and returned by `_fetch_flight_data()`.

---

## Security Considerations

- **API key storage**: The AviationStack key is stored in contract state. This is visible on-chain. For production, consider using a key rotation pattern or a proxy contract that wraps the key server-side. For testnet purposes the free-tier key has negligible risk exposure.
- **Programmatic-over-LLM enforcement**: The boolean approval is computed by code (`delay >= threshold`), not by the LLM. The LLM result is only used for reasoning text and edge-case detection. Even if the LLM were to hallucinate an incorrect approval, the contract code overrides it with the programmatic result.
- **Near-threshold tolerance**: Claims where `|delay − threshold| ≤ 5 minutes` could go either way depending on which minute the API updates. The validator function explicitly defers to the leader in this band to prevent liveness failure, which is the correct trade-off: the 5-minute band is too small to represent meaningful economic disagreement.
