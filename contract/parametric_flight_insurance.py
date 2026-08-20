# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
# -
# ParametricFlightInsurance - GenLayer Intelligent Contract
#
# Automatically settles flight-delay insurance claims using:
#   - Live flight data fetched from the AviationStack API
#   - Comparative Equivalence Principle - validators independently fetch the
#     same flight data and must agree on the delay value (within 5-min margin)
#     AND on the approval decision before consensus is reached
#   - Grounded LLM reasoning - verified delay figures injected as ground truth;
#     LLM handles only policy-term interpretation and edge-case detection
#
# Author: U_StackLabs
# -

import genlayer as gl
from genlayer import *
import json

# - Error classification prefixes -
# [EXPECTED] = deterministic business-logic errors (fail consistently on all nodes)
# [EXTERNAL] = transient external-service failures (safe to retry)
ERR_EXPECTED = "[EXPECTED]"
ERR_EXTERNAL = "[EXTERNAL]"

# - Policy / Claim lifecycle states -
POLICY_ACTIVE   = "active"
POLICY_CLAIMED  = "claimed"
POLICY_SETTLED  = "settled"
POLICY_REJECTED = "rejected"

CLAIM_PENDING  = "pending"
CLAIM_APPROVED = "approved"
CLAIM_REJECTED = "rejected"


def _address_text(value):
    if isinstance(value, str):
        result = value
    else:
        candidate = getattr(value, "as_hex", None)
        result = candidate() if callable(candidate) else candidate
        if not isinstance(result, str):
            result = str(value)
    result = result.strip().lower()
    if len(result) != 42 or not result.startswith("0x"):
        raise gl.vm.UserError("[EXPECTED] ADDRESS: address format")
    try:
        int(result[2:], 16)
    except ValueError:
        raise gl.vm.UserError("[EXPECTED] ADDRESS: address hex")
    if result == "0x" + "0" * 40:
        raise gl.vm.UserError("[EXPECTED] ADDRESS: zero address")
    return result


def _fetch_flight_data(api_key: str, flight_iata: str, flight_date: str) -> dict:
    url = (
        "http://api.aviationstack.com/v1/flights"
        f"?access_key={api_key}"
        f"&flight_iata={flight_iata}"
        f"&flight_date={flight_date}"
        "&limit=1"
    )

    response = gl.nondet.web.get(url)

    if response.status != 200:
        raise gl.vm.UserError(
            f"{ERR_EXTERNAL} AviationStack returned HTTP {response.status} "
            f"for flight {flight_iata} on {flight_date}"
        )

    data = response.json()
    if not data.get("data"):
        raise gl.vm.UserError(
            f"{ERR_EXTERNAL} No flight records returned for "
            f"{flight_iata} on {flight_date}. "
            "API might be delayed or flight doesn't exist."
        )

    flight_record = data["data"][0]
    status = flight_record.get("flight_status", "unknown")
    dep_delay = flight_record.get("departure", {}).get("delay") or 0
    arr_delay = flight_record.get("arrival", {}).get("delay") or 0

    canonical = arr_delay if arr_delay > 0 else dep_delay

    return {
        "flight_iata"             : flight_iata,
        "flight_date"             : flight_date,
        "flight_status"           : status,
        "departure_delay_minutes" : dep_delay,
        "arrival_delay_minutes"   : arr_delay,
        "canonical_delay_minutes" : canonical,
    }


class ParametricFlightInsurance(gl.Contract):
    policies: TreeMap[str, str]
    claims: TreeMap[str, str]
    settings: TreeMap[str, str]
    
    # Track policies per user (non-iterable TreeMap workaround)
    user_policy_count: TreeMap[str, u256]
    user_policy_ids: TreeMap[str, str] # "address#index" -> policy_id
    
    # Monotonic ID counters
    next_id: u256
    
    # Global statistics (workaround for lack of len() / iteration on TreeMap)
    stat_total_policies: u256
    stat_active_policies: u256
    stat_claimed_policies: u256
    stat_settled_policies: u256
    stat_rejected_policies: u256
    stat_total_claims: u256

    # - Constructor -

    def __init__(self):
        pass

    # - Internal helpers -

    def _get_sender(self) -> str:
        return _address_text(gl.message.sender_address)

    @gl.public.write
    def set_api_key(self, api_key: str) -> None:
        sender = self._get_sender()
        current_owner = self.settings.get("owner", "")
        if not current_owner:
            self.settings["owner"] = sender
            current_owner = sender
        if sender != current_owner:
            raise gl.vm.UserError("Only the owner can set the API key")
        self.settings["api_key"] = api_key

    def _next_policy_id(self) -> str:
        pid = f"POL-{int(self.next_id):05d}"
        self.next_id = u256(int(self.next_id) + 1)
        return pid

    def _next_claim_id(self) -> str:
        cid = f"CLM-{int(self.next_id):05d}"
        self.next_id = u256(int(self.next_id) + 1)
        return cid

    @gl.public.write
    def purchase_policy(
        self,
        flight_iata           : str,
        flight_date           : str,
        delay_threshold_minutes: int,
        payout_amount_wei     : int,
    ) -> str:
        if not flight_iata or len(flight_iata.strip()) < 3:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Invalid IATA code: '{flight_iata}'")
        if not flight_date or len(flight_date) != 10:
            raise gl.vm.UserError(f"{ERR_EXPECTED} flight_date must be YYYY-MM-DD, got '{flight_date}'")
        if delay_threshold_minutes < 30:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Minimum delay threshold is 30 minutes")
        if delay_threshold_minutes > 600:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Maximum delay threshold is 600 minutes (10 hours)")
        if payout_amount_wei <= 0:
            raise gl.vm.UserError(f"{ERR_EXPECTED} payout_amount_wei must be positive")

        policy_id = self._next_policy_id()
        self.policies[policy_id] = json.dumps({
            "policy_id"               : policy_id,
            "policyholder"            : self._get_sender(),
            "flight_iata"             : flight_iata.upper().strip(),
            "flight_date"             : flight_date,
            "delay_threshold_minutes" : delay_threshold_minutes,
            "payout_amount_wei"       : payout_amount_wei,
            "state"                   : POLICY_ACTIVE,
            "claim_id"                : None,
        })
        
        # Update statistics and indexes
        self.stat_total_policies = u256(int(self.stat_total_policies) + 1)
        self.stat_active_policies = u256(int(self.stat_active_policies) + 1)
        
        user = self._get_sender()
        count = int(self.user_policy_count.get(user, u256(0))) + 1
        self.user_policy_count[user] = u256(count)
        self.user_policy_ids[user + "#" + str(count)] = policy_id
        
        return policy_id

    @gl.public.write
    def file_claim(self, policy_id: str) -> str:
        if policy_id not in self.policies:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Policy '{policy_id}' does not exist")

        policy = json.loads(self.policies[policy_id])

        if policy["policyholder"] != self._get_sender():
            raise gl.vm.UserError(
                f"{ERR_EXPECTED} Only the policyholder can file a claim on '{policy_id}'"
            )
        if policy["state"] != POLICY_ACTIVE:
            raise gl.vm.UserError(
                f"{ERR_EXPECTED} Policy '{policy_id}' is not active "
                f"(current state: '{policy['state']}')"
            )

        claim_id = self._next_claim_id()
        self.claims[claim_id] = json.dumps({
            "claim_id"               : claim_id,
            "policy_id"              : policy_id,
            "claimant"               : self._get_sender(),
            "state"                  : CLAIM_PENDING,
            "actual_delay_minutes"   : -1,
            "verdict_reasoning"      : "",
            "flight_status"          : "",
            "edge_case_detected"     : "none",
        })

        policy["state"]    = POLICY_CLAIMED
        policy["claim_id"] = claim_id
        self.policies[policy_id] = json.dumps(policy)
        
        # Update statistics
        self.stat_active_policies = u256(int(self.stat_active_policies) - 1)
        self.stat_claimed_policies = u256(int(self.stat_claimed_policies) + 1)
        self.stat_total_claims = u256(int(self.stat_total_claims) + 1)
        
        return claim_id

    @gl.public.write
    def settle_claim(self, claim_id: str) -> None:
        if claim_id not in self.claims:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Claim '{claim_id}' does not exist")

        claim = json.loads(self.claims[claim_id])

        if claim["state"] != CLAIM_PENDING:
            raise gl.vm.UserError(
                f"{ERR_EXPECTED} Claim '{claim_id}' is not pending "
                f"(current state: '{claim['state']}')"
            )

        policy    = json.loads(self.policies[claim["policy_id"]])
        flight    = policy["flight_iata"]
        date      = policy["flight_date"]
        threshold = policy["delay_threshold_minutes"]
        api_key = self.settings.get("api_key", "")

        def leader_fn():
            flight_data = _fetch_flight_data(api_key, flight, date)

            canonical_delay = flight_data["canonical_delay_minutes"]
            flight_status   = flight_data["flight_status"]

            programmatic_approved = (canonical_delay >= threshold)

            prompt = f"""
You are a senior claims adjudicator for parametric flight-delay insurance.

POLICY TERMS
  Flight       : {flight}
  Date         : {date}
  Payout trigger: Arrival delay - {threshold} minutes

VERIFIED FLIGHT DATA  - injected from live aviation API, treat as GROUND TRUTH
  Flight status              : {flight_status}
  Departure delay (minutes)  : {flight_data['departure_delay_minutes']}
  Arrival delay   (minutes)  : {flight_data['arrival_delay_minutes']}
  Canonical delay used        : {canonical_delay} minutes

PROGRAMMATIC VERDICT  - computed by code, DO NOT override
  Delay meets threshold: {programmatic_approved}

YOUR TASK
  1. Honour the programmatic verdict - do NOT change approved/rejected
     based on your own delay calculation.
  2. Identify any edge cases:
       - "cancelled" flight - different claim type, note as edge case
       - "diverted" flight  - typically a covered delay, note it
       - "scheduled" status - flight has not yet landed, claim premature
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

            return {
                "approved"                : programmatic_approved,
                "canonical_delay_minutes" : canonical_delay,
                "reasoning"               : llm_verdict.get("reasoning", ""),
                "flight_status"           : flight_status,
                "edge_case_detected"      : llm_verdict.get("edge_case_detected", "none"),
            }

        def validator_fn(leaders_res):
            if not isinstance(leaders_res, gl.vm.Return):
                return False

            leader_data   = leaders_res.calldata
            leader_delay  = leader_data.get("canonical_delay_minutes", -1)
            leader_ok     = leader_data.get("approved", False)

            try:
                my_data  = _fetch_flight_data(api_key, flight, date)
            except Exception:
                return False

            my_delay = my_data["canonical_delay_minutes"]
            my_ok    = (my_delay >= threshold)

            delay_agrees = abs(my_delay - leader_delay) <= 5

            near_threshold = abs(my_delay - threshold) <= 5
            decision_agrees = (my_ok == leader_ok) or near_threshold

            return delay_agrees and decision_agrees

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        approved = result.get("approved", False)

        claim["actual_delay_minutes"] = result.get("canonical_delay_minutes", 0)
        claim["verdict_reasoning"]     = result.get("reasoning", "")
        claim["flight_status"]         = result.get("flight_status", "unknown")
        claim["edge_case_detected"]    = result.get("edge_case_detected", "none")
        claim["state"] = CLAIM_APPROVED if approved else CLAIM_REJECTED
        self.claims[claim_id] = json.dumps(claim)

        policy_id = claim["policy_id"]
        policy = json.loads(self.policies[policy_id])
        policy["state"] = POLICY_SETTLED if approved else POLICY_REJECTED
        self.policies[policy_id] = json.dumps(policy)
        
        # Update statistics
        self.stat_claimed_policies = u256(int(self.stat_claimed_policies) - 1)
        if approved:
            self.stat_settled_policies = u256(int(self.stat_settled_policies) + 1)
        else:
            self.stat_rejected_policies = u256(int(self.stat_rejected_policies) + 1)

    # - View methods -

    @gl.public.view
    def get_policy(self, policy_id: str) -> dict:
        if policy_id not in self.policies:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Policy '{policy_id}' not found")
        return json.loads(self.policies[policy_id])

    @gl.public.view
    def get_claim(self, claim_id: str) -> dict:
        if claim_id not in self.claims:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Claim '{claim_id}' not found")
        return json.loads(self.claims[claim_id])

    @gl.public.view
    def get_policy_with_claim(self, policy_id: str) -> dict:
        if policy_id not in self.policies:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Policy '{policy_id}' not found")

        policy_str = self.policies[policy_id]
        policy     = json.loads(policy_str)
        claim_id   = policy.get("claim_id")
        claim      = json.loads(self.claims[claim_id]) if claim_id else None

        return {
            "policy" : policy,
            "claim"  : claim,
        }

    @gl.public.view
    def list_policies_for(self, address: str) -> dict:
        user = _address_text(address)
        count = int(self.user_policy_count.get(user, u256(0)))
        
        result = []
        for i in range(1, count + 1):
            pid = self.user_policy_ids[user + "#" + str(i)]
            if pid in self.policies:
                result.append(json.loads(self.policies[pid]))
        return {"policies": result}

    @gl.public.view
    def get_contract_info(self) -> dict:
        return {
            "owner"            : self.settings.get("owner", ""),
            "total_policies"   : int(self.stat_total_policies),
            "active_policies"  : int(self.stat_active_policies),
            "claimed_policies" : int(self.stat_claimed_policies),
            "settled_policies" : int(self.stat_settled_policies),
            "rejected_policies": int(self.stat_rejected_policies),
            "total_claims"     : int(self.stat_total_claims),
        }
