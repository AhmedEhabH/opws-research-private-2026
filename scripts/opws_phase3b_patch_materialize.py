"""OPWS R1 Phase 3B — read-only real Git-object reference-patch materializer.

ENGINEERING ONLY. This module materializes and hashes **reference patches** from Git
objects of a **read-only** repository. It never checks out, alters, cleans or writes to
the Saleor repository, never materializes an OPWS *execution* worktree (R1 requires
execution materialization INSIDE LINUX for real tasks), and never produces a scientific
behavioral outcome. Fixture-only execution on synthetic temporary directories is what
the test suite exercises; the functions accept an explicit ``repo`` path so an owner
can point them at a read-only mirror when a future authorized mission needs it.

Frozen authority (``commit 9038df3e…``, immutable, read via git objects — the R1 files
are NOT present in the HEAD tree):

* ``OPWS_PROTOCOL_R1.md`` §1/§3 — reference patch = ``git diff <parent> <target> -- <selected>``
  applied onto the parent state; PRIMARY status handling for MODIFIED / DELETED /
  RENAMED-old/new / ADDED; test-file changes belong to the common behavior contract.
* ``OPWS_SCOPE_SEMANTICS_R1.json`` — canonical repository-relative scope paths and the
  scope-hash recipe (reused from ``opws_phase2_plan``, which mirrors the frozen
  reference implementation ``scripts/opws_protocol_r1_validate.py``).
* ``OPWS_EXECUTION_REUSE_DEDUP_R1.json`` — the five-field physical-execution identity
  tuple ``(TASK_ID, SCOPE_HASH, REFERENCE_PATCH_HASH, TEST_CONTRACT_HASH, ENVIRONMENT_ID)``.

Explicit determinism contract (M18 / M19A1A): every git subprocess call uses argument
arrays with ``shell=False``, ``--`` pathname separation, absolute-ref verification via
``git cat-file -e <ref>^{commit}``, a bounded-output limit and non-zero return-code
handling. Environment isolation: ``GIT_CONFIG_NOSYSTEM=1`` and
``GIT_CONFIG_GLOBAL=os.devnull`` (plus GIT_CONFIG_* / GIT_DIR / GIT_WORK_TREE /
GIT_INDEX_FILE scrubbing) so no user or hostile global configuration can change patch
bytes.

**Single deterministic diff producer (M19A1A).** ALL modification, deletion, addition,
renamed-old and renamed-new patches — and every common test patch — are produced by ONE
function, ``git_diff_bytes``, as Git's own ``git diff`` patch bytes under the fixed
settings in ``DIFF_SETTINGS``/``DIFF_FLAGS`` (``--no-renames --full-index --binary
--no-ext-diff --no-color --no-textconv`` plus ``diff.renames=false
diff.noprefix=false diff.mnemonicPrefix=false core.autocrlf=false core.quotepath=false``).
Added / renamed-new / deleted / renamed-old sides are Git-native creation/deletion
hunks; hunks, index lines and blob hashes are NEVER synthesized by hand. ``--no-renames``
makes each per-path record independent of Git's rename similarity heuristics: a renamed
pair degrades to delete-old/add-new, yielding pure per-side patches whose old/new side
headers are validated explicitly (never guessed).

**Frozen test-path authority (M19A1A).** The common-contract test split comes ONLY from
an explicit ``TestPathAuthority`` (the census per-task ``test_file`` flags); no
filename heuristic is ever applied at materialization time. The materializer requires
the COMPLETE change-status classification and verifies
``classification keys == authority.changed_paths`` (else it fails closed with
``TestClassificationAuthorityError``). It then partitions into (a) common test changes
and (b) selected non-test reference changes and verifies disjointness/completeness
invariants (``verify_split_invariants``). Callers must never pass the non-test-only
``FULL_REFERENCE`` reference side as a complete change set — that would erase the common
test patch; ``full_reference_partition`` / ``materialize_full_reference`` return the
complete partition (reference side always includes added files and migrations).

The module NEVER guesses the R1.1 GOLD/ADDED conflict: where frozen ADDED handling for
GOLD/SELECT_ALL conflicts with their frozen scope sources, an explicit
``UnresolvedContractRecord`` is produced (never a silent inject nor a rewrite of GOLD).
FULL_REFERENCE (complete historical non-test patch) is implemented as a **PROPOSED R1.1
diagnostic control only**, never as the old GOLD arm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_BOOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_BOOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_BOOT))

from scripts import opws_build as ob  # noqa: E402
from scripts import opws_phase2_plan as p2  # noqa: E402

# ------------------------------------------------------------------ constants
MATERIALIZER_SCHEMA = "opws-phase3b-patch-materialize/1.0-engineering"

# Explicit deterministic diff settings for every patch-producing git call (M19A1A).
# ``diff.renames=false`` (plus the ``--no-renames`` flag) removes rename-similarity
# heuristics from patch bytes; ``diff.noprefix=false`` / ``diff.mnemonicPrefix=false``
# pin the a/ b/ prefix form; ``core.autocrlf=false`` / ``core.quotepath=false`` pin the
# byte-level output. All are passed as ``-c`` argument vectors, never via config files.
DIFF_SETTINGS: tuple[str, ...] = (
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.quotepath=false",
    "-c",
    "diff.renames=false",
    "-c",
    "diff.noprefix=false",
    "-c",
    "diff.mnemonicPrefix=false",
)
DIFF_FLAGS: tuple[str, ...] = (
    "--no-renames",
    "--full-index",
    "--binary",
    "--no-ext-diff",
    "--no-color",
    "--no-textconv",
)

# Default bound for one materialized patch (explicit, documented).
DEFAULT_MAX_PATCH_BYTES = 64 * 1024 * 1024  # 64 MiB per patch payload


# ------------------------------------------------------------------ errors
class Phase3BError(RuntimeError):
    """Base class for all Phase-3B engineering failures (instrumentation, never scientific)."""


class MaterializerError(Phase3BError):
    """Base class for reference-patch materialization failures."""


class GitCommandError(MaterializerError):
    """A read-only git subprocess returned a non-zero exit code."""


class OutputTooLargeError(MaterializerError):
    """A git subprocess produced output beyond the explicit bound (fail closed)."""


class GitObjectIdentityError(MaterializerError):
    """Parent/target object identity could not be verified as an existing commit."""


class RepoPathError(MaterializerError):
    """The supplied repository path is not a readable Git repository (allowed paths only)."""


class ScopePathInvalidError(MaterializerError):
    """A scope or classification path violates the frozen canonical scope-path rule."""


class UnsupportedStatusError(MaterializerError):
    """A changed-file classification status is outside the frozen R1 status set."""


class SymlinkPathError(MaterializerError):
    """A reference-required path is a symlink blob in a tree; fail closed."""


class SubmodulePathError(MaterializerError):
    """A reference-required path is a gitlink/submodule entry in a tree; fail closed."""


class BinaryContentError(MaterializerError):
    """A reference-required blob carries binary (NUL) content; we never guess binary diffs."""


class TestClassificationAuthorityError(MaterializerError):
    """The frozen test-path authority is missing, incomplete or ambiguous (fail closed).

    Raised instead of guessing test membership from filename heuristics
    (``TEST_CLASSIFICATION_AUTHORITY_MISSING`` stop signal).
    """


@dataclass(frozen=True)
class UnresolvedContractRecord:
    """An explicit unresolved-contract record; never a guess, never silent."""

    contract: str
    status: str
    detail: str
    no_guess: bool = True
    proposed_remedy: str = "OWNER_DECISION_REQUIRED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "detail": self.detail,
            "no_guess": self.no_guess,
            "proposed_remedy": self.proposed_remedy,
        }


# ------------------------------------------------------------------ helpers
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ git plumbing (read-only)
def _git_env() -> dict[str, str]:
    """Deterministic git environment for every subprocess call.

    Isolates ALL user/system git configuration (``GIT_CONFIG_NOSYSTEM=1`` and
    ``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM`` pinned to ``os.devnull``, plus any
    ``GIT_CONFIG_*`` variables scrubbed) and irrelevant repository-locator variables
    (``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE``/object-dir overrides) so hostile
    or ambient configuration cannot alter patch bytes. Object access is preserved: the
    repository is addressed explicitly via ``git -C <repo>``.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"):
        env.pop(key, None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


def verify_repository(repo: Path) -> None:
    """Fail closed unless ``repo`` is an existing, readable Git repository.

    Read-only probe via ``git -C <repo> rev-parse --git-dir``. No writes, no checkout.
    """
    if not repo.is_dir():
        raise RepoPathError(f"repository path is not a directory: {repo}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-dir"],
            check=False,
            capture_output=True,
            env=_git_env(),
        )
    except OSError as exc:
        raise RepoPathError(f"could not invoke git at {repo}: {exc}") from exc
    if proc.returncode != 0:
        raise RepoPathError(
            f"repository path is not a git repository (rev-parse rc={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()[:400]}"
        )


def git_capture(repo: Path, *args: str, max_bytes: int = DEFAULT_MAX_PATCH_BYTES) -> bytes:
    """Read-only ``git`` call with argument arrays, ``shell=False``, bounded output.

    Every caller decides whether a trailing ``--`` + pathspec list is needed; this
    function only guarantees array invocation, explicit env, nonzero-rc and bound checks.
    """
    cmd = ["git", "-C", str(repo), *DIFF_SETTINGS, *args]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            env=_git_env(),
        )
    except OSError as exc:
        raise GitCommandError(f"could not invoke git: {exc}") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise GitCommandError(f"git {' '.join(args)} failed rc={proc.returncode}: {stderr[:600]}")
    if len(proc.stdout) > max_bytes:
        raise OutputTooLargeError(
            f"git output exceeded bound ({len(proc.stdout)} > {max_bytes} bytes) "
            f"for: {' '.join(args)}"
        )
    return proc.stdout


def git_diff_bytes(
    repo: Path,
    parent: str,
    target: str,
    *paths: str,
    max_bytes: int = DEFAULT_MAX_PATCH_BYTES,
) -> bytes:
    """SINGLE deterministic diff producer (M19A1A): Git's own patch bytes only.

    Used for ALL modification, deletion, addition, renamed-old and renamed-new patches
    and for common test patches. Equivalent to ``git diff <parent> <target> -- <paths>``
    under the fixed ``DIFF_SETTINGS``/``DIFF_FLAGS`` vectors (argument arrays, no shell).

    * ``--no-renames`` makes every per-path record independent of Git rename-similarity
      heuristics: a renamed pair degrades to delete-old/add-new so the old path yields a
      pure deletion patch and the new path a pure creation patch — both Git-native.
    * ``--full-index`` pins full 40-hex index lines; ``--binary`` pins binary-patch
      representation (binary blobs are still rejected upstream by
      ``verify_path_supported`` — never guessed).
    * Added-file hunks and blob hashes are NEVER synthesized by hand; if Git emits empty
      bytes for a requested path/side the caller's side checks fail closed.

    Raises OutputTooLargeError past ``max_bytes``; GitCommandError on non-zero rc.
    """
    if not paths:
        raise Phase3BError("git_diff_bytes requires at least one path (never a whole-tree diff)")
    cmd: list[str] = ["git", "-C", str(repo), *DIFF_SETTINGS, "diff", *DIFF_FLAGS, parent, target, "--"]
    cmd.extend(paths)
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, env=_git_env())
    except OSError as exc:
        raise GitCommandError(f"could not invoke git: {exc}") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise GitCommandError(f"git diff failed rc={proc.returncode}: {stderr[:600]}")
    if len(proc.stdout) > max_bytes:
        raise OutputTooLargeError(
            f"diff output exceeded bound ({len(proc.stdout)} > {max_bytes} bytes) "
            f"for paths: {list(paths)}"
        )
    return proc.stdout


def verify_ref_commit(repo: Path, ref: str, label: str) -> str:
    """Verify ``ref`` resolves to a commit via ``git cat-file -e <ref>^{commit}``.

    Returns the resolved full commit hash. Raises GitObjectIdentityError (fail closed)
    on missing / non-commit / malformed object identity. An explicit ``^{commit}``
    suffix prevents wrong-type addresses (tree/blob refs cannot satisfy a commit).
    """
    if not isinstance(ref, str) or not ref or "\x00" in ref:
        raise GitObjectIdentityError(f"{label}: invalid ref string {ref!r}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{ref}^{{commit}}"],
            check=False,
            capture_output=True,
            env=_git_env(),
        )
    except OSError as exc:
        raise GitObjectIdentityError(f"{label}: git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise GitObjectIdentityError(
            f"{label}: object identity not found/not a commit: {ref!r} "
            f"({proc.stderr.decode('utf-8', 'replace').strip()[:300]})"
        )
    full = git_capture(repo, "rev-parse", f"{ref}^{{commit}}").decode("ascii").strip()
    if len(full) != 40:
        raise GitObjectIdentityError(f"{label}: resolved hash not a full 40-hex sha: {full!r}")
    return full


def git_name_status_map(repo: Path, parent: str, target: str) -> dict[str, str]:
    """Frozen file-status classification: ``git diff --name-status -z --no-renames <p> <t>``.

    Returns ``{path: status}`` with status one of ``M``, ``D``, ``A`` (frozen R1 §3
    statuses). Rename detection is OFF (same fixed ``--no-renames`` policy as the diff
    producer) so a renamed pair appears as ``D(old)`` + ``A(new)`` — the complete
    physical change set with no similarity heuristics. ``R_OLD``/``R_NEW`` never come
    from git here; they exist only in explicit task classifications. Uses ``-z``
    NUL-delimited output and forward-slash normalized paths.
    """
    stdout = git_capture(repo, "diff", "-z", "--name-status", *DIFF_FLAGS, parent, target)
    fields = stdout.split(b"\x00")
    out: dict[str, str] = {}
    i = 0
    while i < len(fields):
        raw = fields[i]
        if not raw:
            i += 1
            continue
        status = raw.decode("utf-8", "replace")[:2]
        status_letter = status[0]
        if status_letter not in ("A", "C", "D", "M", "R", "T", "U", "X", "B"):
            raise UnsupportedStatusError(f"unparseable git name-status token: {status!r}")
        if status_letter == "R":
            # rename: two path fields follow (old\x00new\x00). Defensive: with
            # --no-renames git should never emit R; fail closed instead of guessing.
            if i + 2 >= len(fields):
                raise UnsupportedStatusError(f"truncated rename record for {raw!r}")
            old = fields[i + 1].decode("utf-8", "replace")
            new = fields[i + 2].decode("utf-8", "replace")
            out[old] = "R_OLD"
            out[new] = "R_NEW"
            i += 3
            continue
        if status_letter in ("C", "T", "U", "X", "B"):
            # not part of the frozen R1 primary set; surface as unsupported rather than guess
            raise UnsupportedStatusError(f"unsupported git status {status_letter!r} for path record")
        if i + 1 >= len(fields):
            raise UnsupportedStatusError(f"truncated status record {status!r}")
        path = fields[i + 1].decode("utf-8", "replace")
        if status_letter == "A":
            out[path] = "A"
        elif status_letter == "D":
            out[path] = "D"
        elif status_letter == "M":
            out[path] = "M"
        i += 2
    return out


def _normalize_many(paths: list[Any], context: str) -> tuple[list[str], int]:
    try:
        unique, dup = p2.normalize_scope_paths(list(paths), context=context)
    except ob.BuildError as exc:
        raise ScopePathInvalidError(str(exc)) from exc
    return unique, dup

# ------------------------------------------------------------------ classification
FROZEN_STATUSES = ("M", "D", "A", "R_OLD", "R_NEW")

# Census per-path statuses -> frozen primary statuses. ``renamed`` is deliberately NOT in
# this map: a census rename record names ONE pair head without per-side paths/flags, so
# it needs an explicit side authority (see census_records_to_authority) — never a guess.
CENSUS_STATUS_TO_FROZEN: dict[str, str] = {"modified": "M", "added": "A", "deleted": "D"}


@dataclass(frozen=True)
class TestPathAuthority:
    """Frozen-authority source for the common-contract test-path split (M19A1A).

    Comes from census per-task ``changed_paths`` records: every changed path is listed
    once with an explicit test/non-test ``test_file`` flag; renamed pairs are expanded to
    both sides with per-side flags by ``census_records_to_authority`` (or supplied
    explicitly). ``changed_paths`` is the COMPLETE changed-path universe for the task
    (== the complete git changed set, verified by the caller with cross-checks); the
    materializer fails closed if a classification path is missing from it. The
    materializer NEVER derives test paths from filename heuristics.
    """

    changed_paths: frozenset[str]
    test_paths: frozenset[str]
    source: str = "census"

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed_paths": sorted(self.changed_paths),
            "test_paths": sorted(self.test_paths),
            "source": self.source,
        }


def normalize_classification(classification: dict[str, str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Validate + canonicalize frozen changed-file classification.

    Returns ``(canonical_classification, invalid_records)`` where each invalid record
    names the offending path and reason (fail-closed guard, never silently dropped).
    """
    canonical: dict[str, str] = {}
    invalid: list[dict[str, Any]] = []
    for raw_path, status in classification.items():
        try:
            norm, _ = p2.normalize_scope_paths([raw_path], context="classification")
        except ob.BuildError as exc:
            invalid.append({"path": raw_path, "reason": f"INVALID_PATH: {exc}"})
            continue
        path = norm[0]
        if status not in FROZEN_STATUSES:
            invalid.append(
                {
                    "path": path,
                    "reason": f"UNSUPPORTED_STATUS: {status!r} (frozen statuses: {FROZEN_STATUSES})",
                }
            )
            continue
        canonical[path] = status
    return canonical, invalid


def _authority_for_classification(
    canonical_class: dict[str, str],
    authority: TestPathAuthority | None,
    *,
    context: str,
) -> TestPathAuthority:
    """Canonicalize + validate an explicit test-path authority against a classification.

    Fail-closed guards (M19A1A):

    * authority is required (never fall back to filename heuristics);
    * every authority path must obey the canonical scope-path rule;
    * ``authority.test_paths ⊆ authority.changed_paths``;
    * ``set(classification) == authority.changed_paths`` — the caller MUST supply the
      COMPLETE change-status classification; a subset (e.g. the non-test-only
      FULL_REFERENCE reference side) is rejected so the common test patch is never
      erased, and authority paths without a classification entry are rejected as
      incomplete classification/authority.
    """
    if authority is None:
        raise TestClassificationAuthorityError(
            f"{context}: explicit TestPathAuthority required for the test split "
            "(TEST_CLASSIFICATION_AUTHORITY_MISSING; filename heuristics never applied)"
        )
    changed: set[str] = set()
    for raw in sorted(authority.changed_paths):
        norm, _ = _normalize_many([raw], context="test-path-authority")
        changed.add(norm[0])
    tests: set[str] = set()
    for raw in sorted(authority.test_paths):
        norm, _ = _normalize_many([raw], context="test-path-authority")
        tests.add(norm[0])
    canonical_authority = TestPathAuthority(
        changed_paths=frozenset(changed),
        test_paths=frozenset(tests),
        source=authority.source,
    )
    if not tests <= changed:
        raise TestClassificationAuthorityError(
            f"{context}: authority test_paths not subset of changed_paths: "
            f"{sorted(tests - changed)[:5]}"
        )
    keys = set(canonical_class)
    if keys != changed:
        missing_from_classification = sorted(changed - keys)[:5]
        not_covered_by_authority = sorted(keys - changed)[:5]
        raise TestClassificationAuthorityError(
            f"{context}: authority.changed_paths must equal the COMPLETE classification "
            f"(TEST_CLASSIFICATION_AUTHORITY_MISSING; missing from classification: "
            f"{missing_from_classification}; not covered by authority: "
            f"{not_covered_by_authority})"
        )
    return canonical_authority


def split_test_reference(
    classification: dict[str, str],
    test_path_authority: TestPathAuthority | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split frozen changed-file classification into reference (non-test) vs test parts.

    Test-file changes belong to the **common behavior contract** (R1 §3) and are never
    part of a selector's editable scope. Test membership comes ONLY from
    ``test_path_authority.test_paths`` (frozen census flags); no filename heuristic is
    applied. Returns ``(reference_classification, test_classification)``.
    """
    if test_path_authority is None:
        raise TestClassificationAuthorityError(
            "split_test_reference requires an explicit TestPathAuthority "
            "(TEST_CLASSIFICATION_AUTHORITY_MISSING; filename heuristics never applied)"
        )
    test_set = test_path_authority.test_paths
    reference: dict[str, str] = {}
    test: dict[str, str] = {}
    for path, status in classification.items():
        (test if path in test_set else reference)[path] = status
    return reference, test


def verify_split_invariants(
    classification: dict[str, str],
    reference_classification: dict[str, str],
    test_classification: dict[str, str],
    *,
    test_path_authority: TestPathAuthority | None = None,
    all_git_changed_paths: set[str] | frozenset[str] | None = None,
) -> dict[str, bool]:
    """Check the M19A1A disjointness/completeness invariants INDEPENDENTLY of tree equality.

    Every invariant must be True for a valid split:

    * ``test_equals_census_authoritative`` / ``changed_test_paths_equal_authority`` —
      ``changed_test_paths == census_authoritative_test_changed_paths`` for the task
      (rename old/new sides treated explicitly by the authority);
    * ``disjoint`` — ``test_changes ∩ reference_changes == ∅`` (vacuously True when the
      test set is empty — use ``reference_test_free`` to catch a test file smuggled into
      the reference part);
    * ``reference_test_free`` — no census-test path appears in the reference (editable)
      part; catches the leak even when the test set is empty;
    * ``union_all_classification`` / ``union_all_git_changed`` —
      ``test ∪ reference == all_git_changed_paths`` (no erased test patch, no orphan
      path);
    * ``selectors_test_free`` — same membership condition at the classification level;
      the per-scope guard ``TEST_CHANGE_NOT_EDITABLE_SCOPE`` enforces it in the
      materializer;
    * ``full_tree_equality_insufficient`` — ALWAYS False by construction: a final-tree
      equality check cannot validate a split, because any partition of the same union
      applies to the same final tree; only the invariants above can.
    """
    test_keys = set(test_classification)
    ref_keys = set(reference_classification)
    all_keys = set(classification)
    authority_test = test_path_authority.test_paths if test_path_authority is not None else None
    universe = set(all_git_changed_paths) if all_git_changed_paths is not None else all_keys
    return {
        "test_equals_census_authoritative": authority_test is not None and test_keys == authority_test,
        "changed_test_paths_equal_authority": (
            authority_test is not None and test_keys == (authority_test & universe)
        ),
        "disjoint": test_keys.isdisjoint(ref_keys),
        "reference_test_free": authority_test is not None and ref_keys.isdisjoint(authority_test),
        "union_all_classification": test_keys | ref_keys == all_keys,
        "union_all_git_changed": test_keys | ref_keys == universe,
        "selectors_test_free": test_keys.isdisjoint(ref_keys),
        "full_tree_equality_insufficient": False,
    }


def census_records_to_authority(
    records: list[dict[str, Any]],
    *,
    rename_sides: dict[str, tuple[str, str, bool, bool]] | None = None,
) -> TestPathAuthority:
    """Map census per-path records to a frozen ``TestPathAuthority`` (M19A1A).

    Census record shape (``research/wp2/wp2_saleor_main297_census_2026-09-22.json``):
    ``{path, status: modified|added|deleted|renamed, test_file, migration_file,
    config_or_infra}``.

    Mapping of changed test paths to census flags:

    * **A side**  — census ``added`` record path == git A path (1:1); flag applies 1:1;
    * **D side**  — census ``deleted`` record path == git D path (1:1); 1:1;
    * **M side**  — census ``modified`` record path == git M path (1:1); 1:1;
    * **rename**  — the census records ONE pair-level ``renamed`` record (one path +
      one flag) with NO per-side paths/flags. Old/new side expansion requires an
      explicit ``rename_sides`` table ``{pair_head: (old, new, old_is_test, new_is_test)}``.
      Without it the record is AMBIGUOUS and the adapter raises
      ``TestClassificationAuthorityError`` (``TEST_CLASSIFICATION_AUTHORITY_MISSING``) —
      sides are never guessed from filenames. ``rename_sides`` also serves as the
      authoritative documentation of which census flag applies to which side.

    Raises TestClassificationAuthorityError on missing paths, unsupported statuses,
    rename records without side authority, or invalid paths.
    """
    changed: set[str] = set()
    tests: set[str] = set()
    for rec in records:
        path = rec.get("path")
        status = rec.get("status")
        if not isinstance(path, str) or not path:
            raise TestClassificationAuthorityError(
                f"census record missing path: {rec!r}"
            )
        if status not in CENSUS_STATUS_TO_FROZEN and status != "renamed":
            raise TestClassificationAuthorityError(
                f"census record status unsupported for {path!r}: {status!r} "
                "(TEST_CLASSIFICATION_AUTHORITY_MISSING)"
            )
        try:
            norm, _ = p2.normalize_scope_paths([path], context="census-record")
        except ob.BuildError as exc:  # pragma: no cover - defensive
            raise TestClassificationAuthorityError(
                f"census record path invalid for {path!r}: {exc}"
            ) from exc
        path = norm[0]
        flag = bool(rec.get("test_file"))
        if status == "renamed":
            if not rename_sides or path not in rename_sides:
                raise TestClassificationAuthorityError(
                    f"census renamed record {path!r} lacks explicit side authority "
                    "(RENAMED_SIDE_AUTHORITY_MISSING; old/new sides never guessed): "
                    "supply rename_sides={{path: (old, new, old_is_test, new_is_test)}}"
                )
            old, new, old_flag, new_flag = rename_sides[path]
            for side, side_flag in ((old, old_flag), (new, new_flag)):
                changed.add(side)
                if side_flag:
                    tests.add(side)
            continue
        changed.add(path)
        if flag:
            tests.add(path)
    return TestPathAuthority(changed_paths=frozenset(changed), test_paths=frozenset(tests), source="census")


# ------------------------------------------------------------------ blob modes
def target_blob_mode(repo: Path, target: str, path: str) -> str:
    """Tree mode of ``path`` at ``target`` (empty string if absent). Read-only."""
    stdout = git_capture(repo, "ls-tree", "-z", target, "--", path)
    if not stdout:
        return ""
    entry = stdout.split(b"\x00", 1)[0].decode("utf-8", "replace")
    return entry.split(" ", 1)[0] if entry else ""


def target_blob_bytes(repo: Path, target: str, path: str) -> bytes:
    """Raw blob bytes at ``path`` in ``target`` (read-only ``git cat-file blob``)."""
    return git_capture(repo, "cat-file", "blob", f"{target}:{path}")


def verify_path_supported(
    repo: Path,
    parent: str,
    target: str,
    path: str,
    *,
    includes_parent: bool,
    includes_target: bool,
) -> dict[str, str]:
    """Fail closed unless ``path`` is a plain (non-binary) regular file on the sides it exists.

    Evidence-based rejection (never dropped silently):

    * symlink blob (mode ``120000``)     -> ``SymlinkPathError``;
    * gitlink/submodule (mode ``160000``) -> ``SubmodulePathError``;
    * any other non-regular mode          -> ``UnsupportedStatusError``;
    * blob content carrying a NUL byte    -> ``BinaryContentError`` (binary diffs are
      never guessed, even though ``--binary`` pins the diff representation).

    Returns per-side mode evidence ``{parent|target: mode}``.
    """
    evidence: dict[str, str] = {}
    for side, present, ref in (("parent", includes_parent, parent), ("target", includes_target, target)):
        if not present:
            continue
        mode = target_blob_mode(repo, ref, path)
        evidence[side] = mode or "MISSING"
        if mode == "120000":
            raise SymlinkPathError(f"{side} side of {path!r} is a symlink blob (mode 120000); fail closed")
        if mode == "160000":
            raise SubmodulePathError(f"{side} side of {path!r} is a gitlink/submodule (mode 160000); fail closed")
        if mode not in ("100644", "100755"):
            raise UnsupportedStatusError(
                f"{side} side of {path!r} has unsupported tree mode {mode!r}; fail closed"
            )
        if b"\x00" in target_blob_bytes(repo, ref, path):
            raise BinaryContentError(f"{side} side of {path!r} has binary (NUL) content; fail closed")
    return evidence


def _checked_patch(repo: Path, parent: str, target: str, path: str, status: str) -> bytes:
    """Native per-path patch for ``status`` with side validation (M19A1A).

    Uses the single producer ``git_diff_bytes``; validates the Git diff actually
    represents the requested old/new side of a rename: empty bytes under any status, or
    a missing native deletion/creation header for ``R_OLD``/``R_NEW``, raise
    ``UnsupportedStatusError`` with evidence (fail closed, never a soft partial).
    """
    patch = git_diff_bytes(repo, parent, target, path)
    if not patch:
        raise UnsupportedStatusError(
            f"no diff bytes for {path!r} under status {status}; requested side does not "
            "match git state between parent/target"
        )
    if status == "R_OLD" and b"deleted file mode" not in patch:
        raise UnsupportedStatusError(
            f"R_OLD patch for {path!r} lacks the native deletion header; the diff does "
            "not represent the rename-old side"
        )
    if status == "R_NEW" and b"new file mode" not in patch:
        raise UnsupportedStatusError(
            f"R_NEW patch for {path!r} lacks the native creation header; the diff does "
            "not represent the rename-new side"
        )
    return patch


# ------------------------------------------------------------------ public materialize
@dataclass(frozen=True)
class MaterializationResult:
    task_id: str
    parent_commit: str
    target_commit: str
    selected_scope_hash: str
    reference_patch_bytes: bytes
    reference_patch_hash: str
    test_patch_bytes: bytes
    test_patch_hash: str
    per_path_status: dict[str, str]
    invalid_prediction_paths: list[dict[str, Any]]
    unresolved_contracts: list[dict[str, Any]] = field(default_factory=list)
    files_changed: tuple[str, ...] = ()
    reference_classification: dict[str, str] = field(default_factory=dict)
    test_classification: dict[str, str] = field(default_factory=dict)
    split_invariants: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": MATERIALIZER_SCHEMA,
            "task_id": self.task_id,
            "parent_commit": self.parent_commit,
            "target_commit": self.target_commit,
            "selected_scope_hash": self.selected_scope_hash,
            "reference_patch_sha256": self.reference_patch_hash,
            "reference_patch_bytes": len(self.reference_patch_bytes),
            "test_patch_sha256": self.test_patch_hash,
            "test_patch_bytes": len(self.test_patch_bytes),
            "per_path_status": dict(self.per_path_status),
            "invalid_prediction_paths": list(self.invalid_prediction_paths),
            "unresolved_contracts": list(self.unresolved_contracts),
            "files_changed": list(self.files_changed),
            "reference_classification": dict(self.reference_classification),
            "test_classification": dict(self.test_classification),
            "split_invariants": dict(self.split_invariants),
            "scientific_outcome": "UNOBSERVED",
        }


def materialize_scoped_reference_patch(
    *,
    task_id: str,
    repo: Path,
    parent_commit: str,
    target_commit: str,
    scope_paths: list[str],
    classification: dict[str, str],
    test_path_authority: TestPathAuthority | None,
    allow_added: bool = False,
    tape_unresolved: list[UnresolvedContractRecord] | None = None,
) -> MaterializationResult:
    """Materialize the frozen scoped reference patch from read-only Git objects.

    Pure in the engineering sense: same inputs -> byte-identical patch and hash; the
    only external effects are read-only git subprocess calls against ``repo``.

    * ``scope_paths`` are normalized with the frozen canonical scope-path rule and hashed
      with the frozen canonical scope hash (reused ``p2.compute_canonical_scope_hash``).
    * ``classification`` MUST be the COMPLETE change-status classification for the task
      (verified equal to ``test_path_authority.changed_paths``; fail closed otherwise —
      the non-test-only FULL_REFERENCE reference side is never a valid classification).
      It is partitioned into (a) common test changes and (b) selected non-test reference
      changes under the explicit frozen ``test_path_authority``; disjointness and
      completeness invariants are re-checked and exposed on the result.
    * Paths present in the scope but absent at the **parent** (parent-only selector,
      ``allow_added=False``) are recorded in ``invalid_prediction_paths`` (R1 §3
      fail-closed guard: counted, excluded, reason recorded — never silently dropped).
    * ``allow_added=True`` is allowed only for reference-derived arms (GOLD / SELECT_ALL /
      FULL_REFERENCE), which may include ADDED paths as full-file creation from the
      target-commit blob (frozen R1 §3 PRIMARY treatment) — Git-native creation hunks.
    * ``R_OLD``/``R_NEW``/``D``/``A`` follow frozen PRIMARY treatment; every per-path
      patch comes from the single ``git_diff_bytes`` producer with native side-header
      validation. Anything outside the frozen statuses is recorded as
      ``invalid_prediction_paths`` and excluded (never guessed).
    """
    verify_repository(repo)
    parent_full = verify_ref_commit(repo, parent_commit, "parent")
    target_full = verify_ref_commit(repo, target_commit, "target")
    scope_unique, _ = _normalize_many(scope_paths, context="scope")
    scope_hash = p2.compute_canonical_scope_hash(scope_unique)
    canonical_class, class_invalid = normalize_classification(classification)
    # M19A1A completeness guard (independent of tree equality): the classification MUST
    # cover the COMPLETE git changed path set for the task (paths only — rename statuses
    # R_OLD/R_NEW encode the same pair as git's no-renames D(old)+A(new)). Passing the
    # non-test-only FULL_REFERENCE reference side here would erase the common test patch
    # and is rejected. Invalid classification records (class_invalid) are already
    # recorded; they are not part of the canonical universe.
    git_changed_paths = set(git_name_status_map(repo, parent_full, target_full))
    if set(canonical_class) != git_changed_paths:
        missing = sorted(git_changed_paths - set(canonical_class))[:5]
        extra = sorted(set(canonical_class) - git_changed_paths)[:5]
        raise TestClassificationAuthorityError(
            f"task {task_id!r}: classification must cover the COMPLETE git changed set "
            f"(TEST_CLASSIFICATION_AUTHORITY_MISSING; missing from classification: "
            f"{missing}; not changed in git: {extra})"
        )
    authority = _authority_for_classification(canonical_class, test_path_authority, context=f"task {task_id!r}")
    reference_class, test_class = split_test_reference(canonical_class, authority)
    split_invariants = verify_split_invariants(
        canonical_class,
        reference_class,
        test_class,
        test_path_authority=authority,
    )
    if (
        not split_invariants["disjoint"]
        or not split_invariants["reference_test_free"]
        or not split_invariants["union_all_classification"]
    ):
        raise TestClassificationAuthorityError(
            f"task {task_id!r}: split invariants violated (fail closed): {split_invariants}"
        )
    if not split_invariants["test_equals_census_authoritative"]:
        raise TestClassificationAuthorityError(
            f"task {task_id!r}: changed_test_paths != census authoritative test paths "
            f"(fail closed): {split_invariants}"
        )

    test_patch = bytearray()
    for path, status in sorted(test_class.items()):
        verify_path_supported(
            repo,
            parent_full,
            target_full,
            path,
            includes_parent=status in ("M", "D", "R_OLD"),
            includes_target=status in ("M", "A", "R_NEW"),
        )
        test_patch += _checked_patch(repo, parent_full, target_full, path, status)

    ref_patch = bytearray()
    files_changed: list[str] = []
    per_path_status: dict[str, str] = {}
    invalid_prediction: list[dict[str, Any]] = list(class_invalid)

    for path in scope_unique:
        ref_status = reference_class.get(path)
        if path not in reference_class:
            if path in test_class:
                # scope listed a test file: tests are never editable scope; recorded, excluded
                invalid_prediction.append(
                    {"path": path, "reason": "TEST_CHANGE_NOT_EDITABLE_SCOPE"}
                )
                continue
            # path unchanged in this task: nothing to materialize (empty/zero contribution)
            per_path_status[path] = "UNCHANGED_NULL"
            continue
        if ref_status == "A" and not allow_added:
            invalid_prediction.append(
                {
                    "path": path,
                    "reason": "ADDED_NOT_SELECTABLE_BY_PARENT_ONLY_SCOPE",
                }
            )
            continue
        if ref_status == "A":
            verify_path_supported(
                repo, parent_full, target_full, path, includes_parent=False, includes_target=True
            )
            per_path_status[path] = "A"
            files_changed.append(path)
            ref_patch += _checked_patch(repo, parent_full, target_full, path, "A")
            continue
        if ref_status in ("M", "D"):
            verify_path_supported(
                repo,
                parent_full,
                target_full,
                path,
                includes_parent=ref_status == "D",
                includes_target=ref_status == "M",
            )
            per_path_status[path] = ref_status
            files_changed.append(path)
            ref_patch += _checked_patch(repo, parent_full, target_full, path, ref_status)
            continue
        if ref_status == "R_OLD":
            verify_path_supported(
                repo, parent_full, target_full, path, includes_parent=True, includes_target=False
            )
            per_path_status[path] = "R_OLD_DELETION"
            files_changed.append(path)
            ref_patch += _checked_patch(repo, parent_full, target_full, path, "R_OLD")
            continue
        if ref_status == "R_NEW":
            if not allow_added:
                invalid_prediction.append(
                    {"path": path, "reason": "RENAME_NEW_PATH_NOT_SELECTABLE_BY_PARENT_ONLY_SCOPE"}
                )
                continue
            verify_path_supported(
                repo, parent_full, target_full, path, includes_parent=False, includes_target=True
            )
            per_path_status[path] = "R_NEW_ADDITION"
            files_changed.append(path)
            ref_patch += _checked_patch(repo, parent_full, target_full, path, "R_NEW")
            continue
        if ref_status in ("R", "UNCHANGED_NULL", None):
            invalid_prediction.append(
                {"path": path, "reason": f"INCOMPLETE_RENAMED_CLASSIFICATION: {ref_status!r}"}
            )
            continue
        invalid_prediction.append({"path": path, "reason": f"UNSUPPORTED_STATUS: {ref_status!r}"})

    ref_bytes = bytes(ref_patch)
    test_bytes = bytes(test_patch)

    unresolved: list[dict[str, Any]] = []
    if tape_unresolved:
        unresolved.extend(rec.as_dict() for rec in tape_unresolved)

    # Explicit unresolved-contract record when an ADDED path was excluded from a
    # reference-derived arm because its frozen scope source cannot decide handling.
    for rec in invalid_prediction:
        if rec["reason"].startswith("ADDED_NOT_SELECTABLE"):
            unresolved.append(
                UnresolvedContractRecord(
                    contract="R1-ADDED-HANDLING",
                    status="UNRESOLVED_PENDING_OWNER",
                    detail=(
                        "GOLD/SELECT_ALL frozen scope sources conflict with frozen ADDED "
                        f"treatment for path {rec['path']}; no guess applied; "
                        "separate PROPOSED R1.1 FULL_REFERENCE control computes it from "
                        "parent/target git objects instead of rewriting GOLD."
                    ),
                ).as_dict()
            )

    return MaterializationResult(
        task_id=task_id,
        parent_commit=parent_full,
        target_commit=target_full,
        selected_scope_hash=scope_hash,
        reference_patch_bytes=ref_bytes,
        reference_patch_hash=sha256_bytes(ref_bytes),
        test_patch_bytes=test_bytes,
        test_patch_hash=sha256_bytes(test_bytes),
        per_path_status=per_path_status,
        invalid_prediction_paths=invalid_prediction,
        unresolved_contracts=unresolved,
        files_changed=tuple(files_changed),
        reference_classification=dict(reference_class),
        test_classification=dict(test_class),
        split_invariants=split_invariants,
    )


# ------------------------------------------------------------------ FULL_REFERENCE (PROPOSED R1.1 diagnostic)
def full_reference_partition(
    repo: Path,
    parent_commit: str,
    target_commit: str,
    test_path_authority: TestPathAuthority,
) -> tuple[dict[str, str], dict[str, str]]:
    """PROPOSED R1.1 diagnostic source: the COMPLETE historical change set, partitioned.

    Computed read-only via ``git diff --name-status -z --no-renames <parent> <target>``
    (A/D/M only; a renamed pair degrades to D(old)+A(new)). Returns
    ``(reference, test)`` where ``reference`` is the complete **non-test** historical
    change set (ALL non-test changes, including added files and migrations) and ``test``
    is the common-contract test change set. ``test_path_authority.changed_paths`` is
    cross-checked to equal the git changed set (fail closed otherwise, e.g. for a census
    rename record whose sides the authority could not expand).

    This is **FULL_REFERENCE**, a proposed diagnostic control (R1.1 DRAFT/UNAPPROVED).
    It does NOT replace GOLD: GOLD keeps the frozen historical proxy scope source
    unchanged. Callers must NEVER treat the ``reference`` side alone as the complete
    change set — that would erase the common test patch; use the returned pair or
    ``materialize_full_reference``.
    """
    verify_repository(repo)
    verify_ref_commit(repo, parent_commit, "parent")
    verify_ref_commit(repo, target_commit, "target")
    name_status = git_name_status_map(repo, parent_commit, target_commit)
    authority = _authority_for_classification(name_status, test_path_authority, context="FULL_REFERENCE")
    reference, test = split_test_reference(name_status, authority)
    return reference, test


def materialize_full_reference(
    *,
    task_id: str,
    repo: Path,
    parent_commit: str,
    target_commit: str,
    test_path_authority: TestPathAuthority,
    tape_unresolved: list[UnresolvedContractRecord] | None = None,
) -> MaterializationResult:
    """Materialize FULL_REFERENCE: all non-test changes + the COMPLETE common test patch.

    Reference side covers every git-changed non-test path (added files and migrations
    included, ``allow_added=True``); test side carries every common-contract test
    change. Renamed pairs degrade to D(old)+A(new) under the fixed ``--no-renames``
    policy. The result's split invariants are verified and exposed.
    """
    verify_repository(repo)
    parent_full = verify_ref_commit(repo, parent_commit, "parent")
    target_full = verify_ref_commit(repo, target_commit, "target")
    name_status = git_name_status_map(repo, parent_full, target_full)
    authority = _authority_for_classification(name_status, test_path_authority, context="FULL_REFERENCE")
    reference, test = split_test_reference(name_status, authority)
    classification = {**reference, **test}
    return materialize_scoped_reference_patch(
        task_id=task_id,
        repo=repo,
        parent_commit=parent_full,
        target_commit=target_full,
        scope_paths=sorted(reference),
        classification=classification,
        test_path_authority=authority,
        allow_added=True,
        tape_unresolved=tape_unresolved,
    )


# ------------------------------------------------------------------ physical dedup identity
PHYSICAL_IDENTITY_FIELDS = ("TASK_ID", "SCOPE_HASH", "REFERENCE_PATCH_HASH", "TEST_CONTRACT_HASH", "ENVIRONMENT_ID")


def physical_execution_identity(
    *,
    task_id: str,
    scope_hash: str,
    reference_patch_hash: str,
    test_contract_hash: str,
    environment_id: str,
) -> dict[str, str]:
    """Frozen five-component physical-execution identity (OPWS_EXECUTION_REUSE_DEDUP_R1).

    Returns the field-keyed tuple serialized for the frozen map file, plus a canonical
    ``physical_execution_id = sha256(compact_json(fields in frozen order))`` so records
    can be tracked without derailing the frozen five-field equality rule.
    """
    payload: dict[str, str] = {
        "TASK_ID": task_id,
        "SCOPE_HASH": scope_hash,
        "REFERENCE_PATCH_HASH": reference_patch_hash,
        "TEST_CONTRACT_HASH": test_contract_hash,
        "ENVIRONMENT_ID": environment_id,
    }
    canonical = json.dumps(
        [payload[f] for f in PHYSICAL_IDENTITY_FIELDS],
        sort_keys=False,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload["physical_execution_id"] = sha256_bytes(canonical.encode("utf-8"))
    return payload


def plan_physical_dedup(records: list[dict[str, str]]) -> dict[str, Any]:
    """Group logical records into physical execution opportunities.

    All five frozen identity fields must be equal before two logical records MAY share
    one physical execution. Equal patch hashes alone are NOT permission to deduplicate
    different scopes. Returns logical-vs-physical counts and per-group records with a
    ``dedup_reason`` (frozen ``OPWS_PHYSICAL_EXECUTION_MAP.json`` semantics).
    """
    groups: dict[str, list[dict[str, str]]] = {}
    for rec in records:
        key = json.dumps(
            [rec.get(f, "") for f in PHYSICAL_IDENTITY_FIELDS],
            sort_keys=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        groups.setdefault(key, []).append(rec)
    physical: list[dict[str, Any]] = []
    for key, recs in groups.items():
        fields = json.loads(key)
        identity = physical_execution_identity(
            task_id=fields[0],
            scope_hash=fields[1],
            reference_patch_hash=fields[2],
            test_contract_hash=fields[3],
            environment_id=fields[4],
        )
        physical.append(
            {
                "physical_execution_id": identity["physical_execution_id"],
                "logical_arm_ids": [r.get("arm_id", "?") for r in recs],
                "logical_record_ids": [r.get("record_id", "?") for r in recs],
                "dedup_reason": "FIVE_FIELDS_EQUAL" if len(recs) > 1 else "SINGLE_RECORD",
                "identity_fields": dict(zip(PHYSICAL_IDENTITY_FIELDS, fields, strict=True)),
            }
        )
    return {
        "n_logical_records": len(records),
        "n_physical_executions": len(physical),
        "physical_executions": physical,
    }


# ------------------------------------------------------------------ apply probe (fixture-only)
def apply_check(worktree_dir: Path, patch_bytes: bytes) -> tuple[bool, str]:
    """Fixture-only ``git apply --check`` probe against a synthetic worktree.

    Used exclusively inside tests on synthetic temporary directories (allowed by the
    M18 guardrails) to detect patch conflicts deterministically. Never used against a
    real Saleor worktree. Returns ``(ok, stderr)``.
    """
    cmd = ["git", "-C", str(worktree_dir), "apply", "--check", "--verbose", "-"]
    try:
        proc = subprocess.run(cmd, input=patch_bytes, check=False, capture_output=True, env=_git_env())
    except OSError as exc:
        raise GitCommandError(f"git apply unavailable: {exc}") from exc
    ok = proc.returncode == 0
    return ok, proc.stderr.decode("utf-8", "replace").strip()[:1200]


# ------------------------------------------------------------------ CLI (engineering demo only)
def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="opws_phase3b_patch_materialize",
        description="Engineering-only read-only reference-patch materializer (M18/M19A1A, no execution).",
    )
    ap.add_argument("--repo", required=True, help="read-only git repository path")
    ap.add_argument("--parent", required=True, help="parent commit object id")
    ap.add_argument("--target", required=True, help="target commit object id")
    ap.add_argument("--task-id", required=True, help="frozen task id")
    ap.add_argument("--scope-json", required=True, help="JSON file with {\"scope\": [paths]} (canonical, validated)")
    ap.add_argument("--classification-json", required=True,
                    help="JSON file with {\"changes\": {path: status}} frozen classification (COMPLETE change set)")
    ap.add_argument("--test-authority-json",
                    help="JSON file with {\"changed_paths\": [...], \"test_paths\": [...], "
                         "\"source\": \"census\"} — frozen census test-path authority (required "
                         "whenever the classification is non-empty; no filename heuristics)")
    ap.add_argument("--allow-added", action="store_true", help="reference-derived arm may include ADDED paths")
    ap.add_argument("--dry-run", action="store_true", help="print summary and hash only; writes nothing")
    ap.add_argument("--out-dir", help="directory for the engineering JSON record (dry-run writes nothing)")
    args = ap.parse_args()

    try:
        scope_data = json.loads(Path(args.scope_json).read_text(encoding="utf-8"))
        class_data = json.loads(Path(args.classification_json).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAILED to read input JSON: {exc}", file=sys.stderr)
        return 2
    scope_paths = scope_data.get("scope") if isinstance(scope_data, dict) else None
    classification = class_data.get("changes") if isinstance(class_data, dict) else None
    if not isinstance(scope_paths, list) or not isinstance(classification, dict):
        print('scope-json needs {"scope": ...}; classification-json needs {"changes": ...}', file=sys.stderr)
        return 2
    authority: TestPathAuthority | None = None
    if args.test_authority_json:
        auth_data = json.loads(Path(args.test_authority_json).read_text(encoding="utf-8"))
        if not isinstance(auth_data, dict):
            print("test-authority-json needs an object {changed_paths, test_paths, source}", file=sys.stderr)
            return 2
        changed = auth_data.get("changed_paths", [])
        tests = auth_data.get("test_paths", [])
        if not isinstance(changed, list) or not isinstance(tests, list):
            print("test-authority-json changed_paths/test_paths must be lists", file=sys.stderr)
            return 2
        authority = TestPathAuthority(
            changed_paths=frozenset(str(p) for p in changed),
            test_paths=frozenset(str(p) for p in tests),
            source=str(auth_data.get("source", "census")),
        )
    if classification and authority is None:
        print(
            "FAILED: test-path authority required for a non-empty classification "
            "(TEST_CLASSIFICATION_AUTHORITY_MISSING; filename heuristics never applied)",
            file=sys.stderr,
        )
        return 2

    try:
        result = materialize_scoped_reference_patch(
            task_id=args.task_id,
            repo=Path(args.repo),
            parent_commit=args.parent,
            target_commit=args.target,
            scope_paths=scope_paths,
            classification=classification,
            test_path_authority=authority,
            allow_added=args.allow_added,
        )
    except TestClassificationAuthorityError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    payload = result.as_dict()
    print(_canonical_json(payload))
    if not args.dry_run and args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        receipt = out / f"{args.task_id}_materialize_receipt.json"
        receipt.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        print(f"WROTE={receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
