# ParametricFlightInsurance — GenLayer Intelligent Contract

> **Automatic, trustless flight-delay insurance powered by GenLayer's Optimistic Democracy consensus.**

---

## What It Does

`ParametricFlightInsurance` is a standalone GenLayer Intelligent Contract that lets users:

1. **Buy** a parametric flight-delay insurance policy on-chain — specifying a flight, date, delay threshold (e.g. 120 min), and payout amount.
2. **File** a claim after their flight lands.
3. **Settle** the claim through decentralised AI-validator consensus — no human adjudicator, no oracle intermediary.

The settlement step fetches **live flight data** from the AviationStack API, verifies the delay programmatically, and uses an LLM to handle policy-term edge cases (cancellation vs. delay, diversions, premature claims). Validators independently replicate this process and must agree before the claim is finalised on-chain.

---

## Why GenLayer Makes This Possible

Traditional smart contracts cannot settle this claim: they have no access to live flight status, cannot interpret policy language, and cannot handle the slight data variance between two independent API calls made seconds apart.

GenLayer provides:

| Capability | How It's Used |
|---|---|
| **Live web access** | `gl.nondet.web.get()` fetches AviationStack API per validator |
| **On-chain LLM reasoning** | `gl.nondet.exec_prompt()` interprets policy edge cases |
| **Non-deterministic consensus** | `gl.vm.run_nondet_unsafe()` coordinates leader + validators |
| **Equivalence Principle** | Validators compare delay values within 5-min margin |

---

## Consensus Design — Comparative Equivalence Principle

This contract uses the **Comparative Equivalence Principle**, where validators replicate the leader's computation and compare quantifiable outputs within a tolerance.

```
LEADER
  ├─ Fetches live flight data from AviationStack
  ├─ Extracts stable fields: dep_delay, arr_delay, flight_status
  ├─ Derives canonical_delay_minutes (arrival delay preferred)
  ├─ Programmatic check: delay >= threshold?   ← deterministic ground truth
  ├─ Injects verified numbers into LLM prompt
  └─ LLM adds reasoning + detects edge cases (cancellation, diversion)
       Returns → { approved, canonical_delay_minutes, reasoning, edge_case }

EACH VALIDATOR
  ├─ Independently fetches the same AviationStack endpoint
  ├─ Derives its own canonical_delay_minutes
  └─ Accepts leader if BOTH:
       (a) |validator_delay − leader_delay| ≤ 5 minutes   ← within API variance
       (b) validator's programmatic approval == leader's   ← same decision
```

### Why 5-minute margin?

AviationStack updates delay figures in approximately 1-minute increments. Two independent validator calls separated by a few seconds can legitimately straddle an update, producing values that differ by 1–3 minutes. A 5-minute margin absorbs this variance without compromising security: a 5-minute discrepancy at a 120-minute threshold cannot flip the outcome.

### Why programmatic approval overrides the LLM?

The LLM is used **only** for policy-term interpretation and reasoning generation. The numeric delay check is deterministic code — injected into the prompt as "GROUND TRUTH" with an explicit instruction not to override it. This prevents hallucination on character-level or numerical tasks while preserving the LLM's ability to handle qualitative edge cases.

---

## Contract API

### Write Methods

| Method | Description |
|---|---|
| `purchase_policy(flight_iata, flight_date, delay_threshold_minutes, payout_amount_wei)` | Creates a new insurance policy. Returns `policy_id`. |
| `file_claim(policy_id)` | Opens a pending claim against an active policy. Returns `claim_id`. |
| `settle_claim(claim_id)` | **Core method.** Triggers AI-validator consensus to approve or reject the claim. Callable by anyone. |

### View Methods

| Method | Description |
|---|---|
| `get_policy(policy_id)` | Returns full policy record. |
| `get_claim(claim_id)` | Returns claim record including AI verdict and measured delay. |
| `get_policy_with_claim(policy_id)` | Returns policy + claim in one call. |
| `list_policies_for(address)` | Returns all policies owned by an address. |
| `get_contract_info()` | Returns aggregate stats (total/active/settled/rejected counts). |

---

## Lifecycle State Machine

```
Policy: ACTIVE ──file_claim()──► CLAIMED ──settle_claim()──► SETTLED
                                                          └──► REJECTED

Claim:  PENDING ──settle_claim()──► APPROVED
                               └──► REJECTED
```

---

## Deployment & Usage

### Prerequisites

1. Get a free AviationStack API key at [aviationstack.com](https://aviationstack.com/) (100 req/month free).
2. Open [GenLayer Studio](https://studio.genlayer.com) or deploy via the GenLayer CLI.

### Deploy

```python
# Constructor argument: your AviationStack API key
ParametricFlightInsurance("YOUR_AVIATIONSTACK_KEY")
```

### Example Walkthrough

```python
# 1. Purchase a policy
policy_id = contract.purchase_policy(
    flight_iata="BA456",
    flight_date="2025-09-01",
    delay_threshold_minutes=120,
    payout_amount_wei=1_000_000_000_000_000_000  # 1 GEN
)
# → "POL-00001"

# 2. File a claim (after the flight lands)
claim_id = contract.file_claim("POL-00001")
# → "CLM-00002"

# 3. Settle via AI consensus (anyone can call this)
contract.settle_claim("CLM-00002")

# 4. Read the verdict
result = contract.get_claim("CLM-00002")
# {
#   "claim_id": "CLM-00002",
#   "state": "approved",                         ← or "rejected"
#   "actual_delay_minutes": 143,
#   "verdict_reasoning": "Flight BA456 arrived 143 minutes late on 2025-09-01,
#                         exceeding the 120-minute policy threshold.",
#   "flight_status": "landed",
#   "edge_case_detected": "none"
# }
```

---

## Error Handling

The contract uses a two-prefix classification scheme:

| Prefix | Meaning | Example |
|---|---|---|
| `[EXPECTED]` | Deterministic business-logic error — fails consistently on all nodes | Wrong policyholder, invalid flight code |
| `[EXTERNAL]` | Transient external-service failure — safe to retry | AviationStack 500, no flight records found |

---

## Stable-Field Extraction

Following GenLayer best practices, `_fetch_flight_data()` extracts **only fields that are stable across independent API calls**:

✅ Extracted: `departure_delay`, `arrival_delay`, `flight_status`  
❌ Excluded: `updated_at`, `live.latitude`, `live.longitude`, `live.speed`, comment counts, cache headers

This is the primary technique for preventing false consensus failures on web-data contracts.

---

## Potential Extensions

- **Multi-leg policies** — chain connections; payout if *any* leg is delayed.
- **Cancellation policies** — separate payout logic for `flight_status == "cancelled"`.
- **Ghost-contract payout** — wire `gl.message.send_tokens()` to `settle_claim()` for real on-chain payouts.
- **DAO governance** — let token holders vote on threshold parameters.
- **Second data source** — add AeroDataBox or OpenSky as a corroborating API for higher security.

---

## License

MIT
