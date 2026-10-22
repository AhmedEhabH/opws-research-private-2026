"""OPWS R1 M19A1B — read-only Git-tree reconstruction audit (AUTHOR CODE ONLY, no execution).

ENGINEERING AUDIT OF GIT OBJECTS ONLY. This module audits **source integrity** of the
bound 219-task OPWS population: for every task it reconstructs the target tree by
applying the COMMON TEST patch (exactly once) followed by the complete non-test
FULL_REFERENCE patch onto the parent tree, using an **isolated temporary Git index and
object store**. It NEVER checks out, alters, cleans or writes to the Saleor object
store / cache (read access only through ``GIT_ALTERNATE_OBJECT_DIRECTORIES``), never
materializes an OPWS execution worktree, and never produces a scientific behavioral
outcome (``REAL_TASK_BEHAVIORAL_OUTCOMES=0``). Real Saleor test execution, pytest
collection from a real Saleor tree and network/dependency activity are out of scope.

Frozen authority (immutable; read via ``--repo``):

* ``research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json`` — the bound
  219 tasks with ``parent_commit`` / ``target_commit`` / ``contract_sha256``.
* ``research/wp2/wp2_saleor_main297_census_2026-09-22.json`` — per-task per-path
  ``test_file`` / ``migration_file`` / ``config_or_infra`` flags. THE canonical
  test-path authority. M19A1A validator (``census_records_to_authority`` plus the
  materializer's completeness/split invariants) is reused verbatim; test membership is
  NEVER inferred from filenames; missing/inconsistent authority fails closed.
* Rename sides: a census ``renamed`` record is ONE pair-level record (one path, one
  flag). Per-side test flags can only come from an explicit side-authority table
  (``--rename-sides-json``, M19A1A's ``rename_sides`` protocol). If the two sides
  cross the test boundary the task records ``RENAME_CROSSES_TEST_BOUNDARY`` and is
  STOPPED (never removed from the 219 denominator; no scientific exclusion encoded).

Tree-mode reconstruction per task:

1. isolated temp dir OUTSIDE the Saleor store holding a temp Git index + object store;
   ``GIT_INDEX_FILE`` / ``GIT_OBJECT_DIRECTORY`` / ``GIT_ALTERNATE_OBJECT_DIRECTORIES``
   point at it (alternates expose the real read-only objects; the real cache is never
   written to). The real object directory is resolved for ordinary clones AND bare
   repos, including ``objects/info/alternates``; unsupported layouts fail closed.
2. ``git read-tree <parent>`` -> ``git apply --cached`` COMMON TEST patch exactly once,
   then the complete non-test FULL_REFERENCE patch from the phase-3B materializer
   (``materialize_full_reference``, single deterministic ``git_diff_bytes`` producer).
   Empty patches are no-ops; deletes, mode changes, zero-byte adds, renames
   (D(old)+A(new) under the frozen ``--no-renames`` policy) and no-final-newline files
   are supported. Binary/symlink/submodule/unsupported statuses surface as explicit
   failure categories (never silently skipped).
3. ``git write-tree`` compared against ``git rev-parse <target>^{tree}``; the first
   differing path is reported on mismatch via a bounded ``git diff-tree``.

**Invariant note (M19A1A):** ``FULL_REFERENCE + common test patch == target tree`` is a
NECESSARY source-integrity invariant, NOT sufficient to prove the test/non-test split.
The split is asserted separately against census flags (M19A1A ``verify_split_invariants``
plus a redundant census-header self-consistency check: ``n_test``/``n_changed`` and
per-status test counts must equal the per-path flags). Tree equality with a wrong split
is recorded ``classification_reconciled=false`` and fails the gate.

Plan mode (``--mode plan``) resolves the frozen per-arm prediction sources at their
AUTHORITATIVE arm-specific locations (R1 registry via ``opws_phase2_plan``; R2 sources
pinned to the frozen R2 tag for BM25/Dense), records scope hash / reference patch SHA256
/ test contract hash / effective reconstructed tree OID per (arm, task), and counts
three measures (unique patch-byte SHA; unique effective tree OID; original frozen
five-field physical-execution identity, unchanged) only over complete validated
records, reporting missing records separately. A missing frozen prediction source is a
hard blocker (``PREDICTION_SOURCE_MISSING``), never a silent zero.

Usage
-----
    python scripts/opws_m19a1b_tree_audit.py --repo <source-repo> \
        --saleor-git <OWNER_SALEOR_GIT_PATH> --out <outside-repo-dir> --mode tree \
        [--rename-sides-json <file>]
    python scripts/opws_m19a1b_tree_audit.py ... --mode all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_BOOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_BOOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_BOOT))

from scripts import opws_build as ob  # noqa: E402
from scripts import opws_phase2_plan as p2  # noqa: E402
from scripts import opws_phase3b_patch_materialize as m  # noqa: E402
from scripts.opws_phase3b_patch_materialize import (  # noqa: E402
    GitCommandError,
    GitObjectIdentityError,
    MaterializationResult,
    MaterializerError,
    TestClassificationAuthorityError,
    TestPathAuthority,
    _git_env,
    census_records_to_authority,
    git_capture,
    materialize_full_reference,
    materialize_scoped_reference_patch,
    verify_ref_commit,
)

# ------------------------------------------------------------------ constants
TREE_RECEIPT_SCHEMA = "opws-m19a1b-full-reference-tree-receipt/1.0"
PLAN_SCHEMA = "opws-m19a1b-effective-patch-plan/1.0"
TREE_RECEIPT_NAME = "FULL_REFERENCE_TREE_RECEIPT_219.json"
PLAN_RECEIPT_NAME = "EFFECTIVE_PATCH_PLAN_219.json"

FIXED_GIB = 1024.0**3
DEFAULT_MIN_FREE_GIB = 31.0  # 30 GiB workspace + 1 GiB reserve (mission guard)
SUBPROC_TIMEOUT_S = 600
BOUNDED_STDOUT_BYTES = 8 * 1024 * 1024
MAX_FIRST_DIFF_PATHS = 8

# Frozen R2 provenance for BM25/Dense arm sources (tag -> peeled commit).
R2_TAG = "m17-comp-baselines-r2-frozen-2026-10-12"
R2_PEELED = "6c2f698154ddcba22ff7d9a85656753a6eaee5ff"

# Reference-derived arms may select ADDED / R_NEW paths (frozen R1 primary treatment);
# parent-only selector arms never may.
ALLOW_ADDED_ARMS = frozenset({"GOLD", "SELECT_ALL", "FULL_REFERENCE"})

# Census header fields subject to the redundant per-path flag self-consistency check.
CENSUS_FLAG_COUNT_FIELDS: tuple[tuple[str, Callable[[dict[str, Any]], bool] | None], ...] = (
    ("n_changed", None),
    ("n_test", lambda r: bool(r.get("test_file"))),
    ("n_test_added", lambda r: bool(r.get("test_file")) and r.get("status") == "added"),
    ("n_test_modified", lambda r: bool(r.get("test_file")) and r.get("status") == "modified"),
    ("n_test_deleted", lambda r: bool(r.get("test_file")) and r.get("status") == "deleted"),
    ("n_migration", lambda r: bool(r.get("migration_file"))),
    ("n_config_or_infra", lambda r: bool(r.get("config_or_infra"))),
)


# ------------------------------------------------------------------ errors
class M19A1BError(RuntimeError):
    """Base class for all M19A1B engineering failures (instrumentation, never scientific)."""


class AuditConfigError(M19A1BError):
    """Invalid or unsupported run configuration (fail closed)."""


class AuthorityError(M19A1BError):
    """Missing or inconsistent frozen test-path / rename authority."""


class ReconstructionError(M19A1BError):
    """Git temp-index reconstruction failure (apply / write-tree / compare)."""


class OutDirError(M19A1BError):
    """Output directory placement violation (must be outside the source repository)."""


# ------------------------------------------------------------------ helpers
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_git(
    args: list[str],
    *,
    env: dict[str, str],
    inputs: bytes | None = None,
    max_bytes: int = BOUNDED_STDOUT_BYTES,
    timeout: int = SUBPROC_TIMEOUT_S,
    context: str,
) -> bytes:
    """Bounded ``subprocess.run(..., shell=False)`` wrapper with explicit env."""
    try:
        proc = subprocess.run(
            args,
            input=inputs,
            check=False,
            capture_output=True,
            env=env,
            timeout=timeout,
        )
    except OSError as exc:
        raise GitCommandError(f"{context}: could not invoke git: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitCommandError(f"{context}: git timed out after {timeout}s") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise GitCommandError(f"{context}: git {' '.join(args[:4])}... rc={proc.returncode}: {stderr[:600]}")
    if len(proc.stdout) > max_bytes:
        raise GitCommandError(
            f"{context}: git output exceeded bound ({len(proc.stdout)} > {max_bytes} bytes)"
        )
    return proc.stdout


def _rmtree_retry(path: Path) -> None:
    """Windows-safe temp-dir removal (git subprocesses can transiently lock files)."""
    for _ in range(6):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            time.sleep(0.4)
    shutil.rmtree(path, ignore_errors=True)


def _head(repo: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=False, capture_output=True, env=_git_env(), timeout=60,
        )
    except OSError:
        return "UNKNOWN"
    if proc.returncode != 0:
        return "UNKNOWN"
    return proc.stdout.decode("ascii", "replace").strip()


def _validate_out_dir(out_dir: Path, repo: Path, saleor_git: Path) -> None:
    """Require receipts OUTSIDE the source repository and OUTSIDE the Saleor store."""
    for label, other in (("source repository", repo.resolve()), ("Saleor store", saleor_git.resolve())):
        try:
            common = Path(os.path.commonpath([str(out_dir.resolve()), str(other)]))
        except ValueError:  # different drives
            continue
        if str(common) == str(out_dir.resolve()) or str(other) == str(out_dir.resolve()):
            raise OutDirError(
                f"--out {out_dir} must be OUTSIDE the {label} ({other}); refusing to write receipts there"
            )


# ------------------------------------------------------------------ GitStore
@dataclass(frozen=True)
class GitStore:
    """Read-only access to the owner-provided Saleor Git object store.

    Resolves the real object directory for ordinary clones AND bare repositories and
    follows ``objects/info/alternates`` (bounded recursion). Fail-closed on any layout
    that cannot be resolved. Never written to.
    """

    root: Path
    git_dir_abs: Path
    common_dir_abs: Path
    object_dirs: tuple[Path, ...]

    @classmethod
    def open(cls, saleor_git: Path) -> GitStore:
        m.verify_repository(saleor_git)
        env = _git_env()
        try:
            git_dir = _run_git(
                ["git", "-C", str(saleor_git), "rev-parse", "--path-format=absolute", "--git-dir"],
                env=env,
                context="GitStore.open",
            ).decode("utf-8", "replace").strip()
            common = _run_git(
                ["git", "-C", str(saleor_git), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                env=env,
                context="GitStore.open",
            ).decode("utf-8", "replace").strip()
        except GitCommandError as exc:
            raise AuditConfigError(f"saleor-git layout unsupported (fail closed): {exc}") from exc
        if not git_dir or not common:
            raise AuditConfigError("saleor-git layout unsupported: empty git-dir/common-dir (fail closed)")
        gd = Path(git_dir).resolve()
        cd = Path(common).resolve()
        seen: list[Path] = []
        for cand in (cd / "objects", gd / "objects"):
            if cand.is_dir() and cand not in seen:
                seen.append(cand)
        if not seen:
            raise AuditConfigError(
                f"saleor-git layout unsupported: no objects directory under {gd} or {cd} (fail closed)"
            )
        object_dirs = cls._expand_alternates(tuple(seen))
        return cls(root=saleor_git.resolve(), git_dir_abs=gd, common_dir_abs=cd, object_dirs=object_dirs)

    @staticmethod
    def _expand_alternates(object_dirs: tuple[Path, ...], depth: int = 8) -> tuple[Path, ...]:
        out: list[Path] = []
        queue = list(object_dirs)
        for _ in range(depth):
            if not queue:
                break
            odir = queue.pop(0)
            if odir in out:
                continue
            out.append(odir)
            alt_file = odir / "info" / "alternates"
            if not alt_file.is_file():
                continue
            try:
                text = alt_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                alt = Path(line).expanduser()
                if not alt.is_absolute():
                    alt = odir / alt
                alt = alt.resolve()
                if alt.is_dir() and alt not in out and alt not in queue:
                    queue.append(alt)
        return tuple(out)

    def hermetic_env(self) -> dict[str, str]:
        env = _git_env()
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = ""
        return env

    def resolve_commit(self, ref: str, label: str) -> str:
        return verify_ref_commit(self.root, ref, label)

    def tree_oid(self, ref: str) -> str:
        stdout = git_capture(self.root, "rev-parse", "--verify", f"{ref}^{{tree}}")
        tree = stdout.decode("ascii").strip()
        if len(tree) != 40:
            raise GitObjectIdentityError(f"tree oid not a full 40-hex sha: {tree!r}")
        return tree

    def detect_rename_pairs(self, parent: str, target: str) -> list[tuple[str, str, int]]:
        """Old/new rename detection (PATH identity only, ``-M`` 50% similarity).

        Patch bytes never depend on this heuristic (the single ``git_diff_bytes``
        producer stays ``--no-renames``); it only establishes WHICH paths form a pair so
        the census rename record can be expanded with explicit per-side flags.
        """
        args: list[str] = [
            "git", "-C", str(self.root), *m.DIFF_SETTINGS, "diff", "--name-status", "-z", "-M",
            parent, target,
        ]
        stdout = _run_git(args, env=self.hermetic_env(), context="GitStore.detect_rename_pairs")
        fields = stdout.split(b"\x00")
        pairs: list[tuple[str, str, int]] = []
        i = 0
        while i < len(fields):
            raw = fields[i]
            if not raw:
                i += 1
                continue
            token = raw.decode("utf-8", "replace")
            if token.startswith("R"):
                if i + 2 >= len(fields):
                    raise ReconstructionError(f"truncated rename record {raw!r}")
                old = fields[i + 1].decode("utf-8", "replace")
                new = fields[i + 2].decode("utf-8", "replace")
                score = 100
                if token[1:].isdigit():
                    score = int(token[1:])
                pairs.append((old, new, score))
                i += 3
                continue
            i += 2  # A/D/M/T/... one path field follows
        return pairs

# ------------------------------------------------------------------ reconstruction workspace
@dataclass
class ReconstructedTree:
    tree_oid: str | None
    exact_equal: bool
    first_diff_paths: list[str]
    apply_error: str | None
    peak_temp_bytes: int


class ReconstructionWorkspace:
    """Isolated temp Git index + object store; writes NEVER reach the real cache.

    Layout (all inside one temp dir created outside the Saleor store): ``gitdir/``
    (minimal bare repo context), ``index.base`` (parent tree index), ``index.work``
    (per-record working index), ``objects/`` (``GIT_OBJECT_DIRECTORY``). Real objects
    are readable ONLY through ``GIT_ALTERNATE_OBJECT_DIRECTORIES``.
    """

    def __init__(self, tmp_parent: Path, store: GitStore, *, min_free_gib: float) -> None:
        free = shutil.disk_usage(tmp_parent).free / FIXED_GIB
        if free < min_free_gib:
            raise AuditConfigError(
                f"workspace free space {free:.2f} GiB < {min_free_gib:.1f} GiB guard "
                "(30 GiB + 1 GiB reserve); refusing to run (fail closed)"
            )
        self.tmp = Path(tempfile.mkdtemp(prefix="opws_m19a1b_", dir=str(tmp_parent)))
        self.gitdir = self.tmp / "gitdir"
        self.gitdir.mkdir()
        # BINARY writes: Path.write_text translates \n -> \r\n on Windows and a CR
        # inside the HEAD ref (or config file) would corrupt the isolated repository.
        (self.gitdir / "HEAD").write_bytes(b"ref: refs/heads/m19a1b\n")
        (self.gitdir / "objects").mkdir()
        (self.gitdir / "refs").mkdir()
        (self.gitdir / "config").write_bytes(b"[core]\n\tbare = true\n")
        self.index_base = self.tmp / "index.base"
        self.index_work = self.tmp / "index.work"
        self.objects = self.tmp / "objects"
        self.objects.mkdir()  # GIT_OBJECT_DIRECTORY must exist or git rejects the repository
        self.peak_bytes = 0
        self._store = store

    def _env(self, index: Path) -> dict[str, str]:
        env = _git_env()
        env["GIT_DIR"] = str(self.gitdir)
        env["GIT_INDEX_FILE"] = str(index)
        env["GIT_OBJECT_DIRECTORY"] = str(self.objects)
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.pathsep.join(
            [str(d) for d in self._store.object_dirs]
        )
        env.pop("GIT_WORK_TREE", None)
        env.pop("GIT_COMMON_DIR", None)
        return env

    def _git(self, index: Path, *args: str, inputs: bytes | None = None) -> bytes:
        cmd: list[str] = ["git"]
        cmd.extend(m.DIFF_SETTINGS)
        cmd.extend(args)
        out = _run_git(cmd, env=self._env(index), inputs=inputs, context="ReconstructionWorkspace")
        self._sample_peak()
        return out

    def _sample_peak(self) -> None:
        total = 0
        for dirpath, _dirnames, filenames in os.walk(self.tmp):
            for name in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    continue
        self.peak_bytes = max(self.peak_bytes, total)

    def load_parent_index(self, parent_tree: str) -> None:
        """``git read-tree <parent>`` into the base index (no checkout)."""
        self._git(self.index_base, "read-tree", parent_tree)

    def apply_patch(self, index: Path, patch: bytes) -> None:
        """``git apply --cached``; empty patches are explicit no-ops (never errors)."""
        if not patch:
            return
        self._git(index, "apply", "--cached", "--whitespace=nowarn", "-", inputs=patch)

    def write_tree(self, index: Path) -> str:
        stdout = self._git(index, "write-tree")
        tree = stdout.decode("ascii").strip()
        if len(tree) != 40:
            raise ReconstructionError(f"write-tree did not return a 40-hex oid: {tree!r}")
        return tree

    def diff_trees(self, tree_a: str, tree_b: str, limit: int = MAX_FIRST_DIFF_PATHS) -> list[str]:
        """First differing path(s) between two trees (bounded), via the isolated env.

        Must run inside this env: the reconstructed tree objects live in the TEMP object
        store (never in the real Saleor store), so the comparison needs both stores.
        """
        args: list[str] = [
            "diff-tree", "-r", "--name-status", "-z", "--no-renames", "--no-ext-diff",
            tree_a, tree_b,
        ]
        stdout = self._git(self.index_work, *args) if tree_a and tree_b else b""
        fields = stdout.split(b"\x00")
        out: list[str] = []
        i = 0
        while i < len(fields) and len(out) < limit:
            raw = fields[i]
            if not raw:
                i += 1
                continue
            token = raw.decode("utf-8", "replace")
            if token.startswith("R"):
                if i + 2 < len(fields):
                    out.append(fields[i + 1].decode("utf-8", "replace"))
                    out.append(fields[i + 2].decode("utf-8", "replace"))
                i += 3
                continue
            if i + 1 < len(fields):
                out.append(fields[i + 1].decode("utf-8", "replace"))
            i += 2
        return out[:limit]

    def reconstruct(self, parent_tree: str, test_patch: bytes, reference_patch: bytes) -> ReconstructedTree:
        """read-tree parent -> apply COMMON TEST patch exactly once -> apply FULL_REFERENCE."""
        apply_error: str | None = None
        tree_oid: str | None = None
        try:
            self.load_parent_index(parent_tree)
            shutil.copyfile(self.index_base, self.index_work)
            self.apply_patch(self.index_work, test_patch)
            self.apply_patch(self.index_work, reference_patch)
            tree_oid = self.write_tree(self.index_work)
        except GitCommandError as exc:
            apply_error = f"GIT_APPLY_FAILED: {exc}"
        return ReconstructedTree(
            tree_oid=tree_oid,
            exact_equal=False,
            first_diff_paths=[],
            apply_error=apply_error,
            peak_temp_bytes=self.peak_bytes,
        )

    def cleanup(self) -> None:
        if self.tmp.exists():
            _rmtree_retry(self.tmp)


# ------------------------------------------------------------------ frozen census
@dataclass
class CensusTaskView:
    """Frozen census record for one task (raw records + header counts)."""

    task_id: str
    records: list[dict[str, Any]]
    header: dict[str, Any]
    source_path: Path
    source_sha256: str

    def self_consistency(self) -> dict[str, bool]:
        """Independent assertion against census flags (redundant header cross-check).

        A deliberately or accidentally wrong flag changes the header counts, so this
        catches a wrong test/non-test split even when FULL_REFERENCE + test patch still
        reproduces the target tree (tree equality is necessary, not sufficient).
        """
        checks: dict[str, bool] = {}
        for item, pred in CENSUS_FLAG_COUNT_FIELDS:
            header_val = self.header.get(item)
            derived = len(self.records) if pred is None else sum(1 for rec in self.records if pred(rec))
            checks[f"{item}_equals_flag_derived"] = header_val == derived
        checks["all_header_counts_consistent"] = all(checks.values())
        return checks


def load_census(repo: Path) -> tuple[dict[str, CensusTaskView], Path, str]:
    census_path = repo / "research" / "wp2" / "wp2_saleor_main297_census_2026-09-22.json"
    if not census_path.is_file():
        raise AuthorityError(f"frozen census missing: {census_path} (TEST_CLASSIFICATION_AUTHORITY_MISSING)")
    data = json.loads(census_path.read_text(encoding="utf-8"))
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise AuthorityError(f"frozen census has no 'tasks' list: {census_path}")
    views: dict[str, CensusTaskView] = {}
    for rec in tasks:
        tid = rec.get("task_id")
        records = rec.get("changed_paths", [])
        if not isinstance(tid, str) or not isinstance(records, list):
            raise AuthorityError(f"census task record malformed: {rec!r}")
        views[tid] = CensusTaskView(
            task_id=tid,
            records=records,
            header=dict(rec),
            source_path=census_path,
            source_sha256=sha256_file(census_path),
        )
    return views, census_path, sha256_file(census_path)


def load_manifest(repo: Path) -> tuple[dict[str, dict[str, Any]], Path, str]:
    manifest_path = repo / "research" / "opws" / "binding" / "OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json"
    if not manifest_path.is_file():
        raise AuthorityError(f"frozen manifest missing: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    per_task = data.get("per_task")
    if not isinstance(per_task, list):
        raise AuthorityError(f"frozen manifest has no 'per_task' list: {manifest_path}")
    by_id: dict[str, dict[str, Any]] = {}
    for rec in per_task:
        tid = rec.get("task_id")
        if not isinstance(tid, str):
            raise AuthorityError(f"manifest task record has no task_id: {rec!r}")
        by_id[tid] = rec
    return by_id, manifest_path, sha256_file(manifest_path)


# ------------------------------------------------------------------ rename side authority
@dataclass(frozen=True)
class RenameSideAuthority:
    """Explicit per-side rename authority (owner-provided, M19A1A protocol)."""

    task_id: str
    old: str
    new: str
    old_is_test: bool
    new_is_test: bool


def load_rename_sides(path: Path | None) -> dict[str, RenameSideAuthority]:
    """Optional explicit per-side rename flag table ``{"tasks": {task_id: {...}}}``."""
    out: dict[str, RenameSideAuthority] = {}
    if path is None:
        return out
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, dict):
        raise AuditConfigError(
            '--rename-sides-json needs {"tasks": {task_id: {old, new, old_is_test, new_is_test}}}'
        )
    for tid, spec in tasks.items():
        if not isinstance(spec, dict):
            raise AuditConfigError(f"rename-sides record for {tid!r} must be an object")
        old = spec.get("old")
        new = spec.get("new")
        old_flag = spec.get("old_is_test")
        new_flag = spec.get("new_is_test")
        if not isinstance(old, str) or not isinstance(new, str) \
                or not isinstance(old_flag, bool) or not isinstance(new_flag, bool):
            raise AuditConfigError(
                f"rename-sides record for {tid!r} must provide old/new strings and boolean flags"
            )
        out[str(tid)] = RenameSideAuthority(
            task_id=str(tid), old=old, new=new, old_is_test=old_flag, new_is_test=new_flag
        )
    return out


@dataclass
class ResolvedAuthority:
    """Authority resolution outcome for one task (shared by tree and plan modes)."""

    authority: TestPathAuthority | None
    error_type: str | None
    error_detail: str
    rename_pair: list[str] | None
    rename_crosses_test_boundary: bool
    rename_side_authority_resolved: bool


def resolve_task_authority(
    *,
    task_id: str,
    view: CensusTaskView,
    store: GitStore,
    parent: str,
    target: str,
    rename_sides: dict[str, RenameSideAuthority],
) -> ResolvedAuthority:
    """M19A1A canonical test-path authority with explicit rename-side handling.

    Rename sides are ALWAYS explicit: old/new path identity comes from git ``-M``
    detection (path facts of the object store, never filename guesses); per-side TEST
    flags can only come from the owner-provided rename-sides table. A boundary-crossing
    pair records ``RENAME_CROSSES_TEST_BOUNDARY`` (STOP the task, keep it in the 219
    denominator).
    """
    census_renamed = [r for r in view.records if r.get("status") == "renamed"]
    git_pairs = store.detect_rename_pairs(parent, target)
    rename_pair = [p for pair in git_pairs for p in (pair[0], pair[1])] or None
    rename_side_map: dict[str, tuple[str, str, bool, bool]] | None = None
    if git_pairs:
        if len(git_pairs) > 1:
            return ResolvedAuthority(None, "MULTIPLE_RENAME_PAIRS",
                                     f"git detected {len(git_pairs)} rename pairs in one task",
                                     rename_pair, False, False)
        old, new, _score = git_pairs[0]
        if not census_renamed:
            return ResolvedAuthority(
                None, "INCONSISTENT_RENAME_DETECTED",
                f"git -M detected rename {old} -> {new} but census has no 'renamed' record "
                "(fail closed; census/git disagreement)",
                rename_pair, False, False,
            )
        pair_head = str(census_renamed[0]["path"])
        side = rename_sides.get(task_id)
        if side is None:
            return ResolvedAuthority(
                None, "RENAMED_SIDE_AUTHORITY_MISSING",
                f"census 'renamed' record {pair_head!r} lacks explicit per-side flag authority "
                f"(detected git pair {old} -> {new}); supply --rename-sides-json "
                "(RENAMED_SIDE_AUTHORITY_MISSING; sides never guessed)",
                rename_pair, False, False,
            )
        if {side.old, side.new} != {old, new}:
            return ResolvedAuthority(
                None, "RENAME_SIDE_AUTHORITY_CONFLICT",
                f"provided sides ({side.old!r}, {side.new!r}) disagree with git -M pair ({old!r}, {new!r})",
                rename_pair, False, True,
            )
        if side.old_is_test != side.new_is_test:
            cross = (
                f"rename {side.old} -> {side.new} crosses the test/non-test boundary "
                f"(old_is_test={side.old_is_test}, new_is_test={side.new_is_test}); STOP this task; "
                "stays in the 219 denominator (no scientific exclusion)"
            )
            return ResolvedAuthority(None, "RENAME_CROSSES_TEST_BOUNDARY", cross,
                                     rename_pair, True, True)
        rename_side_map = {pair_head: (side.old, side.new, side.old_is_test, side.new_is_test)}
    elif census_renamed:
        return ResolvedAuthority(
            None, "RENAMED_PAIR_NOT_DETECTED",
            f"census 'renamed' record {census_renamed[0].get('path')!r} but git -M found no pair "
            "(fail closed; pair identity cannot be established)",
            rename_pair, False, False,
        )
    try:
        if rename_side_map is None:
            authority = census_records_to_authority(view.records)
        else:
            authority = census_records_to_authority(view.records, rename_sides=rename_side_map)
    except TestClassificationAuthorityError as exc:
        return ResolvedAuthority(None, "CLASSIFICATION_AUTHORITY_MISSING", str(exc),
                                 rename_pair, False, rename_side_map is not None)
    return ResolvedAuthority(
        authority=authority, error_type=None, error_detail="", rename_pair=rename_pair,
        rename_crosses_test_boundary=False,
        rename_side_authority_resolved=rename_side_map is not None,
    )


# ------------------------------------------------------------------ tree-mode per-task audit
@dataclass
class TaskAuditRecord:
    """One 219-denominator task audit record (tree mode)."""

    task_id: str
    parent_commit: str
    target_commit: str
    parent_resolved: str | None
    target_resolved: str | None
    target_tree_oid: str | None
    reconstructed_tree_oid: str | None
    exact_equal: bool | None
    status: str
    error_type: str | None
    error_detail: str
    authority_sha256: str | None
    rename_pair: list[str] | None
    rename_crosses_test_boundary: bool
    rename_side_authority_resolved: bool
    changed_paths: list[str]
    changed_test_paths: list[str]
    changed_nontest_paths: list[str]
    disjoint: bool
    union_equals_all_changed_paths: bool
    split_invariants: dict[str, bool]
    census_self_consistency: dict[str, bool]
    classification_reconciled: bool
    test_patch_sha256: str | None
    full_reference_patch_sha256: str | None
    test_patch_bytes: int
    full_reference_patch_bytes: int
    changed_test_file_count: int
    changed_nontest_file_count: int
    peak_temp_bytes: int
    apply_error: str | None
    first_diff_paths: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_commit": self.parent_commit,
            "target_commit": self.target_commit,
            "parent_resolved": self.parent_resolved,
            "target_resolved": self.target_resolved,
            "target_tree_oid": self.target_tree_oid,
            "reconstructed_tree_oid": self.reconstructed_tree_oid,
            "exact_equal": self.exact_equal,
            "status": self.status,
            "error_type": self.error_type,
            "error_detail": self.error_detail,
            "authority_sha256": self.authority_sha256,
            "rename_pair": list(self.rename_pair) if self.rename_pair else None,
            "rename_crosses_test_boundary": self.rename_crosses_test_boundary,
            "rename_side_authority_resolved": self.rename_side_authority_resolved,
            "changed_paths": sorted(self.changed_paths),
            "changed_test_paths": sorted(self.changed_test_paths),
            "changed_nontest_paths": sorted(self.changed_nontest_paths),
            "disjoint": self.disjoint,
            "union_equals_all_changed_paths": self.union_equals_all_changed_paths,
            "split_invariants": dict(self.split_invariants),
            "census_self_consistency": dict(self.census_self_consistency),
            "classification_reconciled": self.classification_reconciled,
            "test_patch_sha256": self.test_patch_sha256,
            "full_reference_patch_sha256": self.full_reference_patch_sha256,
            "test_patch_bytes": self.test_patch_bytes,
            "full_reference_patch_bytes": self.full_reference_patch_bytes,
            "changed_test_file_count": self.changed_test_file_count,
            "changed_nontest_file_count": self.changed_nontest_file_count,
            "peak_temp_bytes": self.peak_temp_bytes,
            "apply_error": self.apply_error,
            "first_diff_paths": self.first_diff_paths,
        }


def _empty_audit(task_id: str, parent: str, target: str) -> TaskAuditRecord:
    return TaskAuditRecord(
        task_id=task_id, parent_commit=parent, target_commit=target,
        parent_resolved=None, target_resolved=None, target_tree_oid=None,
        reconstructed_tree_oid=None, exact_equal=None, status="ERROR", error_type=None,
        error_detail="", authority_sha256=None, rename_pair=None,
        rename_crosses_test_boundary=False, rename_side_authority_resolved=False,
        changed_paths=[], changed_test_paths=[], changed_nontest_paths=[], disjoint=True,
        union_equals_all_changed_paths=True, split_invariants={}, census_self_consistency={},
        classification_reconciled=False, test_patch_sha256=None, full_reference_patch_sha256=None,
        test_patch_bytes=0, full_reference_patch_bytes=0, changed_test_file_count=0,
        changed_nontest_file_count=0, peak_temp_bytes=0, apply_error=None, first_diff_paths=[],
    )


def _failed(rec: TaskAuditRecord, error_type: str, detail: str) -> TaskAuditRecord:
    rec.status = "ERROR"
    rec.error_type = error_type
    rec.error_detail = detail[:2000]
    rec.classification_reconciled = False
    return rec


def audit_task(
    *,
    task_id: str,
    manifest_rec: dict[str, Any],
    census: dict[str, CensusTaskView],
    store: GitStore,
    workspace_factory: Callable[[], ReconstructionWorkspace],
    rename_sides: dict[str, RenameSideAuthority],
    census_sha256: str,
    reconcile_only: bool = False,
) -> TaskAuditRecord:
    """Audit ONE bound task: authority -> split invariants -> FULL_REFERENCE reconstruction.

    ``reconcile_only=True`` (plan mode internal) computes authority + split invariants
    WITHOUT tree reconstruction.
    """
    parent_raw = manifest_rec.get("parent_commit")
    target_raw = manifest_rec.get("target_commit")
    if not isinstance(parent_raw, str) or not isinstance(target_raw, str):
        rec = _empty_audit(task_id, str(parent_raw or ""), str(target_raw or ""))
        return _failed(rec, "MALFORMED_MANIFEST_RECORD", "parent/target commits missing from manifest")
    rec = _empty_audit(task_id, parent_raw, target_raw)
    view = census.get(task_id)
    if view is None:
        return _failed(rec, "CENSUS_TASK_MISSING",
                       "task not found in frozen census (TEST_CLASSIFICATION_AUTHORITY_MISSING)")
    rec.authority_sha256 = census_sha256

    try:
        parent = store.resolve_commit(parent_raw, "parent")
        target = store.resolve_commit(target_raw, "target")
    except (GitObjectIdentityError, GitCommandError) as exc:
        return _failed(rec, "OBJECT_MISSING", str(exc)[:2000])
    rec.parent_resolved = parent
    rec.target_resolved = target
    try:
        rec.target_tree_oid = store.tree_oid(target)
    except GitObjectIdentityError as exc:
        return _failed(rec, "TARGET_TREE_UNRESOLVED", str(exc)[:2000])

    resolved = resolve_task_authority(
        task_id=task_id, view=view, store=store, parent=parent, target=target,
        rename_sides=rename_sides,
    )
    rec.rename_pair = resolved.rename_pair
    rec.rename_crosses_test_boundary = resolved.rename_crosses_test_boundary
    rec.rename_side_authority_resolved = resolved.rename_side_authority_resolved
    if resolved.authority is None:
        if resolved.error_type == "RENAME_CROSSES_TEST_BOUNDARY":
            rec.status = "STOPPED"
            rec.error_type = resolved.error_type
            rec.error_detail = resolved.error_detail
            return rec
        return _failed(rec, str(resolved.error_type), resolved.error_detail or "")

    authority = resolved.authority
    rec.changed_paths = sorted(authority.changed_paths)
    rec.changed_test_paths = sorted(authority.test_paths)
    rec.changed_nontest_paths = sorted(authority.changed_paths - authority.test_paths)
    rec.changed_test_file_count = len(rec.changed_test_paths)
    rec.changed_nontest_file_count = len(rec.changed_nontest_paths)

    census_self = view.self_consistency()
    rec.census_self_consistency = census_self

    try:
        result = materialize_full_reference(
            task_id=task_id,
            repo=store.root,
            parent_commit=parent,
            target_commit=target,
            test_path_authority=authority,
        )
    except TestClassificationAuthorityError as exc:
        return _failed(rec, "CLASSIFICATION_AUTHORITY_MISMATCH", str(exc)[:2000])
    except (MaterializerError, GitCommandError) as exc:
        return _failed(rec, "MATERIALIZATION_FAILED", str(exc)[:2000])

    rec.split_invariants = dict(result.split_invariants)
    rec.disjoint = bool(result.split_invariants.get("disjoint", False))
    rec.union_equals_all_changed_paths = bool(result.split_invariants.get("union_all_git_changed", False))
    split_clean = (
        rec.disjoint
        and rec.union_equals_all_changed_paths
        and bool(result.split_invariants.get("reference_test_free", False))
        and bool(result.split_invariants.get("test_equals_census_authoritative", False))
    )
    rec.classification_reconciled = split_clean and bool(census_self.get("all_header_counts_consistent", False))
    rec.test_patch_sha256 = result.test_patch_hash
    rec.full_reference_patch_sha256 = result.reference_patch_hash
    rec.test_patch_bytes = len(result.test_patch_bytes)
    rec.full_reference_patch_bytes = len(result.reference_patch_bytes)

    if reconcile_only:
        rec.status = "RECONSTRUCTED" if rec.classification_reconciled else "STOPPED"
        return rec

    workspace = workspace_factory()
    try:
        parent_tree = store.tree_oid(parent)
        reconstructed = workspace.reconstruct(
            parent_tree,
            bytes(result.test_patch_bytes),
            bytes(result.reference_patch_bytes),
        )
        if reconstructed.apply_error is not None:
            rec.status = "ERROR"
            rec.error_type = reconstructed.apply_error
            rec.apply_error = reconstructed.apply_error
            return rec
        rec.reconstructed_tree_oid = reconstructed.tree_oid
        rec.peak_temp_bytes = reconstructed.peak_temp_bytes
        if reconstructed.tree_oid is not None and reconstructed.tree_oid == rec.target_tree_oid:
            rec.exact_equal = True
            rec.status = "RECONSTRUCTED"
        else:
            rec.exact_equal = False
            rec.status = "ERROR"
            rec.error_type = "TARGET_TREE_MISMATCH"
            if reconstructed.tree_oid is not None and rec.target_tree_oid is not None:
                rec.first_diff_paths = workspace.diff_trees(reconstructed.tree_oid, rec.target_tree_oid)
            rec.error_detail = (
                f"reconstructed tree {reconstructed.tree_oid} != target tree {rec.target_tree_oid}; "
                f"first differing path(s): {rec.first_diff_paths}"
            )
        return rec
    except (GitCommandError, ReconstructionError, MaterializerError) as exc:
        return _failed(rec, "RECONSTRUCTION_FAILED", str(exc)[:2000])
    finally:
        workspace.cleanup()


# ------------------------------------------------------------------ tree-mode run + receipt
@dataclass
class TreeRunResult:
    records: list[TaskAuditRecord]
    summary: dict[str, Any]
    receipt_path: Path
    disk_free_start_gib: float
    disk_free_end_gib: float
    peak_temp_bytes: int


def run_tree_audit(
    *,
    repo: Path,
    saleor_git: Path,
    out_dir: Path,
    rename_sides_path: Path | None,
    min_free_gib: float,
    tmp_dir: Path | None,
    reconcile_only: bool = False,
) -> TreeRunResult:
    """Complete tree-mode audit over the 219 bound tasks. Never modifies the Saleor store."""
    _validate_out_dir(out_dir, repo, saleor_git)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_parent = tmp_dir or (out_dir / "m19a1b_tmp")
    tmp_parent.mkdir(parents=True, exist_ok=True)

    store = GitStore.open(saleor_git)
    manifest, _manifest_path, manifest_sha = load_manifest(repo)
    census_views, census_path, census_sha = load_census(repo)
    rename_sides = load_rename_sides(rename_sides_path)

    disk_free_start = shutil.disk_usage(tmp_parent).free / FIXED_GIB
    peak_total = 0
    records: list[TaskAuditRecord] = []

    def workspace_factory() -> ReconstructionWorkspace:
        return ReconstructionWorkspace(tmp_parent, store, min_free_gib=min_free_gib)

    for rec_meta in manifest.values():
        tid = rec_meta["task_id"]
        rec = audit_task(
            task_id=tid,
            manifest_rec=rec_meta,
            census=census_views,
            store=store,
            workspace_factory=workspace_factory,
            rename_sides=rename_sides,
            census_sha256=census_sha,
            reconcile_only=reconcile_only,
        )
        peak_total = max(peak_total, rec.peak_temp_bytes)
        records.append(rec)

    disk_free_end = shutil.disk_usage(tmp_parent).free / FIXED_GIB
    summary = build_tree_summary(
        records=records,
        manifest_sha256=manifest_sha,
        census_path=census_path,
        census_sha256=census_sha,
        materializer_path=Path(m.__file__),
        materializer_sha256=sha256_file(Path(m.__file__)),
        head=_head(repo),
        saleor_git_dir=str(store.git_dir_abs),
        saleor_common_dir=str(store.common_dir_abs),
        disk_free_start=disk_free_start,
        disk_free_end=disk_free_end,
        peak_temp_bytes=peak_total,
        min_free_gib=min_free_gib,
    )
    receipt = out_dir / TREE_RECEIPT_NAME
    receipt.write_text(_canonical_json(summary) + "\n", encoding="utf-8")
    return TreeRunResult(
        records=records,
        summary=summary,
        receipt_path=receipt,
        disk_free_start_gib=disk_free_start,
        disk_free_end_gib=disk_free_end,
        peak_temp_bytes=peak_total,
    )


def build_tree_summary(
    *,
    records: list[TaskAuditRecord],
    manifest_sha256: str,
    census_path: Path,
    census_sha256: str,
    materializer_path: Path,
    materializer_sha256: str,
    head: str,
    saleor_git_dir: str,
    saleor_common_dir: str,
    disk_free_start: float,
    disk_free_end: float,
    peak_temp_bytes: int,
    min_free_gib: float,
) -> dict[str, Any]:
    n_exact = sum(1 for r in records if r.exact_equal is True)
    n_reconciled = sum(1 for r in records if r.classification_reconciled)
    n_stopped = sum(1 for r in records if r.status == "STOPPED")
    n_errors = sum(1 for r in records if r.status == "ERROR")
    errors_by_type: dict[str, list[str]] = {}
    for r in records:
        if r.status == "ERROR" and r.error_type:
            errors_by_type.setdefault(str(r.error_type), []).append(r.task_id)
    per_task = [r.as_dict() for r in records]
    per_task.sort(key=lambda d: str(d["task_id"]))
    total = len(records)
    return {
        "schema": TREE_RECEIPT_SCHEMA,
        "artifact": "FULL_REFERENCE_TREE_RECEIPT_219",
        "created_at": _now_iso(),
        "git_state": {
            "repo_head": head,
            "saleor_git_dir": saleor_git_dir,
            "saleor_git_common_dir": saleor_common_dir,
        },
        "inputs": {
            "manifest": "research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json",
            "manifest_sha256": manifest_sha256,
            "census": str(census_path),
            "census_sha256": census_sha256,
            "materializer_module": str(materializer_path),
            "materializer_module_sha256": materializer_sha256,
        },
        "summary": {
            "denominator_tasks": total,
            "n_reconstructed_exact": n_exact,
            "n_classification_reconciled": n_reconciled,
            "n_stopped_rename_boundary": n_stopped,
            "n_errors": n_errors,
            "errors_by_type": errors_by_type,
            "disk_free_gib": {
                "start": round(disk_free_start, 3),
                "end": round(disk_free_end, 3),
                "guard_min": min_free_gib,
            },
            "peak_temp_bytes": peak_temp_bytes,
            "REAL_TASK_BEHAVIORAL_OUTCOMES": 0,
        },
        "exit_gate": {
            "reconstructed_219_219": n_exact == total,
            "authority_reconciled_219_219": n_reconciled == total,
            "pass": n_exact == total and n_reconciled == total,
        },
        "per_task": per_task,
    }


# ------------------------------------------------------------------ plan mode
PLAN_EXTRA_ARMS = ("NEG", "FULL_REFERENCE")


@dataclass
class PlanArmStatus:
    arm_id: str
    scope_source: str | None
    source_sha256: str | None
    provenance: dict[str, Any]
    status: str  # AVAILABLE | MISSING | DEFERRED
    blocker: str | None
    complete: int
    partial: int
    missing_records: int
    per_task: list[dict[str, Any]] = field(default_factory=list)


def _materialize_scoped(
    *,
    task_id: str,
    store: GitStore,
    parent: str,
    target: str,
    scope: list[str],
    classification: dict[str, str],
    authority: TestPathAuthority,
    allow_added: bool,
) -> MaterializationResult:
    try:
        return materialize_scoped_reference_patch(
            task_id=task_id,
            repo=store.root,
            parent_commit=parent,
            target_commit=target,
            scope_paths=scope,
            classification=classification,
            test_path_authority=authority,
            allow_added=allow_added,
        )
    except (TestClassificationAuthorityError, MaterializerError, GitCommandError) as exc:
        raise ReconstructionError(f"scope materialization failed for {task_id}: {exc}") from exc


def _build_plan_records_for_arm(
    *,
    arm_id: str,
    scope_map: dict[str, list[str]],
    task_ids: list[str],
    manifest: dict[str, dict[str, Any]],
    store: GitStore,
    workspace: ReconstructionWorkspace,
    authorities: dict[str, TestPathAuthority],
    full_ref_results: dict[str, MaterializationResult],
    contract_by_task: dict[str, str],
) -> list[dict[str, Any]]:
    """Per-(arm, task) records: scope hash, reference patch SHA256, contract, tree OID.

    Effective tree = parent + COMMON TEST patch (exactly once) + THIS arm's reference
    patch, reconstructed in the isolated workspace. No cross-arm reuse.
    """
    allow_added = arm_id in ALLOW_ADDED_ARMS
    records: list[dict[str, Any]] = []
    for tid in task_ids:
        base: dict[str, Any] = {
            "arm_id": arm_id, "task_id": tid, "scope_hash": None,
            "reference_patch_sha256": None, "test_contract_hash": None,
            "effective_tree_oid": None, "status": "ERROR",
            "error_type": None, "error_detail": "",
        }
        mrec = manifest.get(tid)
        fr = full_ref_results.get(tid)
        authority = authorities.get(tid)
        if mrec is None or fr is None or authority is None:
            base["error_type"] = "AUTHORITY_OR_REFERENCE_UNAVAILABLE"
            base["error_detail"] = "census/manifest authority or reference materialization unavailable for task"
            records.append(base)
            continue
        try:
            parent = store.resolve_commit(str(mrec["parent_commit"]), "parent")
            target = store.resolve_commit(str(mrec["target_commit"]), "target")
        except (GitObjectIdentityError, GitCommandError) as exc:
            base["error_type"] = "OBJECT_MISSING"
            base["error_detail"] = str(exc)[:600]
            records.append(base)
            continue
        scope = scope_map.get(tid)
        if scope is None:
            base["error_type"] = "ARM_SCOPE_MISSING_TASK"
            records.append(base)
            continue
        scope_hash = p2.compute_canonical_scope_hash(list(scope))
        classification = {**dict(fr.reference_classification), **dict(fr.test_classification)}
        try:
            res = _materialize_scoped(
                task_id=tid, store=store, parent=parent, target=target,
                scope=scope, classification=classification, authority=authority,
                allow_added=allow_added,
            )
        except ReconstructionError as exc:
            base["error_type"] = "ARM_SCOPE_MATERIALIZATION_FAILED"
            base["error_detail"] = str(exc)[:600]
            records.append(base)
            continue
        base["scope_hash"] = scope_hash
        base["reference_patch_sha256"] = res.reference_patch_hash
        base["reference_patch_bytes"] = len(res.reference_patch_bytes)
        base["test_contract_hash"] = contract_by_task.get(tid, "UNRESOLVED")
        base["invalid_prediction_paths"] = list(res.invalid_prediction_paths)
        base["unresolved_contracts"] = list(res.unresolved_contracts)
        base["status"] = "OK" if not res.invalid_prediction_paths and not res.unresolved_contracts else "WARN"
        try:
            parent_tree = store.tree_oid(parent)
            recon = workspace.reconstruct(parent_tree, bytes(fr.test_patch_bytes), bytes(res.reference_patch_bytes))
            if recon.apply_error is not None:
                base["status"] = "ERROR"
                base["error_type"] = recon.apply_error
            else:
                base["effective_tree_oid"] = recon.tree_oid
        except (GitCommandError, ReconstructionError) as exc:
            base["status"] = "ERROR"
            base["error_type"] = "TREE_RECONSTRUCTION_FAILED"
            base["error_detail"] = str(exc)[:600]
        records.append(base)
    return records


def build_plan_receipt(
    *,
    repo: Path,
    store: GitStore,
    out_dir: Path,
    arms: list[PlanArmStatus],
    task_ids: list[str],
    env_by_task: dict[str, str],
    tree_receipt: dict[str, Any] | None,
    census_sha256: str,
) -> dict[str, Any]:
    """Assemble EFFECTIVE_PATCH_PLAN_219.json with the three announced measures."""
    complete_records: list[dict[str, Any]] = []
    missing_records: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    for arm in arms:
        for rec in arm.per_task:
            is_complete = rec.get("status") in ("OK", "WARN") and rec.get("effective_tree_oid")
            tid = str(rec["task_id"])
            if is_complete:
                complete_records.append(rec)
                identities.append(
                    {
                        "TASK_ID": tid,
                        "SCOPE_HASH": str(rec["scope_hash"]),
                        "REFERENCE_PATCH_HASH": str(rec["reference_patch_sha256"]),
                        "TEST_CONTRACT_HASH": str(rec["test_contract_hash"] or "UNRESOLVED"),
                        "ENVIRONMENT_ID": env_by_task.get(tid, "UNRESOLVED"),
                        "arm_id": str(rec["arm_id"]),
                        "record_id": f"{rec['arm_id']}:{tid}",
                        "effective_tree_oid": rec.get("effective_tree_oid"),
                    }
                )
            else:
                missing_records.append(rec)

    n_unique_patch_sha = len({r["reference_patch_sha256"] for r in complete_records if r.get("reference_patch_sha256")})
    n_unique_tree_oid = len({r["effective_tree_oid"] for r in complete_records if r.get("effective_tree_oid")})

    five_field = [
        {
            k: v for k, v in p.items()
            if k in ("TASK_ID", "SCOPE_HASH", "REFERENCE_PATCH_HASH", "TEST_CONTRACT_HASH", "ENVIRONMENT_ID")
        }
        for p in identities
    ]
    dedup = m.plan_physical_dedup(five_field)

    arm_status: list[dict[str, Any]] = []
    n_complete_arms = 0
    n_auditable = 0
    for arm in arms:
        coverage = arm.status
        if arm.status == "AVAILABLE":
            n_auditable += 1
            coverage = "COMPLETE" if arm.complete == len(task_ids) else "PARTIAL"
            if coverage == "COMPLETE":
                n_complete_arms += 1
        entry: dict[str, Any] = {
            "arm_id": arm.arm_id,
            "scope_source": arm.scope_source,
            "source_sha256": arm.source_sha256,
            "provenance": arm.provenance,
            "status": arm.status,
            "coverage_status": coverage,
            "blocker": arm.blocker,
            "complete": arm.complete,
            "partial": arm.partial,
            "missing_records": arm.missing_records,
            "of_tasks": len(task_ids),
        }
        arm_status.append(entry)

    full_ref_parity: dict[str, bool | None] = {}
    if tree_receipt is not None:
        tree_exact = {str(r["task_id"]): r.get("exact_equal") for r in tree_receipt.get("per_task", [])}
        for tid in task_ids:
            full_ref_parity[str(tid)] = tree_exact.get(str(tid))

    plan = {
        "schema": PLAN_SCHEMA,
        "artifact": "EFFECTIVE_PATCH_PLAN_219",
        "created_at": _now_iso(),
        "git_state": {"repo_head": _head(repo), "saleor_git_dir": str(store.git_dir_abs)},
        "inputs": {"census_sha256": census_sha256},
        "tree_receipt_read": tree_receipt is not None,
        "full_reference_target_tree_parity": full_ref_parity,
        "denominator_tasks": len(task_ids),
        "arm_status": arm_status,
        "n_arms_auditable": n_auditable,
        "n_arms_complete_219_219": n_complete_arms,
        "n_arms_total": len(arms),
        "measures": {
            "n_records_total": len(complete_records) + len(missing_records),
            "n_complete_validated": len(complete_records),
            "n_missing_records": len(missing_records),
            "unique_patch_byte_sha": n_unique_patch_sha,
            "unique_effective_tree_oid": n_unique_tree_oid,
            "five_field_physical_dedup": {
                "n_logical_records": dedup["n_logical_records"],
                "n_physical_executions": dedup["n_physical_executions"],
                "dedup_semantics": "frozen OPWS_EXECUTION_REUSE_DEDUP_R1 five fields, unchanged",
            },
        },
        "REAL_TASK_BEHAVIORAL_OUTCOMES": 0,
    }
    receipt = out_dir / PLAN_RECEIPT_NAME
    receipt.write_text(_canonical_json(plan) + "\n", encoding="utf-8")
    return plan


def plan_gate_pass(plan: dict[str, Any]) -> tuple[bool, str]:
    """Honest plan-mode gate: no deceptive full-audit claim when any source is unavailable.

    A missing frozen prediction source (``PREDICTION_SOURCE_MISSING``), a partial
    coverage, or a stopped/blocked arm fails the gate; failures are reported, never
    suppressed. ``RANDOM_SIZE_MATCHED_RM_CSS`` is DEFERRED by design (derived at Phase 4)
    and is excluded from the auditable count with an explicit note.
    """
    missing = [a["arm_id"] for a in plan["arm_status"] if a["status"] == "MISSING"]
    if missing:
        return False, (
            f"PREDICTION_SOURCE_MISSING for arms {missing}; no '219/219 all-arms audited' "
            "claim is made (see arm_status)"
        )
    partial = [
        a["arm_id"] for a in plan["arm_status"]
        if a["status"] == "AVAILABLE" and a["coverage_status"] != "COMPLETE"
    ]
    if partial:
        return False, (
            f"PARTIAL coverage for arms {partial}; missing records are reported in "
            "'missing_records', not counted as complete"
        )
    n_auditable = int(plan["n_arms_auditable"])
    n_complete = int(plan["n_arms_complete_219_219"])
    if n_complete != n_auditable:
        return False, f"complete {n_complete}/{n_auditable} auditable arms only"
    return True, (
        f"plan complete for all {n_auditable} auditable arms; "
        "RANDOM_SIZE_MATCHED_RM_CSS DEFERRED (Phase 4); FULL_REFERENCE parity asserted"
    )


def run_plan_audit(
    *,
    repo: Path,
    store: GitStore,
    out_dir: Path,
    rename_sides_path: Path | None,
    min_free_gib: float,
    tmp_dir: Path | None,
    tree_receipt: dict[str, Any] | None,
    workspace_factory: Callable[[], ReconstructionWorkspace] | None = None,
) -> dict[str, Any]:
    """Plan mode: authoritative arm sources -> per-(arm, task) effective records -> receipt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_parent = tmp_dir or (out_dir / "m19a1b_tmp")
    tmp_parent.mkdir(parents=True, exist_ok=True)

    binding = p2.load_binding(repo / "research" / "opws" / "binding")
    task_ids = list(binding["task_ids"])
    env_by_task = dict(binding["env_by_task"])
    contract_by_task = dict(binding["contract_by_task"])
    manifest, _mpath, _msha = load_manifest(repo)
    census_views, _cpath, census_sha = load_census(repo)
    rename_sides = load_rename_sides(rename_sides_path)

    own_workspace = workspace_factory() if workspace_factory is not None else ReconstructionWorkspace(
        tmp_parent, store, min_free_gib=min_free_gib
    )
    try:
        # ---- pass 1: per-task authority + FULL_REFERENCE (shared across arms) ----
        authorities: dict[str, TestPathAuthority] = {}
        full_ref_results: dict[str, MaterializationResult] = {}
        for tid in task_ids:
            mrec = manifest.get(tid)
            view = census_views.get(tid)
            if mrec is None or view is None:
                continue
            try:
                parent = store.resolve_commit(str(mrec["parent_commit"]), "parent")
                target = store.resolve_commit(str(mrec["target_commit"]), "target")
            except (GitObjectIdentityError, GitCommandError):
                continue
            resolved = resolve_task_authority(
                task_id=tid, view=view, store=store, parent=parent, target=target,
                rename_sides=rename_sides,
            )
            if resolved.authority is None:
                continue
            authorities[tid] = resolved.authority
            try:
                fr = materialize_full_reference(
                    task_id=tid, repo=store.root, parent_commit=parent, target_commit=target,
                    test_path_authority=resolved.authority,
                )
                full_ref_results[tid] = fr
            except (MaterializerError, GitCommandError, TestClassificationAuthorityError):
                continue

        # ---- pass 2: arm sources at their authoritative locations ----
        scope_cache: dict[str, Any] = {}
        scope_maps: dict[str, dict[str, list[str]]] = {}
        arms: list[PlanArmStatus] = []
        for arm_id in p2.FROZEN_ARM_ORDER:
            src = p2.ARM_SCOPE_SOURCES[arm_id]
            provenance: dict[str, Any] = {"arm_id": arm_id}
            if arm_id in ("DENSE_K3", "DENSE_K10", "BM25_K3", "BM25_K10", "BM25_TO_CIA_1HOP"):
                provenance["r2_tag"] = R2_TAG
                provenance["r2_tag_peeled_commit"] = R2_PEELED
            try:
                scope_map = p2.resolve_arm_scope_lists(arm_id, task_ids, scope_cache)
            except ob.BuildError as exc:
                deferred = arm_id == "RANDOM_SIZE_MATCHED_RM_CSS"
                arms.append(
                    PlanArmStatus(
                        arm_id=arm_id, scope_source=src.get("path"), source_sha256=None,
                        provenance=provenance,
                        status="DEFERRED" if deferred else "MISSING",
                        blocker=str(exc), complete=0, partial=0,
                        missing_records=len(task_ids)
                        if not deferred else 0,
                    )
                )
                continue
            src_path = src.get("path")
            source_sha = None
            if isinstance(src_path, str) and Path(src_path).is_file():
                source_sha = sha256_file(Path(src_path))
            missing_tasks = [t for t in task_ids if t not in scope_map]
            arm = PlanArmStatus(
                arm_id=arm_id, scope_source=src_path, source_sha256=source_sha,
                provenance=provenance, status="AVAILABLE", blocker=None,
                complete=0, partial=0, missing_records=0,
            )
            if missing_tasks:
                arm.status = "PARTIAL"
                arm.blocker = f"missing scope records for {len(missing_tasks)} tasks: {missing_tasks[:5]}"
                arm.missing_records = len(missing_tasks)
            scope_maps[arm_id] = scope_map
            arms.append(arm)

        # NEG: deterministic empty-scope control (empty reference patch, no scientific inference)
        neg_scope: dict[str, list[str]] = {tid: [] for tid in task_ids}
        # FULL_REFERENCE arm: complete non-test change set per task
        full_ref_scope: dict[str, list[str]] = {
            tid: sorted(fr.reference_classification) for tid, fr in full_ref_results.items()
        }
        arms.append(
            PlanArmStatus(
                arm_id="NEG", scope_source="derived-control:empty-scope", source_sha256=None,
                provenance={"arm_id": "NEG", "kind": "CONTROL"},
                status="AVAILABLE", blocker=None, complete=0, partial=0, missing_records=0,
            )
        )
        arms.append(
            PlanArmStatus(
                arm_id="FULL_REFERENCE", scope_source="materialize_full_reference", source_sha256=None,
                provenance={"arm_id": "FULL_REFERENCE", "kind": "PROPOSED_R1.1_FULL_REFERENCE"},
                status="AVAILABLE", blocker=None, complete=0, partial=0, missing_records=0,
            )
        )

        # ---- pass 3: per-(arm, task) effective records (isolated temp workspace) ----
        for arm in arms:
            if arm.status == "DEFERRED":
                # RANDOM_SIZE_MATCHED_RM_CSS is derived at Phase 4 by design; never
                # audited, never counted: recorded as DEFERRED with an explicit note.
                continue
            if arm.status == "MISSING":
                # A missing frozen prediction source is reported as per-task missing
                # records (never counted as complete) — PREDICTION_SOURCE_MISSING.
                arm.per_task = [
                    {
                        "arm_id": arm.arm_id, "task_id": tid, "scope_hash": None,
                        "reference_patch_sha256": None, "test_contract_hash": None,
                        "effective_tree_oid": None, "status": "ERROR",
                        "error_type": "PREDICTION_SOURCE_MISSING",
                        "error_detail": arm.blocker or "frozen prediction source unavailable",
                    }
                    for tid in task_ids
                ]
                arm.missing_records = len(task_ids)
                continue
            if arm.arm_id == "NEG":
                scope_map = neg_scope
            elif arm.arm_id == "FULL_REFERENCE":
                scope_map = full_ref_scope
            else:
                scope_map = scope_maps[arm.arm_id]
            arm.per_task = _build_plan_records_for_arm(
                arm_id=arm.arm_id, scope_map=scope_map, task_ids=task_ids,
                manifest=manifest, store=store,
                workspace=own_workspace, authorities=authorities,
                full_ref_results=full_ref_results, contract_by_task=contract_by_task,
            )
            ok = [r for r in arm.per_task if r.get("status") in ("OK", "WARN") and r.get("effective_tree_oid")]
            partial = [r for r in arm.per_task if r.get("status") in ("OK", "WARN") and not r.get("effective_tree_oid")]
            arm.complete = len(ok)
            arm.partial = len(partial)
            arm.missing_records = len(arm.per_task) - arm.complete - arm.partial

        return build_plan_receipt(
            repo=repo, store=store, out_dir=out_dir, arms=arms, task_ids=task_ids,
            env_by_task=env_by_task, tree_receipt=tree_receipt, census_sha256=census_sha,
        )
    finally:
        own_workspace.cleanup()


# ------------------------------------------------------------------ CLI
def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="opws_m19a1b_tree_audit",
        description=(
            "M19A1B read-only Git-tree reconstruction audit (author code only; "
            "REAL_TASK_BEHAVIORAL_OUTCOMES=0). Never writes to the Saleor store."
        ),
    )
    ap.add_argument("--repo", required=True, help="source repository containing frozen manifests/census")
    ap.add_argument("--saleor-git", required=True,
                    help="owner-provided read-only Git object store/clone of Saleor (ordinary or bare)")
    ap.add_argument("--out", required=True, help="output directory OUTSIDE the source repository")
    ap.add_argument("--mode", choices=("tree", "plan", "all"), default="tree")
    ap.add_argument("--rename-sides-json",
                    help="optional explicit per-side rename flag authority "
                         '{"tasks": {task_id: {old, new, old_is_test, new_is_test}}}')
    ap.add_argument("--min-free-gib", type=float, default=DEFAULT_MIN_FREE_GIB,
                    help=f"workspace free-space guard in GiB (default {DEFAULT_MIN_FREE_GIB:.0f})")
    ap.add_argument("--tmp-dir", help="temp workspace parent (default <out>/m19a1b_tmp)")
    args = ap.parse_args()

    try:
        repo = Path(args.repo).resolve()
        saleor_git = Path(args.saleor_git).resolve()
        out_dir = Path(args.out).resolve()
        rename_sides_path = Path(args.rename_sides_json).resolve() if args.rename_sides_json else None
        tmp_dir = Path(args.tmp_dir).resolve() if args.tmp_dir else None
        tree_receipt: dict[str, Any] | None = None

        if args.mode in ("tree", "all"):
            result = run_tree_audit(
                repo=repo, saleor_git=saleor_git, out_dir=out_dir,
                rename_sides_path=rename_sides_path, min_free_gib=args.min_free_gib,
                tmp_dir=tmp_dir,
            )
            print(f"TREE_RECEIPT={result.receipt_path}")
            print(f"TREE_SUMMARY={_canonical_json(result.summary['summary'])}")
            print(f"TREE_GATE={_canonical_json(result.summary['exit_gate'])}")
            tree_receipt = result.summary
            if not result.summary["exit_gate"]["pass"]:
                print("TREE_GATE=FAIL (failures are DATA; see per_task records)", file=sys.stderr)
                return 4

        if args.mode in ("plan", "all"):
            if args.mode == "plan":
                receipt_path = out_dir / TREE_RECEIPT_NAME
                if not receipt_path.is_file():
                    print("PLAN_BLOCKER=TREE_RECEIPT_MISSING: run --mode tree first "
                          "(plan mode requires a valid tree receipt)", file=sys.stderr)
                    return 4
                tree_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            store = GitStore.open(saleor_git)
            plan = run_plan_audit(
                repo=repo, store=store, out_dir=out_dir,
                rename_sides_path=rename_sides_path, min_free_gib=args.min_free_gib,
                tmp_dir=tmp_dir, tree_receipt=tree_receipt,
            )
            ok, why = plan_gate_pass(plan)
            print(f"PLAN_RECEIPT={out_dir / PLAN_RECEIPT_NAME}")
            print(f"PLAN_GATE={'PASS' if ok else 'FAIL'}: {why}")
            if not ok:
                return 4
        return 0

    except OutDirError as exc:
        print(f"BLOCKER={exc}", file=sys.stderr)
        return 3
    except (AuditConfigError, AuthorityError, M19A1BError, GitCommandError) as exc:
        print(f"BLOCKER={type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"BLOCKER=OSERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(_cli())
