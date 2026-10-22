# OPWS R1 — Phase 3A Result: Executable Patch-Isolation Engine on TOY Fixtures (2026-10-20)

- **Mission:** M17 OPWS R1 — Phase 3A (toy-only executable patch-isolation engine)
- **Character:** additive code + narrow fixes + targeted tests + LIGHT handoff. **No OPWS
  real-commit scientific task executed, no STAGE_5 on real tasks, no 12-arm population run,
  no Docker/WSL, no model/benchmark inference, no observed scientific F2P/P2P result.**
- **Base:** branch `parallel/opws-instrument-build-2026-10-20`, HEAD unchanged
  `315612639020c8a5d3102fb86d33230422bd66f5` (origin/main `1661ec2…` unaffected). No commit/push/tag.

## 1. VERDICT

**PASS (partial — Phase 3A deliverable met in full; scientific population work remains
un-authorizable, as expected).** All Phase-3A gates are green. The following are NOT done
by design and are explicitly deferred to future owner authorization:

- Phase 4 = technical tests / parity / freeze (including RANDOM_SIZE_MATCHED_RM_CSS
  sampling seed 20261012, and real `REFERENCE_PATCH_HASH` materialization).
- Phase 5 = handoff / STOP on real tasks.
- The scientific population run requires independent future authorization.

## 2. What was delivered

### A. Corrected two Phase-2 fail-open boundaries (`scripts/opws_phase2_plan.py`)
1. **Only `RANDOM_SIZE_MATCHED_RM_CSS` may be deferred.** `build_dedup_plan` previously
   caught `BuildError` for *any* arm and silently merged its missing/invalid source into a
   generic UNRESOLVED group (labelled with the RANDOM scope token). Now only the frozen
   RANDOM arm (path `None`, derived at Phase 4, seed 20261012) is deferred; every other arm
   propagates its `BuildError` (fails closed). `build_validation` likewise no longer records
   `SOURCE_MISSING` / `RESOLVE_FAILED` as data; it raises `BuildError` for any non-RANDOM
   missing/invalid source or SELECT_ALL missing universe.
2. **Strict repository-relative scope paths before hashing/use.** Added
   `normalize_scope_path` / `normalize_scope_paths` enforcing: non-empty strings, no absolute
   paths, no drive prefixes, no backslash escape ambiguity, no `.`/`..` traversal or redundant
   components (frozen `no_aliases`), dedupe with duplicate count (frozen `no_duplicates`).
   `compute_canonical_scope_hash` now validates every path first. The empty scope remains a
   valid zero-size scope. **No new science thresholds were invented**; parent-file existence /
   budget / candidate-universe checks were intentionally NOT added in Phase 2 because the
   frozen protocol defers those to patch materialization (Phase 3/4) and Phase 2 is a
   zero-outcome read-only planning stage. (`ORDERING NOTE:` traversal / out-of-universe paths
   are now rejected at scope-hash time by the canonical path rule, which is directly grounded
   in `OPWS_SCOPE_SEMANTICS_R1.json`.)
3. **Historical Phase-2 projections remain PROVISIONAL.** The 2,493 figure is preserved
   exactly as a *provisional scope-level projection*; it is not reported as a finalized
   physical execution count. `REFERENCE_PATCH_HASH` and the RANDOM arm scope hash remain
   `UNRESOLVED_*` tokens (five frozen identity fields not all known yet).
4. **Determinism preserved.** `python scripts/opws_phase2_plan.py --check --created-at
   2026-10-20T10:00:00Z` → `{"all_identical": true, "artifacts": 2}`; existing on-disk Phase-2
   bindings/artifacts were **not overwritten**.

### B. Toy-only scoped patch engine (`scripts/opws_toy_engine.py`, new)
- Separate, importable, **TOY-ONLY** engine with CLI accepting only `--toy-fixture <path>`
  and `--dry-run` (plus `--out-dir` for receipts). **No real-population run mode exists.**
- Operates on synthetic in-memory repo snapshots + patches; never reads/applies a MAIN297 /
  reference-target patch.
- Enforces the editable-file scope at path and content level; raises explicit
  instrumentation / patch-application error classes (subclasses of `ToyEngineError`):
  `ScopePathInvalidError`, `OutOfScopeWriteError`, `MissingFileError`, `SymlinkEscapeError`,
  `PatchConflictError` (fuzz/unexpected context), `AmbiguousPatchError`, `FixtureError`.
- Deterministic receipts: input hashes, `allowed_scope_hash`, file changes, error class,
  `TOY_ONLY=true`, `SCIENTIFIC_OUTCOME_COUNT=0`. No true F2P/P2P passing outcome is produced.
- **Reuse decision:** the frozen M15-R/M14-R engines operate on the real Saleor repo through
  WSL/Docker + git objects and expose no portable helper for arbitrary synthetic snapshots, so
  they were intentionally NOT reused and their frozen outputs were never touched. Only the
  frozen OPWS canonical scope-path / scope-hash convention (`opws_phase2_plan`) is reused for
  the scope hash — a deliberate, documented isolated implementation.

## 3. Tests (targeted only)

| Area | Result |
|---|---|
| `tests/unit/opws/test_opws_phase2_plan.py` (28 → 47, incl. new A.1/A.2 guards) | **47 passed** |
| `tests/unit/opws/test_opws_toy_engine.py` (14, new) | **14 passed** |
| `tests/unit/opws/test_opws_phase1_build.py` (regression) | **18 passed** |
| `ruff check` on both scripts + both test modules | 0 findings |
| `mypy --strict scripts/opws_phase2_plan.py` | no issues |
| `mypy --strict scripts/opws_toy_engine.py` | no issues |
| `py_compile scripts/opws_phase2_plan.py scripts/opws_toy_engine.py` | OK |
| `git diff --check` | clean (tracked scope); all changes are untracked new paths |
| Dual-module mypy | Running both files in one mypy invocation hits the pre-existing
  `scripts/<name>` vs `<name>` double-module collision (no `scripts/__init__.py`); each file
  passes strict mypy independently. |

**New negative coverage:** missing non-RANDOM arm source (dedup plan + validation);
malformed per-task source fixture with a traversal path; traversal `../`; absolute `/…`,
drive `C:/…`, backslash `saleor\…`, empty path, `a/./b`, `a//b`; duplicate-alias set;
out-of-scope write; symlink escape; patch fuzz/context mismatch; ambiguous multi-location;
missing file; non-list scope; deterministic double build; CLI dry-run vs write; unsupported
CLI option rejected.

## 4. TOY-ONLY enforcement (audit trail)

- CLI exposes ONLY `--toy-fixture`, `--dry-run`, `--out-dir`; `--population` (and any unknown
  option) is rejected (argparse exit non-zero).
- The engine reads synthetic JSON fixtures only; it never opens real repositories, never
  invokes the M15-R/M14-R engines, never calls a model, never uses Docker/WSL, and never
  materializes a git diff.
- Every receipt carries `TOY_ONLY=true` and `SCIENTIFIC_OUTCOME_COUNT=0`.
- F2P/P2P appear only as empty placeholder tokens in documentation; the engine never emits a
  behavior/preservation conclusion.

## 5. How to run the toy demo

```
python scripts/opws_toy_engine.py --toy-fixture research/opws/toy_fixtures/toy_demo_in_scope.json --dry-run
python scripts/opws_toy_engine.py --toy-fixture research/opws/toy_fixtures/toy_demo_in_scope.json --out-dir research/opws/toy_receipts
```

## 6. Unresolved blockers / original Phase-3B owner gate

| Blocker | Owner gate |
|---|---|
| `REFERENCE_PATCH_HASH` needs real git-object scoped-gold-diff materialization | **Phase 3B** (git-object materialization) |
| RANDOM_SIZE_MATCHED_RM_CSS scope hashes (seed 20261012) | **Phase 4** (frozen sampling + parity/freeze) |
| `n_opws_eligible` (STAGE_5 behavior-contract preflight on real tasks) | **Phase 3B** (real STAGE_5) — requires separate authorization |
| Scientific population run (12 arms / e2e) | independent future authorization |

**Original Phase-3B owner gate (unchanged):** STAGE_5 evaluator-engine dry-preflight +
`REFERENCE_PATCH_HASH` materialization. That is real-commit scientific work and is **NOT
authorized in this mission**. Phase 3A stopped here deliberately.

## 7. Verification performed at STOP

- All targeted tests above PASS. No broad suite, no scientific oracle, no STAGE_5, no
  Docker/WSL, no 12-arm evaluation, no dependency downloads were run.
- Branch `parallel/opws-instrument-build-2026-10-20`, HEAD `315612639020c8a5d3102fb86d33230422bd66f5`
  preserved. No commit/push/tag. Frozen artifacts (binding files, Phase-2 jsons, protocol blobs)
  untouched.

## 8. Enumerated new/untracked files (Phase 3A additions)

- `scripts/opws_toy_engine.py`
- `tests/unit/opws/test_opws_toy_engine.py`
- `research/opws/toy_fixtures/toy_demo_in_scope.json`
- `research/opws/toy_receipts/toy_demo_in_scope_toy_receipt.json`
- `research/opws/PHASE3A_RESULT.md` (this memo)
- (modified, still untracked) `scripts/opws_phase2_plan.py`,
  `tests/unit/opws/test_opws_phase2_plan.py`

## 9. Light export (project-light only — no Kaggle/FULL)

Created `project-light-YYYY-MM-DD-HHmm.zip` in the parent directory of `project/`, containing
source, tests and receipts. **Do NOT** upload this to Kaggle; it is a collaboration/session
artifact only. See PROJECT_EXPORT_* block in the STOP report.