# OPWS R1 — Phase 2 Result: Scope Validation & Physical Deduplication Plan (2026-10-20)

- **Mission:** M17 OPWS R1 — Phase 2 (zero-outcome scope validation + five-field physical-execution dedup)
- **Character:** record-only instrument planning. No scientific OPWS outcome is produced or implied.
- **Base:** branch `parallel/opws-instrument-build-2026-10-20`, HEAD `315612639020c8a5d3102fb86d33230422bd66f5`
- **Machine-readable source of truth:**
  - `research/opws/phase2/OPWS_SCOPE_VALIDATION_R1.json`
  - `research/opws/phase2/OPWS_PHYSICAL_DEDUP_PLAN_R1.json`
  - `research/opws/phase2/OPWS_PHASE2_DETERMINISM.json`

## 1. P2A reconciliation (stale hashes + ENVIRONMENT_ID wording)

The determinism gate at the recorded build timestamp passes:

```
python scripts/opws_build.py --check --created-at 2026-10-20T09:00:19Z
→ {"all_identical": true, "artifacts": 7}
```

Two P2A report hash rows were stale (they did not match the determinism-verified on-disk
artifacts) and were corrected **doc-only** in `OPWS_P2A_OWNER_DECISIONS_2026-10-20.md` and
`BUILD_SCOPE.md` (a reconciliation note is embedded in the decisions memo):

| Artifact | Stale file-SHA (removed) | Verified file-SHA (recorded) |
|---|---:|---:|
| `OPWS_POPULATION_BINDING_STATUS.json` | `6d64db27…` (6,292 B) | `f631019a04ca61a141e353a0e6f5627660a8150c81ebb039abf20780be307428` (6,436 B) |
| `OPWS_BUILD_DETERMINISM.json` | `8c3ba0b1…` | `d036b3caeca6d913777cf48333db6f7429a43c902e90cc567e7ec6700dcf721a` |

ENVIRONMENT_ID status wording was reconciled **doc-only** (binding artifact bytes untouched):

- `OPWS_SOURCE_AUTHORITY_TABLE.md` C5/C6/C7 status cells → `resolved (2026-10-20)` with the
  P2A decision memo cited; B2 = `OWNER_APPROVED_CONDITIONAL_GATES_PASS`, B3 =
  `RULE_APPROVED_PROVENANCE_UNVERIFIED` (numbers retracted), B4 =
  `OWNER_APPROVED_CLARIFIED_IN_MEMO`.
- `PHASE1_RESULT.md` §4 + blocker B2 → points at the owner decision B2 resolution.

No frozen scientific input changed (all 9 frozen inputs re-hashed identical), and no
semantic conflict was found.

## 2. Frozen 12-arm registry (resolved from the frozen protocol)

Source: `OPWS_ARM_REGISTRY_R1.json` at protocol commit
`9038df3ea80d7d478c2f949b2d3fae75754bb6e1` (inside the 16-blob bundle, `44f18bca…`).

- `registry_start_hash` = `83399ff875c7793286d66311afb6c62071ea04b3`
- `RANDOM_SEED` = `20261012`
- Frozen arm order (from `arm_id_uniqueness.arm_order`, not file order):

`RM_CSS, AGENT, AGENTLESS_STYLE_ADAPTATION, SIP, DENSE_K3, DENSE_K10, BM25_K3, BM25_K10,
BM25_TO_CIA_1HOP, SELECT_ALL, RANDOM_SIZE_MATCHED_RM_CSS, GOLD` — RQ6 is DESIGN_ONLY.

## 3. Existing per-arm scope artifacts (resolved, 219/219 coverage)

| Arm | Frozen scope source | Resolved |
|---|---|---:|---:|
| RM_CSS, SIP | `research/wp1a/sip_rmcss_per_task_predictions.json` | ✅ 219/219 |
| AGENT | `research/wp1b/main-297-2026-09-22/wp1b_agent_predictions.json` | ✅ 219/219 |
| AGENTLESS_STYLE_ADAPTATION | `D:/wp2_agentless_main297/.../agentless_r1_prediction_freeze.json` | ✅ 219/219 |
| DENSE_K3/K10, BM25_K3/K10, BM25_TO_CIA_1HOP | `D:/wp2_comp_baselines/.../per_task_predictions_r2.json` | ✅ 219/219 |
| SELECT_ALL | per-task `candidate_universe.json` (`benchmark_data/real_commit_impact_saleor/scientific/...`) | ✅ 219/219 |
| GOLD | `research/saleor-reserve-300-rmcss/saleor_reserve_300_proxies.json` (evaluation-only) | ✅ 219/219 |
| RANDOM_SIZE_MATCHED_RM_CSS | no stored per-task artifact; deterministic sampling (seed 20261012) | ⛔ **not generated in Phase 2** (frozen rule: never generate missing selector outputs) |

Canonical scope hashes are computed ONLY from these pre-existing frozen artifacts
(`compute_canonical_scope_hash` = sha256 of sorted-deduped normalized path list,
`json.dumps(..., separators=(",", ":"))`); empty scope is a valid zero-size scope.

## 4. Five-field physical-execution deduplication plan

Frozen identity (OPWS_EXECUTION_REUSE_DEDUP_R1.json): all five fields must be equal.

| Field | Phase-2 availability |
|---|---:|
| TASK_ID | KNOWN_ALL (219 READY tasks) |
| SCOPE_HASH | KNOWN for 11 arms with stored artifacts; `UNRESOLVED_PENDING_PHASE4_RANDOM_SAMPLING` for RANDOM_SIZE_MATCHED_RM_CSS |
| REFERENCE_PATCH_HASH | `UNRESOLVED_PENDING_PATCH_MATERIALIZATION` (needs parent→target scoped gold diff from git objects, Phase 3/4) |
| TEST_CONTRACT_HASH | KNOWN_ALL (frozen behavior contract manifest) |
| ENVIRONMENT_ID | KNOWN_ALL (frozen environment-id proposal) |

Within a task, TEST_CONTRACT_HASH and ENVIRONMENT_ID are task-level constants, and
REFERENCE_PATCH_HASH is a deterministic function of (task, scope); therefore two arms with
the **same canonical scope hash on the same task MAY share one physical execution**. Thus
unique physical executions = per-task count of distinct scope hashes (plus the unresolved
RANDOM arm as its own group until Phase 4).

## 5. Counts (deterministic, recomputable)

| Metric | Value |
|---|---:|
| Logical arm-records (12 arms × 219 tasks) | **2,628** |
| Known scope-hash records | 2,409 (11 arms × 219) |
| Unresolved scope records (RANDOM arm) | 219 |
| **Unique physical executions (scope-level dedup)** | **2,493** |
| Dedup reduction records | 135 |
| Primary pair (RM_CSS, AGENT) logical | 438 |
| Primary pair (RM_CSS, AGENT) unique physical | 417 |
| F2P-positive candidate tasks | 83 |
| `n_opws_eligible` | `UNRESOLVED_PENDING_STAGE5_PREFLIGHT` |
| `n_primary_paired` | `UNRESOLVED_PENDING_STAGE7_ARM_ARTIFACTS` |

## 6. Unresolved dependencies (UNKNOWN where evidence is missing)

1. `REFERENCE_PATCH_HASH` — requires git-object scoped gold diff materialization
   (Phase 3/4). Until then the 5-field map is provisional at scope level.
2. `SCOPE_HASH` for RANDOM_SIZE_MATCHED_RM_CSS — requires the frozen deterministic
   sampling at Phase 4 (seed 20261012); **never generated in Phase 2**.
3. `n_opws_eligible` — requires STAGE_5 behavior-contract preflight (Phase 3).
4. `n_primary_paired` — requires STAGE_7 paired eligibility (Phase 5).

## 7. Resource estimates

- Frozen eval-time basis over the 83 F2P-positive candidates: **12.534 h** raw
  (Σ `wall_s`, `per_task_v2.jsonl`) — reproduces the Phase-1 §7 12.53 h figure.
- Upper bound, all 12 arms, no dedup: **150.41 h raw** → 188–211 h with overhead 1.25–1.40
  (matches Phase-1 §7 150.4 h → 188–211 h).
- Scope-level dedup reduction: 135 of 2,628 records → **~5.1 %** of arm-records; the
  container-time saving is proportional to the unique-physical reduction per eligible task
  and remains `UNKNOWN` until `n_opws_eligible` resolves (dedup cannot be sized in
  hours until STAGE_5 chooses the eligible set).
- Disk: B5 unchanged — C: 30.9 GiB free at Phase-1 record; ≥40 GiB (or relocate Docker
  root) required before any arm run (future gate G5).

## 8. Required future gates

| Gate | Resolves | Phase |
|---|---|---:|
| G1 | `n_opws_eligible` (STAGE_5 behavior-contract preflight) | Phase 3 |
| G2 | `REFERENCE_PATCH_HASH` (git-object scoped gold diff) | Phase 3/4 |
| G3 | RANDOM_SIZE_MATCHED_RM_CSS scope hashes (frozen sampling) | Phase 4 |
| G4 | `n_primary_paired` (STAGE_7 paired eligibility) | Phase 5 |
| G5 | disk ≥ 40 GiB (B5) | before any arm run |

## 9. Verification performed

| Check | Result |
|---|---|
| `pytest tests/unit/opws/test_opws_phase2_plan.py -q` | **28 passed** |
| `pytest tests/unit/opws/test_opws_phase1_build.py -q` (regression) | **18 passed** |
| `ruff check scripts/opws_phase2_plan.py tests/unit/opws/test_opws_phase2_plan.py` | 0 findings |
| `mypy --strict scripts/opws_phase2_plan.py` | no issues |
| `py_compile scripts/opws_phase2_plan.py` | OK |
| `python scripts/opws_phase2_plan.py --check --created-at 2026-10-20T10:00:00Z` | `all_identical=true` |
| Frozen inputs re-hashed before/after | identical (9/9) |

## 10. Prohibitions respected

No OPWS execution, no model/API calls, no selector output generated (RANDOM arm scope
explicitly unresolved), no patch/`git diff` materialization, no worktree/Docker, no frozen
artifact mutation (binding files untouched), no commit/push/tag, no Kaggle/FULL exports,
no scientific outcome produced.

## 11. Final state

- **Git status:** only additive untracked paths (Phase 0/1/2 records + new script + tests
  + phase2 artifacts + this memo + LIGHT zip).
- **Phase 2 status:** scope sources resolved 11/12 (RANDOM pending Phase 4 by rule);
  physical dedup plan emitted with `n_unique_physical_executions = 2493` (UNKNOWN-pending
  `REFERENCE_PATCH_HASH`).
- **Next step:** STOP — awaiting authorization for Phase 3 (STAGE_5 evaluator-engine dry
  preflight + `REFERENCE_PATCH_HASH` materialization) per the frozen protocol.