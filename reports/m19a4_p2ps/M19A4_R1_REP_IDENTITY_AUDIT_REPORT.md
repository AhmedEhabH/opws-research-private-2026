# M19A4-R — P2P Physical-Repetition Identity Audit (supplemental, read-only)

Mission: M19A4-R · Date: 2026-10-24 (local) · Branch:
`parallel/opws-instrument-build-2026-10-20` · HEAD:
`7b93e7555f4851634af489444e0e9670a0acd610`

Status: **CONFIRMED — strict M19A4 P2P_ONLY (9,273) IS physically three
distinct passing repetition indices on both parent and target.** No M19A4
artifact was rewritten. No protocol freeze decision is made here.

---

## 1. Verdict (GO/STOP)

- **GO** — use of the strict P2P_ONLY recovery as a physically-verified
  pass/pass candidate set (9,273 nodes across 83 tasks) is **not** undermined
  by any repetition-identity ambiguity in the C2 MAIN83 evidence.
- The count-based strict rule (`stability_strict`) has a **theoretical
  distinctness gap** (it counts 3 observations without checking rep indices),
  but in this evidence it changes **zero** node identities: B (strict count
  rule) == C (per-repetition stable) exactly.
- **STOP (unchanged)**: the *protocol freeze* question — historical (71
  primary F2P tasks) vs strict (70 primary) as the P2P-S evaluator — still
  requires owner/supervisor signoff, exactly as the original M19A4 STOP report
  stated. This audit does not decide it.

## 2. What was audited / coverage

| Input | Verification |
|---|---|
| Branch / HEAD / 3 untracked paths | HEAD `7b93e755…` and branch match the M19A4 STOP report; exactly the 3 expected untracked paths present at start |
| 6 pinned M19A4 artifacts in `reports/m19a4_p2ps/` | on-disk SHA-256 == STOP report Section 7 pins (all 6 PASS) |
| Evidence manifest `JUNIT_EVIDENCE_MANIFEST.json` | SHA-256 `39ea5470…` == pin |
| 1,801 evidence XML files | full on-disk vs manifest hash scan `full_scan: True`, PASS (from existing `M19A4_VALIDATION_RECEIPT.json`) |
| `OPWS_F2P_NODE_CONTRACT_83.json` | `df1e087b…` == pin |
| `OPWS_F2P_THREE_RUN_SENSITIVITY_83.json` | `62f528b0…` == pin |
| `per_task_v2.jsonl` | `7fdeeb93…` == recorded hash |
| `oracle_confirmation.py` | `4609a225…` == pin |
| `oracle_semantics_v2.py` | pin `aa85f495…` satisfied **only via LF-normalized hashing** (file is CRLF on disk; `loader_variants_contain` checks raw/LF/CRLF variants and Python universal-newline import sees the LF bytes) => pin check legitimately passes |
| Frozen rescue tar `c2_junit_rescue_2026-09-23.tar.gz` | SHA-256 `ebf749c1…` == recorded `.sha256` |
| Evidence-backed test re-run (Python 3.11.9, `M19A4_EVIDENCE_TEST=1`) | 13/13 PASS, `test_real_evidence_aggregates` **executed** (not skipped); reproduced 9275/9273/795/770/27 and aggregate identity `9fc10bc1…` |

## 3. recover_task() distinctness gap (task 3)

`recover_task()` (scripts/opws_m19a4_p2p_s_recover.py) parses every
`{t12}_{state}_r{rep}_f{idx}.xml`, then appends **every** observation into
`runs[node][side]` across all `(state, rep, idx)` fragments. `stability_strict`
classifies STABLE_PASS iff `len(runs)==3` and every value is `"passed"`.
**It never checks that the three observations come from three distinct rep
indices** — e.g., three passed observations all from r0 would be counted as
3/3. Same for the historical merge: last-write-wins over
rep-major/file-minor ordering collapses per-rep duplicates (last wins), so a
duplicate within one rep is invisible historically and counted as separate
observations strictly.

## 4. Read-only diagnosis (task 4) — comparing A / B / C

New diagnostic: `scripts/opws_m19a4_p2p_s_rep_identity_diagnostic.py`
(imports the frozen parser + pins; read-only; writes ONE new artifact).

Definitions:
- **A** — historical P2P_ONLY (last-write-wins merge + `[last]*3`).
- **B** — existing strict P2P_ONLY (the on-disk M19A4 set; recomputation
  cross-checked **node-for-node** against the artifact, STOP if mismatch).
- **C** — per-repetition stable pass on **both** sides: each rep r0/r1/r2
  present (>=1 observation) and every observation in that rep `"passed"`.

Results (83 tasks, 11,284 nodes):

| Metric | Value |
|---|---|
| A (historical P2P_ONLY) | 9,275 |
| B (strict P2P_ONLY) | 9,273 |
| C (per-repetition stable, both sides) | 9,273 |
| **B \ C (strict 3/3 but NOT three distinct passing reps)** | **0 nodes / 0 tasks** |
| C \ B (per-rep stable but outside strict 3/3) | 0 nodes / 0 tasks |
| A \ C (historical but not per-rep stable) | 2 nodes (see §5) |
| Within-rep duplicate observations (same node/side/rep, >1 fragment) | **0** |
| Within-rep conflicting observations (differing outcomes same rep) | **0** |
| Rep-distribution of all 9,273 strict nodes | `t=(1,1,1) p=(1,1,1)` — one observation per rep per side, 100% |

Therefore **B == C exactly**: for every one of the 9,273 strict P2P_ONLY nodes,
the three passing observations are one per distinct repetition on both parent
and target. The count-based rule's gap cannot be exploited on this evidence.

## 5. The 2 historical-only nodes (A \ C) — matches STOP report exactly

From `M19A4_NODE_LEDGER_83.tsv`:

| Task | Node | t_runs | p_runs | A | B | C |
|---|---|---|---|---|---|---|
| `saleor-rc-032b98afff20` | `…test_draft_order_complete_product_without_inventory_tracking` | `passed|passed|passed` | `passed|failed|passed` | P2P_ONLY | FLAKY | no (p rep1 failed) |
| `saleor-rc-30b4edece5aa` | `…test_query_used_gift_card_by_owner` | `failed|passed|passed` | `passed|passed|passed` | P2P_ONLY | FLAKY | no (t rep0 failed) |

These are the exact two nodes in the M19A4 STOP report §4. Under every
"distinct-repetition" reading they are NOT 3/3 — consistent with strict.

## 6. Repetition identity is EXECUTION-attested, not just filename-based (task 7)

- Frozen harness contract (`research/wp2/oracle_confirmation_linux_v2_2026-09-23/harness_v2_freeze_2026-09-23_REVISED.json`,
  git HEAD `493924ef…`): `"execution": {"workers": 1, "early_exit": "DISABLED",
  "stability": "3 target + 3 parent runs"}`.
- The pinned runner `scripts/wp2_linux_dryrun.py::run_state_in_container`
  (on-disk SHA-256 `ad3ef5301a74b67ec7348c2b310b3a467e1607fc7ce6dc2ca8934e8fccb49a9e`
  == harness-freeze harness_files pin) builds, per side:
  `for rep in range(3): for idx, tf in enumerate(test_files):
  pytest ... --junitxml /workspace/{wt}/{tid}_{state}_r{rep}_f{idx}.xml -q {tf}`
  — i.e. the `r0/r1/r2` suffix is minted **at pytest invocation time** (three
  sequential, separate pytest processes per (task, side, test file)), and the
  run script executes all 3×(n_test_files) commands serially.
- Frozen per-task provenance (`per_task_v2.jsonl` records): `"test_command":
  "pytest --ds=saleor.tests.settings --disable-socket --reuse-db (per-file 3x
  per state)"`, with harness commit, timestamps, container digests, env
  fingerprint per task.
- Rescue chain: `copy_and_verify.py` copied `/opt/wp2_v2/c2_artifact_rescue`
  files into the evidence dir **preserving filenames**, with per-file SHA-256
  verification; the frozen repo tar matches its recorded hash; M19A4 verified
  all 1,801 files on disk during generation (`full_scan: True`).

Conclusion: **filename-based identity and execution-level attestation agree**;
r0/r1/r2 are three distinct actual invocations. Caveats (informational, not
evidence gaps): `--reuse-db` means DB state persists across reps within a
(task,state) — reps are distinct invocations but not guaranteed statistically
independent replicates; `junit_sha256: "collected-per-file"` means the task
records deferred per-file hashing to the rescue step (which did hash-verify).

## 7. Adversarial synthetic tests (task 5)

New file `tests/unit/opws/test_opws_m19a4_p2p_s_rep_identity.py` (8 tests,
synthetic XML through the FROZEN parser, offline):

| Case | Result |
|---|---|
| 3 passing observations all from r0 on both sides | NOT 3/3 physically (strict count rule would say 3/3 — gap demonstrated) |
| 1 passing observation per r0/r1/r2 on both sides | IS 3/3 (per-rep stable AND strict P2P_ONLY) |
| missing r1 | fails closed |
| failed r2 | fails closed |
| duplicate conflicting fragments inside r1 | fails closed |
| parent/target mismatch (parent missing r2) | fails closed (not P2P_ONLY) |
| rep_distribution counts | r0-only => (3,0,0); one-per-rep => (1,1,1) |

Preserved original frozen results: no existing M19A4 artifact or test modified.

## 8. Verification performed

- `git diff --check` clean (no tracked changes; repo uncommitted, no new
  tracked modifications).
- Ruff 0.17.0 on all 4 M19A4 Python files (recover + diagnostic + 2 test
  files): **All checks passed**.
- Mypy strict on the new production diagnostic: **Success, no issues**
  (baseline recover script has 10 pre-existing strict errors — scripts/ are
  outside the mypy gate which overrides `tests.*` only).
- `py_compile` on changed files: OK.
- Evidence test re-run (Python 3.11.9, `M19A4_EVIDENCE_TEST=1`):
  13/13 PASS, executes not skips, reproduces 9275/9273/795/770/27 +
  `9fc10bc1…`.
- Adversarial suite: 8/8 PASS.
- Broader smoke `tests/unit/opws/` (whole dir, env set): **180 passed in
  120 s**.
- Untracked-file whitespace audit (explicit; `git diff --check` cannot see
  untracked files): CRLF / TAB / trailing whitespace / missing final newline —
  **clean** on all new and pre-existing untracked Python files + diagnostic
  artifact.

## 9. New artifacts and hashes

| File | SHA-256 |
|---|---|
| `reports/m19a4_p2ps/M19A4_REP_IDENTITY_DIAGNOSTIC.json` | `c7e106bbc601f9f00c06ec4fc75a59a8d476ab32f200812a7b90915871aa55e1` (contains `generated_at_utc`, so timestamp changes per run; identity content deterministic and reproduced 3×) |
| `scripts/opws_m19a4_p2p_s_rep_identity_diagnostic.py` | `c805eeb2177c72b6b9398c542dfd66823a4bfcf3d91541f60beba6c3cd88f7af` |
| `tests/unit/opws/test_opws_m19a4_p2p_s_rep_identity.py` | `a991540ea40e9aaf37955bdb94907c519abb69981a1e1970ca858eea988566d0` |
| `reports/m19a4_p2ps/M19A4_R1_REP_IDENTITY_AUDIT_REPORT.md` | recorded live in the mission STOP report (self-referential; changes with each write, like the M19A4 STOP report §7 note) |

Existing M19A4 artifacts (`M19A4_STOP_GATE_REPORT.md` and the other 6 files)
were **not** modified — their hashes still match the STOP report pins
(verified in §2). The 9,273/9,275/795/770/27 figures are untouched.

## 10. Recommendation & exact next action

- **Recommendation**: GO on strictly-verified P2P-S identity; hardening
  suggestion (cheap, optional): record an explicit per-rep distinctness check
  (one observation per r0/r1/r2, all `passed`, both sides) in the strict
  recipe for the future prospective P2P-S freeze, as defense in depth — it
  changes nothing on this data but closes the count-vs-reps gap in the rule
  itself.
- **Blocked (unchanged, owner-dependent)**: choosing historical-71 vs
  strict-70 as the P2P-S evaluator still requires prospective owner/supervisor
  signoff; DEV-cohort P2P-S freeze artifacts and P2P-U remain out of scope.
- **Exact next action**: post this report for owner review; if signoff on the
  strict (70-primary) evaluator is granted, the existing
  `M19A4_P2P_ONLY_NODES_BY_TASK_83.json` strict set requires **no** identity
  edits (B == C); a prospective protocol freeze would add the rep-distinctness
  rule and re-run to produce a new frozen artifact under a new name, NOT a
  rewrite of M19A4 outputs. No API/model/Saleor/Docker run is required.
