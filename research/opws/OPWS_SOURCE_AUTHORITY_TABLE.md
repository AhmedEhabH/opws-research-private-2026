# OPWS R1 — Source Authority Table (Phase 0.2 / 0.8)

- **Mission:** M17 OPWS R1 experimental-instrument construction
- **Date:** 2026-10-20
- **Scope of this table:** Phase 0 (fail-closed preflight) and Phase 1 (immutable input bindings) only
- **Execution identity:** branch `parallel/opws-instrument-build-2026-10-20`, HEAD `315612639020c8a5d3102fb86d33230422bd66f5`, `origin/main` `1661ec215ede6ae96e82735148db4febffb21580`

## 1. Authority precedence (highest first)

1. The current mission prompt (Phase 0/1 scope, prohibitions, fail-closed rules).
2. The frozen OPWS R1 protocol at tag `m17-opws-protocol-r1-frozen-2026-10-12`.
3. Frozen Full-D7 scientific evidence at tag `m17-d7-r4-scientific-full144-successor-pass-2026-10-17`.
4. Frozen M17 design freeze / resource contract / contract scripts.
5. Historical notebooks, agents, and narrative documents (context only, never authority).
6. Repository instruction files (`AGENTS.md`) where they do not conflict with 1–4.

Where any two disagree, the higher entry wins and the disagreement is recorded in §4. No
`UNKNOWN` is ever promoted to `PASS`.

## 2. Operative authorities

| ID | Artifact | Ref | SHA-256 / identity | Role | Mutability |
|---|---|---|---|---|---|
| A1 | OPWS protocol freeze (16 files) | tag `m17-opws-protocol-r1-frozen-2026-10-12` → tag object `63ff392b92cacf5d274cfe1823275ff3bba90af7` → commit `9038df3ea80d7d478c2f949b2d3fae75754bb6e1` | bundle `44f18bcad2a80f160646ddd676bca2eb80bd3fc06a1a4925a82e301f025cd767` | eligibility funnel, arm registry, dedup, outcome taxonomy, binding schema | frozen; read-only via git objects |
| A2 | Full-D7 evidence tag | tag `m17-d7-r4-scientific-full144-successor-pass-2026-10-17` → tag object `1dfc907361b5fb51b50e97448ce62079989f39f6` → commit `0fea61c799b3b3ded9d0c74a0a20ea3535d103c1` | see A3–A5 | released Full-D7 evidence identity | frozen |
| A3 | Full-D7 READY population | `research/env-canon-r4/R4_FULL144_READINESS_MANIFEST.json` | `3381788cad3f1f2dc45ec269ce3a4ac7219d69714995a53948f0fa9a0d64b4e2` | 144 units, `readiness_verdict=READY`, `member_task_ids`, `immutable_image_id` | frozen |
| A4 | Full-D7 census (unit order + task readiness) | `research/env-canon-r4/R4_I6_CORRECTED_ZERO_CONTAINER_CENSUS_144.json` | `f60668f88b42d8f7aebb6671dba97d705dc8d2bfbed4046ff7e4332361ec9240`; population identity `ce51d2ec0eb28f6b720fbab13a852618e2de0f0a1111a3cc19dc64b1d19defac` | canonical unit order; `per_member_task_readiness.commit_ready=219` | frozen |
| A5 | Runtime/image binding | `research/env-canon-r4/R4_EXECUTION_IMAGE_BINDING_RUNTIME_CLEAN.json` | `fa4776d850cbc6b4aafcaaeea51b711cfe1081689803e5c69427386f246d7ce7`; binding hash `5169c69d45f0761c85792ec182c9e949f58d8c9f5a29355d5a371944293d2ef2` | 11 (docker, native) pairs → immutable image digest | frozen; **not** a population identity |
| A6 | Full-D7 scientific result | `research/env-canon-r4/R4_SCIENTIFIC_FULL144_SUCCESSOR_RESULT_2026-10-17.json` | `22a30f94b11e7b864d2efcf356738e65c3da5d1a792f4030b3c18f6d4d58977d` | 144/144 PASS; unit-order hash `8eb4a724…` | frozen |
| A7 | M17 design freeze | `research/wp2/m17_v1/m17_design_freeze_v1.json` | `7d10074f071a1ed458e8c943dad7a0b06be0bce44a2aee3e3bd9a8437a8957fd` | frame 220, pool gate `n_READY>=40`, frozen input SHA map | frozen |
| A8 | M17 resource contract | `research/wp2/m17_v1/m17_resource_contract.json` | `19924f6484cf7833f78cf490d7b1090dbc65c32a3bc57ee6f8fdce3f7da1d57f` | disk gates: C: <25 GiB warn, <20 GiB hard hold | frozen |
| A9 | Per-task F2P / provenance | `research/wp2/oracle_confirmation_linux_v2_2026-09-23/per_task_v2.jsonl` | `7fdeeb936ea84e7ef47a461e940671ee628114d9a1d960f29a0be008eddce021` | 220 records; frozen F2P counts, eligibility, `environment_fingerprint` | frozen |
| A10 | MAIN_297 census | `research/wp2/wp2_saleor_main297_census_2026-09-22.json` | `6146237d353376632d729e159761470b46fc5eb300fa9def971d5faf7b1f60c0` | deterministic `test_command`, parent/target commits | frozen |
| A11 | MAIN_297 manifest | `research/wp1b/wp1b_main_297_manifest.json` | `d858316667c4a3e28f7bf759001dc1fd8746b93c710592ff646f3f91584811eb` | STAGE_1 frozen task universe (297 IDs) | frozen |
| A12 | Adapter report | `research/wp2/m17_v1/adapter/adapter_report.json` | `2b0eeddd9ebdbc7ba6768f47ceafdf7578e313a4cfb483d4a471da258652a0f8` | `main_resolved=219`, `main_unresolved=1` (`saleor-rc-f76d0093b450`) | frozen |
| A13 | E1 evaluator boundary | `scripts/wp2_m14a_evalcore_e1.py` | `c0f7dc7deaa5af187d6828b53a7fef95253ba97a9fa5602c0d4e42e34ef3f093` | `evaluate_state_e1` | frozen |
| A14 | F2P/P2P contract logic | `scripts/wp2_m17_contract.py` | tracked at HEAD | `f2p_node_set_from_frozen`, `task_resolvable`, terminal vocabulary | frozen |
| A15 | Population identity helpers | `src/benchmark/wp2/full144/population.py` | tracked at HEAD | `ordered_unit_ids()`, `ordered_membership_hash()`, `EXPECTED_*` | frozen |
| A16 | Arm registry | protocol `OPWS_ARM_REGISTRY_R1.json` | inside A1 | frozen order and seed | frozen |

### Frozen arm order and seed (A16)

`RM_CSS, AGENT, AGENTLESS_STYLE_ADAPTATION, SIP, DENSE_K3, DENSE_K10, BM25_K3, BM25_K10,
BM25_TO_CIA_1HOP, SELECT_ALL, RANDOM_SIZE_MATCHED_RM_CSS, GOLD` — `RANDOM_SEED = 20261012`;
RQ6 is `DESIGN_ONLY`.

## 3. Provenance of the protocol authority

The protocol is **not** present in the HEAD tree. It exists in a separate commit lineage:

```
git cat-file -t a117edae1c3c3365ed3f630738c1329a6494e82f  -> commit
git merge-base --is-ancestor a117edae1c3c3365ed3f630738c1329a6494e82f HEAD  -> rc=1
git ls-tree --name-only HEAD research/  -> research/opws   (no research/opws-protocol-r1)
git ls-tree -r --name-only 9038df3e -- research/opws-protocol-r1/  -> 16 files
```

Consequences, applied throughout Phase 0/1:

- Protocol files are read with `git cat-file blob 9038df3e:<path>`, never copied into HEAD and
  never re-frozen.
- The frozen validator `scripts/opws_protocol_r1_validate.py` is run only in a clean,
  throwaway materialization of `a117edae…` (it asserts `git status --short` cleanliness of
  protected docs). Current HEAD's tree is not a valid site for that check.

## 4. Recorded conflicts, ambiguities, and resolutions

| # | Conflict / ambiguity | Competing readings | Resolution applied | Status |
|---|---|---|---|---|
| C1 | Disk-hold thresholds | mission text figures vs frozen contract | Frozen `m17_resource_contract.json` + `scripts/wp2_m17_run.py` (`WARN_GIB=25.0`, `HOLD_GIB=20.0`) govern. C: 30.9 GiB free → above warn, no hold. | resolved |
| C2 | Population size | 144 vs 219 | 144 = validation **units**; 219 = mapped **tasks**. Binding is task-level (`n_env_ready=219`). | resolved |
| C3 | Order hash | `8eb4a724…` vs a task hash | `8eb4a724…` is over the 144 ordered unit IDs and is explicitly *not* reused. New task-level hash `5972b20d…` over the 219 IDs. | resolved |
| C4 | Protocol at HEAD | present in a heritage commit, absent at HEAD | Treated as frozen read-only authority via git objects; no reconstruction at HEAD. | resolved |
| C5 | `ENVIRONMENT_ID` serialization | protocol names the field but defines no recipe | Proposed: `sha256(compact_json([immutable_image_id, deterministic_binding_hash, environment_fingerprint]))`. Recorded as `PROPOSED_PENDING_OWNER_CONFIRMATION` at Phase-1 build; owner decision B2 (2026-10-20) conditionally approved the recipe as frozen → `OWNER_APPROVED_CONDITIONAL_GATES_PASS`. See `OPWS_P2A_OWNER_DECISIONS_2026-10-20.md`. | resolved (2026-10-20) |
| C6 | F2P node identities at binding | bind stored node IDs vs resolve at evaluation | Frozen `wp2_m17_contract.py` resolves node records **at evaluation** and fail-closes when `len(node_set) < frozen_count`. Rule approved via owner decision B3; quantitative "9/219 / 78" claim is `UNVERIFIED_SOURCE_COUNT` and retracted. See `OPWS_P2A_OWNER_DECISIONS_2026-10-20.md`. | resolved (2026-10-20, numbers retracted) |
| C7 | `protocol_sha256` definition | "sha256 of the released freeze" vs tag-peel commit hash | Instrument defines a bundle hash over the 16 blobs (`44f18bca…`) **and** records tag object + commit. Tag-peel commit is not a SHA-256 of content. Owner decision B4 confirmed the bundle-hash reading (`OWNER_APPROVED_CLARIFIED_IN_MEMO`). See `OPWS_P2A_OWNER_DECISIONS_2026-10-20.md`. | resolved (2026-10-20) |
| C8 | "READY population file" | readiness manifest vs census | Readiness manifest bound as `full_d7_ready_population_file`; census bound as order/identity authority. They agree on all 144 units and 219 tasks. | resolved (instrument choice) |
| C9 | `n_opws_eligible`, `n_primary_paired` | must be numbers | Not derivable in Phase 0/1 (STAGE_5 preflight and STAGE_7 arm artifacts require execution). Emitted as `UNRESOLVED_*` tokens, never guessed. | **open** |
| C10 | `binding_created_at` | deterministic vs wall-clock | Injected via `--created-at`; the twice-build gate uses a fixed value, so byte equality is meaningful. | resolved |
| C11 | Per-task `test_command` in `per_task_v2` | inventory claims it is there | It is **not** in `per_task_v2.jsonl`. Bound from `wp2_saleor_main297_census_2026-09-22.json` instead (219/219 non-null). | resolved (source corrected) |
| C12 | Adapter per-task resolution | report carries only counts | `main_resolved=219` + exactly one named unresolved task; per-task resolution derived as `task != unresolved_id`, verified 219/219. | resolved |

## 5. Non-authorities

- `*_GAP_INVENTORY`, `*_HANDOFF`, notebooks, `DECISIONS.md`, `TODO.md`, prompt summaries: planning
  context only. Where they disagree with A1–A16, A1–A16 win.
- Any observed OPWS outcome: never an authority for eligibility, ordering, or selection.
- Gold patches / selector outputs: never used to populate any field in Phase 0/1.

## 6. Prohibited operations observed in Phase 0/1

No OPWS execution, no model API calls, no selector retraining/rethresholding, no population
resizing, no frozen-artifact replacement/move, no push/merge/tag, no Full144 rerun, no secret
exfiltration.
