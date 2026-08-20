# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
# -
# ParametricCropInsurance - GenLayer Intelligent Contract
#
# Automatically settles parametric agricultural drought insurance claims using:
#   - Historical weather data fetched from the free keyless Open-Meteo API
#   - Comparative Equivalence Principle - validators independently fetch the
#     precipitation archive, calculate cumulative rainfall, and must agree
#     on the cumulative sum (within 0.2mm margin) AND the decision.
#   - Grounded LLM reasoning - verified cumulative rain sum injected as ground
#     truth; LLM handles only qualitative drought severity analysis and reasoning.
# -

import genlayer as gl
from genlayer import *
import json

ERR_EXPECTED = "[EXPECTED]"
ERR_EXTERNAL = "[EXTERNAL]"

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


def _fetch_rainfall_data(latitude: str, longitude: str, start_date: str, end_date: str) -> dict:
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={latitude}"
        f"&longitude={longitude}"
        f"&start_date={start_date}"
        f"&end_date={end_date}"
        "&daily=rain_sum"
        "&timezone=GMT"
    )

    response = gl.nondet.web.get(url)

    if response.status != 200:
        raise gl.vm.UserError(
            f"{ERR_EXTERNAL} Open-Meteo API returned HTTP {response.status} "
            f"for coordinates {latitude}, {longitude}"
        )

    data = response.json()
    if not data.get("daily") or not data["daily"].get("rain_sum"):
        raise gl.vm.UserError(
            f"{ERR_EXTERNAL} No weather records returned for coordinates "
            f"{latitude}, {longitude} between {start_date} and {end_date}."
        )

    rain_list = data["daily"]["rain_sum"]
    clean_rain = [r for r in rain_list if r is not None]
    
    if not clean_rain:
        total_rain = 0.0
    else:
        total_rain = sum(clean_rain)

    return {
        "latitude"        : latitude,
        "longitude"       : longitude,
        "start_date"      : start_date,
        "end_date"        : end_date,
        "daily_rain_list" : clean_rain,
        "cumulative_rain" : round(total_rain, 2),
    }


class ParametricCropInsurance(gl.Contract):
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

    def __init__(self, *args, **kwargs):
        pass

    # - Internal helpers -

    def _get_sender(self) -> str:
        return _address_text(gl.message.sender_address)

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
        latitude           : str,
        longitude          : str,
        start_date         : str,
        end_date           : str,
        rain_threshold_mm  : int,
        payout_amount_wei  : int,
    ) -> str:
        """
        Purchase a parametric drought insurance policy.
        
        Parameters
        ----------
        latitude           : Latitude of the farm (e.g., "52.52")
        longitude          : Longitude of the farm (e.g., "13.41")
        start_date         : Start of coverage YYYY-MM-DD (e.g., "2023-08-01")
        end_date           : End of coverage YYYY-MM-DD (e.g., "2023-08-15")
        rain_threshold_mm  : Cumulative rain sum below which payout triggers (e.g. 20)
        payout_amount_wei  : Payout amount in Wei
        """
        if not latitude or not longitude:
            raise gl.vm.UserError(f"{ERR_EXPECTED} Coordinates cannot be empty")
        if len(start_date) != 10 or len(end_date) != 10:
            raise gl.vm.UserError(f"{ERR_EXPECTED} dates must be YYYY-MM-DD format")
        if rain_threshold_mm <= 0:
            raise gl.vm.UserError(f"{ERR_EXPECTED} rain_threshold_mm must be positive")
        if payout_amount_wei <= 0:
            raise gl.vm.UserError(f"{ERR_EXPECTED} payout_amount_wei must be positive")

        policy_id = self._next_policy_id()
        self.policies[policy_id] = json.dumps({
            "policy_id"              : policy_id,
            "policyholder"           : self._get_sender(),
            "latitude"               : latitude.strip(),
            "longitude"              : longitude.strip(),
            "start_date"             : start_date,
            "end_date"               : end_date,
            "rain_threshold_mm"      : rain_threshold_mm,
            "payout_amount_wei"      : payout_amount_wei,
            "state"                  : POLICY_ACTIVE,
            "claim_id"               : None,
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
            "claim_id"             : claim_id,
            "policy_id"            : policy_id,
            "claimant"             : self._get_sender(),
            "state"                : CLAIM_PENDING,
            "cumulative_rain_mm"   : -1.0,
            "verdict_reasoning"    : "",
            "edge_case_detected"   : "none",
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
        lat       = policy["latitude"]
        lon       = policy["longitude"]
        start     = policy["start_date"]
        end       = policy["end_date"]
        threshold = policy["rain_threshold_mm"]

        def leader_fn():
            weather = _fetch_rainfall_data(lat, lon, start, end)
            cum_rain = weather["cumulative_rain"]

            drought_active = (cum_rain < threshold)

            prompt = f"""
You are an agricultural insurance assessor analyzing weather data for a parametric drought policy.

POLICY TERMS:
- Start Date: {start}
- End Date: {end}
- Drought Rain Threshold: {threshold} mm (Cumulative rain below this triggers payout)

VERIFIED WEATHER ARCHIVE DATA:
- Location Coordinates: Latitude {lat}, Longitude {lon}
- Verified Cumulative Rainfall over period: {cum_rain} mm

PROGRAMMATIC VERDICT:
- Rain is below threshold: {drought_active}

YOUR TASK:
1. Validate the programmatic verdict. If cumulative rain ({cum_rain} mm) is less than threshold ({threshold} mm), approve the claim.
2. Analyze the severity. Note if it is a severe drought (e.g., less than 20% of threshold) or borderline.
3. Keep reasoning concise (1-2 sentences).

Respond ONLY as valid JSON:
{{
  "approved"             : {str(drought_active).lower()},
  "cumulative_rain_mm"   : {cum_rain},
  "reasoning"            : "<concise description of the severity and outcome>",
  "edge_case_detected"   : "none" or "<description>"
}}
"""
            llm_verdict = gl.nondet.exec_prompt(prompt, response_format="json")

            return {
                "approved"             : drought_active,
                "cumulative_rain_mm"   : cum_rain,
                "reasoning"            : llm_verdict.get("reasoning", ""),
                "edge_case_detected"   : llm_verdict.get("edge_case_detected", "none"),
            }

        def validator_fn(leaders_res):
            if not isinstance(leaders_res, gl.vm.Return):
                return False

            leader_data = leaders_res.calldata
            leader_rain = leader_data.get("cumulative_rain_mm", -1.0)
            leader_ok   = leader_data.get("approved", False)

            try:
                my_data = _fetch_rainfall_data(lat, lon, start, end)
            except Exception:
                return False

            my_rain = my_data["cumulative_rain"]
            my_ok   = (my_rain < threshold)

            rain_agrees = abs(my_rain - leader_rain) <= 0.2
            
            near_threshold = abs(my_rain - threshold) <= 0.5
            decision_agrees = (my_ok == leader_ok) or near_threshold

            return rain_agrees and decision_agrees

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        approved = result.get("approved", False)

        claim["cumulative_rain_mm"] = result.get("cumulative_rain_mm", 0.0)
        claim["verdict_reasoning"]   = result.get("reasoning", "")
        claim["edge_case_detected"]  = result.get("edge_case_detected", "none")
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
