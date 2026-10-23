# OPWS R1.1 Additive Evidence Addendum — C2 JUnit Node Recovery (2026-10-23)

**Status: PROPOSED EVIDENCE ONLY; SCIENTIFIC POPULATION DECISION PENDING.** This additive record does not change frozen R1/R1.1/R2, MAIN297 predictions, existing TEST_CONTRACT_HASH values, or the 219-task population. No new OPWS behavioral outcomes have been observed.

## Evidence and reproduction

- C2 V2 historical JUnit: 1,801 XML files (46,218,654 bytes), 166 distinct parent/target directories for 83 F2P-positive tasks. Every directory uniquely matched the historical manifest on file count and total bytes. All copied file SHA-256 values matched the WSL probe; archive evidence manifest SHA-256: `39ea5470625188a4357575f971842676d32a3ee811874d256f7978e1989b3647`.
- Raw XML remains at `D:\WP2\evidence\C2_MAIN83_JUNIT_RESCUE_2026-10-23` and original WSL source. This Git commit stores a file-hash manifest, NOT the raw XML. A separate independent backup is necessary for long-term preservation.
- Frozen classifier file SHA-256 (`oracle_semantics_v2.py`, normalized line endings): `aa85f4953bea36974b77340c38fe8219e5a8d577d5e786ff74c06de2fc07423d`; the later Git file content matches that pin. Both historical classifier bundle hash calculations reproduced their recorded values (`b11374fe...` original, `7bdbf714...` revised). Historical Git chronology and original-run provenance are distinct evidence dimensions.
- Historical as-executed replay: frozen `parse_junit_with_failures`, last-write-wins `run_state_in_container` merging, and `classify_node_v2` with the last scalar outcome replicated 3 times. All 83 tasks matched all seven frozen category counts and `n_nodes`; 17 known node identities across five qualification tasks matched exactly.
- Historical recovered 795 F2P nodes: 731 `BEHAVIORAL_F2P` and 64 `SYMBOL_ABSENCE_F2P`. `OPWS_F2P_NODE_CONTRACT_83.json` has byte SHA-256 `df1e087b199277cc56c42fdfd182f85fcd3faf0c74f4701d5add80b52866f124`; its schema-specific aggregate identity hash is `add7853bc80ba1af2d8554b4df19f1170f1724bc80824573c979baadeeba3254`. The independent reviewer used a different canonical identity recipe with aggregate `24a15405...`; these hashes are not interchangeable.

## Construct-validity discrepancies

- Historical implementation overwrote earlier run outcomes and then repeated the final value. Replaying the actual three recorded run outcomes changes 27 classifications across THREE tasks: 25 historical F2P to `FLAKY` in `saleor-rc-05bdc7feb9ac`; one `P2P_ONLY` to `FLAKY` in each of `saleor-rc-032b98afff20` and `saleor-rc-30b4edece5aa`.
- Strict-three-run F2P totals: 707 behavioral and 63 symbol-absence = 770 nodes. Only ONE task loses F2P eligibility; primary behavioral population becomes 70 rather than historical 71, extended F2P-positive population 82 rather than 83. No reverse eligibility change was observed in these recovered records; this is not a general impossibility claim.
- Historical `FLAKY` labels do not all mean temporal variation. Among 987 historical FLAKY nodes, 957 have scalar `(target=passed, parent=missing)`.
- The recovered 83-task contract binds HISTORICAL AS-EXECUTED node sets, not the strict-770 node sets. A strict-primary evaluator requires separately frozen strict exact node lists and hashes, grounded in `OPWS_F2P_THREE_RUN_SENSITIVITY_83.json`.

## Decision and execution gates

- Scientific confirmatory-primary choice is NOT made by this evidence commit. Proposed options: (A) historical 71 primary / strict 70 sensitivity; or (B) strict 70 primary / historical 71 sensitivity. Recommend B for construct validity, subject to prospective owner/supervisor signoff before any OPWS behavioral run.
- Do not silently change historical R1.1 identities or counts, and do not turn historical F2P classification into a claim about any OPWS behavioral outcome.
- OPWS evaluator must validate exact, typed node-ID set equality (including parameter IDs), provenance, and canonical identity hashes for each task and use the same nodes across all arms. An old lower-bound node count check is insufficient. Exactly which primary protocol applies must be frozen before negative/reference pilots.
- The 136 zero-F2P tasks remain zero under historical counts; these are not automatically behaviorally sufficient or newly validated.
