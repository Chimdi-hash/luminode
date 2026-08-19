# { "Depends": "py-genlayer:t0k3n" }
# ─────────────────────────────────────────────────────────────────────────────
# ParametricFlightInsurance — GenLayer Intelligent Contract
#
# Automatically settles flight-delay insurance claims using:
#   • Live flight data fetched from the AviationStack API
#   • Comparative Equivalence Principle — validators independently fetch the
#     same flight data and must agree on the delay value (within 5-min margin)
#     AND on the approval decision before consensus is reached
#   • Grounded LLM reasoning — verified delay figures injected as ground truth;
#     LLM handles only policy-term interpretation and edge-case detection
#
# Author: U_StackLabs
# ─────────────────────────────────────────────────────────────────────────────

from genlayer import *
import json

# ── Error classification prefixes ────────────────────────────────────────────
# [EXPECTED] = deterministic business-logic errors (fail consistently on all nodes)
# [EXTERNAL] = transient external-service failures (safe to retry)
ERR_EXPECTED = "[EXPECTED]"
ERR_EXTERNAL = "[EXTERNAL]"

# ── Policy / Claim lifecycle states ──────────────────────────────────────────
POLICY_ACTIVE   = "active"
POLICY_CLAIMED  = "claimed"
POLICY_SETTLED  = "settled"
POLICY_REJECTED = "rejected"

CLAIM_PENDING  = "pending"
CLAIM_APPROVED = "approved"
CLAIM_REJECTED = "rejected"


class ParametricFlightInsurance(gl.Contract):
    """
    Parametric Flight Delay Insurance — GenLayer Intelligent Contract
    ═══════════════════════════════════════════════════════════════════

    HOW IT WORKS
    ────────────
    1. A *policyholder* calls purchase_policy(), specifying:
         • IATA flight code  (e.g. "BA456")
         • Flight date       (e.g. "2025-03-15")
         • Delay threshold   (e.g. 120 minutes)
         • Payout amount     (stored in wei equivalent units)

    2. After the flight lands the policyholder calls file_claim() to
       register a pending claim against their active policy.

    3. Anyone (including the claimant) calls settle_claim().  This is
       the core non-deterministic step:

         Leader validator
           └─ fetches live flight data from AviationStack API
           └─ extracts STABLE fields only (delay in minutes, flight_status)
           └─ injects numeric delay as GROUND TRUTH into LLM prompt
           └─ LLM handles edge cases: cancellations, diversions, policy terms
           └─ returns structured JSON: {approved, canonical_delay_minutes, ...}

         Each consensus validator
           └─ independently fetches the same AviationStack endpoint
           └─ compares delay value with leader's (must be within 5-min margin)
           └─ confirms approval decision matches leader's verdict
           └─ returns True / False

       This implements the *Comparative Equivalence Principle*: validators
       re-execute the leader's work and compare quantitative outputs within an
       acceptable tolerance.

    4. If consensus is reached the claim/policy state updates on-chain.
       Payout release would be wired to the ghost-contract balance in a
       production deployment (stub left for clarity in this reference impl).

    EQUIVALENCE PRINCIPLE USED
    ──────────────────────────
    Comparative — validators replicate the leader's data fetch and compare
    numerical delay figures within a 5-minute margin of error, then confirm
    the boolean approval decision matches.  This is appropriate for
    quantifiable outputs (minutes of delay) with natural measurement variance
    across independent API calls made at slightly different times.

    STATE SCHEMA
    ────────────
    policies  : dict[policy_id → policy_record]
    claims    : dict[claim_id  → claim_record]
    api_key   : str   (AviationStack access_key, set at deployment)
    owner     : str   (deployer address)
    _next_id  : int   (monotonic ID counter)
    """

    policies : dict
    claims   : dict
    api_key  : str
    owner    : str
    _next_id : int

    # ── Constructor ──────────────────────────────────────────────────────────

    def __init__(self, aviationstack_api_key: str) -> None:
        """
        Deploy the insurance contract.

        Parameters
        ----------
        aviationstack_api_key : str
            Free-tier key from https://aviationstack.com/
            (100 requests/month on the free plan — sufficient for testnet).
        """
        self.policies  = {}
        self.claims    = {}
        self.api_key   = aviationstack_api_key
        self.owner     = gl.message.sender_address
        self._next_id  = 1

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _next_policy_id(self) -> str:
        pid = f"POL-{self._next_id:05d}"
        self._next_id += 1
        return pid

    def _next_claim_id(self) -> str:
        cid = f"CLM-{self._next_id:05d}"
        self._next_id += 1
        return cid

    def _fetch_flight_data(self, flight_iata: str, flight_date: str) -> dict:
        """
        Fetch live flight data from AviationStack and return ONLY stable fields.

        Volatile fields (updated_at, timestamps, comment counts, etc.) are
        deliberately excluded to prevent spurious consensus failures caused by
        the natural drift between independent validator API calls.

        Returns
        -------
        dict with keys:
            flight_iata, flight_date, flight_status,
            departure_delay_minutes, arrival_delay_minutes,
            canonical_delay_minutes
        """
        url = (
            "http://api.aviationstack.com/v1/flights"
            f"?access_key={self.api_key}"
            f"&flight_iata={flight_iata}"
            f"&flight_date={flight_date}"
            "&limit=1"
        )

        response = gl.nondet.web.get(url)

        if response.status != 200:
            raise ValueError(
                f"{ERR_EXTERNAL} AviationStack returned HTTP {response.status} "
                f"for flight {flight_iata} on {flight_date}"
            )

        raw = json.loads(response.body.decode("utf-8"))

        if not raw.get("data"):
            raise ValueError(
                f"{ERR_EXTERNAL} No flight records returned for "
                f"{flight_iata} on {flight_date}. "
                "Flight may not have operated or date is too far in the future."
            )

        flight = raw["data"][0]
        departure = flight.get("departure", {})
        arrival   = flight.get("arrival",   {})

        dep_delay = int(departure.get("delay") or 0)
        arr_delay = int(arrival.get("delay")   or 0)
        status    = flight.get("flight_status", "unknown")  # scheduled/active/landed/cancelled/diverted

        # Canonical delay = arrival delay (traveller's actual experience).
        # Fall back to departure delay if arrival data is absent (en-route).
        canonical = arr_delay if arr_delay > 0 else dep_delay

        return {
            "flight_iata"              : flight_iata,
            "flight_date"              : flight_date,
            "flight_status"            : status,
            "departure_delay_minutes"  : dep_delay,
            "arrival_delay_minutes"    : arr_delay,
            "canonical_delay_minutes"  : canonical,
        }

    # ── Write: purchase a policy ─────────────────────────────────────────────

    @gl.public.write
    def purchase_policy(
        self,
        flight_iata           : str,
        flight_date           : str,
        delay_threshold_minutes: int,
        payout_amount_wei     : int,
    ) -> str:
        """
        Purchase a parametric flight-delay insurance policy.

        Parameters
        ----------
        flight_iata              : IATA flight code, e.g. "BA456"
        flight_date              : ISO-8601 date, e.g. "2025-03-15"
        delay_threshold_minutes  : Minimum arrival delay for payout, e.g. 120
        payout_amount_wei        : Coverage amount in wei-equivalent units

        Returns
        -------
        str : The newly created policy_id (e.g. "POL-00001")
        """
        if not flight_iata or len(flight_iata.strip()) < 3:
            raise ValueError(f"{ERR_EXPECTED} Invalid IATA code: '{flight_iata}'")
        if not flight_date or len(flight_date) != 10:
            raise ValueError(f"{ERR_EXPECTED} flight_date must be YYYY-MM-DD, got '{flight_date}'")
        if delay_threshold_minutes < 30:
            raise ValueError(f"{ERR_EXPECTED} Minimum delay threshold is 30 minutes")
        if delay_threshold_minutes > 600:
            raise ValueError(f"{ERR_EXPECTED} Maximum delay threshold is 600 minutes (10 hours)")
        if payout_amount_wei <= 0:
            raise ValueError(f"{ERR_EXPECTED} payout_amount_wei must be positive")

        policy_id = self._next_policy_id()
        self.policies[policy_id] = {
            "policy_id"               : policy_id,
            "policyholder"            : gl.message.sender_address,
            "flight_iata"             : flight_iata.upper().strip(),
            "flight_date"             : flight_date,
            "delay_threshold_minutes" : delay_threshold_minutes,
            "payout_amount_wei"       : payout_amount_wei,
            "state"                   : POLICY_ACTIVE,
            "claim_id"                : None,
        }
        return policy_id

    # ── Write: file a claim ──────────────────────────────────────────────────

    @gl.public.write
    def file_claim(self, policy_id: str) -> str:
        """
        File a delay claim against an active policy.

        Only the original policyholder may file a claim.
        The policy moves to 'claimed' state immediately; settlement
        is triggered separately via settle_claim().

        Returns
        -------
        str : The newly created claim_id (e.g. "CLM-00002")
        """
        if policy_id not in self.policies:
            raise ValueError(f"{ERR_EXPECTED} Policy '{policy_id}' does not exist")

        policy = self.policies[policy_id]

        if policy["policyholder"] != gl.message.sender_address:
            raise ValueError(
                f"{ERR_EXPECTED} Only the policyholder can file a claim on '{policy_id}'"
            )
        if policy["state"] != POLICY_ACTIVE:
            raise ValueError(
                f"{ERR_EXPECTED} Policy '{policy_id}' is not active "
                f"(current state: '{policy['state']}')"
            )

        claim_id = self._next_claim_id()
        self.claims[claim_id] = {
            "claim_id"               : claim_id,
            "policy_id"              : policy_id,
            "claimant"               : gl.message.sender_address,
            "state"                  : CLAIM_PENDING,
            "actual_delay_minutes"   : -1,
            "verdict_reasoning"      : "",
            "flight_status"          : "",
            "edge_case_detected"     : "none",
        }

        self.policies[policy_id]["state"]    = POLICY_CLAIMED
        self.policies[policy_id]["claim_id"] = claim_id
        return claim_id

    # ── Write: settle a claim (core non-deterministic method) ────────────────

    @gl.public.write
    def settle_claim(self, claim_id: str) -> None:
        """
        Settle a pending claim using AI-validator consensus.

        ═══════════════════════════════════════════════════════
        CONSENSUS DESIGN — Comparative Equivalence Principle
        ═══════════════════════════════════════════════════════

        LEADER
          1. Fetches live flight data from AviationStack API
          2. Extracts stable fields: departure_delay, arrival_delay, status
          3. Derives canonical_delay_minutes (arrival delay preferred)
          4. Programmatic check: canonical_delay >= threshold → approved?
          5. Injects numeric delay as GROUND TRUTH into LLM prompt
          6. LLM interprets policy edge cases (cancellation vs. delay,
             diversions, etc.) and produces final JSON verdict
          7. Returns: {approved, canonical_delay_minutes, reasoning, ...}

        VALIDATOR (for each consensus validator)
          1. Independently fetches the same AviationStack endpoint
          2. Derives its own canonical_delay_minutes
          3. Accepts leader's result if BOTH conditions hold:
             (a) |validator_delay - leader_delay| ≤ 5 minutes   ← quantitative
             (b) validator's programmatic approval == leader's   ← decision
          4. Returns True (accept) or False (reject)

        This is a Comparative Equivalence Principle implementation:
        validators replicate the leader's computation and compare
        quantifiable outputs within a tolerance that accounts for
        natural API response variance between independent calls.
        ═══════════════════════════════════════════════════════

        Parameters
        ----------
        claim_id : str — a pending claim ID returned by file_claim()

        Callable by anyone (not just the policyholder) to allow
        third-party settlement triggers in production workflows.
        """
        if claim_id not in self.claims:
            raise ValueError(f"{ERR_EXPECTED} Claim '{claim_id}' does not exist")

        claim = self.claims[claim_id]

        if claim["state"] != CLAIM_PENDING:
            raise ValueError(
                f"{ERR_EXPECTED} Claim '{claim_id}' is not pending "
                f"(current state: '{claim['state']}')"
            )

        policy    = self.policies[claim["policy_id"]]
        flight    = policy["flight_iata"]
        date      = policy["flight_date"]
        threshold = policy["delay_threshold_minutes"]

        # ── Leader function ──────────────────────────────────────────────────
        def leader_fn():
            # Step 1 — Fetch live data (non-deterministic web access)
            flight_data = self._fetch_flight_data(flight, date)

            canonical_delay = flight_data["canonical_delay_minutes"]
            flight_status   = flight_data["flight_status"]

            # Step 2 — Programmatic ground-truth check
            programmatic_approved = (canonical_delay >= threshold)

            # Step 3 — LLM handles policy-term interpretation & edge cases
            # Numeric facts are injected as GROUND TRUTH so the LLM cannot
            # hallucinate or override the delay calculation.
            prompt = f"""
You are a senior claims adjudicator for parametric flight-delay insurance.

POLICY TERMS
  Flight       : {flight}
  Date         : {date}
  Payout trigger: Arrival delay ≥ {threshold} minutes

VERIFIED FLIGHT DATA  ← injected from live aviation API, treat as GROUND TRUTH
  Flight status              : {flight_status}
  Departure delay (minutes)  : {flight_data['departure_delay_minutes']}
  Arrival delay   (minutes)  : {flight_data['arrival_delay_minutes']}
  Canonical delay used        : {canonical_delay} minutes

PROGRAMMATIC VERDICT  ← computed by code, DO NOT override
  Delay meets threshold: {programmatic_approved}

YOUR TASK
  1. Honour the programmatic verdict — do NOT change approved/rejected
     based on your own delay calculation.
  2. Identify any edge cases:
       • "cancelled" flight → different claim type, note as edge case
       • "diverted" flight  → typically a covered delay, note it
       • "scheduled" status → flight has not yet landed, claim premature
  3. Write a 1-2 sentence plain-English reasoning for the claimant.

Respond ONLY as valid JSON (no markdown fences):
{{
  "approved"                : {str(programmatic_approved).lower()},
  "canonical_delay_minutes" : {canonical_delay},
  "reasoning"               : "<1-2 sentences for the claimant>",
  "flight_status"           : "{flight_status}",
  "edge_case_detected"      : "none" or "<brief description>"
}}
"""
            llm_verdict = gl.nondet.exec_prompt(prompt, response_format="json")

            # Safety: always use programmatic approval as source of truth;
            # only borrow reasoning and edge-case notes from the LLM.
            return {
                "approved"                : programmatic_approved,
                "canonical_delay_minutes" : canonical_delay,
                "reasoning"               : llm_verdict.get("reasoning", ""),
                "flight_status"           : flight_status,
                "edge_case_detected"      : llm_verdict.get("edge_case_detected", "none"),
            }

        # ── Validator function ───────────────────────────────────────────────
        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False

            leader_data   = leaders_res.calldata
            leader_delay  = leader_data.get("canonical_delay_minutes", -1)
            leader_ok     = leader_data.get("approved", False)

            # Independently fetch — may differ slightly due to API call timing
            try:
                my_data  = self._fetch_flight_data(flight, date)
            except Exception:
                # Cannot validate without data; abstain (return False)
                return False

            my_delay = my_data["canonical_delay_minutes"]
            my_ok    = (my_delay >= threshold)

            # ── Comparative Equivalence Principle checks ──────────────────
            # (a) Quantitative: delay values must agree within 5-min margin.
            #     5 minutes chosen because AviationStack updates in ~1-min
            #     increments and two independent calls can straddle an update.
            delay_agrees = abs(my_delay - leader_delay) <= 5

            # (b) Decision: both validators must reach the same approve/reject.
            #     If the delay is near the threshold (within 5 min), the
            #     decision *may* legitimately differ — in that case we defer
            #     to the leader (return True) to avoid a liveness failure on
            #     borderline cases.
            near_threshold = abs(my_delay - threshold) <= 5
            decision_agrees = (my_ok == leader_ok) or near_threshold

            return delay_agrees and decision_agrees

        # ── Run consensus ────────────────────────────────────────────────────
        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        # ── Persist outcome ──────────────────────────────────────────────────
        approved = result.get("approved", False)

        self.claims[claim_id]["actual_delay_minutes"] = result.get("canonical_delay_minutes", 0)
        self.claims[claim_id]["verdict_reasoning"]     = result.get("reasoning", "")
        self.claims[claim_id]["flight_status"]         = result.get("flight_status", "unknown")
        self.claims[claim_id]["edge_case_detected"]    = result.get("edge_case_detected", "none")
        self.claims[claim_id]["state"] = CLAIM_APPROVED if approved else CLAIM_REJECTED

        policy_id = claim["policy_id"]
        self.policies[policy_id]["state"] = POLICY_SETTLED if approved else POLICY_REJECTED

        # NOTE: In a production deployment the payout would be released here
        # via gl.message.send_tokens() or a ghost-contract call.  Omitted in
        # this reference implementation for clarity.

    # ── View methods ─────────────────────────────────────────────────────────

    @gl.public.view
    def get_policy(self, policy_id: str) -> dict:
        """Return full policy record for the given policy_id."""
        if policy_id not in self.policies:
            raise ValueError(f"{ERR_EXPECTED} Policy '{policy_id}' not found")
        return self.policies[policy_id]

    @gl.public.view
    def get_claim(self, claim_id: str) -> dict:
        """
        Return full claim record including AI verdict and delay measurement.
        """
        if claim_id not in self.claims:
            raise ValueError(f"{ERR_EXPECTED} Claim '{claim_id}' not found")
        return self.claims[claim_id]

    @gl.public.view
    def get_policy_with_claim(self, policy_id: str) -> dict:
        """
        Return a policy and its associated claim (if any) in one call.
        Useful for frontend dashboards.
        """
        if policy_id not in self.policies:
            raise ValueError(f"{ERR_EXPECTED} Policy '{policy_id}' not found")

        policy   = self.policies[policy_id]
        claim_id = policy.get("claim_id")
        claim    = self.claims[claim_id] if claim_id else None

        return {
            "policy" : policy,
            "claim"  : claim,
        }

    @gl.public.view
    def list_policies_for(self, address: str) -> list:
        """
        Return all policy records owned by the given wallet address.
        """
        return [
            p for p in self.policies.values()
            if p["policyholder"] == address
        ]

    @gl.public.view
    def get_contract_info(self) -> dict:
        """
        Return high-level contract statistics.
        """
        total         = len(self.policies)
        active        = sum(1 for p in self.policies.values() if p["state"] == POLICY_ACTIVE)
        settled_count = sum(1 for p in self.policies.values() if p["state"] == POLICY_SETTLED)
        rejected_count= sum(1 for p in self.policies.values() if p["state"] == POLICY_REJECTED)
        claimed_count = sum(1 for p in self.policies.values() if p["state"] == POLICY_CLAIMED)

        return {
            "owner"            : self.owner,
            "total_policies"   : total,
            "active_policies"  : active,
            "claimed_policies" : claimed_count,
            "settled_policies" : settled_count,
            "rejected_policies": rejected_count,
            "total_claims"     : len(self.claims),
        }
