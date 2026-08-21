# Architecture — LumiNode

## Overview

`LumiNode` is a GenLayer Intelligent Contract that automatically audits node performance telemetry against custom specification profiles. It combines:

- **On-chain state** — Node specifications, telemetry logs, and finalized audit records stored in contract storage.
- **Live web access** — Node performance endpoints and server logs fetched dynamically by validators.
- **LLM reasoning** — Semantic analysis of performance logs against textual specification descriptions.
- **Exact-Match Consensus** — Validators independently execute evaluations and verify exact match parity before finalization.

---

## Repository Structure

```
luminode/
├── contract/
│   └── luminode.py                      # The Intelligent Contract
├── docs/
│   └── architecture.md                  # This file
├── schemas/
│   └── audit-proposal-v1.json           # JSON schema for the consensus proposals
├── contract/conftest.py                  # Shared pytest fixtures
├── contract/direct/                     # Unit tests for pure logic
├── contract/consensus/                  # Equivalence Principle tests
├── contract/deployment/                 # Deploy + method smoke tests
├── contract/integration/                # End-to-end lifecycle tests
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## Contract Components

### State

```
LumiNode
 ├── spec_records: TreeMap[str, str]       # spec_id -> Spec JSON
  ├── telemetry_records: TreeMap[str, str]  # spec_id -> Telemetry JSON
  ├── audit_records: TreeMap[str, str]      # spec_id -> Audit JSON
  ├── creator_spec_count: TreeMap[str, u256] # creator -> count
  ├── creator_spec_id: TreeMap[str, str]    # creator#index -> spec_id
  └── spec_count: u256                      # Monotonic spec counter
```

---

## Data Flow — `audit_node()`

```
audit_node(spec_id)
│
├── [DETERMINISTIC] Validate spec and telemetry exist
│
├── [NON-DETERMINISTIC — Leader]
│    ├── _fetch(log_urls)
│    │    └── Web logs source → extract stable log metrics
│    │
│    ├── LLM prompt (response_format="json")
│    │    → Reads specification metrics + fetched log content
│    │    → Evaluates PASS/FAIL/UNRESOLVED status for each metric
│    │    → Returns: {"metrics": [{"metric_id", "status"}]}
│    │
│    └── Returns leader proposal dict
│
├── [NON-DETERMINISTIC — Each Validator]
│    ├── Independently fetches log URLs
│    ├── Independently evaluates metrics using LLM
│    └── Exact-Match Equivalence:
│         Validator checks: leader_proposal.calldata == my_expected_proposal
│
└── [DETERMINISTIC] Persist outcome to contract state
     → audit_records[spec_id] = FINALIZED audit record
```

---

## Equivalence Principle Choice

This contract uses the **Exact-Match Comparative Equivalence Principle** because:

1. The primary output is a structured array of metric statuses (`PASS`/`FAIL`/`UNRESOLVED`). These statuses must align exactly to ensure consistent validation across the network.
2. Web logs represent a stable historical state for a specific audit period, meaning validators should arrive at the same semantic conclusion given the same logs.

---

## Error Classification

| Prefix | Meaning | Examples |
|---|---|---|
| `[EXPECTED]` | Deterministic business error; all nodes agree to fail | Spec not found, unauthorized auditor, duplicate telemetry |
| `[EXTERNAL]` | Transient external failure; safe to retry | Logs server returned 503, connection timeout |
