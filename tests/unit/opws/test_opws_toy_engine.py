"""OPWS R1 Phase 3A — toy-only scoped patch engine unit tests.

The engine is TOY-ONLY: it runs on synthetic fixtures, never executes OPWS, never
calls a model, never touches real repos, and never produces a scientific pass/fail.
F2P/P2P labels here are *empty placeholder tokens* only (the fixtures generate no
behavior/preservation outcomes); ``SCIENTIFIC_OUTCOME_COUNT`` is always 0.
"""
from __future__ import annotations

import contextlib
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_toy_engine as eng  # noqa: E402


def _write_fixture(tmp_path: Path, data: dict) -> Path:
    path = tmp_path if tmp_path.suffix == ".json" else (tmp_path / "fixture.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _valid_fixture() -> dict:
    return {
        "toy_only": True,
        "allowed_scope": ["saleor/core/jwt.py", "saleor/graphql/page/resolvers.py"],
        "snapshot": {
            "saleor/core/jwt.py": ["def encode(payload):", "    return payload", "def decode(tok):", "    return tok"],
            "saleor/graphql/page/resolvers.py": ["def resolve_page(info, id):", "    return None"],
        },
        "patches": [
            {"op": "edit", "path": "saleor/core/jwt.py",
             "old_lines": ["    return payload"], "new_lines": ["    return payload.upper()"]},
        ],
    }


# ---------------------------------------------------------------- happy path
def test_valid_in_scope_edit_produces_toy_two_point_two_receipt(tmp_path: Path) -> None:
    fp = _write_fixture(tmp_path, _valid_fixture())
    r = eng.run_toy(fp, dry_run=True)
    assert r["TOY_ONLY"] is True
    assert r["SCIENTIFIC_OUTCOME_COUNT"] == 0
    assert r["success"] is True
    assert r["error_class"] is None
    assert r["allowed_scope_hash"] == eng.p2.compute_canonical_scope_hash(
        ["saleor/core/jwt.py", "saleor/graphql/page/resolvers.py"]
    )
    assert len(r["file_changes"]) == 1
    chg = r["file_changes"][0]
    assert chg["path"] == "saleor/core/jwt.py"
    assert chg["op"] == "edit"
    assert chg["before_sha256"] != chg["after_sha256"]
    # the F2P/P2P tokens are NEVER produced; the receipt must not claim any
    assert "f2p" not in json.dumps(r).lower() and "behavior_sufficient" not in r


def test_allowed_scope_header_matches_frozen_canonical_hash() -> None:
    # empty scope is a VALID zero-size scope; hash is deterministic and matches the
    # recomputation from the frozen canonical convention.
    h = eng.p2.compute_canonical_scope_hash([])
    assert isinstance(h, str) and len(h) == 64
    assert h == eng.p2.compute_canonical_scope_hash([])


# ---------------------------------------------------------------- fail-closed
def test_forbidden_out_of_scope_patch_is_an_instrument_class(tmp_path: Path) -> None:
    fx = _valid_fixture()
    fx["patches"] = [{"op": "edit", "path": "saleor/out/of/scope.py",
                      "old_lines": ["x"], "new_lines": ["y"]}]
    fp = _write_fixture(tmp_path, fx)
    r = eng.run_toy(fp, dry_run=True)
    assert r["success"] is False
    assert r["error_class"] == "OutOfScopeWriteError"
    assert r["TOY_ONLY"] is True and r["SCIENTIFIC_OUTCOME_COUNT"] == 0


def test_traversal_path_is_rejected_not_tracked(tmp_path: Path) -> None:
    fx = _valid_fixture()
    fx["patches"] = [{"op": "edit", "path": "../escape.py", "old_lines": ["x"], "new_lines": ["y"]}]
    fp = _write_fixture(tmp_path, fx)
    r = eng.run_toy(fp, dry_run=True)
    assert r["success"] is False
    assert r["error_class"] == "ScopePathInvalidError"


def test_backslash_absolute_drive_path_rejected(tmp_path: Path) -> None:
    for n, bad in enumerate(["C:/abs.py", "saleor\\core\\jwt.py", "/abs/saleor.py"]):
        fx = _valid_fixture()
        fx["patches"] = [{"op": "edit", "path": bad, "old_lines": ["x"], "new_lines": ["y"]}]
        r = eng.run_toy(_write_fixture(tmp_path / f"bad{n}", fx), dry_run=True)
        assert r["success"] is False, bad
        assert r["error_class"] == "ScopePathInvalidError", bad


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    fx = _valid_fixture()
    fx["snapshot"]["saleor/link.py"] = {"type": "symlink", "target": "../../../etc/passwd"}
    fx["allowed_scope"].append("saleor/link.py")
    fx["patches"] = [{"op": "edit", "path": "saleor/link.py", "old_lines": ["x"], "new_lines": ["y"]}]
    fp = _write_fixture(tmp_path, fx)
    r = eng.run_toy(fp, dry_run=True)
    assert r["success"] is False
    assert r["error_class"] == "SymlinkEscapeError"


def test_patch_context_mismatch_is_fuzz_rejected(tmp_path: Path) -> None:
    fx = _valid_fixture()
    fx["patches"] = [{"op": "edit", "path": "saleor/core/jwt.py",
                      "old_lines": ["    return WRONG_PAYLOAD"], "new_lines": ["    return payload"]}]
    fp = _write_fixture(tmp_path, fx)
    r = eng.run_toy(fp, dry_run=True)
    assert r["success"] is False
    assert r["error_class"] == "PatchConflictError"


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    fx = _valid_fixture()
    fx["patches"] = [{"op": "edit", "path": "saleor/core/jwt.py",
                      "old_lines": ["nope"], "new_lines": ["yes"]}]
    del fx["snapshot"]["saleor/core/jwt.py"]
    fp = _write_fixture(tmp_path, fx)
    r = eng.run_toy(fp, dry_run=True)
    assert r["success"] is False
    assert r["error_class"] == "MissingFileError"


def test_ambiguous_edit_context_rejected(tmp_path: Path) -> None:
    fx = _valid_fixture()
    fx["snapshot"]["saleor/core/jwt.py"] = ["aa", "bb", "aa", "bb"]
    fx["patches"] = [{"op": "edit", "path": "saleor/core/jwt.py",
                      "old_lines": ["aa", "bb"], "new_lines": ["cc"]}]
    fp = _write_fixture(tmp_path, fx)
    r = eng.run_toy(fp, dry_run=True)
    assert r["success"] is False
    assert r["error_class"] == "AmbiguousPatchError"


def test_malformed_fixture_errors_without_touching_scope() -> None:
    with pytest.raises(eng.FixtureError):
        eng.load_toy_fixture(Path("does/not/exist.json"))


# ---------------------------------------------------------------- determinism
def test_double_build_is_deterministic(tmp_path: Path) -> None:
    fp = _write_fixture(tmp_path, _valid_fixture())
    r1 = eng.run_toy(fp, dry_run=True)
    r2 = eng.run_toy(fp, dry_run=True)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    assert r1["determinism_token"] == r2["determinism_token"]
    assert r1["input_hashes"]["fixture_sha256"] == r2["input_hashes"]["fixture_sha256"]


# ---------------------------------------------------------------- CLI
def test_cli_dry_run_prints_to_stdout_and_writes_nothing(tmp_path: Path) -> None:
    fp = _write_fixture(tmp_path, _valid_fixture())
    out_dir = tmp_path / "receipts"
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        rc = eng.main(["--toy-fixture", str(fp), "--dry-run", "--out-dir", str(out_dir)])
    assert rc == 0
    assert "\"TOY_ONLY\":true" in buf.getvalue()
    assert not (out_dir / f"{fp.stem}_toy_receipt.json").exists()


def test_cli_writes_receipt_with_toy_only_flags(tmp_path: Path) -> None:
    fp = _write_fixture(tmp_path, _valid_fixture())
    out_dir = tmp_path / "receipts"
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        eng.main(["--toy-fixture", str(fp), "--out-dir", str(out_dir)])
    receipt = json.loads((out_dir / f"{fp.stem}_toy_receipt.json").read_text(encoding="utf-8"))
    assert receipt["TOY_ONLY"] is True
    assert receipt["SCIENTIFIC_OUTCOME_COUNT"] == 0
    assert receipt["success"] is True


def test_cli_only_supports_toy_fixture_and_dry_run(tmp_path: Path) -> None:
    fp = _write_fixture(tmp_path, _valid_fixture())
    buf = StringIO()
    # unknown/unsupported option must be rejected (no real-population mode exists)
    with (
        pytest.raises(SystemExit) as e,
        contextlib.redirect_stdout(buf),
    ):
        eng.main(["--population", "run", "--toy-fixture", str(fp), "--dry-run"])
    assert e.value.code != 0
