# M19A1B_IMPLEMENTATION_ONLY

**Mission:** M19A1B — OPWS Git-tree reconstruction audit (AUTHOR CODE ONLY, Git objects only, no behavioral evaluation).

**HEAD before/after change:** `57d38654b8f8692181c1b774c68939cde6d58140` (branch
`parallel/opws-instrument-build-2026-10-20`, clean worktree verified before edits).

## Implemented (committed)

1. **`scripts/opws_m19a1b_tree_audit.py`** — standalone audit CLI/toolkit:
   - `--repo` (source repo with frozen manifest+census), `--saleor-git` (owner-provided
     read-only Saleor object store, ordinary or bare), `--out` (must be OUTSIDE the
     source repo), `--mode tree|plan|all` (default `tree`), optional
     `--rename-sides-json`, `--min-free-gib` (guard, default 31.0 = 30 GiB + 1 GiB reserve).
   - Tree mode: per bound task loads parent/target SHAs, canonical test-path authority
     from the census `test_file` flags via M19A1A's validator
     (`census_records_to_authority` + materializer completeness/split invariants,
     reused verbatim — fail-closed on missing/inconsistent authority). Reconstructs the
     target tree with an **isolated temp Git index + object store**
     (`GIT_INDEX_FILE`/`GIT_OBJECT_DIRECTORY`/`GIT_ALTERNATE_OBJECT_DIRECTORIES`;
     object dir resolved for clones AND bare repos incl. `objects/info/alternates`;
     no checkout, no writes to the real cache): `git read-tree <parent>` →
     `git apply --cached` COMMON TEST patch exactly once → complete non-test
     FULL_REFERENCE patch (single deterministic `git_diff_bytes` producer) →
     `git write-tree` compared with `git rev-parse <target>^{tree}`; first differing
     path reported via workspace-env `git diff-tree` on mismatch. Empty patches are
     no-ops; deletes, mode changes, zero-byte adds, renames (D+A), no-final-newline
     supported; binary/symlink/submodule/unsupported statuses produce explicit error
     categories. Per-task records: identities, target/reconstructed tree OIDs,
     exact_equal, test/non-test path lists, disjoint+union invariants, census-header
     self-consistency, patch SHA256 + byte counts, error types. Temp files removed in
     `finally`; disk free before/after + peak temp usage recorded.
     Output `FULL_REFERENCE_TREE_RECEIPT_219.json` (schema
     `opws-m19a1b-full-reference-tree-receipt/1.0`). Exit nonzero unless 219/219
     reconstructed exactly AND 219/219 classification reconciled.
     `REAL_TASK_BEHAVIORAL_OUTCOMES=0`.
   - **Split assertion is SEPARATE from tree equality (mission-required):** tree
     equality is recorded as necessary-only; reconciliation additionally requires the
     M19A1A split invariants (`reference_test_free`, census-test equality, disjoint +
     union vs all git changed paths) AND a redundant census-header count check
     (`n_test`/`n_changed`/per-status counts vs per-path flags), so a wrong split fails
     `classification_reconciled=false` even when the final tree matches.
   - **Renames explicit:** git `-M` detection gives old/new path identity; per-side
     TEST flags only from `--rename-sides-json` (M19A1A `rename_sides` protocol);
     boundary crossing records `RENAME_CROSSES_TEST_BOUNDARY` and STOPS the task
     (stays in the 219 denominator; no scientific exclusion coded). Missing side
     authority → `RENAMED_SIDE_AUTHORITY_MISSING` (fail closed). Real census has
     1/219 rename task (`saleor-rc-663543eaf563`) — owner must supply its side table
     in the real run; until then the tool reports it as data, never hides it.
   - Plan mode (`--mode plan`, gated on the tree receipt): resolves the frozen
     per-task prediction sources at their authoritative arm-specific locations
     (R1 registry via `opws_phase2_plan.resolve_arm_scope_lists`; R2 tag
     `m17-comp-baselines-r2-frozen-2026-10-12` peeled `6c2f6981…` recorded for
     BM25/Dense). Per (arm,task) records: predicted scope hash, reference patch
     SHA256, test contract hash (manifest `contract_sha256`), effective reconstructed
     tree OID, validity/error status. Three measures over complete validated records
     only: unique patch-byte SHA; unique effective tree OID; frozen five-field
     physical-execution identity (reused unchanged). Missing frozen source →
     `PREDICTION_SOURCE_MISSING` per-task records + clear plan-mode blocker; no
     deceptive "219/219 12 arms audited" claim (exit 4). `RANDOM_SIZE_MATCHED_RM_CSS`
     recorded DEFERRED (Phase 4) and excluded explicitly.
2. **`tests/unit/opws/test_opws_m19a1b_tree_audit.py`** — 15 synthetic-git tests
   (mission scenarios i–x plus positive plan-counts, bare-repo store, alternates
   store, CLI smoke): identity across modify/delete/add/mode change; zero-byte
   `__init__.py`; no-final-newline; flagged `test_*.py` outside `tests/` (flag
   authority, no filename heuristic); rename within one boundary reconstructs and
   crossing records STOP; wrong test flag fails classification even when tree
   matches; target-tree mismatch reports first differing path; cleanup on failed
   apply with source store refs/index/object store unchanged; hostile global git
   config inert; plan-mode missing frozen arm can never count as completed;
   complete-validated three measures asserted; bare-repo `--saleor-git`;
   `objects/info/alternates`-served store; end-to-end CLI `--mode tree`.

## Test evidence

- `py -3.11 -m pytest tests/unit/opws/ -q` → **156 passed** (141 pre-existing + 15 new; none weakened).
- `ruff check` on both changed files: pass. `mypy --strict` on the new script: pass
  (0 issues). `py_compile` both files: pass. `git diff --check`: pass.
- No Saleor store touched, no network/dependency/Docker/WSL/pytest-from-real-Saleor;
  no real-task claims; `REAL_TASK_BEHAVIORAL_OUTCOMES=0`.

## Blocked / owner-only parts (real-runnable code is complete)

- The **real 219-task audit was NOT run** (mission: owner runs via
  `--mode tree` against the real Saleor store). `--mode plan` after tree gate.
- Real rename task requires an owner-provided `--rename-sides-json` entry
  (`saleor-rc-663543eaf563`); without it tree mode reports
  `RENAMED_SIDE_AUTHORITY_MISSING` as data (exit nonzero), never a silent success.
- Census `n_*` header counts are used as a redundant flag-consistency check; a census
  corrected after 2026-09-22 would surface as `classification_reconciled=false`.