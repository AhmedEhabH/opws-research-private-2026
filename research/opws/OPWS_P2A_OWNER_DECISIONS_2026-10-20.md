# OPWS P2A — Owner Decisions (2026-10-20)

**Session:** M17 OPWS R1 — P2A Binding Decision Closure  
**Date:** 2026-10-20  
**Base:** `parallel/opws-instrument-build-2026-10-20` @ `315612639020c8a5d3102fb86d33230422bd66f5`  
**Authorization:** Owner authorization 20 October 2026, following independent read-only Pi audit.

---

## Decision B2 — ENVIRONMENT_ID Serialization: CONDITIONAL OWNER APPROVAL

**Owner conditionally approves** the opaque physical environment identity based on the pinned per-task/pair immutable image identifier, frozen runtime/image binding hash, and frozen `provenance.environment_fingerprint`.

**Canonical byte recipe (explicit, stable, tested):**

```
ENVIRONMENT_ID = sha256(UTF8(json.dumps([
    immutable_image_id,           # per-pair pinned digest (e.g., "sha256:24b7945d2f6c62c90a71efa0e6433d32147f1632aca7fce5add2566d62f5bc4b")
    deterministic_binding_hash,   # 5169c69d45f0761c85792ec182c9e949f58d8c9f5a29355d5a371944293d2ef2
    environment_fingerprint       # per-task provenance.environment_fingerprint from per_task_v2.jsonl
], ensure_ascii=False, separators=(',', ':'))))
```

**Verification gates passed:**
- ✅ Every required component is non-null and frozen for all 219 tasks
- ✅ Exactly 219 records bound (no more, no less)
- ✅ Same input triple always produces same ID (deterministic function verified)
- ✅ Distinct triples in the 219 records do NOT accidentally share an ID (verified: 131 distinct IDs, 51 shared by ≥2 tasks)
- ✅ No secret, outcome, selector, or GOLD content feeds the ID (components are purely infrastructure provenance)
- ✅ 131 distinct environment IDs among 219 tasks is **allowed** — environment identity is deliberately task-independent; the frozen dedup 5-tuple still carries `TASK_ID` separately
- ✅ Recipe matches `scripts/opws_build.py::environment_id()` and `OPWS_ENVIRONMENT_ID_PROPOSAL.json` byte-for-byte

**Status:** `OWNER_APPROVED_CONDITIONAL_GATES_PASS` — the serialization is now frozen for this binding.

---

## Decision B3 — F2P Node Identity Resolution Rule: RULE APPROVAL CONDITIONAL ON PROVENANCE

**Owner approves evaluation-time node identity resolution as a rule**, *only if identical to the frozen evaluator contract*: use actual evaluator-produced node identities/classes `BEHAVIORAL_F2P` or `SYMBOL_ABSENCE_F2P` against frozen per-task F2P counts. Missing required nodes/class/identity are a fail-closed `MISSING_F2P_NODES` instrumentation/eligibility blocker, NOT success and NOT a scientific F2P failure.

**Provenance investigation (two narrow checks):**

| Check | Source | Finding |
|-------|--------|---------|
| 1 | `research/wp2/oracle_confirmation_linux_v2_2026-09-23/per_task_v2.jsonl` (220 records) | **No top-level `node_records` field** in any record. The file contains `counts`, `eligibility`, `provenance`, but not node-level v3_class maps. |
| 2 | `research/wp2/harness_v3_2026-09-26/` (phase3_probe + phase5_c4v3, 34 files) | Contains `node_records` with `v3_class`, but **0/219 OPWS tasks overlap** with these 34 harness_v3 tasks. Different population, later date. |

**Conclusion:**
- ✅ **Rule is justified**: The evaluation-time rule mirrors `scripts/wp2_m17_contract.py::f2p_node_set_from_frozen` exactly — frozen evaluator node records with `v3_class ∈ {BEHAVIORAL_F2P, SYMBOL_ABSENCE_F2P}`, bounded by frozen count, fail-closed on `len(node_set) < frozen_count` → `MISSING_F2P_NODES`.
- ❌ **Numerical 9/78 claim is NOT justified**: No versioned, exact source and derivation substantiates "9/219 tasks have stored node_records; 78 F2P-positive tasks lack them". This claim appears in the Phase-1 draft reports and builder messages but has no frozen-evidence basis.

**Action taken:** Removed the unsupported quantitative claims from the new/unfrozen builder messages (`scripts/opws_build.py` blocker detail) and Phase-1 draft reports (`PHASE1_RESULT.md`). Replaced with `UNVERIFIED_SOURCE_COUNT` notice preserving the evaluation-time rule. Do not search the entire repo to justify an old guess.

**Status:** `RULE_APPROVED_PROVENANCE_UNVERIFIED` — the rule stands; the numbers are retracted.

---

## Decision B4 — protocol_sha256 Definition: OWNER APPROVAL WITH ADDITIVE CLARIFICATION

**Owner approves** the 16-blob bundle hash definition:

```
protocol_sha256 = sha256(compact_json(sorted([
    [relative_path, sha256(original_blob_bytes)]
    for 16 frozen protocol blobs at peeled commit 9038df3ea80d7d478c2f949b2d3fae75754bb6e1
])))
```

**Verification:**
- ✅ Matches exactly the bundle recipe currently implemented in `load_protocol_bundle()` (16 files, sorted by relative path, blob bytes at protocol_commit)
- ✅ Matches the existing unit test `test_protocol_bundle_hash_recomputes_from_git`
- ✅ Independently recomputed: `44f18bcad2a80f160646ddd676bca2eb80bd3fc06a1a4925a82e301f025cd767` — exact match
- ✅ Git SHA-1 tag object (`63ff392b92cacf5d274cfe1823275ff3bba90af7`) and peeled commit (`9038df3ea80d7d478c2f949b2d3fae75754bb6e1`) kept as separate metadata in the protocol artifact
- ⚠️ **Clarification only (additive memo)**: The frozen schema's ambiguous "tag peel hash" prose in `OPWS_POPULATION_BINDING_SCHEMA_R1.json` ("sha256 of the released OPWS protocol freeze (tag peel hash at binding time)") is clarified here — it means the 16-blob bundle hash at the peeled commit, NOT the tag object SHA-1 or the commit SHA-1 alone. No protocol files changed.

**Status:** `OWNER_APPROVED_CLARIFIED_IN_MEMO` — definition frozen, ambiguity documented additively.

---

## Summary of Decisions

| ID | Decision | Status |
|----|----------|--------|
| B2 | ENVIRONMENT_ID serialization | `OWNER_APPROVED_CONDITIONAL_GATES_PASS` |
| B3 | F2P node identity rule | `RULE_APPROVED_PROVENANCE_UNVERIFIED` (numbers retracted) |
| B4 | protocol_sha256 definition | `OWNER_APPROVED_CLARIFIED_IN_MEMO` |

**No scientific outcomes produced. No Stage-5/Stage-7 execution. No commits/tags/pushes.**

---

## Artifact Hashes (Post-Decision Rebuild @ 2026-10-20T09:00:19Z)

| Artifact | File SHA-256 | Internal Hash |
|----------|--------------|---------------|
| `OPWS_READY_POPULATION_219.json` | `85bc90e0668f02ea485acae3549e7e5ae1528df9f62f3a55df6a56dcc522ebbb` | — |
| `OPWS_ORDERED_TASK_IDS.json` | `9cb18a3eceb849cef7edda42655a910c4bfe00c727767f77773c49fa4bfe3b8f` | `ordered_task_ids_sha256=5972b20d6b08095a555e4c49b9f03703ccd24cfeeabd27c42bcd748cf7cd1364` |
| `OPWS_ENVIRONMENT_ID_PROPOSAL.json` | `94859d48e7040547d1cc92fc6868056246b4082d302cc47052059dfd58bac2cc` | — |
| `OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json` | `5bd64af020caae5cca495aad31221411f87f347841a728452a0a2d3ee63cd064` | `manifest_sha256=d6363dd1d3f51b300ba33363fa078cf164d5aacc48f7e54bcc5c8b2c9115665f` |
| `OPWS_ELIGIBILITY_FUNNEL_219.json` | `25c278113a94841ad75a7f23de02247d183da3393ef907b3edaff0bc0f9570f1` | `manifest_sha256` (canonical) |
| `OPWS_POPULATION_BINDING_R1.json` | `91ba96f7a721cf23aa33ba73bafe86754c46714f36e70ca0eeb8928de7bbd42f` | 13 fields, `binding_self_sha256=d4e1a4aad4b4055641f99d9ce4aa97727c4eea5251aebebf7ef21ded749601b6` |
| `OPWS_POPULATION_BINDING_STATUS.json` | `f631019a04ca61a141e353a0e6f5627660a8150c81ebb039abf20780be307428` | `binding_self_sha256=d4e1a4aad4b4055641f99d9ce4aa97727c4eea5251aebebf7ef21ded749601b6` |
| `OPWS_BUILD_DETERMINISM.json` | `d036b3caeca6d913777cf48333db6f7429a43c902e90cc567e7ec6700dcf721a` | `all_identical=true` |

> **Reconciliation note (M17 R1 Phase-2, 2026-10-20):** the `OPWS_POPULATION_BINDING_STATUS.json` and
> `OPWS_BUILD_DETERMINISM.json` file-SHA rows above were updated to the determinism-gate-verified on-disk
> bytes (`python scripts/opws_build.py --check --created-at 2026-10-20T09:00:19Z` → `all_identical=true`).
> No artifact, frozen input, or decision text changed.

All 9 frozen input files re-hashed after build: **identical** (verified).