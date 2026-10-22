# OPWS R1 — Phase 3B Engineering Result: real Git-object patch materializer + evaluator-adapter skeleton, NO scientific execution (2026-10-22)

- **Mission:** M18 — OPWS Phase 3B (engineering; **no** behavioral outcomes)
- **Character:** additive code + synthetic-fixture tests + receipts + LIGHT export. **No real-task
  F2P/P2P test, no STAGE_5 scientific preflight, no 12-arm run, no E2E generation, no Docker/WSL
  run, no API inference, no dependency install/download, no behavioral evaluator instantiated for a
  real task, no commit/tag/push.**
- **Execution identity:** branch `parallel/opws-instrument-build-2026-10-20`, HEAD
  `0fab02d38b6c3747f32808f375ade9b7a8e4e40d` (matches the owner-reported pushed commit; worktree
  clean before and after; only newly added untracked files), origin/main `1661ec215e…` unaffected.

## 1. VERDICT

**TECHNICAL_IMPLEMENTATION_PASS (engineering only; scientific PASS is explicitly NOT claimed).**
`REAL_TASK_BEHAVIORAL_OUTCOMES=0`, `LLM_GENERATION_RUNS=0`.

## 2. Preflight facts and reconciliation (task A)

- HEAD == owner-reported `0fab02d3…`; branch matches; `git status --short` clean at start; the 30
  checkpointed Phase0–3A files of the `0fab02d3` checkpoint commit are present.
- **Reconciliation recorded:** the frozen R1 authority commit `9038df3e…` is **NOT an ancestor** of
  HEAD (merge-base = `1661ec21…` = origin/main). `research/opws-protocol-r1/*` exists only inside
  the frozen commit's tree. All six frozen R1 files were therefore read **via read-only git objects**
  (`git show 9038df3e:<path>`), never copied into HEAD, never re-frozen — consistent with the
  Phase-0/1 Source Authority Table (entry §3, A1).
- Interfaces reused (no second toy engine): `scripts/opws_phase2_plan.py` →
  `normalize_scope_path(s)`, `compute_canonical_scope_hash` (mirrors the frozen reference
  implementation `scripts/opws_protocol_r1_validate.py`), `sha256_bytes`; `scripts/opws_build.py` →
  `BuildError` convention; toy engine error-class pattern (`scripts/opws_toy_engine.py`). M15-R/M14-R
  frozen engines were NOT reused (consistent with Phase 3A decision) and their outputs untouched.
- Real task identity source for future materialization: `research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json`
  (219 tasks; per-task `parent_commit`, `target_commit`, `test_command`, `contract_sha256`).

## 3. Delivered modules

| File | Role |
|---|---|
| `scripts/opws_phase3b_patch_materialize.py` (new) | read-only Git-object reference-patch materializer (task B) |
| `scripts/opws_phase3b_evaluator_adapter.py` (new) | contract/env-identity adapter skeleton + taxonomy (task C) |
| `tests/unit/opws/test_opws_phase3b_patch_materialize.py` (new) | 28 synthetic-git-repo tests (task D) |
| `tests/unit/opws/test_opws_phase3b_evaluator_adapter.py` (new) | 16 adapter tests (task D) |
| `research/opws/phase3b/demo_scope.json`, `demo_classification.json` (new) | deterministic demo fixtures |
| `research/opws/phase3b/demo_materialize_run1/run2_receipt.json` (new) | deterministic double-run receipts |
| `research/opws/phase3b/PHASE3B_RECEIPT.json` (new) | JSON receipt (this mission) |

### Materializer key facts
- Pure function `materialize_scoped_reference_patch(task_id, repo, parent_commit, target_commit, scope_paths, classification, test_paths=None, allow_added=False, tape_unresolved=None)`
  → `MaterializationResult` with `reference_patch_bytes`, `reference_patch_hash`, `test_patch_bytes`,
  `test_patch_hash`, `selected_scope_hash`, `per_path_status`, `invalid_prediction_paths`,
  `unresolved_contracts`, `files_changed`, `scientific_outcome="UNOBSERVED"`.
- Deterministic git invocation: argument arrays, `shell=False`, `--` pathname separation,
  `git cat-file -e <ref>^{commit}` absolute-ref verification (returns full 40-hex), bounded output
  (`DEFAULT_MAX_PATCH_BYTES=64 MiB`, `OutputTooLargeError`), explicit diff settings
  (`-c core.autocrlf=false -c core.quotepath=false -c diff.renames=false --no-ext-diff --no-color --no-textconv`).
- Frozen PRIMARY status handling: MODIFIED/DELETED → `git diff <parent> <target> -- <path>`;
  RENAMED old → `git diff --no-renames … -- <oldpath>` deletion side; RENAMED new / ADDED →
  full-file creation from the target-commit blob (mode-guarded; symlink blob (120000) fails closed
  with `SymlinkPathError`; binary content fails closed `UnsupportedStatusError`).
- `allow_added=False` (parent-only selector) records ADDED / RENAMED-new scope paths in
  `invalid_prediction_paths` with reason (never silently dropped — frozen R1 §3 fail-closed guard)
  and emits an explicit `R1-ADDED-HANDLING` unresolved record where frozen scope sources conflict.
- Test changes split by `split_test_reference` into the **common behavior contract**
  (`test_patch_hash`); scope listing a test path → `TEST_CHANGE_NOT_EDITABLE_SCOPE` record.
- `full_reference_classification(repo, parent, target)` = complete historical **non-test** change
  set derived read-only from `git diff --name-status -z -M` — **PROPOSED R1.1 diagnostic control
  only**; GOLD keeps its frozen proxy source unchanged.
- `physical_execution_identity(...)` + `plan_physical_dedup(records)` implement the frozen
  five-field tuple `(TASK_ID, SCOPE_HASH, REFERENCE_PATCH_HASH, TEST_CONTRACT_HASH, ENVIRONMENT_ID)`;
  equal patch hashes are never permission to dedup different scopes (test-proven).
- `apply_check(worktree_dir, patch_bytes)` — fixture-only `git apply --check` probe (synthetic tmp
  dirs only; never a real Saleor worktree).

### Adapter key facts (task C)
- `instantiate_contract(contract_hash, node_ids, contract_kind, environment_id)` — instantiation
  boundary that fails closed `ContractNotInstantiatedError` (→ frozen `TEST_CONTRACT_INVALID`) on
  malformed hash/empty node list/bad env id. **Distinguishes failure to instantiate a contract from
  behavioral failure**: `evaluate_behavior(...)` always raises
  `BehavioralEvaluationNotAuthorizedError` in M18 — scientific PASS/FAIL remain UNOBSERVED.
- R1.1 **PROPOSED** control records: NEG, FULL_REFERENCE, ORIGINAL_R1_GOLD / GOLD_PROXY,
  SELECT_ALL — arm IDs, frozen sources and denominators unchanged
  (`r11_proposed_control_records()`), all `status=PROPOSED_R11`.
- Common test contract applied exactly once per TEST_CONTRACT_HASH (`apply_common_tests_once`).
- Fail-closed engineering taxonomy `classify_engineering_failure(exc)` /
  `classify_apply_check(ok, stderr)` mapping onto the frozen invalid classes
  (PATCH_APPLICATION_INVALID, TEST_CONTRACT_INVALID, ENVIRONMENT_INVALID, INFRASTRUCTURE_FATAL,
  ARM_PREDICTION_INVALID, UNKNOWN_FAIL_CLOSED); scientific classes are asserted never produced
  (`guard_non_scientific`).

## 4. Tests

| Area | Result |
|---|---|
| `tests/unit/opws/test_opws_phase3b_patch_materialize.py` (28) | **28 passed** |
| `tests/unit/opws/test_opws_phase3b_evaluator_adapter.py` (16) | **16 passed** |
| 3A regression: `test_opws_phase1_build.py` (18) + `test_opws_phase2_plan.py` (47) + `test_opws_toy_engine.py` (14) | **79 passed** |
| `tests/unit/opws/` full run | **123 passed** (29 s) |
| `ruff check` all 4 changed files | 0 findings |
| `mypy --strict` both new scripts | no issues |
| `py_compile` all 4 changed files | OK |
| `git diff --check` | clean (tracked scope untouched) |

**M18 coverage checklist (D.12/D.13 mapping):** modified patch ✓; added file ✓ (reference arms) and
parent-only scope invalid-record ✓; deleted file ✓ (non-test) and deleted test → common contract ✓;
rename old/new sides ✓ + new-path parent-only invalid ✓; test-file common contract exactly once ✓
(`apply_common_tests_once` dedupe on TEST_CONTRACT_HASH) ; empty scope → safe null patch ✓;
traversal/absolute/drive/backslash/`a//b`/`a/./b` rejected ✓; symlink/path escape rejected ✓
(mode-120000 blob) ; missing parent/target object → `GitObjectIdentityError` ✓; patch conflict via
`git apply --check` → `PATCH_APPLICATION_INVALID` ✓; changed blob fingerprint ✓ (apply reproduces
target blob bytes; tamper changes hash); unexpected output → `OutputTooLargeError` ✓; stable SHA +
deterministic double run ✓; SCOPE_HASH mismatch vs equal REFERENCE_PATCH_HASH → two physical
executions, equal five-tuple → one ✓; failing FULL_REFERENCE contract fixture → `TEST_CONTRACT_INVALID`,
never a selector (`ARM_PREDICTION_INVALID`) failure ✓.

**Per-fixture deterministic SHA (double-run, CLI):**
- `task=saleor-rc-demo` scope `demo_scope.json` + classification `demo_classification.json`,
  `allow_added=true`:
  - run1 & run2 identical → `reference_patch_sha256=57891c693d7b7210a019e7c1b019fd3fe400907088d940d60d9e38a23bbc0a1e`
  - `test_patch_sha256=f1da2c6c5497ad22dda3227a0aab3eddbaa1e274984a3de3c548f3ee13beecd6`
  - `selected_scope_hash=eda107cbc76d5bef489a276fa2baaaeeaa87796a916d754607b0a788b850c0c0`
- Adapter dry-run contract instantiation: `instantiation_id=68d7c4a65443de19927eb23a5787245aefb3025c041c3bc2c92592a563e0c8ce`
  (contract_hash=`aa…aa`, node_ids=`f2p-1,f2p-2`).

## 5. Unresolved R1.1 decisions (explicit; no guessing)

| # | Contract | Status | Recorded in |
|---|---|---|---|
| U1 | GOLD scope source (historical proxy non-test set) vs GOLD-validity expectation (full non-test reference patch) | `UNRESOLVED_PENDING_OWNER` — R1.1 amendment is DRAFT/UNAPPROVED; GOLD not rewritten; FULL_REFERENCE is a separate PROPOSED diagnostic | materializer `UnresolvedContractRecord` / this memo |
| U2 | Frozen ADDED handling (reference-derived arms may include added files) vs frozen scope sources that cannot express them | `UNRESOLVED_PENDING_OWNER` — explicit `R1-ADDED-HANDLING` records, never silent injection | `MaterializationResult.unresolved_contracts` |
| U3 | `ENVIRONMENT_ID` serialization recipe | prior owner-approved proposal stands (`OPWS_ENVIRONMENT_ID_PROPOSAL.json`); not re-decided here | Phase-2/owner decisions C5 |
| U4 | Real Saleor git repository path | not recorded in this repo; the materializer takes it as an explicit read-only parameter — a future authorized execution mission must supply the path to a read-only mirror | this memo §7 |
| U5 | AGENTS.md end-of-mission LIVE_STATUS update | **deliberately not touched** in M18: LIVE_STATUS is the WP-1b research line's current-state signal and its external study-deck consumer; this engineering mission's receipt contract (§15 of the prompt) is the controlling deliverable set. Flagged for owner. | this memo |

## 6. Prohibitions obeyed (audit trail)

No real-task F2P/P2P test; no STAGE_5 preflight; no 12-arm run; no E2E generation; no Docker/WSL;
no API inference; no dependency install/download; no behavioral evaluator for a real task; no
checkout/alter/clean/write to the Saleor repository; no OPWS execution worktree materialized on
Windows/NTFS (only `git apply --check` and `git apply` on synthetic tmp dirs inside tests, which are
fixture-only); no commit/tag/push; no mass repo scan; no overwrite of frozen evidence/outputs; no
secrets in logs; `REAL_TASK_BEHAVIORAL_OUTCOMES=0`; `LLM_GENERATION_RUNS=0`. No negative outcome
was reinterpreted as any RM-CSS/Agent result.

## 7. Exact next owner actions

1. **R1.1**: decide U1/U2 (GOLD source vs ADDED-in-reference-arms scope semantics; approve or
   reject the FULL_REFERENCE diagnostic and the `R1-ADDED-HANDLING` rule) → then decide U3 env-id
   freeze and supply the read-only Saleor mirror path (U4).
2. Then 1–3 **task-control pilot** (e.g., deterministic GOLD/SELECT_ALL + NEG + FULL_REFERENCE on a
   handful of tasks) with STAGE_5 inside Linux under separate owner authorization.
3. Then the RANDOM_SIZE_MATCHED_RM_CSS Phase-4 parity/freeze, and finally the paired scientific
   population run (separate authorization).
