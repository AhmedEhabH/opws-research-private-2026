# M19A4 STOP-GATE REPORT — P2P-S Exact Identity Recovery

Status: **CANDIDATE RECOVERY AUDIT — OFFLINE** · Date: 2026-10-24 (local) ·
Branch: `parallel/opws-instrument-build-2026-10-20` · HEAD: `7b93e7555f4851634af489444e0e9670a0acd610`

This is an offline provenance audit. It produces candidate identity lists only;
it does NOT freeze any protocol, does not change the frozen F2P contracts or
cohort, and does not claim any OPWS behavioral outcome.

---

## 1. Objective and replay rule

Recover the exact historical `P2P_ONLY` (changed-test pass-to-pass) test-node
identities for the frozen 83-task OPWS cohort from the C2 MAIN83 JUnit XML
evidence, using the frozen classifier and the frozen historical merge order.

Replay rule (identical to `scripts/opws_m19a2_build_node_contract.py`):

1. For each of the 83 tasks use `n_test_files` from
   `per_task_v2.jsonl`; enumerate
   `{task12}_{p|t}_r{rep}_f{idx}.xml` for `rep in 0..2`, `idx in 0..nf-1`.
2. Parse each XML with the frozen `parse_junit_with_failures`
   (hash-pinned `4609a2256d...`).
3. Merge per side with **rep-major, file-minor, last-write-wins**
   (exactly the historical `run_state_in_container` order).
4. Classify with frozen `classify_node_v2` (hash-pinned
   `aa85f4953be...`) with the merged last scalar replicated 3×:
   - `P2P_ONLY`  ⇔  target-last == `passed` AND parent-last == `passed`
     (classifier step 3; FLAKY checked first).
5. **Strict three-run projection** (candidate sensitivity): a node is stable
   pass on a side iff its 3 recorded outcomes are exactly `['passed']*3`
   (fewer/more appearances ⇒ unstable); same classifier precedence.

## 2. Evidence and input verification (all PASS)

| Input | SHA-256 | Status |
|---|---|---|
| `JUNIT_EVIDENCE_MANIFEST.json` (evidence dir) | `39ea5470625188a4357575f971842676d32a3ee811874d256f7978e1989b3647` | verified |
| All 1,801 evidence XML files (on-disk vs manifest) | per-file | all match |
| `OPWS_F2P_NODE_CONTRACT_83.json` | `df1e087b199277cc56c42fdfd182f85fcd3faf0c74f4701d5add80b52866f124` | verified (matches M19A3 pin) |
| `OPWS_F2P_THREE_RUN_SENSITIVITY_83.json` | `62f528b060cbbc814f137cbba509443cc4d6fdcb2730010ecc25ce99f942fe41` | verified (matches M19A3 pin) |
| `per_task_v2.jsonl` | in provenance artifact | counted/replayed |
| `oracle_semantics_v2.py` (LFs variant) | `aa85f4953bea36974b77340c38fe8219e5a8d577d5e786ff74c06de2fc07423d` | pin OK |
| `oracle_confirmation.py` | `4609a2256d0803c1029fae572db62c28f6885b8a12628094a9e10bcb65b752d1` | pin OK |

`C2_MAIN83_JUNIT_RESCUE_2026-10-23` = 1,801 XML files, 46,218,654 bytes,
166 parent/target dirs (83 tasks × 2 sides × 3 reps), every file hash verified.

## 3. Recovery results (83/83 tasks, no forced agreement)

| Aggregate | Historical as-executed | Strict three-run |
|---|---|---|
| tasks recovered | 83 | 83 |
| n_nodes (union target∪parent) | 11,284 | 11,284 |
| **P2P_ONLY nodes** | **9,275** | **9,273** |
| BEHAVIORAL_F2P | 731 | 707 |
| SYMBOL_ABSENCE_F2P | 64 | 63 |
| F2P total | 795 | 770 |
| FLAKY | 987 | — |
| tasks with F2P (primary) | 71 | 70 |
| tasks with F2P (extended) | 83 | 82 |
| changed nodes hist→strict | — | **27** (3 tasks) |

Per-task gate results (all 83 tasks):
- `evidence_enumeration_complete`: **83/83 PASS**
- `replay_counts_match_contract` (all 7 categories + n_nodes): **83/83 PASS**
- `strict_vs_frozen_sensitivity` (strict counts + strict F2P ids vs frozen
  sensitivity file): **83/83 PASS**
- `changed_nodes_match_frozen_sensitivity` (27 changed-node records incl.
  run lists): **83/83 PASS**

Reconciliation with frozen evidence — the recovered historical F2P set is
exactly 795 (731 behavioral + 64 symbol-absence), the strict projection is
exactly 770, primary tasks 83/82/70 match the frozen contract, and the 27
changed nodes (25 F2P→FLAKY on `saleor-rc-05bdc7feb9ac`, one P2P_ONLY→FLAKY
on each of `saleor-rc-032b98afff20` and `saleor-rc-30b4edece5aa`) equal the
frozen sensitivity file node-for-node including recorded run lists.

## 4. P2P_ONLY identity deltas (historical vs strict)

- Historical-only P2P_ONLY (excluded under strict): **2 nodes**
  - `test_draft_order_complete_product_without_inventory_tracking`
    (032b98afff20) — parent runs `passed|failed|passed`, target runs
    `passed|passed|passed`.
  - `test_query_used_gift_card_by_owner` (30b4edece5aa) — parent runs
    `passed|passed|passed`, target runs `failed|passed|passed`.
- Strict-only additions over historical: **0 nodes**. No node becomes P2P_ONLY
  under strict that was not P2P_ONLY historically.

These two exact nodes demonstrate the historical-vs-strict distinction: the
historical last-write-wins merge + `[last]*3` replay classified them
P2P_ONLY; the strict three-run reading marks them FLAKY.

## 5. Evidence anomalies (non-blocking, recorded)

- **One stray file** outside the frozen enumeration: `05bdc7feb9ac_t/timing_r0_f0.xml`
  (name does not match the `{task12}_{state}_r{rep}_f{idx}.xml` pattern; it was
  never read by the frozen M19A2 replay, which still achieved an exact 83/83
  count match). It IS included in the evidence manifest (hash-verified) and is
  ignored here, exactly like the frozen replay. Manifest total 1,801 = 1,800
  enumerated + this 1 stray file.
- No missing enumerated files; no duplicate node identities; no unparseable XML.
- Per-node appearance counts: nodes classified P2P_ONLY always have exactly 3
  parent and 3 target appearances (they must, to be stable-pass under strict);
  nodes with >3 appearances are FLAKY/TARGET_INVALID under strict (recorded in
  ledger).

## 6. Scientific guards honored

- Frozen F2P contracts and cohort untouched (files read-only, hashes pinned).
- 83/82/70 and 795/770 figures unchanged and reproduced.
- No P2P-U membership invented — P2P-U V2 uses the separate frozen
  unchanged-test pool; nothing here claims P2P-U.
- These lists are **candidate** P2P-S (changed-test pass-to-pass) node sets for
  the 83-task cohort, NOT an approved OPWS P2P-S protocol.
- Zero API/model calls; zero Saleor/Docker/WSL execution; no regeneration, no
  benchmark API, no future-commit or gold-oracle access.
- No commit, push, or tag created.

## 7. Artifacts (reports/m19a4_p2ps/)

| File | SHA-256 |
|---|---|
| `M19A4_P2P_ONLY_NODES_BY_TASK_83.json` | `18963d7e806484e4bbedae91ae099f25ea6de8334bbdbd82f31d4763127d850b` |
| `M19A4_NODE_LEDGER_83.tsv` (11,284 rows) | `dad04c423bb9aca3df0d55569092ccb02ea4c8639590f582f6f1b80781e5724a` |
| `M19A4_PROVENANCE_AND_INPUT_HASHES.json` | `fde23699592c5808d05fe9aafa41815a912d16ee70eb364992e6d8ea4f4daa00` |
| `M19A4_PER_TASK_RECONCILIATION.json` | `53e9b63388e082c1fedc07bea50b673eca10325d9c7a4a5b58b9dfec35fac3e2` |
| `M19A4_HISTORICAL_VS_STRICT_SENSITIVITY.json` | `f874619afae72a745e883420885afff8568618bc32dab9475fdd4f8c35c2e747` |
| `M19A4_VALIDATION_RECEIPT.json` | `801121101714b8d8b4206023b7b23abb4e06f45488d2872cd5e31ae2e26efe7d` |
| `M19A4_STOP_GATE_REPORT.md` | recorded in the mission STOP report (changed after this table is written) |

Aggregate identity hash (historical+strict P2P_ONLY sets, canonical recipe):
`9fc10bc12d382ba2ee83bb1c6498046483b162ff2b3016b77ea2fa3cb0edf10a`

## 8. What remains blocked

- **Protocol freeze**: choosing historical (71 primary) vs strict (70 primary)
  as the P2P-S evaluator requires prospective owner/supervisor signoff —
  explicitly NOT made here.
- **P2P-S full protocol**: still requires the DEV-cohort freeze artefacts
  (`p2p_s_freeze_v1.py` + `per_test_dev_v2.jsonl` pipeline) — out of scope.
- **P2P-U**: unchanged-test proximity-capped set — out of scope, no membership
  inferred.
- **Behavioral runs**: any real OPWS behavioral experiment remains blocked
  pending review.
- LIVE_STATUS.json is stale (as-of 2026-10-05, pre-M19A2/M19A3); not updated
  in this audit-only mission.
