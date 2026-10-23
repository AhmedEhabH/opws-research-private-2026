"""OPWS R1 M19A1B — Git-tree reconstruction audit unit tests (synthetic git repos only).

M19A1B guardrails: every test runs against synthetic repositories created inside
``tmp_path`` (fixture-only execution on synthetic temporary directories is allowed).
Nothing is checked out, altered or written inside any real repository; the owner's
Saleor object store is never touched here. Real-task F2P/P2P evaluation, STAGE_5
preflight, Docker/WSL, API inference and downloads are NOT exercised; no scientific
outcome is produced (``REAL_TASK_BEHAVIORAL_OUTCOMES=0`` is asserted in receipts).

Coverage (mission scenarios i-x):
  i.   identity on source modifications, deletes, additions and mode changes;
  ii.  zero-byte added ``__init__.py``;
  iii. file without a final newline;
  iv.  flagged ``test_*.py`` OUTSIDE ``tests/`` (census flag wins; no filename heuristic);
  v.   rename within one boundary (reconstructs) and rename crossing the boundary
       (records ``RENAME_CROSSES_TEST_BOUNDARY`` and stops, staying in the denominator);
  vi.  deliberately wrong test flag fails classification even when the final tree
       happens to match (tree equality is necessary, NOT sufficient);
  vii. target-tree mismatch records exact_equal=False and the first differing path;
  viii.cleanup on failure; source git refs/index/worktree/object store unchanged;
  ix.  hostile global git configuration cannot change the reconstruction;
  x.   plan mode: a missing frozen arm source cannot count as completed.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_build as ob  # noqa: E402
from scripts import opws_m19a1b_tree_audit as ta  # noqa: E402
from scripts import opws_phase2_plan as p2  # noqa: E402
from scripts import opws_phase3b_patch_materialize as m  # noqa: E402

# ------------------------------------------------------------------ synthetic git helpers
_ENV = {k: v for k, v in os.environ.items()}
_ENV["GIT_CONFIG_NOSYSTEM"] = "1"
for _k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"):
    _ENV.pop(_k, None)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        env=_ENV,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')}"
    return proc.stdout.decode("utf-8", "replace").strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "store"
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


def _count_objects(repo: Path) -> str:
    return _git(repo, "count-objects", "-v")


def _store_unchanged(repo: Path, before: str, head: str, before_index: bytes | None) -> None:
    assert _count_objects(repo) == before, "store object store changed during the audit"
    assert _git(repo, "rev-parse", "HEAD") == head, "store HEAD changed during the audit"
    index_path = repo / ".git" / "index"
    after_index = index_path.read_bytes() if index_path.exists() else None
    assert after_index == before_index, "store index changed during the audit"
    assert not index_path.with_suffix(".lock").exists(), "store index lock left behind"


def _capture_store_state(repo: Path) -> tuple[str, str, bytes | None]:
    index_path = repo / ".git" / "index"
    return (
        _count_objects(repo),
        _git(repo, "rev-parse", "HEAD"),
        index_path.read_bytes() if index_path.exists() else None,
    )


def _header_counts(records: list[dict[str, object]]) -> dict[str, int]:
    return {
        "n_changed": len(records),
        "n_test": sum(1 for r in records if r["test_file"]),
        "n_test_added": sum(1 for r in records if r["status"] == "added" and r["test_file"]),
        "n_test_modified": sum(1 for r in records if r["status"] == "modified" and r["test_file"]),
        "n_test_deleted": sum(1 for r in records if r["status"] == "deleted" and r["test_file"]),
        "n_migration": sum(1 for r in records if r.get("migration_file")),
        "n_config_or_infra": sum(1 for r in records if r.get("config_or_infra")),
    }


def _write_source(
    tmp_path: Path,
    *,
    task_id: str,
    parent: str,
    target: str,
    records: list[dict[str, object]],
    counts: dict[str, int] | None = None,
    f2p_total: int = 0,
) -> Path:
    """Synthetic source repository (manifest + census) for the single task."""
    source = tmp_path / "source"
    binding = source / "research" / "opws" / "binding"
    binding.mkdir(parents=True)
    census_dir = source / "research" / "wp2"
    census_dir.mkdir(parents=True)
    counts = counts or _header_counts(records)
    census = {
        "artifact": "wp2_saleor_main297_census",
        "tasks": [
            {
                "task_id": task_id,
                "status": "OK",
                "parent_commit": parent,
                "target_commit": target,
                "parent_available": True,
                "target_available": True,
                **counts,
                "changed_paths": [
                    {
                        "path": r["path"],
                        "status": r["status"],
                        "test_file": bool(r["test_file"]),
                        "migration_file": bool(r.get("migration_file", False)),
                        "config_or_infra": bool(r.get("config_or_infra", False)),
                    }
                    for r in records
                ],
            }
        ],
    }
    (census_dir / "wp2_saleor_main297_census_2026-09-22.json").write_text(
        json.dumps(census, sort_keys=True), encoding="utf-8"
    )
    manifest = {
        "artifact": "opws_behavior_contract_manifest",
        "n_tasks": 1,
        "per_task": [
            {
                "task_id": task_id,
                "parent_commit": parent,
                "target_commit": target,
                "contract_sha256": hashlib.sha256(f"{task_id}-contract".encode()).hexdigest(),
                "adapter_resolved": True,
                "f2p": {"total": f2p_total},
            }
        ],
    }
    (binding / "OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return source


def _run_tree(
    tmp_path: Path,
    *,
    source: Path,
    store: Path,
    rename_sides_path: Path | None = None,
) -> dict[str, object]:
    out = tmp_path / "out"
    ta.run_tree_audit(
        repo=source,
        saleor_git=store,
        out_dir=out,
        rename_sides_path=rename_sides_path,
        min_free_gib=0.01,
        tmp_dir=None,
    )
    receipt = json.loads((out / ta.TREE_RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["summary"]["REAL_TASK_BEHAVIORAL_OUTCOMES"] == 0
    return receipt


def _first_record(receipt: dict[str, object]) -> dict[str, object]:
    per_task = receipt["per_task"]
    assert isinstance(per_task, list) and len(per_task) == 1
    rec = per_task[0]
    assert isinstance(rec, dict)
    return rec


def _rename_sides_file(tmp_path: Path, task_id: str, old: str, new: str, old_test: bool, new_test: bool) -> Path:
    path = tmp_path / "rename_sides.json"
    path.write_text(
        json.dumps({"tasks": {task_id: {"old": old, "new": new, "old_is_test": old_test, "new_is_test": new_test}}},
                   sort_keys=True),
        encoding="utf-8",
    )
    return path


# ================================================================= 1. identity: modify/delete/add/mode
def test_identity_across_modify_delete_add_and_mode_change(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/core/legacy.py", "def legacy():\n    return 0\n")
    _write_lf(store / "saleor/core/tool.py", "def tool():\n    return 0\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    store.joinpath("saleor/core/legacy.py").unlink()
    _write_lf(store / "saleor/core/new_stuff.py", "def helper():\n    return 1\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _git(store, "add", "-A")
    _git(store, "update-index", "--chmod=+x", "saleor/core/tool.py")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/core/legacy.py", "status": "deleted", "test_file": False},
        {"path": "saleor/core/new_stuff.py", "status": "added", "test_file": False},
        {"path": "saleor/core/tool.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    receipt = _run_tree(tmp_path, source=source, store=store)
    rec = _first_record(receipt)
    assert rec["status"] == "RECONSTRUCTED"
    assert rec["exact_equal"] is True
    assert rec["classification_reconciled"] is True
    assert rec["changed_test_file_count"] == 1
    assert rec["changed_nontest_file_count"] == 4
    assert rec["full_reference_patch_bytes"] > 0 and rec["test_patch_bytes"] > 0
    assert receipt["summary"]["n_reconstructed_exact"] == 1
    assert receipt["summary"]["n_classification_reconciled"] == 1
    assert receipt["exit_gate"]["pass"] is True


# ================================================================= 2. zero-byte added __init__.py
def test_zero_byte_added_init_py_reconstructs(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(store / "saleor/migrations/__init__.py", "")  # zero-byte
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/migrations/__init__.py", "status": "added", "test_file": False,
         "migration_file": True},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    receipt = _run_tree(tmp_path, source=source, store=store)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True and rec["classification_reconciled"] is True
    assert rec["status"] == "RECONSTRUCTED"


# ================================================================= 3. file without final newline
def test_no_final_newline_file_reconstructs(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()")  # NO trailing newline
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    receipt = _run_tree(tmp_path, source=source, store=store)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True and rec["classification_reconciled"] is True


# ================================================================= 4. flagged test_*.py outside tests/
def test_flag_authority_outside_tests_dir_no_filename_heuristic(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    for path, text in {
        "saleor/core/test_util.py": "def u():\n    return 1\n",
        "saleor/core/test_runner.py": "def r():\n    return 2\n",
        "saleor/core/util_runner.py": "def r2():\n    return 3\n",
    }.items():
        _write_lf(store / path, text)
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    for path, text in {
        "saleor/core/test_util.py": "def u():\n    return 11\n",
        "saleor/core/test_runner.py": "def r():\n    return 22\n",
        "saleor/core/util_runner.py": "def r2():\n    return 33\n",
    }.items():
        _write_lf(store / path, text)
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    # test_runner.py LOOKS like a test by basename but the frozen census flag says
    # NON-test: the audit must follow the flag exactly (no filename heuristic ever).
    records = [
        {"path": "saleor/core/test_util.py", "status": "modified", "test_file": True},
        {"path": "saleor/core/test_runner.py", "status": "modified", "test_file": False},
        {"path": "saleor/core/util_runner.py", "status": "modified", "test_file": False},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    receipt = _run_tree(tmp_path, source=source, store=store)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True and rec["classification_reconciled"] is True
    assert rec["changed_test_paths"] == ["saleor/core/test_util.py"]
    assert "saleor/core/test_runner.py" in rec["changed_nontest_paths"]
    assert rec["changed_test_file_count"] == 1 and rec["changed_nontest_file_count"] == 2


# ================================================================= 5a. rename within one boundary reconstructs
def test_rename_within_one_boundary_reconstructs(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/payment/utils.py", "def pay():\n    return 1\n")
    _write_lf(store / "saleor/payment/tests/test_utils_old.py", "def x():\n    return 1\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    store.joinpath("saleor/payment/tests/test_utils_old.py").rename(
        store / "saleor/payment/tests/test_utils.py"
    )
    _write_lf(store / "saleor/payment/utils.py", "def pay():\n    return 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/payment/utils.py", "status": "modified", "test_file": False},
        {"path": "saleor/payment/tests/test_utils_old.py", "status": "renamed", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    sides = _rename_sides_file(
        tmp_path, "t1",
        "saleor/payment/tests/test_utils_old.py", "saleor/payment/tests/test_utils.py",
        True, True,
    )
    receipt = _run_tree(tmp_path, source=source, store=store, rename_sides_path=sides)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True and rec["classification_reconciled"] is True
    assert rec["status"] == "RECONSTRUCTED"
    assert rec["rename_side_authority_resolved"] is True
    assert rec["rename_crosses_test_boundary"] is False
    assert set(rec["changed_test_paths"]) == {
        "saleor/payment/tests/test_utils_old.py", "saleor/payment/tests/test_utils.py",
    }


# ================================================================= 5b. rename crossing the boundary records STOP
def test_rename_crosses_test_boundary_records_stop(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/payment/utils.py", "def pay():\n    return 1\n")
    _write_lf(store / "saleor/payment/utils_old.py", "def u():\n    return 1\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    (store / "saleor/payment/tests").mkdir(parents=True, exist_ok=True)
    store.joinpath("saleor/payment/utils_old.py").rename(store / "saleor/payment/tests/test_utils.py")
    _write_lf(store / "saleor/payment/utils.py", "def pay():\n    return 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/payment/utils.py", "status": "modified", "test_file": False},
        {"path": "saleor/payment/utils_old.py", "status": "renamed", "test_file": False},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    sides = _rename_sides_file(
        tmp_path, "t1",
        "saleor/payment/utils_old.py", "saleor/payment/tests/test_utils.py",
        False, True,  # old non-test -> new test: boundary crossing
    )
    receipt = _run_tree(tmp_path, source=source, store=store, rename_sides_path=sides)
    rec = _first_record(receipt)
    assert rec["status"] == "STOPPED"
    assert rec["error_type"] == "RENAME_CROSSES_TEST_BOUNDARY"
    assert rec["rename_crosses_test_boundary"] is True
    assert rec["classification_reconciled"] is False
    # stays in the 219 denominator: reconstructed count must NOT reach 1
    assert receipt["summary"]["n_reconstructed_exact"] == 0
    assert receipt["exit_gate"]["pass"] is False


# ================================================================= 6. wrong test flag: tree equality is NOT sufficient
def test_wrong_test_flag_fails_classification_even_when_tree_matches(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    # BOTH files are truthfully test changes (n_test=2), but the (corrupted) census flags
    # mark BOTH non-test. The union still reconstructs the identical final tree...
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": False},
    ]
    counts = {
        "n_changed": 2,
        "n_test": 2,  # truth, contradicting the flipped flags above
        "n_test_modified": 2,
        "n_test_added": 0,
        "n_test_deleted": 0,
        "n_migration": 0,
        "n_config_or_infra": 0,
    }
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target,
                           records=records, counts=counts)
    receipt = _run_tree(tmp_path, source=source, store=store)
    rec = _first_record(receipt)
    # ... the final tree DOES match (necessary invariant holds) ...
    assert rec["exact_equal"] is True
    # ... but classification reconciliation FAILS: census flags contradict n_test counts
    assert rec["classification_reconciled"] is False
    assert rec["census_self_consistency"]["n_test_equals_flag_derived"] is False
    assert receipt["summary"]["n_classification_reconciled"] == 0
    assert receipt["exit_gate"]["pass"] is False


# ================================================================= 7. target-tree mismatch -> first differing path
def test_target_tree_mismatch_records_first_differing_path(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    sstore = ta.GitStore.open(store)
    workspace = ta.ReconstructionWorkspace(tmp_path, sstore, min_free_gib=0.01)
    try:
        parent_tree = sstore.tree_oid(parent)
        target_tree = sstore.tree_oid(target)
        test_patch = m.git_diff_bytes(store, parent, target, "saleor/graphql/tests/test_a.py")
        # reference patch deliberately dropped -> reconstructed tree == parent + test only
        recon = workspace.reconstruct(parent_tree, test_patch, b"")
        assert recon.apply_error is None
        assert recon.tree_oid is not None and recon.tree_oid != target_tree
        diff_paths = workspace.diff_trees(recon.tree_oid, target_tree)
        assert "saleor/core/jwt.py" in diff_paths
        assert len(diff_paths) >= 1  # first differing path IS reported (never empty)
    finally:
        workspace.cleanup()


# ================================================================= 8. cleanup on failure; store untouched
def test_failed_apply_cleans_temp_and_leaves_store_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    before_state = _capture_store_state(store)
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)

    captured: list[Path] = []

    def broken_workspace_factory() -> ta.ReconstructionWorkspace:
        ws = ta.ReconstructionWorkspace(tmp_path, ta.GitStore.open(store), min_free_gib=0.01)
        captured.append(ws.tmp)
        return ws

    fake_result = m.MaterializationResult(
        task_id="t1",
        parent_commit=parent,
        target_commit=target,
        selected_scope_hash="00" * 32,
        reference_patch_bytes=b"not a patch at all",
        reference_patch_hash="11" * 32,
        test_patch_bytes=b"this is not a patch",  # garbage: the FIRST apply must fail
        test_patch_hash="22" * 32,
        per_path_status={},
        invalid_prediction_paths=[],
        files_changed=(),
        split_invariants={
            "disjoint": True,
            "reference_test_free": True,
            "union_all_classification": True,
            "union_all_git_changed": True,
            "test_equals_census_authoritative": True,
            "changed_test_paths_equal_authority": True,
            "selectors_test_free": True,
            "full_tree_equality_insufficient": False,
        },
    )
    monkeypatch.setattr(ta, "materialize_full_reference", lambda **kw: fake_result)
    rec = ta.audit_task(
        task_id="t1",
        manifest_rec={"task_id": "t1", "parent_commit": parent, "target_commit": target,
                      "contract_sha256": "c" * 64},
        census=ta.load_census(source)[0],
        store=ta.GitStore.open(store),
        workspace_factory=broken_workspace_factory,
        rename_sides={},
        census_sha256="00" * 32,
    )
    assert rec.status == "ERROR"
    assert rec.apply_error is not None, "apply failure must be surfaced explicitly, never a silent skip"
    for tmp in captured:
        assert not tmp.exists(), "temporary workspace was not cleaned up on failure"
    _store_unchanged(store, *before_state)


# ================================================================= 9. hostile global git config
def test_hostile_global_git_config_no_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)

    hostile = tmp_path / "hostile.gitconfig"
    hostile.write_text(
        "[diff]\n\tnoprefix = true\n\tmnemonicPrefix = true\n\trenames = true\n"
        "[core]\n\tautocrlf = true\n\tquotepath = true\n"
        "[apply]\n\twhitespace = fix\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "0")
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "poisoned-index"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(tmp_path / "poisoned-objects"))
    receipt = _run_tree(tmp_path, source=source, store=store)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True and rec["classification_reconciled"] is True


# ================================================================= 10. plan mode: missing frozen arm source
def _write_plan_source(
    tmp_path: Path,
    *,
    task_ids: list[str],
    commits: dict[str, tuple[str, str]],
    records_by_task: dict[str, list[dict[str, object]]],
) -> Path:
    source = tmp_path / "psource"
    binding = source / "research" / "opws" / "binding"
    binding.mkdir(parents=True)
    census_dir = source / "research" / "wp2"
    census_dir.mkdir(parents=True)
    per_task = []
    census_tasks = []
    for tid in task_ids:
        parent, target = commits[tid]
        records = records_by_task[tid]
        per_task.append({
            "task_id": tid, "parent_commit": parent, "target_commit": target,
            "contract_sha256": hashlib.sha256(f"{tid}-contract".encode()).hexdigest(),
            "adapter_resolved": True, "f2p": {"total": 0},
        })
        census_tasks.append({
            "task_id": tid, "status": "OK", "parent_commit": parent, "target_commit": target,
            "parent_available": True, "target_available": True,
            **_header_counts(records),
            "changed_paths": [
                {"path": r["path"], "status": r["status"], "test_file": bool(r["test_file"]),
                 "migration_file": False, "config_or_infra": False}
                for r in records
            ],
        })
    (binding / "OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json").write_text(
        json.dumps({"artifact": "opws_behavior_contract_manifest", "n_tasks": len(task_ids),
                    "per_task": per_task}, sort_keys=True), encoding="utf-8"
    )
    (census_dir / "wp2_saleor_main297_census_2026-09-22.json").write_text(
        json.dumps({"artifact": "wp2_saleor_main297_census", "tasks": census_tasks}, sort_keys=True),
        encoding="utf-8",
    )
    (binding / "OPWS_ORDERED_TASK_IDS.json").write_text(
        json.dumps({"ordered_task_ids": task_ids}, sort_keys=True), encoding="utf-8"
    )
    (binding / "OPWS_ENVIRONMENT_ID_PROPOSAL.json").write_text(
        json.dumps({"per_task": [{"task_id": tid, "environment_id": f"env-{tid}"} for tid in task_ids]},
                   sort_keys=True), encoding="utf-8"
    )
    return source


def _synthetic_arm_sources(
    tmp_path: Path,
    *,
    task_ids: list[str],
    scope_paths: list[str],
    missing_arm: str | None = None,
) -> dict[str, dict[str, str | None]]:
    """Frozen 12-arm registry clone pointing at synthetic files (one arm may be absent)."""
    def keyed_file(key: str) -> Path:
        path = tmp_path / f"arm_{key}.json"
        path.write_text(
            json.dumps({"per_task": {tid: {key: list(scope_paths)} for tid in task_ids}}),
            encoding="utf-8",
        )
        return path

    r2_entry: dict[str, str] = {
        "DENSE@3_selected": list(scope_paths), "DENSE@10_selected": list(scope_paths),
        "BM25@3_selected": list(scope_paths), "BM25@10_selected": list(scope_paths),
        "BM25_TO_CIA_1HOP_selected": list(scope_paths),
    }
    r2 = tmp_path / "arm_r2.json"
    r2.write_text(json.dumps({"per_task": {tid: r2_entry for tid in task_ids}}), encoding="utf-8")
    proxies = tmp_path / "arm_proxies.json"
    proxies.write_text(
        json.dumps({"proxies": {tid: list(scope_paths) for tid in task_ids}}), encoding="utf-8"
    )

    rmcss = keyed_file("rmcss_predicted_set")
    sip = keyed_file("sip_predicted_set")
    agent = keyed_file("selected_paths")
    agentless = keyed_file("prediction_set")
    files: dict[str, Path] = {
        "RM_CSS": rmcss, "AGENT": agent,
        "AGENTLESS_STYLE_ADAPTATION": agentless, "SIP": sip,
        "DENSE_K3": r2, "DENSE_K10": r2, "BM25_K3": r2, "BM25_K10": r2,
        "BM25_TO_CIA_1HOP": r2, "GOLD": proxies,
    }
    if missing_arm in files:
        missing_file = tmp_path / "MISSING_arm_source.json"
        missing_file.write_text("{}", encoding="utf-8")
        files[missing_arm] = missing_file
    registry: dict[str, dict[str, str | None]] = {
        "RM_CSS": {"path": str(files["RM_CSS"]), "key": "rmcss_predicted_set"},
        "AGENT": {"path": str(files["AGENT"]), "key": "selected_paths"},
        "AGENTLESS_STYLE_ADAPTATION": {"path": str(files["AGENTLESS_STYLE_ADAPTATION"]), "key": "prediction_set"},
        "SIP": {"path": str(files["SIP"]), "key": "sip_predicted_set"},
        "DENSE_K3": {"path": str(files["DENSE_K3"]), "key": "DENSE@3_selected"},
        "DENSE_K10": {"path": str(files["DENSE_K10"]), "key": "DENSE@10_selected"},
        "BM25_K3": {"path": str(files["BM25_K3"]), "key": "BM25@3_selected"},
        "BM25_K10": {"path": str(files["BM25_K10"]), "key": "BM25@10_selected"},
        "BM25_TO_CIA_1HOP": {"path": str(files["BM25_TO_CIA_1HOP"]), "key": "BM25_TO_CIA_1HOP_selected"},
        "SELECT_ALL": {"path": "universe-template", "key": "records.path"},
        "RANDOM_SIZE_MATCHED_RM_CSS": {"path": None, "key": None},
        "GOLD": {"path": str(files["GOLD"]), "key": "proxies"},
    }
    if missing_arm == "SELECT_ALL" or missing_arm == "RANDOM_SIZE_MATCHED_RM_CSS":
        registry[missing_arm]["path"] = str(tmp_path / "MISSING_arm_source.json")
    return registry


def _two_task_store(tmp_path: Path) -> tuple[Path, dict[str, tuple[str, str]], dict[str, list[dict[str, object]]]]:
    """One store with two independent task commit pairs (non-test + test changes)."""
    store = _init_repo(tmp_path)
    commits: dict[str, tuple[str, str]] = {}
    records_by_task: dict[str, list[dict[str, object]]] = {}
    for tid, extra_test in (("t1", "saleor/graphql/tests/test_a.py"), ("t2", "saleor/graphql/tests/test_b.py")):
        _write_lf(store / "saleor/core/jwt.py", f"def encode_{tid}():\n    return 0\n")
        _write_lf(store / extra_test, f"def test_{tid}():\n    assert True\n")
        _commit_all(store, f"{tid} one")
        parent = _git(store, "rev-parse", "HEAD")
        _write_lf(store / "saleor/core/jwt.py", f"def encode_{tid}():\n    return 1\n")
        _write_lf(store / extra_test, f"def test_{tid}():\n    assert True\n    assert 2 == 2\n")
        _commit_all(store, f"{tid} two")
        target = _git(store, "rev-parse", "HEAD")
        commits[tid] = (parent, target)
        records_by_task[tid] = [
            {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
            {"path": extra_test, "status": "modified", "test_file": True},
        ]
    return store, commits, records_by_task


def test_plan_missing_arm_source_never_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, commits, records_by_task = _two_task_store(tmp_path)
    task_ids = ["t1", "t2"]
    source = _write_plan_source(tmp_path, task_ids=task_ids, commits=commits, records_by_task=records_by_task)
    monkeypatch.setattr(ob, "EXPECTED_N_TASKS", 2)
    monkeypatch.setattr(p2, "ARM_SCOPE_SOURCES", _synthetic_arm_sources(
        tmp_path, task_ids=task_ids, scope_paths=["saleor/core/jwt.py"], missing_arm="DENSE_K3"))

    def universe_factory(task_id: str) -> Path:
        path = tmp_path / f"universe_{task_id}.json"
        path.write_text(json.dumps({"records": [{"path": "saleor/core/jwt.py"}]}), encoding="utf-8")
        return path
    monkeypatch.setattr(p2, "_universe_file", universe_factory)

    plan = ta.run_plan_audit(
        repo=source,
        store=ta.GitStore.open(store),
        out_dir=tmp_path / "pout",
        rename_sides_path=None,
        min_free_gib=0.01,
        tmp_dir=None,
        tree_receipt=None,
    )
    assert plan["REAL_TASK_BEHAVIORAL_OUTCOMES"] == 0
    by_arm = {a["arm_id"]: a for a in plan["arm_status"]}
    assert by_arm["DENSE_K3"]["status"] == "MISSING"  # frozen source unavailable -> hard blocker
    ok_cross, why = ta.plan_gate_pass(plan)
    assert ok_cross is False
    assert "PREDICTION_SOURCE_MISSING" in why
    # missing records are reported separately and NEVER counted as complete
    assert plan["measures"]["n_missing_records"] == 2  # 1 missing arm x 2 tasks
    assert plan["n_arms_complete_219_219"] == 12       # 10 frozen + NEG + FULL_REFERENCE
    assert plan["n_arms_auditable"] == 12


def test_plan_complete_validated_three_measures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, commits, records_by_task = _two_task_store(tmp_path)
    task_ids = ["t1", "t2"]
    source = _write_plan_source(tmp_path, task_ids=task_ids, commits=commits, records_by_task=records_by_task)
    monkeypatch.setattr(ob, "EXPECTED_N_TASKS", 2)
    monkeypatch.setattr(p2, "ARM_SCOPE_SOURCES", _synthetic_arm_sources(
        tmp_path, task_ids=task_ids, scope_paths=["saleor/core/jwt.py"], missing_arm=None))

    def universe_factory(task_id: str) -> Path:
        path = tmp_path / f"universe_{task_id}.json"
        path.write_text(json.dumps({"records": [{"path": "saleor/core/jwt.py"}]}), encoding="utf-8")
        return path
    monkeypatch.setattr(p2, "_universe_file", universe_factory)

    plan = ta.run_plan_audit(
        repo=source,
        store=ta.GitStore.open(store),
        out_dir=tmp_path / "pout",
        rename_sides_path=None,
        min_free_gib=0.01,
        tmp_dir=None,
        tree_receipt=None,
    )
    assert plan["REAL_TASK_BEHAVIORAL_OUTCOMES"] == 0
    ok_cross, why = ta.plan_gate_pass(plan)
    assert ok_cross is True, why
    # auditable arms: 11 frozen (RANDOM deferred) + NEG + FULL_REFERENCE = 13
    assert plan["n_arms_auditable"] == 13
    assert plan["n_arms_complete_219_219"] == 13
    assert plan["measures"]["n_complete_validated"] == 13 * 2  # 2 tasks each
    assert plan["measures"]["n_missing_records"] == 0
    # three distinct measures over complete validated records
    assert isinstance(plan["measures"]["unique_patch_byte_sha"], int)
    assert isinstance(plan["measures"]["unique_effective_tree_oid"], int)
    dedup = plan["measures"]["five_field_physical_dedup"]
    assert dedup["n_logical_records"] == 26
    assert 0 < dedup["n_physical_executions"] <= 26
    assert "frozen OPWS_EXECUTION_REUSE_DEDUP_R1 five fields, unchanged" in dedup["dedup_semantics"]
    assert plan["tree_receipt_read"] is False


# ================================================================= 11. bare-repo saleor-git store
# The mission requires the real object directory to resolve for BOTH ordinary clones
# AND bare repositories (fail closed otherwise).
def test_tree_audit_against_bare_repo_store(tmp_path: Path) -> None:
    seed = _init_repo(tmp_path)
    _write_lf(seed / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(seed / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(seed, "one")
    parent = _git(seed, "rev-parse", "HEAD")
    _write_lf(seed / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(seed / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(seed, "two")
    target = _git(seed, "rev-parse", "HEAD")
    bare = tmp_path / "store.git"
    proc = subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(bare)],
                          capture_output=True, env=_ENV)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    # GitStore.open resolves git-dir and common-dir for a BARE repo
    sstore = ta.GitStore.open(bare)
    assert sstore.git_dir_abs == bare.resolve()
    receipt = _run_tree(tmp_path, source=source, store=bare)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True
    assert rec["classification_reconciled"] is True
    assert receipt["exit_gate"]["pass"] is True


# ================================================================= 12. alternates resolution
# A store whose object dir is served by another store's objects/info/alternates must
# still reconstruct exactly (the audit reads the real objects, never writes them).
def test_tree_audit_reads_store_through_object_alternates(tmp_path: Path) -> None:
    owner = _init_repo(tmp_path)
    _write_lf(owner / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(owner / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(owner, "one")
    parent = _git(owner, "rev-parse", "HEAD")
    _write_lf(owner / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(owner / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(owner, "two")
    target = _git(owner, "rev-parse", "HEAD")

    # vacuous clone: same repo shape, EMPTY object dir, served by owner's objects
    vacuous = tmp_path / "vacuous"
    proc = subprocess.run(["git", "clone", "-q", "--no-local", "--no-hardlinks", str(owner), str(vacuous)],
                          capture_output=True, env=_ENV)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    _rmtree_retry_local(vacuous / ".git" / "objects")
    (vacuous / ".git" / "objects").mkdir(parents=True, exist_ok=True)
    (vacuous / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
    # LF-only alternates line (CRLF would corrupt the path)
    (vacuous / ".git" / "objects" / "info" / "alternates").write_bytes(
        (owner / ".git" / "objects").resolve().as_posix().encode("utf-8") + b"\n"
    )
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    # GitStore must follow the alternates file and expose BOTH object dirs
    sstore = ta.GitStore.open(vacuous)
    assert len(sstore.object_dirs) == 2
    receipt = _run_tree(tmp_path, source=source, store=vacuous)
    rec = _first_record(receipt)
    assert rec["exact_equal"] is True
    assert rec["classification_reconciled"] is True
    # the vacuous clone's local object store stays empty: nothing was written to it
    assert not list((vacuous / ".git" / "objects").glob("[0-9a-f][0-9a-f]"))


def _rmtree_retry_local(path: Path) -> None:
    import shutil
    import time

    for _ in range(6):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            time.sleep(0.4)
    shutil.rmtree(path, ignore_errors=True)


# ================================================================= 13. CLI entry-point smoke
# All other tests call module functions; this one exercises the real CLI end-to-end
# on synthetic fixtures (fixture-only execution, allowed by the M18 guardrails).
def test_cli_tree_mode_end_to_end(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n")
    _commit_all(store, "one")
    parent = _git(store, "rev-parse", "HEAD")
    _write_lf(store / "saleor/core/jwt.py", "def encode(p):\n    return p.upper()\n")
    _write_lf(store / "saleor/graphql/tests/test_a.py", "def test_a():\n    assert True\n    assert 2 == 2\n")
    _commit_all(store, "two")
    target = _git(store, "rev-parse", "HEAD")
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": True},
    ]
    source = _write_source(tmp_path, task_id="t1", parent=parent, target=target, records=records)
    out = tmp_path / "cli_out"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "opws_m19a1b_tree_audit.py"),
         "--repo", str(source), "--saleor-git", str(store), "--out", str(out),
         "--mode", "tree", "--min-free-gib", "0.01"],
        capture_output=True, text=True, env=_ENV,
    )
    assert proc.returncode == 0, proc.stderr
    assert "TREE_RECEIPT=" in proc.stdout
    assert "TREE_GATE=" in proc.stdout
    receipt = json.loads((out / ta.TREE_RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["exit_gate"]["pass"] is True
    assert receipt["summary"]["REAL_TASK_BEHAVIORAL_OUTCOMES"] == 0

def test_cli_tree_gate_fail_returns_nonzero(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    prod = store / "saleor/core/jwt.py"
    test = store / "saleor/graphql/tests/test_a.py"

    _write_lf(prod, "value = 1\n")
    _write_lf(test, "def test_a():\n    assert True\n")
    _commit_all(store, "parent")
    parent = _git(store, "rev-parse", "HEAD")

    _write_lf(prod, "value = 2\n")
    _write_lf(test, "def test_a():\n    assert 2 == 2\n")
    _commit_all(store, "target")
    target = _git(store, "rev-parse", "HEAD")

    # Deliberately inconsistent census counts versus test_file flags.
    records = [
        {"path": "saleor/core/jwt.py", "status": "modified", "test_file": False},
        {"path": "saleor/graphql/tests/test_a.py", "status": "modified", "test_file": False},
    ]
    counts = {
        "n_changed": 2, "n_test": 1,
        "n_test_added": 0, "n_test_modified": 1, "n_test_deleted": 0,
        "n_migration": 0, "n_config_or_infra": 0,
    }

    source = _write_source(
        tmp_path, task_id="t1", parent=parent, target=target,
        records=records, counts=counts,
    )
    out = tmp_path / "cli_failed_out"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "opws_m19a1b_tree_audit.py"),
            "--repo", str(source),
            "--saleor-git", str(store),
            "--out", str(out),
            "--mode", "tree",
            "--min-free-gib", "0.01",
        ],
        capture_output=True, text=True, env=_ENV,
    )

    assert proc.returncode == 4, proc.stderr
    assert "TREE_GATE=FAIL" in proc.stderr

    receipt = json.loads(
        (out / ta.TREE_RECEIPT_NAME).read_text(encoding="utf-8")
    )
    assert receipt["exit_gate"]["pass"] is False
    assert receipt["summary"]["n_reconstructed_exact"] == 1
    assert receipt["summary"]["n_classification_reconciled"] == 0

def test_workspace_ntfs_config_is_scoped(tmp_path: Path) -> None:
    store = _init_repo(tmp_path)
    workspace = ta.ReconstructionWorkspace(
        tmp_path, ta.GitStore.open(store), min_free_gib=0.01
    )
    try:
        output = workspace._git(
            workspace.index_base, "config", "--get", "core.protectNTFS"
        )
        assert output.strip() == b"false"
    finally:
        workspace.cleanup()
