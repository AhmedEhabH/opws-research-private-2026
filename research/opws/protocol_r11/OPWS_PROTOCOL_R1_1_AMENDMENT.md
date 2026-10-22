# OPWS Protocol R1.1 — Owner-accepted decision set (local Git attestation pending)

**Purpose:** clarify control semantics before any real-task behavioral outcome. This is an additive prospective amendment to R1, not a revision of its frozen contents or a claim that R1.1 was previously preregistered.

**Frozen authority:** OPWS R1 Git commit `9038df3ea80d7d478c2f949b2d3fae75754bb6e1`, protocol bundle SHA-256 `44f18bcad2a80f160646ddd676bca2eb80bd3fc06a1a4925a82e301f025cd767`.

**Current engineering checkpoint:** `51ab05fefd1ff0c3221867e3dbfdc941e0083ac8` (M18 tests 123 PASS; real behavioral results ZERO).

**Owner approval state:** `ACCEPTED_IN_CHAT_2026-10-22; LOCAL_GIT_ATTESTATION_PENDING`. The owner responded "تمام" following the enumerated R1.1 decisions, accepting the decision set in principle. This document is prepared for owner review and local Git attestation; it is not yet a remotely committed protocol. No prediction/artifact has been changed by this text, and no scientific execution is authorized.

## Decision R11-01: Retain the pre-existing twelve R1 arms

**Important correction:** OPWS_ARM_REGISTRY_R1.json ALREADY declares **BM25_K3, BM25_K10, DENSE_K3, DENSE_K10, and BM25_TO_CIA_1HOP**. It also declares RM_CSS, AGENT, AGENTLESS_STYLE_ADAPTATION, SIP, SELECT_ALL, RANDOM_SIZE_MATCHED_RM_CSS, and GOLD. Do not add a duplicate BM25 arm or relabel the frozen R2 source. **Use the frozen predictions** from `m17-comp-baselines-r2-frozen-2026-10-12` after their source SHA, task coverage, and exact arm data keys have been verified on the owner's machine. The R1 original registry remains unchanged. Do not imply that existing DENSE_K3/K10 necessarily use `all-MiniLM-L6-v2` until R2 protocol/model provenance confirms it.

Any new exact MiniLM ranker required for RQ1 is a **separately labeled retrospective/configured baseline** and is not silently equated with an R1 dense arm. No results-based choice of k. Keep the frozen `RANDOM_SIZE_MATCHED_RM_CSS` rule (including its original empty-scope handling) unchanged.

## Decision R11-02: Distinguish control scopes and eligibility

- `NEG` (new diagnostic control, separate namespace from original 12): parent production tree plus the same common reference test patch. For F2P-positive tasks, at least one required F2P node must fail; missing/invalid nodes are instrumentation blockers, not a negative result.
- `FULL_REFERENCE` (new positive diagnostic control, separate namespace): **all non-test changes** between parent and target (including additions, migrations, non-Python production/config changes where applicable) plus the same test patch. Must apply cleanly, pass all required F2P nodes, and pass preserved P2P nodes before the task can be scientifically qualified. If it fails, no selector is blamed.
- `GOLD_PROXY` (descriptive alias for original frozen `GOLD`, not silently rewritten): reference patch restricted to **original historical non-test Python proxy**. Never claim this is automatically the complete non-test reference patch. It diagnoses proxy inadequacy; no longer used as the sole positive validity gate.
- `SELECT_ALL`: original candidate-universe maximal selector/control, same scope as frozen R1. In the prior 297-task **Git byte-patch identity audit**, it matched GOLD_PROXY 297/297; this is not behavioral equality nor physical dedup permission.

A task that passes NEG discrimination and FULL_REFERENCE is eligible for the next scope assessment subject to the unchanged contract/infra rules. If GOLD_PROXY fails while FULL_REFERENCE passes, record `PROXY_INADEQUATE` separately; do not silently drop or count as RM-CSS failure. Compare conditional rates transparently across eligible and proxy-inadequate strata. Do not presume success monotonicity under file addition.

## Decision R11-03: File-status and common test semantics

- Preserve the original R1 parent-visible selector universe and invalid prediction rules. Parent-only predictions cannot invent added paths or renamed-new paths.
- `FULL_REFERENCE` gets all non-test reference changes even when not in the candidate universe, including migrations and new files. The R1 `GOLD` historical proxy is NEVER extended to these paths after seeing labels.
- Treat all reference test changes as a common test contract, applied **exactly once** with an identical `TEST_CONTRACT_HASH` across control/predicted-scope runs. `saleor/graphql/test_middleware.py` has test functions/imports in 29 of the 297 universes but was unchanged in all those reference diffs: no duplicate patch application; future test classification must be explicit and versioned rather than guessed from the filename alone.
- Preserve fail-closed behavior for symlinks, binaries, unsupported rename/path operations, missing Git objects, and patch conflicts. No silent omission of unexpected files.

## Decision R11-04: Keep physical execution identities and prior environment decision

Never reuse a physical run unless all five frozen keys agree: `TASK_ID, SCOPE_HASH, REFERENCE_PATCH_HASH, TEST_CONTRACT_HASH, ENVIRONMENT_ID`. Equal patch hash alone is not enough. Linux Git-object worktrees only. Preserve the frozen rerun policy (no outcome-driven scientific reruns).

**ENVIRONMENT_ID is NOT an open design decision:** the owner conditionally approved its canonical three-part SHA-256 recipe on 20 October (see `research/opws/OPWS_P2A_OWNER_DECISIONS_2026-10-20.md`, Decision B2), with checks on 219 tasks. Implement that exact recipe. Missing frozen components fail closed.

## Decision R11-05: Scientific measurements and attrition

- Primary observable: `opws_joint_pass = behavior_sufficient AND preservation_pass` under reference-patch/perfect-generator assumption; not LLM E2E success.
- Predeclared RQ2 conditional reports: P(sufficient | historical proxy fully covered) and P(sufficient | historical proxy partially covered), both **with raw denominators**. Report `PROXY_INADEQUATE`, `CONTROL_FAIL`, `INFRA_BLOCKED`, `MISSING_RESULT`, `TIMEOUT` separately.
- Report Wilson intervals for proportions and paired-effect intervals with discordant counts for selector comparisons. Reuse R1's original paired-bootstrap identity and seed as appropriate, with any different interval type explicitly additive and labeled.
- Feasibility trigger 40 control-qualified tasks is **not a power guarantee**. If below 40, a separately identified reserve-extension cohort may be considered under a documented eligibility/seed rule defined before its outcomes; original rejected tasks are not silently replaced. Insufficient final n => inconclusive, not selectively omitted.
- R1 original statistical language calling this RQ3 belongs to earlier protocol history. The October MSc registration proposal has TWO RQs: RQ1 selection accuracy/cost; RQ2 scope behavioral sufficiency. Do not retrospectively rename R1 files.

## Decision R11-06: Safety, disk, and execution order

1. Record source identities and frozen R2 baseline coverage from the read-only inventory; do not recompute existing predictions. Verify path validity and dense-model provenance before calling any baseline fully validated.
2. Commit this accepted versioned R1.1 decision set with the frozen R1 and R2 authority identities and local inventory-receipt SHA. No real-task F2P/P2P results may have been observed when attesting.
3. Complete real test evaluator integration and synthetic tests without running a scientific Saleor task. The current M18 `evaluate_behavior()` deliberately raises rather than executing real F2P/P2P.
4. Before a controlled real pilot, measure disk from a single task with cleanup enabled, preserve **at least 30 GiB free**, and STOP if projected peak space crosses the threshold. Follow frozen same-task environment identity and Linux worktree restrictions.
5. Run predeclared small `NEG` + `FULL_REFERENCE` instrument controls first; then GOLD_PROXY and predictions only after qualified controls. Avoid looking at selector outcomes before control qualification.
6. Separate control-pilot outcomes (engineering/calibration) from later scientific sample analyses; lock amendments first.

## Approval, baseline evidence, and provenance

- **Decision:** R11-01 through R11-06 accepted in the user's 2026-10-22 conversation after presentation of those decisions. Local repository attestation remains pending: the owner must explicitly run the companion script with `-ConfirmOwnerApproval`, inspect the Git diff, and verify the private push. A chat acknowledgment is not a cryptographic signature and must never be fabricated as such.
- **R2 frozen tag:** `m17-comp-baselines-r2-frozen-2026-10-12`, peeled commit `6c2f698154ddcba22ff7d9a85656753a6eaee5ff`. Local read-only inspection (reported by owner) found **297 task IDs, 219 bound tasks, zero missing**, and prediction-key coverage of **219/219** for each of `BM25_K3`, `BM25_K10`, `DENSE_K3`, `DENSE_K10`, and `BM25_TO_CIA_1HOP`. This is **coverage only**, not proof that every selected path is valid or that R2 Dense used MiniLM. The SHA of the local inventory receipt will be recorded during Git attestation.
- **No behavior disclosure:** M18 synthetic tests were run; **no real Saleor F2P/P2P result** and no LLM-generated fix was produced. The amended measurement contract must be committed **before** any scientific behavioral outcomes are observed.
- **Frozen protocol:** never rewrite original R1 artifacts at `9038df3e`; this document is an additive successor describing precise changes and preserving prior history.
- **Approval condition:** only once the companion Git attestation completes may the state be described as `R1_1_APPROVED_AND_COMMITTED`. The private commit SHA and receipt are authoritative; the document alone is not a remote push.
