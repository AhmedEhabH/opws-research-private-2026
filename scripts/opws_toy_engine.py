"""OPWS R1 Phase 3A — TOY-ONLY scoped patch-isolation engine.

INSTRUMENTATION ONLY. This engine produces **no scientific outcome**. It operates
exclusively on synthetic in-memory "toy" repository snapshots + patches supplied by an
explicit ``--toy-fixture <path>``. There is **no real-population run mode** in Phase 3A.

Behaviour (fail-closed, deterministic):

* Enforces the selected editable-file scope at **both** path and content level.
* Rejects out-of-scope file writes, missing files, symlink escapes, patch
  fuzz / unexpected context, malformed scope paths, and ambiguous patch application.
* Every failure is raised as an explicit instrumentation / patch-application error
  class (``ToyEngineError`` subclasses) — failures are **never** classified as a
  scientific pass/fail.
* Every receipt is marked ``"TOY_ONLY": true`` and
  ``"SCIENTIFIC_OUTCOME_COUNT": 0``. No true F2P/P2P passing outcome is ever produced.

This is a **deliberately isolated** implementation: the frozen M15-R/M14-R patch
engines operate on real Saleor repos via WSL/Docker and git objects and have no
portable helper for arbitrary synthetic snapshots, so they are intentionally NOT
reused and their frozen outputs are never touched. Only the frozen OPWS canonical
scope-path / scope-hash convention (``opws_phase2_plan.normalize_scope_path*`` and
``compute_canonical_scope_hash``) is reused, purely for the scope hash.

Usage
-----
    python scripts/opws_toy_engine.py --toy-fixture <path> [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_BOOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_BOOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_BOOT))

from scripts import opws_build as ob  # noqa: E402
from scripts import opws_phase2_plan as p2  # noqa: E402

TOY_RECEIPT_SCHEMA = "opws-toy-only-receipt-r1/1.0"


# ------------------------------------------------------------------ error classes
class ToyEngineError(RuntimeError):
    """Base class for all toy-only engine failures (instrumentation, never scientific)."""


class FixtureError(ToyEngineError):
    """The toy fixture JSON is malformed or violates the toy schema."""


class ScopePathInvalidError(ToyEngineError):
    """A scope or patch path is not a valid canonical repository-relative path."""


class OutOfScopeWriteError(ToyEngineError):
    """A patch attempts to write/edit a file outside the selected editable scope."""


class MissingFileError(ToyEngineError):
    """A patch references a file that is absent from the toy snapshot or the scope."""


class SymlinkEscapeError(ToyEngineError):
    """A patch path resolves to a symlink target outside the toy repository root."""


class PatchConflictError(ToyEngineError):
    """Patch context (old lines) does not match the toy snapshot: fuzz/unexpected context."""


class AmbiguousPatchError(ToyEngineError):
    """Patch context matches more than one location; application is ambiguous."""


# ------------------------------------------------------------------ helpers
def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _file_content_sha(lines: list[str]) -> str:
    return _sha("\n".join(lines).encode("utf-8"))


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _resolve_within_root(path: str, symlinks: dict[str, str]) -> str:
    """Resolve ``path`` through declared symlinks; reject any escape from the toy root.

    Returns the resolved repository-relative path, or raises SymlinkEscapeError.
    """
    seen: set[str] = set()
    cur = path
    while cur in symlinks:
        if cur in seen:
            raise SymlinkEscapeError(f"symlink cycle at {cur}")
        seen.add(cur)
        target = symlinks[cur]
        if target.startswith("/") or ":" in target.split("/", 1)[0] or target.startswith(".."):
            raise SymlinkEscapeError(f"symlink escape from root: {cur} -> {target}")
        cur = target
    return cur


# ------------------------------------------------------------------ fixture load
def load_toy_fixture(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FixtureError(f"toy fixture missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"fixture is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FixtureError("fixture root must be a mapping")
    if not data.get("toy_only"):
        raise FixtureError("fixture must declare \"toy_only\": true")
    for key in ("snapshot", "allowed_scope", "patches"):
        if key not in data:
            raise FixtureError(f"fixture missing required key: {key}")
    if not isinstance(data["allowed_scope"], list):
        raise FixtureError("allowed_scope must be a list of repository-relative paths")
    if not isinstance(data["patches"], list):
        raise FixtureError("patches must be a list")
    return data


def _normalize_scope(paths: list[Any], context: str) -> list[str]:
    try:
        unique, _ = p2.normalize_scope_paths([str(p) for p in paths], context=context)
    except ob.BuildError as exc:
        raise ScopePathInvalidError(str(exc)) from exc
    return unique


def build_snapshot(snapshot: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str]]:
    """Partition the toy snapshot into plain files, symlink map, and content hashes.

    Returns ``(files, symlinks, content_hashes)``.
    """
    files: dict[str, list[str]] = {}
    symlinks: dict[str, str] = {}
    content_hashes: dict[str, str] = {}
    for raw, value in snapshot.items():
        try:
            path, _ = p2.normalize_scope_paths([str(raw)], context="toy-snapshot")
        except ob.BuildError as exc:
            raise ScopePathInvalidError(str(exc)) from exc
        p = path[0]
        if isinstance(value, dict) and value.get("type") == "symlink":
            target = str(value["target"])
            symlinks[p] = target
            continue
        if not isinstance(value, list):
            raise FixtureError(f"snapshot file {p!r} must be a list of lines or a symlink dict")
        lines = [str(x) for x in value]
        files[p] = lines
        content_hashes[p] = _file_content_sha(lines)
    return files, symlinks, content_hashes


def _resolve_patch_path(path: str, allowed_scope: list[str], files: dict[str, list[str]],
                        symlinks: dict[str, str]) -> tuple[str, str]:
    """Validate the patch path is canonical, in scope, not a symlink escape, and exists.

    Returns ``(canonical_path, resolved_real_path)``.
    """
    try:
        norm, _ = p2.normalize_scope_paths([str(path)], context=f"patch:{path}")
    except ob.BuildError as exc:
        raise ScopePathInvalidError(str(exc)) from exc
    canonical = norm[0]
    if canonical not in allowed_scope:
        raise OutOfScopeWriteError(f"patch writes out-of-scope file: {canonical}")
    real = _resolve_within_root(canonical, symlinks)
    if canonical in symlinks or real != canonical:
        # writing through/at a symlink that is not itself the canonical editable file
        raise SymlinkEscapeError(f"patch path aliases a symlink: {canonical}")
    if canonical not in files:
        raise MissingFileError(f"patch references missing file: {canonical}")
    return canonical, real


# ------------------------------------------------------------------ patch engine
def apply_patch_ops(files: dict[str, list[str]], patches: list[dict[str, Any]],
                    allowed_scope: list[str], symlinks: dict[str, str]) -> list[dict[str, str]]:
    """Apply each patch operation to the in-memory snapshot; returns file-change records.

    Raises an explicit ToyEngineError subclass on any failure. Never mutates the
    filesystem and never produces a scientific outcome.
    """
    changes: list[dict[str, str]] = []
    for patch in patches:
        if not isinstance(patch, dict):
            raise FixtureError("each patch must be a mapping")
        op = patch.get("op")
        if op not in ("edit", "add", "delete"):
            raise FixtureError(f"unsupported patch op: {op!r}")
        path = patch.get("path")
        canonical, _ = _resolve_patch_path(str(path), allowed_scope, files, symlinks)

        if op == "add":
            if canonical in files:
                # for a toy snapshot we also require the file absent from snapshot dir
                raise PatchConflictError(f"add op on existing file: {canonical}")
            new_lines = [str(x) for x in patch.get("new_lines", [])]
            before: str | None = None
            files[canonical] = list(new_lines)
            after_sha = _file_content_sha(files[canonical])
        elif op == "delete":
            old_lines = [str(x) for x in patch.get("old_lines", [])]
            if old_lines != files.get(canonical, []):
                raise PatchConflictError(
                    f"delete context mismatch (fuzz/unexpected) on {canonical}"
                )
            before = _file_content_sha(files[canonical])
            del files[canonical]
            after: list[str] = []
            after_sha = _file_content_sha(after)
        else:  # edit
            old_lines = [str(x) for x in patch.get("old_lines", [])]
            if not old_lines:
                raise PatchConflictError(f"edit op requires non-empty old_lines on {canonical}")
            current = files[canonical]
            matches: list[int] = []
            for idx in range(len(current) - len(old_lines) + 1):
                if current[idx:idx + len(old_lines)] == old_lines:
                    matches.append(idx)
            if not matches:
                raise PatchConflictError(f"edit context not found (fuzz/unexpected) on {canonical}")
            if len(matches) > 1:
                raise AmbiguousPatchError(f"edit context matches {len(matches)} locations on {canonical}")
            new_lines = [str(x) for x in patch.get("new_lines", [])]
            before = _file_content_sha(current)
            files[canonical] = current[:matches[0]] + new_lines + current[matches[0] + len(old_lines):]
            after_sha = _file_content_sha(files[canonical])

        changes.append(
            {
                "path": canonical,
                "op": op,
                "before_sha256": before or "",
                "after_sha256": after_sha,
            }
        )
    return changes


# ------------------------------------------------------------------ receipt
def build_receipt(*, fixture_path: str, fixture_sha256: str,
                  files: dict[str, list[str]], content_hashes: dict[str, str],
                  allowed_scope: list[str], changes: list[dict[str, str]] | None,
                  error: ToyEngineError | None, dry_run: bool) -> dict[str, Any]:
    success = error is None
    snapshot_hashes = {
        p: _file_content_sha(lines) if p in files else None
        for p, lines in files.items()
    }
    snapshot_sha256 = _sha(_canonical_json(sorted(snapshot_hashes.items())).encode("utf-8"))
    allowed_scope_hash = p2.compute_canonical_scope_hash(list(allowed_scope))
    receipt = {
        "artifact": "opws_toy_only_receipt_r1",
        "schema_version": TOY_RECEIPT_SCHEMA,
        "TOY_ONLY": True,
        "SCIENTIFIC_OUTCOME_COUNT": 0,
        "mission": "M17_OPWS_R1_PHASE3A_TOY_ONLY",
        "dry_run": dry_run,
        "fixture_path": fixture_path,
        "input_hashes": {
            "fixture_sha256": fixture_sha256,
            "allowed_scope_sha256": allowed_scope_hash,
            "snapshot_sha256": snapshot_sha256,
        },
        "allowed_scope": sorted(allowed_scope),
        "allowed_scope_hash": allowed_scope_hash,
        "scope_size_files": len(allowed_scope),
        "success": success,
        "error_class": None if success else type(error).__name__,
        "error_message": None if success else str(error),
        "file_changes": changes or [],
        "content_hashes": content_hashes,
    }
    # determinism token covering the byte-deterministic core (no timestamps / randomness)
    body = {k: v for k, v in receipt.items() if k not in ("determinism_token",)}
    receipt["determinism_token"] = _sha(_canonical_json(body).encode("utf-8"))
    return receipt


def run_toy(fixture_path: Path, *, dry_run: bool) -> dict[str, Any]:
    """Run the toy-only scoped patch engine on one explicit fixture; returns a receipt."""
    fx = load_toy_fixture(fixture_path)
    fixture_sha256 = _sha(fixture_path.read_bytes())
    validated_scope: list[str] = []
    try:
        validated_scope = _normalize_scope(fx["allowed_scope"], context="toy-allowed-scope")
        files, symlinks, content_hashes = build_snapshot(fx["snapshot"])
        changes = apply_patch_ops(files, fx["patches"], validated_scope, symlinks)
        error = None
    except ToyEngineError as exc:
        files = {}
        content_hashes = {}
        changes = None
        error = exc
    return build_receipt(
        fixture_path=str(fixture_path), fixture_sha256=fixture_sha256,
        files=files, content_hashes=content_hashes, allowed_scope=validated_scope,
        changes=changes, error=error, dry_run=dry_run,
    )


# ------------------------------------------------------------------ CLI (Phase 3A only)
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OPWS R1 Phase 3A TOY-ONLY scoped patch-isolation engine (no real-population mode)."
    )
    parser.add_argument("--toy-fixture", required=True, help="path to the synthetic toy fixture JSON")
    parser.add_argument("--dry-run", action="store_true", help="compute + print receipt without writing it")
    parser.add_argument("--out-dir", default="research/opws/toy_receipts", help="receipt output directory")
    args = parser.parse_args(argv)

    fixture_path = Path(args.toy_fixture)
    dry_run = args.dry_run
    receipt = run_toy(fixture_path, dry_run=dry_run)

    if dry_run:
        print(_canonical_json(receipt))
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{fixture_path.stem}_toy_receipt.json"
    out_path = out_dir / name
    out_path.write_text(_canonical_json(receipt) + "\n", encoding="utf-8", newline="\n")
    print(f"TOY_ONLY receipt written: {out_path}")
    return 0 if receipt["success"] else 0  # failures are recorded data, not a scientific gate


if __name__ == "__main__":
    raise SystemExit(main())
