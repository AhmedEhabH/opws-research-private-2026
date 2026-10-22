# OPWS P2A — Verification Report (2026-10-20)

**Session:** M17 OPWS R1 — P2A Binding Decision Closure  
**Date:** 2026-10-20  
**Base:** `parallel/opws-instrument-build-2026-10-20` @ `315612639020c8a5d3102fb86d33230422bd66f5`

---

## Preflight Identity Verification

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Working directory | `D:\WP2\active\opws-instrument-build-2026-10-20` | `D:\WP2\active\opws-instrument-build-2026-10-20` | ✅ |
| Branch | `parallel/opws-instrument-build-2026-10-20` | `parallel/opws-instrument-build-2026-10-20` | ✅ |
| HEAD | `315612639020c8a5d3102fb86d33230422bd66f5` | `315612639020c8a5d3102fb86d33230422bd66f5` | ✅ |
| Tracked modifications | none | none | ✅ |
| Untracked (expected) | Phase 0/1 artifacts | 13 additive paths | ✅ |

---

## Frozen Input Integrity (9 files, pre/post build)

| Input File | SHA-256 (Pre) | SHA-256 (Post) | Unchanged |
|------------|---------------|----------------|-----------|
| `R4_FULL144_READINESS_MANIFEST.json` | `3381788cad3f1f2dc45ec269ce3a4ac7219d69714995a53948f0fa9a0d64b4e2` | same | ✅ |
| `R4_I6_CORRECTED_ZERO_CONTAINER_CENSUS_144.json` | `f60668f88b42d8f7aebb6671dba97d705dc8d2bfbed4046ff7e4332361ec9240` | same | ✅ |
| `R4_EXECUTION_IMAGE_BINDING_RUNTIME_CLEAN.json` | `fa4776d850cbc6b4aafcaaeea51b711cfe1081689803e5c69427386f246d7ce7` | same | ✅ |
| `R4_SCIENTIFIC_FULL144_SUCCESSOR_RESULT_2026-10-17.json` | `22a30f94b11e7b864d2efcf356738e65c3da5d1a792f4030b3c18f6d4d58977d` | same | ✅ |
| `per_task_v2.jsonl` | `7fdeeb936ea84e7ef47a461e940671ee628114d9a1d960f29a0be008eddce021` | same | ✅ |
| `wp2_saleor_main297_census_2026-09-22.json` | `6146237d353376632d729e159761470b46fc5eb300fa9def971d5faf7b1f60c0` | same | ✅ |
| `adapter_report.json` | `2b0eeddd9ebdbc7ba6768f47ceafdf7578e313a4cfb483d4a471da258652a0f8` | same | ✅ |
| `wp1b_main_297_manifest.json` | `d858316667c4a3e28f7bf759001dc1fd8746b93c710592ff646f3f91584811eb` | same | ✅ |
| `wp2_m14a_evalcore_e1.py` | `c0f7dc7deaa5af187d6828b53a7fef95253ba97a9fa5602c0d4e42e34ef3f093` | same | ✅ |

**All 9/9 frozen inputs byte-identical before and after build.**

---

## Build Determinism Gate

```
C:\Users\Ahmed\AppData\Local\anaconda3\python.exe scripts/opws_build.py --check --created-at 2026-10-20T09:00:19Z
→ {"all_identical": true, "artifacts": 7}
```

```
C:\Users\Ahmed\AppData\Local\anaconda3\python.exe scripts/opws_build.py --created-at 2026-10-20T09:00:19Z
→ all_identical=true, binding_self_sha256=d4e1a4aad4b4055641f99d9ce4aa97727c4eea5251aebebf7ef21ded749601b6
```

Rebuild with same `--created-at` produces **byte-identical** artifacts (7/7).

---

## Targeted Static Validation

| Check | Command | Result |
|-------|---------|--------|
| Unit tests | `pytest tests/unit/opws/test_opws_phase1_build.py -q` | **18 passed** in 3.61s |
| Ruff lint | `ruff check scripts/opws_build.py tests/unit/opws/test_opws_phase1_build.py` | **0 findings** |
| Python compile | `python -m py_compile scripts/opws_build.py` | **OK** |
| Git diff check | `git diff --check` | **No whitespace errors** |

**No full test suite run (per policy). No baseline M17 suite run.**

---

## Cardinality Invariants (Post-Build)

| Metric | Expected | Actual | Result |
|--------|----------|--------|--------|
| Units (READY) | 144 | 144 | ✅ |
| Tasks (expanded) | 219 | 219 | ✅ |
| F2P-positive tasks | 83 | 83 | ✅ |
| PRIMARY_BEHAVIORAL_F2P_ELIGIBLE | 71 | 71 | ✅ |
| Ordered task IDs SHA-256 | `5972b20d6b08095a555e4c49b9f03703ccd24cfeeabd27c42bcd748cf7cd1364` | same | ✅ |
| Unit-order hash (144) | `8eb4a7242e12bb03715adac5fffdea2e4340585843fc137ececd38952ad6a19e` | reproduced | ✅ |
| Task hash ≠ Unit hash | enforced | `5972b20d... ≠ 8eb4a724...` | ✅ |
| Protocol blobs | 16 | 16 | ✅ |
| Protocol bundle SHA-256 | `44f18bcad2a80f160646ddd676bca2eb80bd3fc06a1a4925a82e301f025cd767` | recomputed match | ✅ |
| Stage-5 (behavior_executable) | all 219 UNRESOLVED | 219 UNRESOLVED | ✅ |
| Stage-6 (opws_eligible) | 0/136/83 | 0/136/83 | ✅ |
| Stage-7 (primary_paired) | 0/136/83 | 0/136/83 | ✅ |
| `n_opws_eligible` | UNRESOLVED token | token (not 0/219) | ✅ |
| `n_primary_paired` | UNRESOLVED token | token (not 0/219) | ✅ |

---

## Decision Verification

### B2 — ENVIRONMENT_ID
- **Recipe verified** in `scripts/opws_build.py::environment_id()` and `OPWS_ENVIRONMENT_ID_PROPOSAL.json`
- **219 tasks → 131 distinct IDs** (51 shared by ≥2 tasks, max group size 6)
- **Components non-null**: all 219 tasks have immutable_image_id, deterministic_binding_hash, environment_fingerprint
- **No collision**: distinct triples → distinct IDs verified
- **No leakage**: components are infrastructure provenance only
- **Gate**: `OWNER_APPROVED_CONDITIONAL_GATES_PASS` ✅

### B3 — F2P Node Identity Rule
- **Rule verified**: `scripts/wp2_m17_contract.py::f2p_node_set_from_frozen` matches builder's `node_identity_binding_mode = "AT_EVALUATION_BOUNDED_BY_FROZEN_COUNT"`
- **Provenance check 1**: `per_task_v2.jsonl` — 0/220 records have `node_records`
- **Provenance check 2**: `harness_v3_2026-09-26` — 34 files with `node_records`, 0/219 OPWS task overlap
- **Quantitative claim "9/219, 78"**: **UNVERIFIED_SOURCE_COUNT** — retracted from builder messages and Phase-1 reports
- **Gate**: `RULE_APPROVED_PROVENANCE_UNVERIFIED` ✅ (rule stands, numbers removed)

### B4 — protocol_sha256
- **Recipe verified**: `load_protocol_bundle()` computes 16-blob sorted bundle hash at peeled commit `9038df3e`
- **Independent recomputation**: matches `44f18bcad2a80f160646ddd676bca2eb80bd3fc06a1a4925a82e301f025cd767`
- **Unit test**: `test_protocol_bundle_hash_recomputes_from_git` passes
- **Schema ambiguity**: "tag peel hash" prose clarified in additive memo (not in frozen protocol)
- **Gate**: `OWNER_APPROVED_CLARIFIED_IN_MEMO` ✅

---

## Prohibitions Respected

| Prohibition | Verified |
|-------------|----------|
| No OPWS execution | ✅ |
| No model/API calls | ✅ |
| No frozen artifact mutation | ✅ (9/9 inputs unchanged) |
| No selector/outcome/GOLD analysis | ✅ |
| No retraining/rethresholding | ✅ |
| No commit/push/tag | ✅ |
| No Docker/WSL execution | ✅ |
| No Stage-5/Stage-7 behavioral tests | ✅ |
| No Kaggle/pilot packaging | ✅ |
| No FULL exports | ✅ |

---

## Zero Scientific Outcomes

- No arm execution performed
- No selector evaluation
- No F2P/P2P behavioral tests run
- No GOLD/SELECT_ALL diagnostics
- No bootstrap/statistical analysis
- No model API calls (cost = $0)
- Pi authoring model usage: **Input/Output/Reasoning only** (no benchmark API cost)

---

## LIGHT Export

Created: `project-light-2026-10-20-<HHMM>.zip` (see manifest below)

---

## Final State

- **Branch:** `parallel/opws-instrument-build-2026-10-20`
- **HEAD:** `315612639020c8a5d3102fb86d33230422bd66f5`
- **Git status:** Only additive untracked paths (Phase 0/1 artifacts + new decision/verification files + LIGHT zip)
- **Binding status:** `DRAFT_PARTIAL_PHASE1_HOLD` (unchanged — decisions resolve serialization/rule, not Stage-5/7)
- **Stage-5/7:** All 219 UNRESOLVED (requires separate owner approval for Phase 3+)
- **Original Phase 2 scope/dedup:** NOT authorized — separate owner approval required
- **Stage-5 engine construction:** NOT authorized
- **Scientific runs:** NOT authorized

---

## What Remains (Requires Separate Owner Approval)

1. **Phase 3 (evaluator engine):** STAGE_5 OPWS worktree dry preflight / behavior-contract executability
2. **Phase 4 (technical tests/freeze):** Any arm execution, 12-arm population, RM_CSS vs AGENT, GOLD/SELECT_ALL
3. **Phase 5 (handoff/STOP):** STAGE_7 paired eligibility, outcome aggregation, analysis
4. **Original Phase 2 scope/dedup physical plan:** Zero-outcome scope/dedup plan
5. **Resource risk (B5):** C: 30.9 GiB free; 11 immutable images must fit before any arm run