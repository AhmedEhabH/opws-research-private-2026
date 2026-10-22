# M19A1A — OPWS Patch Materializer Integrity Repair (Engineering Result)

**Scope:** `scripts/opws_phase3b_patch_materialize.py` only (+ synthetic unit tests).
No adapter rewrite, no real Saleor execution, no Docker/WSL/network, no scientific outcome.

## Identity

| Item | Value |
|---|---|
| Before HEAD | `7af889202c9fe951284a4ee315593b6f832b0af8` (branch `parallel/opws-instrument-build-2026-10-20`, clean tree at start) |
| Frozen R1 commit | `9038df3e` (read-only `git show`) — "docs(eval): freeze OPWS R1 protocol" |
| Frozen R1.1 | current HEAD at start of mission (`7af8892…`) |
| Real-task behavioral outcomes | `REAL_TASK_BEHAVIORAL_OUTCOMES=0` |

## Files changed

| File | Change | Why |
|---|---|---|
| `scripts/opws_phase3b_patch_materialize.py` | Rewired to a single deterministic diff producer + explicit test-path authority + fail-closed guards | M19A1A integrity repair |
| `tests/unit/opws/test_opws_phase3b_patch_materialize.py` | Call-site updates only (required `test_path_authority`); two scenario-completeness fixes (symlink real.txt, stable-sha legacy.py) so the classification matches the task's complete git change set; FULL_REFERENCE test moved to the new partition API | Signature change, no assertion masked |
| `tests/unit/opws/test_opws_phase3b_m19a1a_integrity.py` | 18 new synthetic tests (new file) | M19A1A invariants |

## Changed behavior (in the materializer)

1. **Single deterministic Git diff producer `git_diff_bytes(repo, parent, target, *paths)`** used for ALL M/D/A/R_OLD/R_NEW and common-test patches. Git's own patch bytes only — added/deleted/renamed sides are Git-native creation/deletion hunks (manual hunks/blob hashes eliminated: `_creation_patch`/`_deletion_patch`/`_addition_side_patch` removed). Fixed settings: `--no-renames --full-index --binary --no-ext-diff --no-color --no-textconv` + `-c diff.renames=false -c diff.noprefix=false -c diff.mnemonicPrefix=false -c core.autocrlf=false -c core.quotepath=false`. Env isolation: `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_SYSTEM=os.devnull`, `GIT_CONFIG_*`/`GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` scrubbed. Existing 64 MiB bound enforced.
2. **No scientific filename heuristic.** `_default_test_classifier` removed. The split uses an explicit `TestPathAuthority` (census `test_file` flags). Coverage guards raise `TestClassificationAuthorityError` (`TEST_CLASSIFICATION_AUTHORITY_MISSING`) when authority is missing, `test_paths ⊄ changed_paths`, or when the classification is not the COMPLETE git changed path set (new git name-status cross-check in the materializer), so a non-test-only FULL_REFERENCE result can never be passed as a complete change set.
3. **Complete classification + partition.** The materializer receives the COMPLETE change-status classification, partitions into (a) common test changes and (b) selected non-test reference changes, and verifies split invariants (`verify_split_invariants`: census-test equality, disjointness, `reference_test_free`, union vs classification and vs git-changed universe) which are also exposed on the result.
4. **FULL_REFERENCE** is now a complete partition (`full_reference_partition` / `materialize_full_reference`) that always includes ALL non-test changes (added files and migrations) and the complete common test patch; it never erases the test side.
5. **Fail-closed object checks** with evidence: symlink (120000) → `SymlinkPathError`; gitlink/submodule (160000) → `SubmodulePathError`; NUL binary content → `BinaryContentError`; unsupported modes/statuses recorded or raised — never dropped silently. Rename old/new sides validated by native deletion/creation header presence.
6. **A/D/M/rename → census flag mapping (documented + enforced):** A→`added`(1:1), D→`deleted`(1:1), M→`modified`(1:1); rename = one pair-level census record → explicit `rename_sides` table required (`census_records_to_authority`), otherwise `TEST_CLASSIFICATION_AUTHORITY_MISSING`.

## Verification

| Gate | Result |
|---|---|
| `py -3.11 -m pytest tests/unit/opws/ -q` | **141 passed** (123 existing maintained + 18 new) |
| `ruff check` (3 touched files) | pass |
| `mypy --strict` (materializer) | pass |
| `python -m py_compile` (3 files) | pass |
| `git diff --check` | pass |

## Test counts (deliverable)

- 123 existing OPWS unit tests maintained (updated calls for signature changes; no assertions disabled).
- 18 new synthetic tests: native full-index patches, no-final-newline added file, zero-byte added `migrations/__init__.py`, mode-only change, rename with edited sides, test flag outside `tests/`, explicit `conftest.py` flag, hostile global config byte-identical, binary/symlink/submodule fail-closed, missing/incomplete authority, union/disjointness/census-equality invariants, **full-tree equality is INSUFFICIENT to validate the test split**, FULL_REFERENCE partition completeness, census rename side authority, rename side-header validation.

## Blockers / fail-closed records

- **Rename side authority is not derivable from the census offline.** The Main297 census records a rename as ONE pair-level record (`status: "renamed"`, one path, one flag); the materializer requires an explicit per-side `rename_sides` table for `R_OLD`/`R_NEW` side flags. Without it (offline, no Saleor checkout permitted in this mission) real rename tasks must fail closed with `TEST_CLASSIFICATION_AUTHORITY_MISSING`. Census-wide: 1/297 census tasks contain a `renamed` record. No real census receipt was fabricated.

## Assumptions

- Synthetic repos/tests are authoritative for engineering behavior; real 219-tree claims require a following authorized mission (M19A1B) with explicit object store access.
- `core.autocrlf=false` faithful worktrees are required to apply `--full-index` patches (fixtures fixed accordingly; this is a fixture-correctness fix, not an assertion change).
- No protocol changes; no edits to frozen evidence; `REAL_TASK_BEHAVIORAL_OUTCOMES=0`.

## Hashes

- Materializer (working tree): git-blob `2b4d71b5…`, sha256 `577a3695fb5a1f64d225d20f6c73df84a38616b1ea8437d718174d311eeb476a`
- New tests: git-blob `b068e1e0…`, sha256 `447eb6819425160aad2fc3f276bf9691360cd31ae2d675a15767eb6a5dc919b9`
- Old tests (updated): git-blob `7999162a…`
- Before HEAD: `7af889202c9fe951284a4ee315593b6f832b0af8`