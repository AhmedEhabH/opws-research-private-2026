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

Explicit determinism contract (M18): every git subprocess call uses argument arrays with
``shell=False``, ``--`` pathname separation, absolute-ref verification via
``git cat-file -e <ref>^{commit}``, a bounded-output limit and non-zero return-code
handling. Patch bytes are hashed as ``sha256(bytes)`` of the raw ``git diff`` output
under explicit settings (``--no-ext-diff --no-color --no-textconv``,
``-c core.autocrlf=false -c core.quotepath=false``) plus generated creation/deletion
sides where the frozen status semantics require them.

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
from collections.abc import Callable
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

# Explicit deterministic diff settings for every patch-producing git call.
DIFF_SETTINGS: tuple[str, ...] = (
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.quotepath=false",
    "-c",
    "diff.renames=false",
)
DIFF_FLAGS: tuple[str, ...] = ("--no-ext-diff", "--no-color", "--no-textconv")

# Default bound for one materialized patch (explicit, documented).
DEFAULT_MAX_PATCH_BYTES = 64 * 1024 * 1024  # 64 MiB per patch payload

def _default_test_classifier(p: str) -> bool:
    return (
        p.endswith("_test.py")
        or p.endswith("/test_")
        or p.endswith("/tests.py")
        or "/tests/" in p
        or "/testing/" in p
    )


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
    """A reference-required path is a symlink blob in the target tree; fail closed."""


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
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
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
    """Frozen file-status classification: ``git diff --name-status -z -M <p> <t>``.

    Returns ``{path: status}`` with status one of ``M``, ``D``, ``R``, ``A`` (frozen R1
    §3 statuses). Uses ``-z`` NUL-delimited output and forward-slash normalized paths.
    """
    stdout = git_capture(repo, "diff", "-z", "-M", "--name-status", *DIFF_FLAGS, parent, target)
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
            # rename: two path fields follow (old\x00new\x00)
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


def split_test_reference(
    classification: dict[str, str],
    test_paths: frozenset[str] | None = None,
    *,
    test_classifier: Callable[[str], bool] = _default_test_classifier,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split frozen changed-file classification into reference (non-test) vs test parts.

    Test-file changes belong to the **common behavior contract** (R1 §3) and are never
    part of a selector's editable scope. The split is explicit: either pass ``test_paths``
    (frozen source-derived) or the default frozen test-path classifier. Returns
    ``(reference_classification, test_classification)``.
    """
    test_set = (
        set(test_paths)
        if test_paths is not None
        else {p for p in classification if test_classifier(p)}
    )
    reference: dict[str, str] = {}
    test: dict[str, str] = {}
    for path, status in classification.items():
        (test if path in test_set else reference)[path] = status
    return reference, test


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


# ------------------------------------------------------------------ patch sides
def _diff_bytes(repo: Path, parent: str, target: str, *paths: str) -> bytes:
    cmd = ["git", "-C", str(repo), "diff", *DIFF_FLAGS, parent, target, "--"]
    for p in paths:
        cmd.append(p)
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, env=_git_env())
    except OSError as exc:
        raise GitCommandError(f"could not invoke git: {exc}") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise GitCommandError(f"git diff failed rc={proc.returncode}: {stderr[:600]}")
    if len(proc.stdout) > DEFAULT_MAX_PATCH_BYTES:
        raise OutputTooLargeError(f"diff output exceeded bound for paths {list(paths)}")
    return proc.stdout


def _creation_patch(repo: Path, target: str, path: str) -> bytes:
    """Full-file creation patch from the target-commit blob (frozen R1 ADDED treatment).

    Builds a deterministic unified diff ``--- /dev/null`` -> ``+++ b/<path>`` from the
    target blob. Fails closed on symlink blobs (mode 120000) and on binary content.
    """
    mode = target_blob_mode(repo, target, path)
    if mode == "120000":
        raise SymlinkPathError(f"added path {path!r} is a symlink blob at target; fail closed")
    blob = target_blob_bytes(repo, target, path)
    if b"\x00" in blob:
        raise UnsupportedStatusError(
            f"added path {path!r} has binary content; materializer does not guess binary diffs"
        )
    lines = blob.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    body = b"".join(b"+" + ln + b"\n" for ln in lines)
    n = len(lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode {mode or '100644'}\n"
        "index 0000000.." + hashlib.sha1(blob).hexdigest()[:7] + "\n"
        f"--- /dev/null\n+++ b/{path}\n"
        f"@@ -0,0 +1,{n} @@\n"
    ).encode("utf-8") + body


def _deletion_patch(repo: Path, parent: str, target: str, path: str) -> bytes:
    """Deletion-side patch for a RENAMED-old or DELETED path.

    Uses ``git diff --no-renames <parent> <target> -- <path>`` so a rename pair degrades
    to delete-old/add-new and the filtered old path yields a pure deletion hunk.
    """
    cmd = ["git", "-C", str(repo), "diff", "--no-renames", *DIFF_FLAGS, parent, target, "--", path]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, env=_git_env())
    except OSError as exc:
        raise GitCommandError(f"could not invoke git: {exc}") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise GitCommandError(f"git diff --no-renames failed rc={proc.returncode}: {stderr[:600]}")
    if len(proc.stdout) > DEFAULT_MAX_PATCH_BYTES:
        raise OutputTooLargeError(f"deletion-side diff exceeded bound for {path!r}")
    return proc.stdout


def _addition_side_patch(repo: Path, target: str, path: str) -> bytes:
    """Addition-side patch for a RENAMED-new path (reference-derived arms only)."""
    return _creation_patch(repo, target, path)


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
    test_paths: frozenset[str] | None = None,
    allow_added: bool = False,
    tape_unresolved: list[UnresolvedContractRecord] | None = None,
) -> MaterializationResult:
    """Materialize the frozen scoped reference patch from read-only Git objects.

    Pure in the engineering sense: same inputs -> byte-identical patch and hash; the
    only external effects are read-only git subprocess calls against ``repo``.

    * ``scope_paths`` are normalized with the frozen canonical scope-path rule and hashed
      with the frozen canonical scope hash (reused ``p2.compute_canonical_scope_hash``).
    * Paths present in the scope but absent at the **parent** (parent-only selector,
      ``allow_added=False``) are recorded in ``invalid_prediction_paths`` (R1 §3
      fail-closed guard: counted, excluded, reason recorded — never silently dropped).
    * ``allow_added=True`` is allowed only for reference-derived arms (GOLD / SELECT_ALL /
      FULL_REFERENCE), which may include ADDED paths as full-file creation from the
      target-commit blob (frozen R1 §3 PRIMARY treatment).
    * ``R_OLD``/``R_NEW``/``D``/``A`` follow frozen PRIMARY treatment. Anything else is
      recorded as ``invalid_prediction_paths`` and excluded (never guessed).
    """
    verify_repository(repo)
    parent_full = verify_ref_commit(repo, parent_commit, "parent")
    target_full = verify_ref_commit(repo, target_commit, "target")
    scope_unique, _ = _normalize_many(scope_paths, context="scope")
    scope_hash = p2.compute_canonical_scope_hash(scope_unique)
    canonical_class, class_invalid = normalize_classification(classification)
    reference_class, test_class = split_test_reference(canonical_class, test_paths)

    test_patch = bytearray()
    for path, status in sorted(test_class.items()):
        if status in ("M", "D"):
            test_patch += _diff_bytes(repo, parent_full, target_full, path)
        elif status == "A":
            test_patch += _creation_patch(repo, target_full, path)
        elif status in ("R_OLD", "R_NEW"):
            test_patch += _diff_bytes(repo, parent_full, target_full, path)
        else:  # pragma: no cover - normalized above
            continue

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
            per_path_status[path] = "A"
            ref_patch += _creation_patch(repo, target_full, path)
            files_changed.append(path)
            continue
        if ref_status in ("M", "D"):
            per_path_status[path] = ref_status
            files_changed.append(path)
            ref_patch += _diff_bytes(repo, parent_full, target_full, path)
            continue
        if ref_status == "R_OLD":
            per_path_status[path] = "R_OLD_DELETION"
            files_changed.append(path)
            ref_patch += _deletion_patch(repo, parent_full, target_full, path)
            continue
        if ref_status == "R_NEW":
            if not allow_added:
                invalid_prediction.append(
                    {"path": path, "reason": "RENAME_NEW_PATH_NOT_SELECTABLE_BY_PARENT_ONLY_SCOPE"}
                )
                continue
            per_path_status[path] = "R_NEW_ADDITION"
            files_changed.append(path)
            ref_patch += _addition_side_patch(repo, target_full, path)
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
    )


# ------------------------------------------------------------------ FULL_REFERENCE (PROPOSED R1.1 diagnostic)
def full_reference_classification(repo: Path, parent_commit: str, target_commit: str) -> dict[str, str]:
    """PROPOSED R1.1 diagnostic source: the complete historical non-test change set.

    Computed read-only via ``git diff --name-status -z -M <parent> <target>`` minus the
    common-contract test files. This is **FULL_REFERENCE**, a proposed diagnostic control
    (R1.1 DRAFT/UNAPPROVED). It does NOT replace GOLD: GOLD keeps the frozen historical
    proxy scope source unchanged.
    """
    verify_repository(repo)
    verify_ref_commit(repo, parent_commit, "parent")
    verify_ref_commit(repo, target_commit, "target")
    name_status = git_name_status_map(repo, parent_commit, target_commit)
    reference, _ = split_test_reference(name_status)
    return reference


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
        description="Engineering-only read-only reference-patch materializer (M18, no execution).",
    )
    ap.add_argument("--repo", required=True, help="read-only git repository path")
    ap.add_argument("--parent", required=True, help="parent commit object id")
    ap.add_argument("--target", required=True, help="target commit object id")
    ap.add_argument("--task-id", required=True, help="frozen task id")
    ap.add_argument("--scope-json", required=True, help="JSON file with {\"scope\": [paths]} (canonical, validated)")
    ap.add_argument("--classification-json", required=True,
                    help="JSON file with {\"changes\": {path: status}} frozen classification")
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

    result = materialize_scoped_reference_patch(
        task_id=args.task_id,
        repo=Path(args.repo),
        parent_commit=args.parent,
        target_commit=args.target,
        scope_paths=scope_paths,
        classification=classification,
        allow_added=args.allow_added,
    )
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
