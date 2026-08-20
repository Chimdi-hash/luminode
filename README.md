# ParametricCropInsurance — GenLayer Intelligent Contract

> **Automatic, keyless weather-based drought insurance for farmers, powered by GenLayer's Optimistic Democracy.**

---

## What It Does

`ParametricCropInsurance` is a standalone GenLayer Intelligent Contract that allows:

1. **Farmers** to purchase drought insurance on-chain by specifying their farm's coordinates (latitude and longitude), a date range, a cumulative rainfall threshold (in mm), and a payout amount.
2. **Claimants** to file a claim if they experience a drought during the coverage period.
3. **AI-Validator Consensus** to verify and settle the claim automatically by fetching weather records, aggregating cumulative rainfall, and deciding on the payout status without third-party oracles or API keys.

---

## Key Innovation: Free Public API Consensus

Unlike traditional parametric contracts that require paid API plans, centralized oracles, or complex API key setup (which frequently crashes sandboxed environments), this contract queries the **Open-Meteo Historical Archive API**. 

* **No API Keys Required:** Valid, public keyless endpoints ensure 100% successful deployments on the GenLayer Studio.
* **Deterministic Aggregation + Qualitative Context:** Cumulative rainfall sum is calculated programmatically (preventing LLM calculation errors), while the LLM is leveraged solely to assess drought severity and write the final verdict reasoning.

---

## Consensus Design — Comparative Equivalence Principle

To verify claims, validators replicate the leader's computation using a **Comparative Equivalence Principle**:

```
LEADER
  ├─ Fetches historical weather daily rainfall list from Open-Meteo
  ├─ Calculates cumulative rainfall sum (in mm)
  ├─ Evaluates rain < threshold?  ← Deterministic ground-truth check
  ├─ Injects metrics into LLM prompt
  └─ LLM writes short reasoning explaining the drought severity
       Returns → { approved, cumulative_rain_mm, reasoning, edge_case }

EACH CONSENSUS VALIDATOR
  ├─ Independently fetches the same Open-Meteo coordinates/dates
  ├─ Aggregates its own cumulative rainfall sum
  └─ Accepts leader's result if BOTH:
       (a) |validator_rain - leader_rain| <= 0.2 mm   ← accounts for floating-point changes
       (b) validator's programmatic approval == leader's decision
```

---

## Contract API

### Write Methods (`gl.public.write`)

* `purchase_policy(latitude, longitude, start_date, end_date, rain_threshold_mm, payout_amount_wei)`: Purchases a policy. Returns `policy_id`.
* `file_claim(policy_id)`: Registers a pending claim for an active policy. Returns `claim_id`.
* `settle_claim(claim_id)`: Triggers AI-validator consensus. Queries Open-Meteo API, calculates rainfall, executes LLM evaluation, and settles the claim on-chain.

### View Methods (`gl.public.view`)

* `get_policy(policy_id)`: Returns the detailed policy JSON.
* `get_claim(claim_id)`: Returns the detailed claim JSON.
* `get_policy_with_claim(policy_id)`: Returns both the policy and its claim in one response.
* `list_policies_for(address)`: Returns all policies purchased by a specific address.
* `get_contract_info()`: Returns global contract statistics (total policies, active, claimed, settled, rejected).

---

## Deployment & Testing in GenLayer Studio

### Step 1 — Deploy
Leave constructor arguments blank. The contract constructor accepts optional arguments dynamically to prevent deployment crashes.

### Step 2 — Buy a Policy
Call `purchase_policy` with a location and past date range (historical archive requires dates in the past, e.g. a previous crop season):
```python
purchase_policy(
    latitude="52.52",
    longitude="13.41",
    start_date="2023-08-01",
    end_date="2023-08-15",
    rain_threshold_mm=80,
    payout_amount_wei=1000000000000000000
)
# Returns: "POL-00000"
```

### Step 3 — File a Claim
Call `file_claim` from the same wallet address:
```python
file_claim("POL-00000")
# Returns: "CLM-00001"
```

### Step 4 — Settle the Claim
Call `settle_claim` (callable by anyone to allow automated scheduler bots):
```python
settle_claim("CLM-00001")
```

### Step 5 — Verify Payout
Call `get_claim("CLM-00001")` to view the finalized consensus result:
```json
{
  "state": "approved",
  "cumulative_rain_mm": 69.9,
  "verdict_reasoning": "Drought confirmed. Cumulative rain was 69.9mm, below the 80mm threshold. Crop stress is moderate."
}
```
