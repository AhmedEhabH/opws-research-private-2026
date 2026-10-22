"""OPWS R1 Phase 3B — read-only patch materializer unit tests (synthetic git repos).

M18 guardrails: every test runs against synthetic repositories created inside
``tmp_path`` (fixture-only execution on synthetic temporary directories is allowed).
Nothing is checked out, altered or written inside any real repository; real-task F2P/P2P
evaluation, STAGE_5 preflight, Docker/WSL, API inference and downloads are NOT exercised.
Scientific PASS/FAIL states are never produced: the assertions below are engineering
outcomes (patch bytes, hashes, identity tuples, taxonomy codes).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_phase3b_evaluator_adapter as ada  # noqa: E402
from scripts import opws_phase3b_patch_materialize as m  # noqa: E402


# ------------------------------------------------------------------ synthetic repo helpers
def _git(repo: Path, *args: str, data: bytes | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=data,
        capture_output=True,
        env=dict(_ENV),
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')}"
    return proc.stdout.decode("utf-8", "replace").strip()


_ENV = None  # placeholder set below


def _git_env() -> dict[str, str]:
    env = dict(subprocess.os.environ)  # keep a stable snapshot
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


_ENV = _git_env()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for key, val in {
        "user.email": "t@t",
        "user.name": "t",
        "core.autocrlf": "false",
        "core.quotepath": "false",
    }.items():
        _git(repo, "config", key, val)
    return repo


def _write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as fh:
        fh.write(text)


def _commit_all(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)
    return _git(repo, "rev-parse", "HEAD")


def _simple_task_repo(tmp_path: Path, *scenario: str) -> tuple[Path, str, str]:
    """Build a synthetic repo; returns (repo, parent, target).

    Scenario keywords apply in order against the second commit:
      modified  - saleor/core/jwt.py content change
      deleted   - delete non-test file saleor/core/legacy.py
      renamed   - pure git mv saleor/core/jwt.py -> saleor/core/token_utils.py
      added     - new file saleor/core/new_stuff.py
      test_mod  - modify test file saleor/graphql/tests/test_a.py
      test_del  - delete test file saleor/graphql/tests/test_tracing.py
    """
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(repo / "saleor/core/legacy.py", "def legacy():\n    return 0\n")
    _write_lf(repo / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _write_lf(repo / "saleor/graphql/tests/test_tracing.py", "old tracing\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    if "modified" in scenario:
        _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    if "renamed" in scenario:
        repo.joinpath("saleor/core/jwt.py").rename(repo / "saleor/core/token_utils.py")
    if "added" in scenario:
        _write_lf(repo / "saleor/core/new_stuff.py", "def helper():\n    return 1\n")
    if "deleted" in scenario:
        repo.joinpath("saleor/core/legacy.py").unlink()
    if "test_mod" in scenario:
        _write_lf(repo / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    if "test_del" in scenario:
        repo.joinpath("saleor/graphql/tests/test_tracing.py").unlink()
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    return repo, parent, target


def _authority(classification: dict[str, str], tests: set[str]) -> m.TestPathAuthority:
    """M19A1A: explicit frozen test-path authority for a synthetic task change set."""
    return m.TestPathAuthority(
        changed_paths=frozenset(classification),
        test_paths=frozenset(tests),
        source="synthetic-fixture",
    )

# ---------------------------------------------------------------- 1. modified
def test_modified_file_materializes_correct_patch(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/jwt.py"],
        classification={"saleor/core/jwt.py": "M"},
        test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
    )
    patch = result.reference_patch_bytes.decode("utf-8")
    assert "a/saleor/core/jwt.py" in patch and "b/saleor/core/jwt.py" in patch
    assert "return p.upper()" in patch and "-    return p" in patch
    assert result.per_path_status == {"saleor/core/jwt.py": "M"}
    assert result.reference_patch_hash == hashlib.sha256(result.reference_patch_bytes).hexdigest()
    assert result.invalid_prediction_paths == []


# ---------------------------------------------------------------- 2. added
def test_added_file_full_creation_for_reference_arms(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "added")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/new_stuff.py"],
        classification={"saleor/core/new_stuff.py": "A"},
        test_path_authority=_authority({"saleor/core/new_stuff.py": "A"}, set()),
        allow_added=True,
    )
    patch = result.reference_patch_bytes.decode("utf-8")
    assert "new file mode" in patch
    assert "+++ b/saleor/core/new_stuff.py" in patch
    assert "def helper():" in patch
    assert result.per_path_status["saleor/core/new_stuff.py"] == "A"


def test_added_file_parent_only_scope_is_recorded_not_silently_dropped(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "added")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/new_stuff.py"],
        classification={"saleor/core/new_stuff.py": "A"},
        test_path_authority=_authority({"saleor/core/new_stuff.py": "A"}, set()),
        allow_added=False,
    )
    assert result.per_path_status == {}
    assert result.reference_patch_bytes == b""
    assert result.invalid_prediction_paths == [
        {"path": "saleor/core/new_stuff.py", "reason": "ADDED_NOT_SELECTABLE_BY_PARENT_ONLY_SCOPE"}
    ]
    assert any(rec["contract"] == "R1-ADDED-HANDLING" for rec in result.unresolved_contracts)


# ---------------------------------------------------------------- 3. deleted
def test_deleted_file_materializes_deletion(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "deleted")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/legacy.py"],
        classification={"saleor/core/legacy.py": "D"},
        test_path_authority=_authority({"saleor/core/legacy.py": "D"}, set()),
    )
    patch = result.reference_patch_bytes.decode("utf-8")
    assert "deleted file mode" in patch and "def legacy():" in patch
    assert result.per_path_status["saleor/core/legacy.py"] == "D"


def test_deleted_test_file_goes_to_common_contract(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "test_del")
    # a deleted TEST file is a common-contract change, never editable scope
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/graphql/tests/test_tracing.py"],
        classification={"saleor/graphql/tests/test_tracing.py": "D"},
        test_path_authority=_authority(
            {"saleor/graphql/tests/test_tracing.py": "D"}, {"saleor/graphql/tests/test_tracing.py"}
        ),
    )
    assert result.reference_patch_bytes == b""
    # a scope listing a test file is a fail-closed invalid prediction (test files are
    # never editable scope): recorded, not silently dropped
    assert result.invalid_prediction_paths == [
        {"path": "saleor/graphql/tests/test_tracing.py", "reason": "TEST_CHANGE_NOT_EDITABLE_SCOPE"}
    ]
    assert b"saleor/graphql/tests/test_tracing.py" in result.test_patch_bytes
    assert "deleted file mode" in result.test_patch_bytes.decode("utf-8")


# ---------------------------------------------------------------- 4. rename pair
def test_rename_pair_old_and_new_sides(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "renamed")
    classification = {"saleor/core/jwt.py": "R_OLD", "saleor/core/token_utils.py": "R_NEW"}
    old = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/jwt.py"],
        classification=classification,
        test_path_authority=_authority(classification, set()),
    )
    new = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/token_utils.py"],
        classification=classification,
        test_path_authority=_authority(classification, set()),
        allow_added=True,
    )
    old_patch = old.reference_patch_bytes.decode("utf-8")
    new_patch = new.reference_patch_bytes.decode("utf-8")
    assert "deleted file mode" in old_patch or "---" in old_patch
    assert old.per_path_status["saleor/core/jwt.py"] == "R_OLD_DELETION"
    assert "new file mode" in new_patch and "def encode(p):" in new_patch
    assert new.per_path_status["saleor/core/token_utils.py"] == "R_NEW_ADDITION"


def test_rename_new_path_not_selectable_by_parent_only_scope(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "renamed")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/token_utils.py"],
        classification={"saleor/core/jwt.py": "R_OLD", "saleor/core/token_utils.py": "R_NEW"},
        test_path_authority=_authority(
            {"saleor/core/jwt.py": "R_OLD", "saleor/core/token_utils.py": "R_NEW"}, set()
        ),
        allow_added=False,
    )
    assert result.reference_patch_bytes == b""
    assert result.invalid_prediction_paths[0]["reason"].startswith("RENAME_NEW_PATH_NOT_SELECTABLE")


# ---------------------------------------------------------------- 5. test-file common contract
def test_test_file_common_contract_split_and_separate_hash(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified", "test_mod")
    classification = {
        "saleor/core/jwt.py": "M",
        "saleor/graphql/tests/test_a.py": "M",
    }
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/jwt.py"],
        classification=classification,
        test_path_authority=_authority(classification, {"saleor/graphql/tests/test_a.py"}),
    )
    # test change is in the common-contract patch, never in the editable reference patch
    assert b"saleor/graphql/tests/test_a.py" not in result.reference_patch_bytes
    assert b"saleor/graphql/tests/test_a.py" in result.test_patch_bytes
    assert result.test_patch_hash != result.reference_patch_hash
    ref, test = m.split_test_reference(classification, _authority(classification, {"saleor/graphql/tests/test_a.py"}))
    assert ref == {"saleor/core/jwt.py": "M"}
    assert test == {"saleor/graphql/tests/test_a.py": "M"}


# ---------------------------------------------------------------- 6. empty scope
def test_empty_scope_safe_null_patch(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=[],
        classification={"saleor/core/jwt.py": "M"},
        test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
    )
    assert result.reference_patch_bytes == b""
    assert result.reference_patch_hash == hashlib.sha256(b"").hexdigest()
    assert result.files_changed == ()
    assert result.selected_scope_hash == m.p2.compute_canonical_scope_hash([])


# ---------------------------------------------------------------- 7. unsafe scope paths
@pytest.mark.parametrize(
    "bad",
    [
        "../escape.py",
        "a/../../escape.py",
        "/abs/saleor/x.py",
        "C:/abs/x.py",
        "saleor\\core\\x.py",
        "a//b.py",
        "a/./b.py",
        "",
    ],
)
def test_traversal_absolute_and_alias_paths_rejected(tmp_path: Path, bad: str) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    with pytest.raises(m.ScopePathInvalidError):
        m.materialize_scoped_reference_patch(
            task_id="saleor-rc-t",
            repo=repo,
            parent_commit=parent,
            target_commit=target,
            scope_paths=[bad],
            classification={"saleor/core/jwt.py": "M"},
            test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
        )


def test_unsafe_classification_path_rejected_not_guessed(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/jwt.py"],
        classification={"saleor/core/jwt.py": "M", "../evil.py": "A"},
        test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
    )
    assert any(rec["path"] == "../evil.py" for rec in result.invalid_prediction_paths)


def test_nonempty_garbage_repo_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(m.RepoPathError):
        m.materialize_scoped_reference_patch(
            task_id="saleor-rc-t",
            repo=tmp_path / "not-a-repo",
            parent_commit="a" * 40,
            target_commit="b" * 40,
            scope_paths=["a.py"],
            classification={"a.py": "M"},
            test_path_authority=_authority({"a.py": "M"}, set()),
        )


# ---------------------------------------------------------------- 8. symlink blob
def test_symlink_blob_path_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "real.txt", "hello\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    blob = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
        input=b"../outside.txt",
        capture_output=True,
    )
    assert blob.returncode == 0
    _git(repo, "update-index", "--add", "--cacheinfo", "120000", blob.stdout.decode().strip(), "link.txt")
    _write_lf(repo / "real.txt", "bye\n")
    _git(repo, "add", "real.txt")
    _git(repo, "commit", "-qm", "two")  # NOT add -A: that would drop the staged cacheinfo symlink
    target = _git(repo, "rev-parse", "HEAD")
    assert m.target_blob_mode(repo, target, "link.txt") == "120000"
    # M19A1A: classification must cover the COMPLETE git changed set (real.txt also changed)
    classification = {"link.txt": "A", "real.txt": "M"}
    with pytest.raises(m.SymlinkPathError):
        m.materialize_scoped_reference_patch(
            task_id="saleor-rc-t",
            repo=repo,
            parent_commit=parent,
            target_commit=target,
            scope_paths=["link.txt"],
            classification=classification,
            test_path_authority=_authority(classification, set()),
            allow_added=True,
        )


# ---------------------------------------------------------------- 9. missing object identity
@pytest.mark.parametrize("which", ["parent_commit", "target_commit"])
def test_missing_parent_or_target_object_fails_closed(tmp_path: Path, which: str) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    kwargs = {"parent_commit": parent, "target_commit": target}
    kwargs[which] = "0" * 40  # not present in the repository
    with pytest.raises(m.GitObjectIdentityError):
        m.materialize_scoped_reference_patch(
            task_id="saleor-rc-t",
            repo=repo,
            scope_paths=["saleor/core/jwt.py"],
            classification={"saleor/core/jwt.py": "M"},
            test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
            **kwargs,
        )


# ---------------------------------------------------------------- 10. patch conflict probe
def test_patch_conflict_detected_via_apply_check(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/jwt.py"],
        classification={"saleor/core/jwt.py": "M"},
        test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
    )
    worktree = tmp_path / "wt"
    proc = subprocess.run(["git", "clone", "-q", str(repo), str(worktree)], capture_output=True)
    assert proc.returncode == 0
    # faithful parent worktree: --full-index patches verify the old-side blob hash, so
    # autocrlf must be off before checkout (Windows git defaults autocrlf=true)
    _git(worktree, "config", "core.autocrlf", "false")
    _git(worktree, "checkout", "-qf", parent)
    ok, _ = m.apply_check(worktree, result.reference_patch_bytes)
    assert ok is True
    # tamper the parent file -> patch no longer applies cleanly
    _write_lf(worktree / "saleor/core/jwt.py", "def encode(p):\n    return 'tampered'\n")
    ok2, _err = m.apply_check(worktree, result.reference_patch_bytes)
    assert ok2 is False
    classified = ada.classify_apply_check(ok2, _err)
    assert classified["taxonomy_class"] == "PATCH_APPLICATION_INVALID"
    assert "ERROR_PATCH_CONFLICT" in classified["engineering_code"]


# ---------------------------------------------------------------- 11. changed blob fingerprint
def test_changed_blob_fingerprint_matches_target_blob(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    result = m.materialize_scoped_reference_patch(
        task_id="saleor-rc-t",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/jwt.py"],
        classification={"saleor/core/jwt.py": "M"},
        test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
    )
    worktree = tmp_path / "wt"
    proc = subprocess.run(["git", "clone", "-q", str(repo), str(worktree)], capture_output=True)
    assert proc.returncode == 0
    # clone -> checkout -f parent (force: the config flip may make the worktree look dirty)
    _git(worktree, "config", "core.autocrlf", "false")
    proc = subprocess.run(
        ["git", "-C", str(worktree), "checkout", "-f", "-q", parent],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    apply_proc = subprocess.run(
        ["git", "-C", str(worktree), "apply", "-"],
        input=result.reference_patch_bytes,
        capture_output=True,
    )
    assert apply_proc.returncode == 0, apply_proc.stderr.decode("utf-8", "replace")
    patched = (worktree / "saleor/core/jwt.py").read_bytes()
    expected = m.target_blob_bytes(repo, target, "saleor/core/jwt.py")
    # line-ending normalization guard: compare byte content modulo CRLF translation
    norm_patched = patched.replace(b"\r\n", b"\n")
    norm_expected = expected.replace(b"\r\n", b"\n")
    assert norm_patched == norm_expected
    assert hashlib.sha256(norm_patched).hexdigest() == hashlib.sha256(norm_expected).hexdigest()
    tampered = patched + b"\n# tampered"
    assert hashlib.sha256(tampered).hexdigest() != hashlib.sha256(expected).hexdigest()


# ---------------------------------------------------------------- 12. bounded output
def test_unexpected_output_bounded(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    with pytest.raises(m.OutputTooLargeError):
        m.git_capture(repo, "diff", parent, target, "--", "saleor/core/jwt.py", max_bytes=1)


# ---------------------------------------------------------------- 13. stable sha double run
def test_stable_sha_deterministic_double_run(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified", "added", "deleted", "renamed", "test_mod")
    # scenario is (modified, added, deleted, renamed, test_mod): git has FIVE changed
    # paths (no test_del); classification must reflect the COMPLETE changed set (M19A1A)
    classification = {
        "saleor/core/jwt.py": "R_OLD",
        "saleor/core/token_utils.py": "R_NEW",
        "saleor/core/new_stuff.py": "A",
        "saleor/core/legacy.py": "D",
        "saleor/graphql/tests/test_a.py": "M",
    }
    kwargs = {
        "task_id": "saleor-rc-t",
        "repo": repo,
        "parent_commit": parent,
        "target_commit": target,
        "scope_paths": [
            "saleor/core/jwt.py",
            "saleor/core/token_utils.py",
            "saleor/core/new_stuff.py",
            "saleor/graphql/tests/test_tracing.py",
        ],
        "classification": classification,
        "test_path_authority": _authority(classification, {"saleor/graphql/tests/test_a.py"}),
        "allow_added": True,
    }
    first = m.materialize_scoped_reference_patch(**kwargs)
    second = m.materialize_scoped_reference_patch(**kwargs)
    assert first.reference_patch_bytes == second.reference_patch_bytes
    assert first.reference_patch_hash == second.reference_patch_hash
    assert first.test_patch_hash == second.test_patch_hash
    assert first.as_dict() == second.as_dict()


# ---------------------------------------------------------------- 14. dedup identity
def test_scope_hash_mismatch_equal_patch_hash_not_deduped(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified")
    classification = {"saleor/core/jwt.py": "M"}
    scope_a = m.materialize_scoped_reference_patch(
        task_id="t", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/core/jwt.py"], classification=classification,
        test_path_authority=_authority(classification, set()),
    )
    # scope adds an UNCHANGED sibling path -> same reference patch bytes, different scope hash
    scope_b = m.materialize_scoped_reference_patch(
        task_id="t", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/core/jwt.py", "saleor/graphql/tests/test_a.py"],
        classification=classification,
        test_path_authority=_authority(classification, set()),
    )
    assert scope_a.reference_patch_hash == scope_b.reference_patch_hash  # equal patch hashes
    assert scope_a.selected_scope_hash != scope_b.selected_scope_hash  # but different scopes
    plan = m.plan_physical_dedup(
        [
            {"record_id": "r1", "arm_id": "A", **m.physical_execution_identity(
                task_id="t", scope_hash=scope_a.selected_scope_hash,
                reference_patch_hash=scope_a.reference_patch_hash,
                test_contract_hash="9" * 64, environment_id="env1")},
            {"record_id": "r2", "arm_id": "B", **m.physical_execution_identity(
                task_id="t", scope_hash=scope_b.selected_scope_hash,
                reference_patch_hash=scope_b.reference_patch_hash,
                test_contract_hash="9" * 64, environment_id="env1")},
            {"record_id": "r3", "arm_id": "C", **m.physical_execution_identity(
                task_id="t", scope_hash=scope_b.selected_scope_hash,
                reference_patch_hash=scope_b.reference_patch_hash,
                test_contract_hash="9" * 64, environment_id="env1")},
        ]
    )
    assert plan["n_logical_records"] == 3
    assert plan["n_physical_executions"] == 2  # equal patch hashes alone are NO permission to dedup
    reasons = {p["dedup_reason"] for p in plan["physical_executions"]}
    assert reasons == {"FIVE_FIELDS_EQUAL", "SINGLE_RECORD"}


# ---------------------------------------------------------------- 15. FULL_REFERENCE derivation
def test_full_reference_partition_splits_complete_change_set_by_authority(tmp_path: Path) -> None:
    repo, parent, target = _simple_task_repo(tmp_path, "modified", "added", "deleted", "test_mod", "test_del")
    classification = {
        "saleor/core/jwt.py": "M",
        "saleor/core/new_stuff.py": "A",
        "saleor/core/legacy.py": "D",
        "saleor/graphql/tests/test_a.py": "M",
        "saleor/graphql/tests/test_tracing.py": "D",
    }
    authority = _authority(classification, {"saleor/graphql/tests/test_a.py", "saleor/graphql/tests/test_tracing.py"})
    reference, test = m.full_reference_partition(repo, parent, target, authority)
    # FULL_REFERENCE carries ALL non-test changes (added files included), never test changes
    assert reference == {
        "saleor/core/jwt.py": "M",
        "saleor/core/new_stuff.py": "A",
        "saleor/core/legacy.py": "D",
    }
    assert set(test) == authority.test_paths
    inv = m.verify_split_invariants(classification, reference, test, test_path_authority=authority)
    assert inv["disjoint"] and inv["union_all_classification"] and inv["test_equals_census_authoritative"]
    # full materialization: added non-test file materialized; the common test patch is preserved
    full = m.materialize_full_reference(
        task_id="saleor-rc-t", repo=repo, parent_commit=parent, target_commit=target,
        test_path_authority=authority,
    )
    assert b"new file mode" in full.reference_patch_bytes
    assert b"saleor/graphql/tests/test_a.py" in full.test_patch_bytes
    assert full.split_invariants["union_all_git_changed"] is True


def test_full_reference_contract_failure_is_invalid_contract_not_selector(tmp_path: Path) -> None:
    # A FULL_REFERENCE control whose contract cannot instantiate is TEST_CONTRACT_INVALID,
    # never a selector (ARM_PREDICTION_INVALID) failure.
    try:
        ada.instantiate_contract(contract_hash="zz-not-a-hash", node_ids=["n1"])
    except ada.ContractNotInstantiatedError as exc:
        classification = ada.classify_engineering_failure(exc)
        assert classification["taxonomy_class"] == "TEST_CONTRACT_INVALID"
        assert classification["taxonomy_class"] != "ARM_PREDICTION_INVALID"
    else:
        pytest.fail("malformed contract hash must fail closed")
    # good FULL_REFERENCE contract hash -> generic node list placeholder is fine (synthetic)
    inst = ada.instantiate_contract(contract_hash="a" * 64, node_ids=["f2p-node-1"])
    assert inst.status == "INSTANTIATED"
