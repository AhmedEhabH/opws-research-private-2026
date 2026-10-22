#!/usr/bin/env python3
"""LIGHT project export for M17 OPWS R1 Phase 3A (non-Kaggle collaboration artifact).

The mission authorizes ONLY a `project-light-YYYY-MM-DD-HHmm.zip` (no Kaggle/FULL).
It bundles the Phase-3A source, tests, toy fixtures, receipts, and the Phase-0..3A OPWS
working records so a collaborator can review the mission without shipping heavy runtime
dirs, `dist/`, full git object store, or datasets.

INCLUDE: toy engine + phase-2 plan + their tests, toy fixtures/receipts, OPWS research
records under `research/opws/**`, the two `controller/light_profile_opws_*.json`, and the
`.git/HEAD` pointer for branch/commit identity.
EXCLUDE: `.git/**` except HEAD, `__pycache__`, `*.pyc`, `dist/**`, `benchmark_data/**`,
node_modules, caches.
"""
from __future__ import annotations

import datetime
import hashlib
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = PROJECT_DIR.parent

EXCLUDE_DIRS = {".mypy_cache", ".ruff_cache", ".pytest_cache", "__pycache__", "node_modules"}
EXCLUDE_SUFFIXES = {".pyc"}
INCLUDE_STEMS = {".git/HEAD", ".git/COMMIT_EDITMSG"}


def include(rel: str) -> bool:
    parts = rel.split("/")
    if any(ex in parts for ex in EXCLUDE_DIRS):
        return False
    if rel.endswith(tuple(EXCLUDE_SUFFIXES)):
        return False
    if rel.startswith("dist/") or rel.startswith("benchmark_data/") or rel.startswith("runs_"):
        return False
    if rel.startswith(".git/"):
        return rel in INCLUDE_STEMS
    # only the OPWS-relevant working-set
    if rel.startswith(("scripts/opws_", "tests/unit/opws/", "research/opws/", "controller/")):
        return True
    return False


def collect() -> dict[str, Path]:
    entries: dict[str, Path] = {}
    # git-tracked + untracked working files present on disk
    for p in PROJECT_DIR.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(PROJECT_DIR).as_posix()
        if rel in (".git/index", ".git/packed-refs"):
            continue
        if include(rel):
            entries[rel] = p
    # HEAD pointer (supports both real .git dir and worktree gitdir-file layouts)
    head = PROJECT_DIR / ".git" / "HEAD"
    if head.is_file():
        entries[".git/HEAD"] = head
    else:
        try:
            gitdir = Path((PROJECT_DIR / ".git").read_text(encoding="utf-8").strip().split()[-1])
            head_wt = gitdir / "HEAD"
            if head_wt.is_file():
                entries[".git/HEAD"] = head_wt
            entries[".git"] = PROJECT_DIR / ".git"
        except OSError:
            pass
    return entries


def main() -> int:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    out = PARENT_DIR / f"project-light-{stamp}.zip"
    entries = collect()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(entries):
            zf.write(entries[rel], rel)

    size = out.stat().st_size
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        bad = zf.testzip()
    print("PROJECT_EXPORT_READY")
    print(f"PROJECT_EXPORT_NAME={out.name}")
    print(f"PROJECT_EXPORT_PATH={out}")
    print(f"PROJECT_EXPORT_SIZE_BYTES={size}")
    print(f"PROJECT_EXPORT_SHA256={digest}")
    print(f"ENTRIES={len(names)}")
    print(f"TESTZIP_OK={bad is None}")
    print(f"HAS_HEAD={'/.git/HEAD' in names or '.git/HEAD' in names}")
    print(f"HAS_PHASE3A={'research/opws/PHASE3A_RESULT.md' in names}")
    print(f"UPLOAD_THIS_FILE={out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
