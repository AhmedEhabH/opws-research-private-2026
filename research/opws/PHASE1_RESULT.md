# OPWS R1 — Phase 1 Result and Costed Plan

- **Status:** `DRAFT_PARTIAL_PHASE1_HOLD` — Phase 1 built and verified; it is not a final binding.
- **Built:** 2026-10-20T09:00:19Z
- **Base:** `parallel/opws-instrument-build-2026-10-20` @ `315612639020c8a5d3102fb86d33230422bd66f5`
- **Machine-readable source of truth:** `research/opws/binding/OPWS_POPULATION_BINDING_STATUS.json`

## 1. The 13-field binding (draft)

| # | Field | Value |
|---|---|---|
| 1 | `full_d7_evidence_commit` | `0fea61c799b3b3ded9d0c74a0a20ea3535d103c1` |
| 2 | `full_d7_tag` | `m17-d7-r4-scientific-full144-successor-pass-2026-10-17` |
| 3 | `full_d7_ready_population_file` | `research/env-canon-r4/R4_FULL144_READINESS_MANIFEST.json` |
| 4 | `full_d7_ready_population_sha256` | `3381788cad3f1f2dc45ec269ce3a4ac7219d69714995a53948f0fa9a0d64b4e2` |
| 5 | `n_env_ready` | `219` |
| 6 | `behavior_contract_manifest` | `research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json` |
| 7 | `behavior_contract_manifest_sha256` | `d6363dd1d3f51b300ba33363fa078cf164d5aacc48f7e54bcc5c8b2c9115665f` |
| 8 | `n_opws_eligible` | `UNRESOLVED_PENDING_STAGE5_PREFLIGHT` |
| 9 | `n_primary_paired` | `UNRESOLVED_PENDING_STAGE7_ARM_ARTIFACTS` |
| 10 | `ordered_task_ids` | 219 IDs, `saleor-rc-438595033c60` … `saleor-rc-aa2bcdd0c218` |
| 11 | `ordered_task_ids_sha256` | `5972b20d6b08095a555e4c49b9f03703ccd24cfeeabd27c42bcd748cf7cd1364` |
| 12 | `binding_created_at` | `2026-10-20T09:00:19Z` |
| 13 | `protocol_sha256` | `44f18bcad2a80f160646ddd676bca2eb80bd3fc06a1a4925a82e301f025cd767` (16-blob bundle at `9038df3e`) |

Binding self-hash: `d4e1a4aad4b4055641f99d9ce4aa97727c4eea5251aebebf7ef21ded749601b6`.

**Fields 8 and 9 are tokens, not numbers.** Producing an integer would require the
STAGE_5 preflight and STAGE_7 arm-artifact validation that Phase 0/1 is forbidden to run.
They are never reported as `0` or `219`.

## 2. Ordered task hash

```
recipe: sha256(utf8(json.dumps(ordered_task_ids, separators=(",", ":"))))
order : unit-major expansion of the frozen 144-unit READY census
        (unit order = R4_I6 census; member order = readiness member_task_ids)
value : 5972b20d6b08095a555e4c49b9f03703ccd24cfeeabd27c42bcd748cf7cd1364
```

The frozen unit-level hash `8eb4a7242e12bb03715adac5fffdea2e4340585843fc137ececd38952ad6a19e`
is reproduced by the same recipe over the 144 **unit** IDs and is explicitly not reused. The
build fails closed if the two hashes ever coincide.

## 3. Population and eligibility funnel

Population is 144 units → 219 unique tasks. `per_task_v2.jsonl` has one extra record
(`saleor-rc-f76d0093b450`) that is the single adapter-unresolved task and is outside the
219-task READY population.

| Stage | true | false | unresolved | Meaning |
|---|---:|---:|---:|---|
| 1 `in_universe` | 219 | 0 | 0 | all 219 present in `wp1b_main_297_manifest.json` |
| 2 `test_evidence` | 83 | 136 | 0 | frozen F2P count > 0 (71 classification `BEHAVIORAL_F2P` + 12 symbol-absence-only `NOT_PRIMARY`; 5 tasks carry both classes; 71 `PRIMARY_BEHAVIORAL_F2P_ELIGIBLE`) |
| 3 `behavior_contract` | 219 | 0 | 0 | adapter resolved + deterministic test command + E1 boundary |
| 4 `env_ready` | 219 | 0 | 0 | all units `readiness_verdict=READY` |
| 5 `behavior_executable` | 0 | 0 | 219 | requires OPWS worktree preflight — not run |
| 6 `opws_eligible` | 0 | 136 | 83 | 136 definitively fail stage 2; 83 pending stage 5 |
| 7 `primary_paired_eligible` | 0 | 136 | 83 | pending stage 5 + RM_CSS/AGENT/GOLD artifacts |

**ENV_READY = 219 is not OPWS_ELIGIBLE = 219.** No task is currently confirmed eligible.
The largest possible eligible set is 83, the F2P-positive set.

## 4. Environment-id proposal

```
ENVIRONMENT_ID = sha256(utf8(compact_json([
    immutable_image_id,            # per-pair pinned digest
    deterministic_binding_hash,    # 5169c69d45f0761c85792ec182c9e949f58d8c9f5a29355d5a371944293d2ef2
    environment_fingerprint        # per-task provenance fingerprint
])))
```

- 219 task records → **131 distinct** environment IDs (51 environments shared by ≥2 tasks).
  This is correct: environment identity is deliberately task-independent; the frozen dedup
  tuple still carries `TASK_ID` separately.
- Status: `PROPOSED_PENDING_OWNER_CONFIRMATION` at Phase-1 build time; **owner decision B2 (2026-10-20) conditionally approved the recipe → `OWNER_APPROVED_CONDITIONAL_GATES_PASS`** (see `OPWS_P2A_OWNER_DECISIONS_2026-10-20.md`).

## 5. Behavior contract manifest

219 per-task contracts, each with adapter resolution, target/parent commits, deterministic
test command, E1 boundary hash, frozen F2P counts/classes, and the P2P-S/P2P-U preservation
definition. Every contract carries its own `contract_sha256`; the manifest carries
`manifest_sha256`.

F2P node identities are bound as a **rule**, not as stored IDs:
`frozen evaluator node records with v3_class ∈ {BEHAVIORAL_F2P, SYMBOL_ABSENCE_F2P}`,
fail-closed when `len(node_set) < frozen_count` — exactly `scripts/wp2_m17_contract.py`.
The quantitative claim "9/219 tasks have stored node_records; 78 F2P-positive tasks lack them" is **UNVERIFIED_SOURCE_COUNT**:
the `per_task_v2.jsonl` has no top-level `node_records`, and `harness_v3` artifacts cover a disjoint task set.
The evaluation-time rule stands; bind-time stored-ID reading is not supported by frozen evidence. Recorded as blocker B3.

## 6. Blockers (exact)

| ID | Class | Detail | Owner action |
|---|---|---|---|
| B1 | missing execution | STAGE_5 requires an OPWS worktree patch/eval dry preflight | authorize Phase 3 |
| B2 | owner decision | `ENVIRONMENT_ID` serialization is undefined in the frozen protocol | **RESOLVED** — owner decision B2 (2026-10-20): recipe approved conditional on gates, `OWNER_APPROVED_CONDITIONAL_GATES_PASS` |
| B3 | owner confirmation | F2P node identities as evaluation-time rule vs stored IDs | confirm the rule |
| B4 | owner confirmation | `protocol_sha256` = 16-blob bundle hash vs tag-peel commit id | confirm the definition |
| B5 | resource risk | C: 30.9 GiB free; 11 immutable images must fit before any arm run | free ≥40 GiB or relocate the Docker data root to D: |

B1–B4 do not invalidate the artifacts; they prevent treating them as a final immutable
binding. B5 is a Phase 3 prerequisite.

## 7. Costed plan for Phases 2–5 (estimates, not commitments)

**Cost basis measured from frozen evidence:** the 83 F2P-positive tasks have
`Σ wall_s = 12.53 h` for one target+parent evaluation per task (mean 543.7 s, median
424.8 s, max 3599.4 s). Overhead factor 1.25–1.40 for materialization, patch apply, image
pulls, orchestration.

| Phase | Work | Engineering | Container compute | API cost |
|---|---|---|---:|---:|
| P2 | resolve B2–B4; re-emit binding with fixed serialization; finalize ordered-ID hash; re-run determinism gate | 0.5 d | 0 h | $0 |
| P3 | STAGE_5 preflight executor: OPWS patch application + behavior/preservation contract dry run on a small frozen sample; close B5 | 2–3 d | 2–4 h | $0 |
| P4 | full arm evaluation, chunked/resumable. Primary pair (RM_CSS, AGENT): 25.1 h raw → **31–35 h**. Upper bound all 12 arms (no dedup): 150.4 h raw → **188–211 h**. Physical dedup by `(TASK_ID, SCOPE_HASH, REFERENCE_PATCH_HASH, TEST_CONTRACT_HASH, ENVIRONMENT_ID)` reduces this; the exact unique-scope count is a P3 output, so the range stays until then. | 1 d + supervision | 31–35 h (primary) / 188–211 h (upper bound) | $0 |
| P5 | finalize `n_opws_eligible` / `n_primary_paired`, task-by-task gap reasons, review card, evidence audit, LIVE_STATUS update | 1–2 d | 0 h | $0 |

- **Total engineering:** 4.5–6.5 days.
- **Total container compute:** 33–39 h for the primary pair; up to 190–215 h for the full
  12-arm upper bound before dedup.
- **Model/API spend: $0.** Arms consume frozen prediction artifacts; this instrument never
  generates code and never calls a model.
- **Wall-clock** depends on concurrency; at 4 parallel containers the primary pair is
  roughly 8–10 h and the undeduped 12-arm upper bound roughly 47–53 h.

Chunking rule for P4: `--max-items N --resume`, one chunk per tool call, ≤45 min per call,
progress persisted after every chunk.

## 8. Verification performed

| Check | Result |
|---|---|
| `ruff check scripts/opws_build.py tests/unit/opws/test_opws_phase1_build.py` | PASS (0 findings) |
| `pytest tests/unit/opws/test_opws_phase1_build.py -q` | **18 passed** in 6.16 s |
| `python scripts/opws_build.py --check --created-at …` | `all_identical=true`, 7 artifacts |
| Frozen protocol validator (clean tree of `9038df3e`) | `OPWS_PROTOCOL_R1_VALIDATION=PASS`, exit 0 |
| `pytest tests/unit/wp2/test_opws_protocol_r1.py -q` (same tree) | **41 passed** in 8.58 s |
| Frozen inputs re-hashed before/after build | identical (9/9) |
| `git status --porcelain` | only additive untracked paths |

The HEAD baseline `pytest tests/unit/wp2/m17` result (103 passed / 7 failed) is recorded in
`PHASE0_GATE.json` as a pre-existing external frozen-cache defect and is not attributed to
or repaired by this mission.
