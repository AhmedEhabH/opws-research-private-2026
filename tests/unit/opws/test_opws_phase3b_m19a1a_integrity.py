"""M19A1A — OPWS patch materializer integrity repair: synthetic unit tests.

Covers the M19A1A engineering invariants WITHOUT any real Saleor execution:

* single deterministic ``git_diff_bytes`` producer (native patches, no manual
  hunks/blob hashes; fixed flag vector; hostile config isolation);
* explicit frozen test-path authority (no filename heuristics), coverage checks
  and fail-closed ``TEST_CLASSIFICATION_AUTHORITY_MISSING``;
* disjointness / completeness split invariants and the demonstration that
  full-tree equality alone is INSUFFICIENT to validate the test split;
* fail-closed binary / symlink / submodule rejection with evidence;
* no-final-newline, zero-byte added ``migrations/__init__.py``, mode-only and
  rename-with-edits materialization; census rename side authority.

M18 guardrails: every test runs against synthetic repositories created inside
``tmp_path``; nothing touches Saleor checkouts/indexes/object stores; no Docker,
WSL, container evaluators, downloads or scientific outcomes.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_phase3b_patch_materialize as m  # noqa: E402


# ------------------------------------------------------------------ synthetic repo helpers
def _git(repo: Path, *args: str, data: bytes | None = None, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=data,
        capture_output=True,
        env=dict(_ENV),
    )
    if check:
        assert proc.returncode == 0, (
            f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')}"
        )
    return proc.stdout.decode("utf-8", "replace").strip()


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
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


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _commit_all(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)
    return _git(repo, "rev-parse", "HEAD")


def _authority(
    classification: dict[str, str],
    tests: set[str],
    *,
    extra_changed: set[str] | None = None,
) -> m.TestPathAuthority:
    """M19A1A explicit frozen test-path authority for a synthetic task change set."""
    changed = frozenset(classification) | frozenset(extra_changed or set())
    return m.TestPathAuthority(
        changed_paths=changed,
        test_paths=frozenset(tests),
        source="synthetic-fixture",
    )


# ================================================================= 1. single producer
def test_git_diff_bytes_native_full_index_modification(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/new_stuff.py", "def helper():\n    return 1\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/core/new_stuff.py", "def helper():\n    return 2\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    patch = m.git_diff_bytes(repo, parent, target, "saleor/core/new_stuff.py")
    text = patch.decode("utf-8", "replace")
    assert text.startswith("diff --git a/saleor/core/new_stuff.py b/saleor/core/new_stuff.py")
    # --full-index pins 40-hex hashes on both sides (git's own bytes, never synthesized)
    assert re.search(r"index [0-9a-f]{40}\.\.[0-9a-f]{40} ", text) is not None  # 40-hex::40-hex
    assert "return 2" in text and "-    return 1" in text
    # double run byte-identical
    assert m.git_diff_bytes(repo, parent, target, "saleor/core/new_stuff.py") == patch


def test_git_diff_bytes_no_paths_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "a.txt", "x\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "a.txt", "y\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(m.Phase3BError):
        m.git_diff_bytes(repo, parent, target)  # whole-tree diff refused


# ================================================================= 2. no-final-newline added file
def test_added_file_without_final_newline_native_and_deterministic(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "commit", "-qm", "one", "--allow-empty")  # empty parent tree
    parent = _git(repo, "rev-parse", "HEAD")
    _write_bytes(repo / "saleor/core/raw.py", b"def raw():\n    return 'no-newline'")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/core/raw.py": "A"}
    result = m.materialize_scoped_reference_patch(
        task_id="t1",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/raw.py"],
        classification=classification,
        test_path_authority=_authority(classification, set()),
        allow_added=True,
    )
    patch = result.reference_patch_bytes
    assert b"new file mode" in patch
    assert b"No newline at end of file" in patch
    assert result.reference_patch_hash == m.sha256_bytes(patch)
    again = m.materialize_scoped_reference_patch(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/core/raw.py"], classification=classification,
        test_path_authority=_authority(classification, set()), allow_added=True,
    )
    assert again.reference_patch_bytes == patch
    assert again.reference_patch_hash == result.reference_patch_hash


# ================================================================= 3. zero-byte added migrations/__init__.py
def test_zero_byte_added_migrations_init_materializes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "commit", "-qm", "one", "--allow-empty")  # empty parent tree
    parent = _git(repo, "rev-parse", "HEAD")
    _write_bytes(repo / "saleor/migrations/__init__.py", b"")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/migrations/__init__.py": "A"}
    result = m.materialize_scoped_reference_patch(
        task_id="t1",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/migrations/__init__.py"],
        classification=classification,
        test_path_authority=_authority(classification, set()),
        allow_added=True,
    )
    patch = result.reference_patch_bytes
    assert patch != b""  # native creation diff exists for an empty file
    assert b"new file mode" in patch
    assert result.per_path_status["saleor/migrations/__init__.py"] == "A"
    # applies cleanly against the parent state
    worktree = tmp_path / "wt"
    proc = subprocess.run(["git", "clone", "-q", str(repo), str(worktree)], capture_output=True, env=dict(_ENV))
    assert proc.returncode == 0
    _git(worktree, "checkout", "-qf", parent)
    ok, _err = m.apply_check(worktree, patch)
    assert ok is True


# ================================================================= 4. mode-only change
def test_mode_only_change_materializes_mode_hunks(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/exec.py", "#!/usr/bin/env python\nprint(1)\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    blob = _git(repo, "hash-object", "saleor/core/exec.py")
    _git(repo, "update-index", "--add", "--cacheinfo", "100755", blob, "saleor/core/exec.py")
    _git(repo, "commit", "-qm", "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/core/exec.py": "M"}
    result = m.materialize_scoped_reference_patch(
        task_id="t1",
        repo=repo,
        parent_commit=parent,
        target_commit=target,
        scope_paths=["saleor/core/exec.py"],
        classification=classification,
        test_path_authority=_authority(classification, set()),
    )
    patch = result.reference_patch_bytes
    assert b"old mode 100644" in patch and b"new mode 100755" in patch
    assert result.per_path_status["saleor/core/exec.py"] == "M"


# ================================================================= 5. rename with edited sides
def test_rename_with_edited_sides_native_deletion_and_creation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/old_name.py", "OLD_ONLY_LINE\nshared\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    repo.joinpath("saleor/core/old_name.py").rename(repo / "saleor/core/new_name.py")
    _write_lf(repo / "saleor/core/new_name.py", "NEW_ONLY_LINE\nshared\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {
        "saleor/core/old_name.py": "R_OLD",
        "saleor/core/new_name.py": "R_NEW",
    }
    old = m.materialize_scoped_reference_patch(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/core/old_name.py"], classification=classification,
        test_path_authority=_authority(classification, set()),
    )
    new = m.materialize_scoped_reference_patch(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/core/new_name.py"], classification=classification,
        test_path_authority=_authority(classification, set()), allow_added=True,
    )
    old_patch = old.reference_patch_bytes
    new_patch = new.reference_patch_bytes
    # --no-renames: old side is a pure native deletion of the OLD content...
    assert b"deleted file mode" in old_patch
    assert b"OLD_ONLY_LINE" in old_patch
    assert b"NEW_ONLY_LINE" not in old_patch
    # ...and the new side a pure native creation carrying the EDITED content
    assert b"new file mode" in new_patch
    assert b"NEW_ONLY_LINE" in new_patch and b"OLD_ONLY_LINE" not in new_patch
    assert old.per_path_status["saleor/core/old_name.py"] == "R_OLD_DELETION"
    assert new.per_path_status["saleor/core/new_name.py"] == "R_NEW_ADDITION"
    # apply both to the parent state -> target tree (faithful LF worktree: full-index
    # patches verify the old-side blob hash, so core.autocrlf must be off before checkout)
    worktree = tmp_path / "wt"
    proc = subprocess.run(["git", "clone", "-q", str(repo), str(worktree)], capture_output=True, env=dict(_ENV))
    assert proc.returncode == 0
    _git(worktree, "config", "core.autocrlf", "false")
    _git(worktree, "checkout", "-qf", parent)
    ok_old, _e1 = m.apply_check(worktree, old_patch)
    ok_new, _e2 = m.apply_check(worktree, new_patch)
    assert ok_old is True and ok_new is True


# ================================================================= 6. test filename outside tests/ with frozen flag
def test_test_flag_outside_tests_dir_is_honored_not_guessed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/ops_lib.py", "def v():\n    return 1\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/ops_lib.py", "def v():\n    return 2\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/ops_lib.py": "M"}
    # explicitly flagged test by the frozen authority, despite not being under tests/
    flagged = m.materialize_scoped_reference_patch(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/ops_lib.py"], classification=classification,
        test_path_authority=_authority(classification, {"saleor/ops_lib.py"}),
    )
    assert b"saleor/ops_lib.py" in flagged.test_patch_bytes
    assert b"saleor/ops_lib.py" not in flagged.reference_patch_bytes
    assert flagged.invalid_prediction_paths == [
        {"path": "saleor/ops_lib.py", "reason": "TEST_CHANGE_NOT_EDITABLE_SCOPE"}
    ]
    # same path WITHOUT the flag goes to the reference patch
    unflagged = m.materialize_scoped_reference_patch(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/ops_lib.py"], classification=classification,
        test_path_authority=_authority(classification, set()),
    )
    assert b"saleor/ops_lib.py" in unflagged.reference_patch_bytes
    assert unflagged.test_patch_bytes == b""


# ================================================================= 7. conftest.py explicitly flagged
def test_conftest_explicitly_flagged_as_common_contract(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/graphql/conftest.py", "import pytest\n\n@pytest.fixture\ndef fx():\n    return 1\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/graphql/conftest.py", "import pytest\n\n@pytest.fixture\ndef fx():\n    return 2\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/graphql/conftest.py": "M"}
    result = m.materialize_scoped_reference_patch(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/graphql/conftest.py"], classification=classification,
        test_path_authority=_authority(classification, {"saleor/graphql/conftest.py"}),
    )
    assert b"conftest.py" in result.test_patch_bytes
    assert result.reference_patch_bytes == b""
    assert result.invalid_prediction_paths == [
        {"path": "saleor/graphql/conftest.py", "reason": "TEST_CHANGE_NOT_EDITABLE_SCOPE"}
    ]


# ================================================================= 8. hostile global config
def test_hostile_global_config_cannot_change_patch_bytes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/core/jwt.py": "M"}

    def materialize() -> bytes:
        result = m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=["saleor/core/jwt.py"], classification=classification,
            test_path_authority=_authority(classification, set()),
        )
        return result.reference_patch_bytes

    baseline = materialize()
    # hostile global config (and ambient GIT_CONFIG_* injection) must be inert
    hostile = tmp_path / "hostile-gitconfig"
    hostile.write_text(
        "[core]\n\tautocrlf = true\n\tquotepath = true\n\tsafecrlf = true\n"
        "[diff]\n\tnoprefix = true\n\tmnemonicPrefix = true\n\trenames = true\n"
        "\texternal = cat\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = str(hostile)
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "core.autocrlf"
    env["GIT_CONFIG_VALUE_0"] = "true"
    os.environ.update(env)
    try:
        hostile_patch = materialize()
    finally:
        for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
            os.environ.pop(k, None)
    assert hostile_patch == baseline
    assert m.sha256_bytes(hostile_patch) == m.sha256_bytes(baseline)
    # env isolation is explicit
    env2 = m._git_env()
    assert env2["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env2["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "GIT_CONFIG_COUNT" not in env2
    assert "GIT_DIR" not in env2 and "GIT_WORK_TREE" not in env2


# ================================================================= 9. binary / symlink / submodule fail closed
def test_binary_content_fails_closed_modified_and_added(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_bytes(repo / "saleor/core/blob.bin", b"\x00\x01\x02ok-text-with-nul")
    _write_lf(repo / "saleor/core/ok.py", "def ok():\n    return 1\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_bytes(repo / "saleor/core/blob.bin", b"\x00\xff\xfechanged")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/core/blob.bin": "M"}
    with pytest.raises(m.BinaryContentError):
        m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=["saleor/core/blob.bin"], classification=classification,
            test_path_authority=_authority(classification, set()),
        )
    # ADDED binary also fails closed
    (tmp_path / "r2").mkdir(parents=True, exist_ok=True)
    repo2 = _init_repo(tmp_path / "r2")
    _git(repo2, "commit", "-qm", "one", "--allow-empty")
    p2 = _git(repo2, "rev-parse", "HEAD")
    _write_bytes(repo2 / "bin.dat", b"\x00\x01\x02\x03")
    _commit_all(repo2, "two")
    t2 = _git(repo2, "rev-parse", "HEAD")
    cl2 = {"bin.dat": "A"}
    with pytest.raises(m.BinaryContentError):
        m.materialize_scoped_reference_patch(
            task_id="t2", repo=repo2, parent_commit=p2, target_commit=t2,
            scope_paths=["bin.dat"], classification=cl2,
            test_path_authority=_authority(cl2, set()), allow_added=True,
        )


def test_symlink_path_fails_closed_with_evidence(tmp_path: Path) -> None:
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
    _git(repo, "commit", "-qm", "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"link.txt": "A"}
    with pytest.raises(m.SymlinkPathError):
        m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=["link.txt"], classification=classification,
            test_path_authority=_authority(classification, set()), allow_added=True,
        )


def test_submodule_gitlink_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "base.txt", "base\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    # a gitlink entry (mode 160000) pointing at a commit object
    inner_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", "160000", inner_commit, "vendor/sub")
    _git(repo, "commit", "-qm", "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"vendor/sub": "A"}
    with pytest.raises(m.SubmodulePathError):
        m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=["vendor/sub"], classification=classification,
            test_path_authority=_authority(classification, set()), allow_added=True,
        )


# ================================================================= 10. missing / incomplete test flags fail closed
def test_missing_or_incomplete_test_authority_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(repo / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(repo / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/core/jwt.py": "M", "saleor/graphql/tests/test_a.py": "M"}
    base = dict(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        scope_paths=["saleor/core/jwt.py"], classification=classification,
    )
    with pytest.raises(m.TestClassificationAuthorityError):
        m.materialize_scoped_reference_patch(**base, test_path_authority=None)
    # authority missing one changed path -> incomplete authority
    with pytest.raises(m.TestClassificationAuthorityError):
        m.materialize_scoped_reference_patch(
            **base,
            test_path_authority=_authority({"saleor/core/jwt.py": "M"}, set()),
        )
    # classification missing one authority path -> incomplete classification
    with pytest.raises(m.TestClassificationAuthorityError):
        m.materialize_scoped_reference_patch(
            **base,
            test_path_authority=_authority(
                classification, set(), extra_changed={"saleor/core/other.py"}
            ),
        )
    # test_paths not a subset of changed_paths
    with pytest.raises(m.TestClassificationAuthorityError):
        m.materialize_scoped_reference_patch(
            **base,
            test_path_authority=_authority(
                classification, {"saleor/not/changed.py"}
            ),
        )
    # split_test_reference without an authority refuses immediately
    with pytest.raises(m.TestClassificationAuthorityError):
        m.split_test_reference(classification, None)


# ================================================================= 11. split invariants
def test_split_invariants_union_disjoint_and_census_equality(tmp_path: Path) -> None:
    classification = {
        "saleor/core/jwt.py": "M",
        "saleor/graphql/tests/test_a.py": "M",
        "saleor/migrations/0001_auto.py": "A",
    }
    authority = _authority(classification, {"saleor/graphql/tests/test_a.py"})
    reference = {"saleor/core/jwt.py": "M", "saleor/migrations/0001_auto.py": "A"}
    test = {"saleor/graphql/tests/test_a.py": "M"}
    inv = m.verify_split_invariants(classification, reference, test, test_path_authority=authority)
    assert inv["test_equals_census_authoritative"] is True
    assert inv["changed_test_paths_equal_authority"] is True
    assert inv["disjoint"] is True
    assert inv["union_all_classification"] is True
    assert inv["union_all_git_changed"] is True
    assert inv["selectors_test_free"] is True
    assert inv["full_tree_equality_insufficient"] is False
    # a split that moves the test change OUT of the test set breaks census equality
    bad = m.verify_split_invariants(
        classification,
        {"saleor/core/jwt.py": "M", "saleor/migrations/0001_auto.py": "A", "saleor/graphql/tests/test_a.py": "M"},
        {},
        test_path_authority=authority,
    )
    assert bad["test_equals_census_authoritative"] is False
    assert bad["changed_test_paths_equal_authority"] is False
    assert bad["disjoint"] is True  # vacuously: the wrong split emptied the test set
    assert bad["reference_test_free"] is False  # a census-test path IS in the reference part
    assert bad["union_all_classification"] is True  # union still complete -> tree equal


# ================================================================= 12. full-tree equality alone is insufficient
def test_full_tree_equality_alone_is_insufficient_for_split_validation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(repo / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(repo / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    classification = {"saleor/core/jwt.py": "M", "saleor/graphql/tests/test_a.py": "M"}
    authority = _authority(classification, {"saleor/graphql/tests/test_a.py"})

    calls: dict[str, int] = {}

    def applied_tree(patch_bytes: bytes, tag: str) -> dict[str, bytes]:
        n = calls.get(tag, 0)
        calls[tag] = n + 1
        wt = tmp_path / f"wt-{tag}-{n}"
        proc = subprocess.run(["git", "clone", "-q", str(repo), str(wt)], capture_output=True, env=dict(_ENV))
        assert proc.returncode == 0
        _git(wt, "config", "core.autocrlf", "false")  # faithful parent worktree for full-index apply
        _git(wt, "checkout", "-qf", parent)
        ip = subprocess.run(
            ["git", "-C", str(wt), "apply", "-"], input=patch_bytes, capture_output=True, env=dict(_ENV)
        )
        assert ip.returncode == 0, ip.stderr.decode("utf-8", "replace")
        tree: dict[str, bytes] = {}
        for p in ("saleor/core/jwt.py", "saleor/graphql/tests/test_a.py"):
            tree[p] = (wt / p).read_bytes()
        return tree

    correct = m.materialize_full_reference(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        test_path_authority=authority,
    )
    # CORRECT partition: test patch is separate; union applies to the final tree
    tree_correct = applied_tree(bytes(correct.reference_patch_bytes) + bytes(correct.test_patch_bytes), "correct")
    # WRONG partition: the test patch is smuggled INSIDE the reference patch (union equal)
    leaked_ref = m.git_diff_bytes(repo, parent, target, "saleor/core/jwt.py") + m.git_diff_bytes(
        repo, parent, target, "saleor/graphql/tests/test_a.py"
    )
    tree_wrong = applied_tree(leaked_ref, "wrong")
    # full-tree equality HOLDS for both — it cannot detect the leak
    assert tree_correct == tree_wrong
    # but the split invariants reject the wrong partition outright
    wrong_ref = dict(classification)
    wrong_test: dict[str, str] = {}
    inv = m.verify_split_invariants(classification, wrong_ref, wrong_test, test_path_authority=authority)
    assert inv["disjoint"] is True  # vacuously true (test set emptied) — NOT the detector
    assert inv["reference_test_free"] is False  # census-test path smuggled into the reference part
    assert inv["test_equals_census_authoritative"] is False
    assert inv["union_all_classification"] is True  # union identical -> identical final tree
    assert inv["full_tree_equality_insufficient"] is False


# ================================================================= 13. FULL_REFERENCE completeness
def test_full_reference_partition_never_erases_common_test_patch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(repo / "saleor/migrations/0001_initial.py", "MIGRATION = True\n")
    _write_lf(repo / "saleor/graphql/tests/test_new.py", "def test_new():\n    assert True\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    name_status = m.git_name_status_map(repo, parent, target)
    assert set(name_status) == {
        "saleor/core/jwt.py",
        "saleor/migrations/0001_initial.py",
        "saleor/graphql/tests/test_new.py",
    }
    authority = _authority(name_status, {"saleor/graphql/tests/test_new.py"})
    reference, test = m.full_reference_partition(repo, parent, target, authority)
    # FULL_REFERENCE carries ALL non-test changes, including added migration files
    assert reference == {
        "saleor/core/jwt.py": "M",
        "saleor/migrations/0001_initial.py": "A",
    }
    assert test == {"saleor/graphql/tests/test_new.py": "A"}
    full = m.materialize_full_reference(
        task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
        test_path_authority=authority,
    )
    assert b"new file mode" in full.reference_patch_bytes  # added migration materialized
    assert b"saleor/graphql/tests/test_new.py" in full.test_patch_bytes
    assert full.split_invariants["union_all_git_changed"] is True
    assert full.split_invariants["test_equals_census_authoritative"] is True
    # the non-test-only reference side is NOT accepted as a complete change set
    with pytest.raises(m.TestClassificationAuthorityError):
        m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=sorted(reference), classification=reference,
            test_path_authority=_authority(reference, set()), allow_added=True,
        )


# ================================================================= 14. census rename side authority
def test_census_rename_record_requires_side_authority(tmp_path: Path) -> None:
    renamed_record = {"path": "saleor/payment/tests/test_utils.py", "status": "renamed", "test_file": True}
    # no side authority -> fail closed (side split is ambiguous offline)
    with pytest.raises(m.TestClassificationAuthorityError):
        m.census_records_to_authority([renamed_record])
    # explicit side authority expands R_OLD/R_NEW with per-side flags
    auth = m.census_records_to_authority(
        [renamed_record],
        rename_sides={
            "saleor/payment/tests/test_utils.py": (
                "saleor/payment/test_utils.py",
                "saleor/payment/tests/test_utils.py",
                False,
                True,
            )
        },
    )
    assert "saleor/payment/test_utils.py" in auth.changed_paths
    assert "saleor/payment/tests/test_utils.py" in auth.changed_paths
    assert auth.test_paths == frozenset({"saleor/payment/tests/test_utils.py"})
    # A/D/M records map 1:1 with their flags
    recs = [
        {"path": "saleor/payment/search.py", "status": "modified", "test_file": False},
        {"path": "saleor/payment/tests/test_x.py", "status": "added", "test_file": True},
        {"path": "saleor/payment/legacy.py", "status": "deleted", "test_file": False},
    ]
    auth2 = m.census_records_to_authority(recs)
    assert auth2.changed_paths == frozenset(
        {"saleor/payment/search.py", "saleor/payment/tests/test_x.py", "saleor/payment/legacy.py"}
    )
    assert auth2.test_paths == frozenset({"saleor/payment/tests/test_x.py"})
    # materializer integration: R_OLD/R_NEW sides with per-side test flags honored
    assert m.CENSUS_STATUS_TO_FROZEN == {"modified": "M", "added": "A", "deleted": "D"}
    assert "renamed" not in m.CENSUS_STATUS_TO_FROZEN


# ================================================================= 15. rename side header validation
def test_renamed_side_header_validation_rejects_wrong_side(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lf(repo / "only_modified.py", "def a():\n    return 1\n")
    _commit_all(repo, "one")
    parent = _git(repo, "rev-parse", "HEAD")
    _write_lf(repo / "only_modified.py", "def a():\n    return 2\n")
    _commit_all(repo, "two")
    target = _git(repo, "rev-parse", "HEAD")
    # classifying a plain MODIFIED path as R_OLD must fail: no native deletion header
    classification = {"only_modified.py": "R_OLD"}
    with pytest.raises(m.UnsupportedStatusError):
        m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=["only_modified.py"], classification=classification,
            test_path_authority=_authority(classification, set()),
        )
    classification = {"only_modified.py": "R_NEW"}
    with pytest.raises(m.UnsupportedStatusError):
        m.materialize_scoped_reference_patch(
            task_id="t1", repo=repo, parent_commit=parent, target_commit=target,
            scope_paths=["only_modified.py"], classification=classification,
            test_path_authority=_authority(classification, set()), allow_added=True,
        )
