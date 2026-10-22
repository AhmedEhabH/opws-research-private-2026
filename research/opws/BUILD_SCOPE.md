# OPWS R1 — Build Scope (Phase 0 / Phase 1)

- **Mission:** M17 OPWS R1 experimental-instrument construction
- **Date:** 2026-10-20
- **Base:** branch `parallel/opws-instrument-build-2026-10-20`, HEAD `315612639020c8a5d3102fb86d33230422bd66f5`
- **Character:** record-only instrument construction. No scientific OPWS outcome is produced or implied.

## 1. In scope (built here)

| Item | Path | Nature |
|---|---|---|
| Deterministic builder (read-only over frozen evidence) | `scripts/opws_build.py` | additive, new |
| Phase 0/1 verification suite (18 tests) | `tests/unit/opws/test_opws_phase1_build.py` | additive, new |
| Source authority table | `research/opws/OPWS_SOURCE_AUTHORITY_TABLE.md` | additive, new |
| Phase 0 gate record | `research/opws/PHASE0_GATE.json` | additive, new |
| Build scope (this file) | `research/opws/BUILD_SCOPE.md` | additive, new |
| Phase 1 result memo | `research/opws/PHASE1_RESULT.md` | additive, new |
| Ready-population artifact | `research/opws/binding/OPWS_READY_POPULATION_219.json` | generated, new |
| Ordered task IDs + hash | `research/opws/binding/OPWS_ORDERED_TASK_IDS.json` | generated, new |
| Environment-id proposal | `research/opws/binding/OPWS_ENVIRONMENT_ID_PROPOSAL.json` | generated, new |
| Behavior contract manifest | `research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json` | generated, new |
| Eligibility funnel manifest | `research/opws/binding/OPWS_ELIGIBILITY_FUNNEL_219.json` | generated, new |
| 13-field draft binding | `research/opws/binding/OPWS_POPULATION_BINDING_R1.json` | generated, new |
| Binding status / blockers | `research/opws/binding/OPWS_POPULATION_BINDING_STATUS.json` | generated, new |
| Twice-built determinism gate | `research/opws/binding/OPWS_BUILD_DETERMINISM.json` | generated, new |

Nothing pre-existing is modified. `git status --porcelain` shows only these additive paths.

## 2. Out of scope (not started)

- Phase 2: zero-outcome scope/dedup physical plan (population binding finalization after owner decisions; any protocol re-freeze).
- Phase 3: evaluator engine (STAGE_5 OPWS worktree dry preflight / behavior-contract executability).
- Phase 4: technical tests/freeze (any arm execution, 12-arm population, RM_CSS vs AGENT, GOLD / SELECT_ALL diagnostics).
- Phase 5: handoff/STOP (STAGE_7 paired eligibility, outcome aggregation, analysis).

**Real science requires separate owner approval; the above phases are not authorized in this session.**

Explicitly not performed: OPWS execution, Full144 rerun, model API calls, selector
retraining/rethresholding, generated code or repair, Agent rerun, population resizing,
frozen-artifact replacement/move, push/merge/tag, secret handling.

## 3. Generated artifact inventory (as built at `2026-10-20T09:00:19Z`)

File SHA-256 is over the exact on-disk bytes. "Internal hash" is the artifact's own
canonical content hash where it carries one.

| Artifact | Bytes | File SHA-256 | Internal hash |
|---|---:|---|---|
| `OPWS_READY_POPULATION_219.json` | 185,468 | `85bc90e0668f02ea485acae3549e7e5ae1528df9f62f3a55df6a56dcc522ebbb` | — |
| `OPWS_ORDERED_TASK_IDS.json` | 7,358 | `9cb18a3eceb849cef7edda42655a910c4bfe00c727767f77773c49fa4bfe3b8f` | `ordered_task_ids_sha256=5972b20d6b08095a555e4c49b9f03703ccd24cfeeabd27c42bcd748cf7cd1364` |
| `OPWS_ENVIRONMENT_ID_PROPOSAL.json` | 127,378 | `94859d48e7040547d1cc92fc6868056246b4082d302cc47052059dfd58bac2cc` | — |
| `OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json` | 435,224 | `5bd64af020caae5cca495aad31221411f87f347841a728452a0a2d3ee63cd064` | `manifest_sha256=d6363dd1d3f51b300ba33363fa078cf164d5aacc48f7e54bcc5c8b2c9115665f` |
| `OPWS_ELIGIBILITY_FUNNEL_219.json` | 106,918 | `25c278113a94841ad75a7f23de02247d183da3393ef907b3edaff0bc0f9570f1` | `manifest_sha256` (canonical) |
| `OPWS_POPULATION_BINDING_R1.json` | 7,535 | `91ba96f7a721cf23aa33ba73bafe86754c46714f36e70ca0eeb8928de7bbd42f` | exactly 13 fields |
| `OPWS_POPULATION_BINDING_STATUS.json` | 6,436 | `f631019a04ca61a141e353a0e6f5627660a8150c81ebb039abf20780be307428` | `binding_self_sha256=d4e1a4aad4b4055641f99d9ce4aa97727c4eea5251aebebf7ef21ded749601b6` |
| `OPWS_BUILD_DETERMINISM.json` | 2,054 | `d036b3caeca6d913777cf48333db6f7429a43c902e90cc567e7ec6700dcf721a` | `all_identical=true` |

Rebuilding with a different `--created-at` changes `binding_created_at`, the binding file
hash, the status self-hash, and the determinism file — nothing else. With the same
`--created-at` the build is byte-identical (verified).

## 4. Reproduction

```powershell
# Determinism gate only (writes nothing; exits non-zero if bytes differ)
C:\Users\Ahmed\AppData\Local\anaconda3\python.exe scripts/opws_build.py --check --created-at 2026-10-20T09:00:19Z

# Rebuild into research/opws/binding
C:\Users\Ahmed\AppData\Local\anaconda3\python.exe scripts/opws_build.py --created-at 2026-10-20T09:00:19Z

# Phase 1 gates
C:\Users\Ahmed\AppData\Local\anaconda3\python.exe -m pytest tests/unit/opws/test_opws_phase1_build.py -q
```

Protocol validator (frozen, must be run in a clean materialization of
`9038df3e`/`a117edae`, not at HEAD):

```powershell
git -C C:\Users\Ahmed\AppData\Local\Temp\opencode\m17_phase0_full status --short
C:\Users\Ahmed\AppData\Local\anaconda3\python.exe scripts/opws_protocol_r1_validate.py
# -> OPWS_PROTOCOL_R1_VALIDATION=PASS, exit 0
```

## 5. Frozen inputs (verified untouched by the build)

| Input | SHA-256 |
|---|---|
| `research/env-canon-r4/R4_FULL144_READINESS_MANIFEST.json` | `3381788cad3f1f2dc45ec269ce3a4ac7219d69714995a53948f0fa9a0d64b4e2` |
| `research/env-canon-r4/R4_I6_CORRECTED_ZERO_CONTAINER_CENSUS_144.json` | `f60668f88b42d8f7aebb6671dba97d705dc8d2bfbed4046ff7e4332361ec9240` |
| `research/env-canon-r4/R4_EXECUTION_IMAGE_BINDING_RUNTIME_CLEAN.json` | `fa4776d850cbc6b4aafcaaeea51b711cfe1081689803e5c69427386f246d7ce7` |
| `research/env-canon-r4/R4_SCIENTIFIC_FULL144_SUCCESSOR_RESULT_2026-10-17.json` | `22a30f94b11e7b864d2efcf356738e65c3da5d1a792f4030b3c18f6d4d58977d` |
| `research/wp2/oracle_confirmation_linux_v2_2026-09-23/per_task_v2.jsonl` | `7fdeeb936ea84e7ef47a461e940671ee628114d9a1d960f29a0be008eddce021` |
| `research/wp2/wp2_saleor_main297_census_2026-09-22.json` | `6146237d353376632d729e159761470b46fc5eb300fa9def971d5faf7b1f60c0` |
| `research/wp2/m17_v1/adapter/adapter_report.json` | `2b0eeddd9ebdbc7ba6768f47ceafdf7578e313a4cfb483d4a471da258652a0f8` |
| `research/wp1b/wp1b_main_297_manifest.json` | `d858316667c4a3e28f7bf759001dc1fd8746b93c710592ff646f3f91584811eb` |
| `scripts/wp2_m14a_evalcore_e1.py` | `c0f7dc7deaa5af187d6828b53a7fef95253ba97a9fa5602c0d4e42e34ef3f093` |

The test suite re-hashes all of these before and after a build and asserts equality.

## 6. Non-claims

- This build does **not** establish that the OPWS instrument is executable.
- It does **not** establish `n_opws_eligible` or `n_primary_paired`.
- It does **not** freeze the environment-id serialization.
- It does **not** validate any arm, selector, gold patch, or scientific outcome.
- The 219 READY tasks are **not** 219 eligible tasks: only 83 have frozen F2P evidence,
  and none has completed the STAGE_5 preflight.
