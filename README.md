# LumiNode — On-Chain Node Performance Auditor

> **AI-Powered performance auditing and metric verification for Web3 nodes, powered by GenLayer's Optimistic Democracy.**

---

## Deployed Contract Address
The contract is compiled, linted, and deployed on the GenLayer Studio network:
* **Contract Address:** [`0x246BE62A430A8E81B901BB6748Ad581090829713`](https://explorer-studio.genlayer.com/address/0x246BE62A430A8E81B901BB6748Ad581090829713)

---

## What It Does

`LumiNode` is a decentralized intelligent contract designed to audit the performance of blockchain validators, decentralized RPC nodes, or edge storage servers against custom specification profiles.

1. **Auditors** define a node performance specification profile (Node Spec) outlining strict metrics (e.g. CPU constraints, Uptime requirements, Memory limits).
2. **Node Providers** submit their telemetry log reports (Node Telemetry) pointing to raw JSON/text files containing telemetry logs.
3. **GenLayer AI-Validator Consensus** verifies the logs programmatically and calls an LLM to assess compliance against each metric, finalizing the audit status on-chain.

---

## Why GenLayer Makes This Possible

Traditional smart contracts cannot read raw logs, parse unstructured textual files, or verify qualitative performance metrics. Oracle networks can fetch text, but cannot reason about whether a log report conforms to a specification description.

GenLayer provides:
* **Direct Web Access:** Validators dynamically fetch raw log reports.
* **Semantic Analysis:** AI agents evaluate qualitative logs against specific descriptions.
* **Exact-Match Consensus:** Validators execute independent audits and must agree on the complete metric status array before finalizing.

---

## Consensus Design — Exact-Match Equivalence Check

LumiNode utilizes a **Non-Comparative Equivalence check**:

* **Leader:** Fetches raw log files, aggregates metrics, and calls the LLM with the specification requirements. Generates a structured proposal: `{"spec_id": ..., "state": "FINALIZED", "metrics": [{"metric_id": ..., "status": "PASS|FAIL|UNRESOLVED"}]}`.
* **Consensus Validators:** Independently fetch the same log files and replicate the evaluation. They accept the leader's proposal only if their independently generated metrics status array matches the leader's exactly.

---

## Contract API

### Write Methods (`gl.public.write`)

* `create_spec(spec_json: str) -> str`: Registers a new Node Specification profile. Returns `spec_id`.
* `submit_telemetry(telemetry_json: str) -> None`: Submits a telemetry metric log report.
* `audit_node(spec_id: str) -> None`: Triggers consensus nodes to fetch, evaluate, and audit the node's performance.
* `retry_audit(spec_id: str) -> None`: Retries an audit that previously encountered transient network/provider failures.

### View Methods (`gl.public.view`)

* `get_spec(spec_id: str) -> dict`: Returns the Node Spec profile.
* `get_telemetry(spec_id: str) -> dict`: Returns the submitted telemetry report.
* `get_audit(spec_id: str) -> dict`: Returns the finalized audit results.
* `get_metric_result(spec_id: str, metric_id: str) -> dict`: Queries the audit status of a single metric.
* `is_audited(spec_id: str) -> bool`: Returns `True` if the node has been audited and finalized.

---

## How to Test in GenLayer Studio

### Step 1 — Deploy
Leave constructor arguments blank. Click **Deploy**.

### Step 2 — Create a Specification Profile
Call `create_spec` with a Node Spec JSON payload string:
```json
{
  "schema_version": "1.0",
  "auditor": "0xholder00000000000000000000000000000000002",
  "node_id": "LUMI-NODE-PROD-01",
  "spec_description": "Production edge validator specification profile.",
  "metrics": [
    {"metric_id": "uptime_check", "description": "Uptime must be >= 99.9%"},
    {"metric_id": "cpu_check", "description": "Average CPU usage must be <= 80%"}
  ]
}
```
**Returns:** a `spec_id` (e.g., `spec-1ab45...`)

### Step 3 — Submit Telemetry
From the auditor wallet, call `submit_telemetry` with telemetry metrics:
```json
{
  "schema_version": "1.0",
  "spec_id": "spec-1ab45...",
  "report_summary": "Node reports normal parameters. Uptime is 99.99%, CPU usage is 14%.",
  "log_urls": ["https://gist.githubusercontent.com/username/gist_id/raw/node_logs.json"]
}
```
*Note: Make sure to replace `spec_id` with your actual returned ID.*

### Step 4 — Run the Audit
Call `audit_node` specifying the `spec_id`:
```python
audit_node("spec-1ab45...")
```

### Step 5 — Verify Audit Result
Call `get_audit("spec-1ab45...")` to check the verdict:
```json
{
  "state": "FINALIZED",
  "metrics": [
    {"metric_id": "uptime_check", "status": "PASS"},
    {"metric_id": "cpu_check", "status": "PASS"}
  ],
  "result": "VERIFIED"
}
```
