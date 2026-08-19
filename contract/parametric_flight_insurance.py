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

class ParametricFlightInsurance(gl.Contract):
    policies: TreeMap[str, str]
    claims: TreeMap[str, str]
    config: TreeMap[str, str]
    next_id: u256

    def __init__(self):
        pass

    def _get_sender(self) -> str:
        addr = gl.message.sender_address
        if isinstance(addr, str):
            return addr
        candidate = getattr(addr, "as_hex", None)
        res = candidate() if callable(candidate) else candidate
        if isinstance(res, str):
            return res
        return str(addr)

    @gl.public.write
    def set_api_key(self, api_key: str) -> None:
        sender = self._get_sender()
        current_owner = self.config.get("owner", "")
        if not current_owner:
            current_owner = sender
            self.config["owner"] = sender
        if sender != current_owner:
            raise gl.vm.UserError("Only the owner can set the API key")
        self.config["api_key"] = api_key

    def _next_policy_id(self) -> str:
        pid = f"POL-{int(self.next_id):05d}"
        self.next_id = u256(int(self.next_id) + 1)
        return pid

    def _next_claim_id(self) -> str:
        cid = f"CLM-{int(self.next_id):05d}"
        self.next_id = u256(int(self.next_id) + 1)
        return cid

    def _fetch_flight_data(self, flight_iata: str, flight_date: str) -> dict:
        
        url = (
            "http://api.aviationstack.com/v1/flights"
            f"?access_key={self.config.get("api_key", "")}"
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

        raw = json.loads(response.body.decode("utf-8"))

        if not raw.get("data"):
            raise gl.vm.UserError(
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

    # - Write: purchase a policy -

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
        return policy_id

    # - Write: file a claim -

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
        return claim_id

    # - Write: settle a claim (core non-deterministic method) -

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

        policy    = self.policies[claim["policy_id"]]
        flight    = policy["flight_iata"]
        date      = policy["flight_date"]
        threshold = policy["delay_threshold_minutes"]

        # - Leader function -
        def leader_fn():
            # Step 1 - Fetch live data (non-deterministic web access)
            flight_data = self._fetch_flight_data(flight, date)

            canonical_delay = flight_data["canonical_delay_minutes"]
            flight_status   = flight_data["flight_status"]

            # Step 2 - Programmatic ground-truth check
            programmatic_approved = (canonical_delay >= threshold)

            # Step 3 - LLM handles policy-term interpretation & edge cases
            # Numeric facts are injected as GROUND TRUTH so the LLM cannot
            # hallucinate or override the delay calculation.
            prompt = f
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

        # - Validator function -
        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False

            leader_data   = leaders_res.calldata
            leader_delay  = leader_data.get("canonical_delay_minutes", -1)
            leader_ok     = leader_data.get("approved", False)

            # Independently fetch - may differ slightly due to API call timing
            try:
                my_data  = self._fetch_flight_data(flight, date)
            except Exception:
                # Cannot validate without data; abstain (return False)
                return False

            my_delay = my_data["canonical_delay_minutes"]
            my_ok    = (my_delay >= threshold)

            # - Comparative Equivalence Principle checks -
            # (a) Quantitative: delay values must agree within 5-min margin.
            #     5 minutes chosen because AviationStack updates in ~1-min
            #     increments and two independent calls can straddle an update.
            delay_agrees = abs(my_delay - leader_delay) <= 5

            # (b) Decision: both validators must reach the same approve/reject.
            #     If the delay is near the threshold (within 5 min), the
            #     decision *may* legitimately differ - in that case we defer
            #     to the leader (return True) to avoid a liveness failure on
            #     borderline cases.
            near_threshold = abs(my_delay - threshold) <= 5
            decision_agrees = (my_ok == leader_ok) or near_threshold

            return delay_agrees and decision_agrees

        # - Run consensus -
        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        # - Persist outcome -
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

        # NOTE: In a production deployment the payout would be released here
        # via gl.message.send_tokens() or a ghost-contract call.  Omitted in
        # this reference implementation for clarity.

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

        policy   = self.policies[policy_id]
        claim_id = policy.get("claim_id")
        claim = json.loads(self.claims[claim_id]) if claim_id else None

        return {
            "policy" : policy,
            "claim"  : claim,
        }

    @gl.public.view
    def list_policies_for(self, address: str) -> list:
        
        return [
            p for p in self.policies.values()
            if p["policyholder"] == address
        ]

    @gl.public.view
    def get_contract_info(self) -> dict:
        
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
